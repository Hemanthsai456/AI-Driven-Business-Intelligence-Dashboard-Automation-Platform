"""Mock LLM client adapter for offline testing and deterministic unit test suites."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from providers.base import LLMClient, LLMClientError
from providers.types import GeneratorCallLog


class MockLLMClient(LLMClient):
    """Mock client for offline testing and deterministic unit test suites."""

    def __init__(
        self,
        canned_response: Optional[Dict[str, Any]] = None,
        latency_seconds: float = 0.01,
        should_fail: bool = False,
        model_name: str = "mock-model",
    ):
        super().__init__("mock", model_name)
        self.canned_response = canned_response or {}
        self.latency_seconds = latency_seconds
        self.should_fail = should_fail
        self.call_history: List[str] = []

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
