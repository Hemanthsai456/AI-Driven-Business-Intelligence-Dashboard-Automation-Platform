"""Compatibility wrapper for providers.

Deprecated: Import directly from `providers` or `providers.factory`.
This module delegates to the agnostic providers package.
"""

from providers.adapters.gemini import GeminiClient
from providers.adapters.groq import GroqClient
from providers.adapters.mock import MockLLMClient
from providers.adapters.ollama import OllamaClient
from providers.base import (
    LLMClient,
    LLMClientError,
    get_strict_json_schema,
    make_strict_schema,
)
from providers.factory import (
    LLMProviderFactory,
    get_llm_client,
    get_multi_provider_clients,
)

__all__ = [
    "GeminiClient",
    "GroqClient",
    "LLMClient",
    "LLMClientError",
    "LLMProviderFactory",
    "MockLLMClient",
    "OllamaClient",
    "get_llm_client",
    "get_multi_provider_clients",
    "get_strict_json_schema",
    "make_strict_schema",
]
