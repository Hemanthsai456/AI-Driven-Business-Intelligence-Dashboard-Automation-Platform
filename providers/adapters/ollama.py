"""Ollama local model adapter via REST API."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

DEFAULT_OLLAMA_HOST: str = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL: str = "llama3"
OLLAMA_HOST_ENV: str = "OLLAMA_HOST"
OLLAMA_MODEL_ENV: str = "OLLAMA_MODEL"

from providers.base import LLMClient, LLMClientError
from providers.types import GeneratorCallLog



class OllamaClient(LLMClient):
    """Client for local Ollama instance."""

    def __init__(
        self,
        host: Optional[str] = None,
        model_name: Optional[str] = None,
        skip_health_check: bool = False,
    ):
        model = model_name or os.getenv(OLLAMA_MODEL_ENV, DEFAULT_OLLAMA_MODEL)
        super().__init__("ollama", model)

        self.host = (host or os.getenv(OLLAMA_HOST_ENV, DEFAULT_OLLAMA_HOST)).rstrip("/")

        # Health check at startup
        should_skip = skip_health_check or os.getenv("OLLAMA_SKIP_HEALTH_CHECK", "0").lower() in ("1", "true")
        if not should_skip:
            try:
                req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=5.0) as _:
                    pass
            except Exception as e:
                raise LLMClientError(
                    f"Ollama health check failed. Is it running at {self.host}? Error: {str(e)}"
                )

    def _call_api(self, prompt, schema, sys_inst):
        url = f"{self.host}/api/generate"

        full_prompt = prompt
        if sys_inst:
            full_prompt = f"{sys_inst}\n\n{prompt}"

        if self.capabilities["strict_schema"]:
            full_prompt += (
                f"\n\nYou must respond with a JSON object strictly matching this schema: "
                f"{json.dumps(schema)}"
            )

        data = {
            "model": self.model_name,
            "prompt": full_prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60.0) as response:
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
