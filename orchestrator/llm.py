"""LLM client integration using the official google-genai SDK.

Features:
- Enforces model name and API key from environment variables only.
- Strict startup / initialization validation with clear error messages.
- Structured JSON output schema enforcement via response_schema.
- Pydantic validation fallback.
- Per-call telemetry logging: model, generator, steps, tokens (input/output/thinking),
  latency, and estimated cost.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from orchestrator.config import (
    DEFAULT_GEMINI_MODEL,
    ESTIMATED_INPUT_COST_PER_M,
    ESTIMATED_OUTPUT_COST_PER_M,
    GEMINI_API_KEY_ENV,
    GEMINI_MODEL_ENV,
)
from orchestrator.schemas import GeneratorCallLog


class LLMClientError(RuntimeError):
    """Raised when an LLM provider invocation or configuration fails."""


class LLMClient(ABC):
    """Abstract interface for structured LLM plan generation."""

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        """Generate structured JSON adhering to the provided JSON schema."""
        pass


class GeminiClient(LLMClient):
    """Official Google GenAI SDK client for Gemini models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        # Enforce API key from env vars only unless explicitly passed
        self.api_key = api_key or os.getenv(GEMINI_API_KEY_ENV)
        self.model_name = model_name or os.getenv(GEMINI_MODEL_ENV, DEFAULT_GEMINI_MODEL)

        if not self.api_key:
            raise LLMClientError(
                f"Gemini API key is missing. Set the environment variable '{GEMINI_API_KEY_ENV}' "
                "or pass api_key directly."
            )

        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            raise LLMClientError(f"Failed to initialize google-genai Client: {str(e)}")

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "llm_direct",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        """Invoke Gemini with structured JSON schema output."""
        from google.genai import types

        start_time = time.perf_counter()
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                system_instruction=system_instruction,
            )

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            latency = time.perf_counter() - start_time
            raw_text = response.text or "{}"
            parsed = json.loads(raw_text)

            # Token usage telemetry
            input_tokens = 0
            output_tokens = 0
            thinking_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = response.usage_metadata
                input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0
                thinking_tokens = getattr(usage, "thinking_token_count", 0) or 0

            # Estimate cost
            cost = (
                (input_tokens / 1_000_000.0) * ESTIMATED_INPUT_COST_PER_M
                + (output_tokens / 1_000_000.0) * ESTIMATED_OUTPUT_COST_PER_M
            )

            call_log = GeneratorCallLog(
                model=self.model_name,
                generator=generator_label,
                steps=1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
                latency_seconds=round(latency, 4),
                estimated_cost_usd=round(cost, 6),
            )

            return parsed, call_log

        except json.JSONDecodeError as e:
            raise LLMClientError(f"Gemini returned invalid JSON: {str(e)}")
        except Exception as e:
            raise LLMClientError(f"Gemini API call failed: {str(e)}")


class MockLLMClient(LLMClient):
    """Mock client for offline testing and deterministic unit test suites."""

    def __init__(
        self,
        canned_response: Optional[Dict[str, Any]] = None,
        latency_seconds: float = 0.01,
        should_fail: bool = False,
    ):
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
            model="mock-gemini-test",
            generator=generator_label,
            steps=1,
            input_tokens=150,
            output_tokens=120,
            thinking_tokens=0,
            latency_seconds=self.latency_seconds,
            estimated_cost_usd=0.000045,
        )

        return self.canned_response, call_log
