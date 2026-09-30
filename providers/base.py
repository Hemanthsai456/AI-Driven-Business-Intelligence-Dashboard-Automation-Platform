"""Base LLMClient interface and JSON schema utilities.

Architecture guarantees:
- Agnostic contract for structured LLM analytical plan generation.
- Decoupled from specific provider SDKs and vendor transport logic.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel
from providers.capabilities import get_capabilities
from providers.types import GeneratorCallLog


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
    """Return strict JSON schema with additionalProperties=False for Pydantic model."""
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
        """Generate structured JSON data conforming to response_schema."""
        pass

    def _execute_with_retries(self, func, *args, **kwargs):
        """Execute a function with exponential backoff for 429 rate limit errors."""
        import re
        max_retries = 4
        base_delay = 2.0
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if any(k in err_str for k in ("429", "too many requests", "resource_exhausted", "503", "unavailable")):
                    if attempt == max_retries - 1:
                        raise LLMClientError(f"{self.provider} transient error / rate limit exceeded: {e}")
                    # Parse explicit retry delay if present in error message
                    match = re.search(r"retry\s+in\s+([\d\.]+)\s*s", str(e), re.IGNORECASE)
                    if not match:
                        match = re.search(r"retrydelay['\":\s]+(\d+)", str(e), re.IGNORECASE)
                    if match:
                        sleep_secs = min(45.0, float(match.group(1)) + 1.0)
                    else:
                        sleep_secs = base_delay * (2 ** attempt)
                    time.sleep(sleep_secs)
                else:
                    raise e
        raise LLMClientError("Max retries exceeded")
