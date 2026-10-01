"""Groq provider adapter via HTTP REST endpoint."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

DEFAULT_GROQ_MODEL: str = "openai/gpt-oss-120b"
GROQ_API_KEY_ENV: str = "GROQ_API_KEY"
GROQ_MODEL_ENV: str = "GROQ_MODEL"

from providers.base import LLMClient, LLMClientError
from providers.types import GeneratorCallLog



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
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "bi-platform/1.0",
        }

        messages = []
        if sys_inst:
            messages.append({"role": "system", "content": sys_inst})

<<<<<<< HEAD
        if schema:
=======
        if self.capabilities["strict_schema"]:
>>>>>>> main
            messages.append({
                "role": "system",
                "content": f"You must respond with a JSON object strictly matching this schema: {json.dumps(schema)}",
            })

        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30.0) as response:
            return json.loads(response.read().decode("utf-8"))

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
                response = self._execute_with_retries(
                    self._call_api, prompt, response_schema, system_instruction
                )
                latency = time.perf_counter() - start_time

                content = response["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                usage = response.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

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
                    raise LLMClientError("Groq returned invalid JSON after retry")
            except Exception as e:
                raise LLMClientError(f"Groq API call failed: {str(e)}")

        raise LLMClientError("Unexpected loop exit in GroqClient")
