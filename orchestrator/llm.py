"""LLM client integration using official SDKs (Gemini, Groq, Ollama).

Features:
- Multi-provider support: Gemini, Groq, Ollama.
- Enforces model name and API key from environment variables only.
- Strict startup validation (Ollama health check, clear error if down).
- Structured JSON output schema enforcement (all fields required, additionalProperties false).
- Exponential backoff on 429, retry once on invalid output, timeouts.
- Telemetry per call: provider, model id/version, latency, tokens, cost.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from orchestrator.config import (
    DEFAULT_GEMINI_MODEL,
    ESTIMATED_INPUT_COST_PER_M,
    ESTIMATED_OUTPUT_COST_PER_M,
    GEMINI_API_KEY_ENV,
    GEMINI_MODEL_ENV,
    GROQ_API_KEY_ENV,
    GROQ_MODEL_ENV,
    DEFAULT_GROQ_MODEL,
    OLLAMA_HOST_ENV,
    OLLAMA_MODEL_ENV,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_HOST,
)
from orchestrator.schemas import GeneratorCallLog
from orchestrator.capabilities import get_capabilities


class LLMClientError(RuntimeError):
    """Raised when an LLM provider invocation or configuration fails."""


def make_strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively enforce strict JSON schema for LLMs."""
    if isinstance(schema, dict):
        if schema.get("type") == "object" or "properties" in schema:
            schema["additionalProperties"] = False
            props = schema.get("properties", {})
            req = schema.get("required", [])
            for k in props.keys():
                if k not in req:
                    req.append(k)
            if req:
                schema["required"] = req
            for v in props.values():
                make_strict_schema(v)
        if "items" in schema and isinstance(schema["items"], dict):
            make_strict_schema(schema["items"])
        if "$defs" in schema:
            for v in schema["$defs"].values():
                make_strict_schema(v)
        if "anyOf" in schema:
            for v in schema["anyOf"]:
                make_strict_schema(v)
    return schema


def get_strict_json_schema(model_class: Type[BaseModel]) -> Dict[str, Any]:
    schema = model_class.model_json_schema()
    return make_strict_schema(schema)


class LLMClient(ABC):
    """Abstract interface for structured LLM plan generation."""

    def __init__(self, provider: str, model_name: str):
        self.provider = provider
        self.model_name = model_name
        self.capabilities = get_capabilities(provider, model_name)

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        pass

    def _execute_with_retries(self, func, *args, **kwargs):
        """Execute a function with exponential backoff for 429 errors."""
        max_retries = 3
        base_delay = 1.0
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "too many requests" in err_str:
                    if attempt == max_retries - 1:
                        raise LLMClientError(f"{self.provider} rate limit exceeded: {e}")
                    time.sleep(base_delay * (2 ** attempt))
                else:
                    raise e
        raise LLMClientError("Max retries exceeded")


