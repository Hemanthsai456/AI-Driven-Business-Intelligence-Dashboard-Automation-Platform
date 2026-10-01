"""Official Google GenAI SDK adapter for Gemini models."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional, Tuple

DEFAULT_GEMINI_MODEL: str = "gemini-3.8-flash"
GEMINI_API_KEY_ENV: str = "GEMINI_API_KEY"
GEMINI_MODEL_ENV: str = "GEMINI_MODEL"
ESTIMATED_INPUT_COST_PER_M: float = 0.075
ESTIMATED_OUTPUT_COST_PER_M: float = 0.30

from providers.base import LLMClient, LLMClientError
from providers.types import GeneratorCallLog



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

    @staticmethod
    def _sanitize_gemini_schema(schema: Any) -> Any:
        """Strip additionalProperties and additional_properties that Google GenAI proto rejects."""
        if isinstance(schema, dict):
            clean = {}
            for k, v in schema.items():
                if k in ("additionalProperties", "additional_properties"):
                    continue
                clean[k] = GeminiClient._sanitize_gemini_schema(v)
            return clean
        elif isinstance(schema, list):
            return [GeminiClient._sanitize_gemini_schema(x) for x in schema]
        return schema

    def _call_api(self, prompt, schema, sys_inst):
        from google.genai import types
        gemini_schema = self._sanitize_gemini_schema(schema) if (schema and self.capabilities["strict_schema"]) else None
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=gemini_schema,
            system_instruction=sys_inst,
            temperature=0.0,
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

        for attempt in range(2):
            try:
                response = self._execute_with_retries(
                    self._call_api, prompt, response_schema, system_instruction
                )
                latency = time.perf_counter() - start_time

                raw_text = response.text or "{}"
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

                cost = (
                    (input_tokens / 1_000_000.0) * ESTIMATED_INPUT_COST_PER_M
                    + (output_tokens / 1_000_000.0) * ESTIMATED_OUTPUT_COST_PER_M
                )

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
                if attempt == 1:
                    raise LLMClientError("Gemini returned invalid JSON after retry")
            except Exception as e:
                raise LLMClientError(f"Gemini API call failed: {str(e)}")

        raise LLMClientError("Unexpected loop exit in GeminiClient")