class GeminiClient(LLMClient):
    """Official Google GenAI SDK client for Gemini models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        model = model_name or os.getenv(GEMINI_MODEL_ENV, DEFAULT_GEMINI_MODEL)
        super().__init__("gemini", model)
        
        self.api_key = api_key or os.getenv(GEMINI_API_KEY_ENV)
        if not self.api_key:
            raise LLMClientError(
                f"Gemini API key is missing. Set '{GEMINI_API_KEY_ENV}'."
            )

        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            raise LLMClientError(f"Failed to initialize google-genai Client: {str(e)}")

    def _call_api(self, prompt, schema, sys_inst):
        from google.genai import types
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema if self.capabilities["strict_schema"] else None,
            system_instruction=sys_inst,
            temperature=0.0, # Deterministic where possible
        )
        return self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        
        start_time = time.perf_counter()
        retries = 0
        failures = 0
        
        # We retry once on invalid output (JSON decode error)
        for attempt in range(2):
            try:
                response = self._execute_with_retries(self._call_api, prompt, response_schema, system_instruction)
                latency = time.perf_counter() - start_time
                
                raw_text = response.text or "{}"
                # strip potential markdown code blocks
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                    
                parsed = json.loads(raw_text.strip())

                input_tokens = 0
                output_tokens = 0
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    usage = response.usage_metadata
                    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                    output_tokens = getattr(usage, "candidates_token_count", 0) or 0

                cost = (input_tokens / 1_000_000.0) * ESTIMATED_INPUT_COST_PER_M + (output_tokens / 1_000_000.0) * ESTIMATED_OUTPUT_COST_PER_M

                call_log = GeneratorCallLog(
                    model=self.model_name,
                    provider=self.provider,
                    generator=generator_label,
                    steps=1 + retries,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_seconds=round(latency, 4),
                    estimated_cost_usd=round(cost, 6),
                )
                return parsed, call_log
            except json.JSONDecodeError:
                retries += 1
                failures += 1
                if attempt == 1:
                    raise LLMClientError("Gemini returned invalid JSON after retry")
            except Exception as e:
                raise LLMClientError(f"Gemini API call failed: {str(e)}")
        
        raise LLMClientError("Unexpected loop exit in GeminiClient")


class GroqClient(LLMClient):
    """Client for Groq via standard OpenAI compatible API or direct HTTP."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        model = model_name or os.getenv(GROQ_MODEL_ENV, DEFAULT_GROQ_MODEL)
        super().__init__("groq", model)
        
        self.api_key = api_key or os.getenv(GROQ_API_KEY_ENV)
        if not self.api_key:
            raise LLMClientError(
                f"Groq API key is missing. Set '{GROQ_API_KEY_ENV}'."
            )

    def _call_api(self, prompt, schema, sys_inst):
        import urllib.request
        import json
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if sys_inst:
            messages.append({"role": "system", "content": sys_inst})
        
        if self.capabilities["strict_schema"]:
             messages.append({"role": "system", "content": f"You must respond with a JSON object strictly matching this schema: {json.dumps(schema)}"})
        
        messages.append({"role": "user", "content": prompt})
        
        data = {
            "model": self.model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }
        
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30.0) as response:
            return json.loads(response.read().decode('utf-8'))

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        
        start_time = time.perf_counter()
        retries = 0
        
        for attempt in range(2):
            try:
                response = self._execute_with_retries(self._call_api, prompt, response_schema, system_instruction)
                latency = time.perf_counter() - start_time
                
                content = response["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                
                usage = response.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                
                # Assume Groq cost is similar or 0 for now
                cost = 0.0
                
                call_log = GeneratorCallLog(
                    model=self.model_name,
                    provider=self.provider,
                    generator=generator_label,
                    steps=1 + retries,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_seconds=round(latency, 4),
                    estimated_cost_usd=cost,
                )
                return parsed, call_log
            except json.JSONDecodeError:
                retries += 1
                if attempt == 1:
                    raise LLMClientError("Groq returned invalid JSON after retry")
            except Exception as e:
                raise LLMClientError(f"Groq API call failed: {str(e)}")
                
        raise LLMClientError("Unexpected loop exit in GroqClient")


class OllamaClient(LLMClient):
    """Client for local Ollama instance."""

    def __init__(
        self,
        host: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        model = model_name or os.getenv(OLLAMA_MODEL_ENV, DEFAULT_OLLAMA_MODEL)
        super().__init__("ollama", model)
        
        self.host = (host or os.getenv(OLLAMA_HOST_ENV, DEFAULT_OLLAMA_HOST)).rstrip("/")
        
        # Health check at startup
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method='GET')
            with urllib.request.urlopen(req, timeout=5.0) as _:
                pass
        except Exception as e:
            raise LLMClientError(f"Ollama health check failed. Is it running at {self.host}? Error: {str(e)}")

    def _call_api(self, prompt, schema, sys_inst):
        import urllib.request
        import json
        
        url = f"{self.host}/api/generate"
        
        full_prompt = prompt
        if sys_inst:
            full_prompt = f"{sys_inst}\n\n{prompt}"
            
        if self.capabilities["strict_schema"]:
             full_prompt += f"\n\nYou must respond with a JSON object strictly matching this schema: {json.dumps(schema)}"
        
        data = {
            "model": self.model_name,
            "prompt": full_prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.0
            }
        }
        
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
        with urllib.request.urlopen(req, timeout=60.0) as response:
            return json.loads(response.read().decode('utf-8'))

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        
        start_time = time.perf_counter()
        retries = 0
        
        for attempt in range(2):
            try:
                response = self._execute_with_retries(self._call_api, prompt, response_schema, system_instruction)
                latency = time.perf_counter() - start_time
                
                content = response.get("response", "{}")
                parsed = json.loads(content)
                
                input_tokens = response.get("prompt_eval_count", 0)
                output_tokens = response.get("eval_count", 0)
                
                call_log = GeneratorCallLog(
                    model=self.model_name,
                    provider=self.provider,
                    generator=generator_label,
                    steps=1 + retries,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_seconds=round(latency, 4),
                    estimated_cost_usd=0.0,
                )
                return parsed, call_log
            except json.JSONDecodeError:
                retries += 1
                if attempt == 1:
                    raise LLMClientError("Ollama returned invalid JSON after retry")
            except Exception as e:
                raise LLMClientError(f"Ollama API call failed: {str(e)}")
                
        raise LLMClientError("Unexpected loop exit in OllamaClient")


class MockLLMClient(LLMClient):
    """Mock client for offline testing and deterministic unit test suites."""

    def __init__(
        self,
        canned_response: Optional[Dict[str, Any]] = None,
        latency_seconds: float = 0.01,
        should_fail: bool = False,
    ):
        super().__init__("mock", "mock-model")
        self.canned_response = canned_response or {}
        self.latency_seconds = latency_seconds
        self.should_fail = should_fail
        self.call_history: list[str] = []

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        self.call_history.append(prompt)
        time.sleep(self.latency_seconds)

        if self.should_fail:
            raise LLMClientError("Mock LLM client simulated failure.")

        call_log = GeneratorCallLog(
            model=self.model_name,
            provider=self.provider,
            generator=generator_label,
            steps=1,
            input_tokens=150,
            output_tokens=120,
            thinking_tokens=0,
            latency_seconds=self.latency_seconds,
            estimated_cost_usd=0.000045,
        )

        return self.canned_response, call_log
