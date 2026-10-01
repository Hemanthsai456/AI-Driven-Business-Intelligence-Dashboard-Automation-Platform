"""Provider-Agnostic LLM Layer.

Responsible for:
- Abstract LLMClient interface and structured schema enforcement
- Provider-specific adapters (Gemini, Groq, Ollama, Mock)
- Config-driven dynamic LLM client instantiation and multi-provider pools
"""

from providers.base import (
    LLMClient,
    LLMClientError,
    ProviderInitializationError,
    get_strict_json_schema,
    make_strict_schema,
)
from providers.adapters.gemini import GeminiClient
from providers.adapters.groq import GroqClient
from providers.adapters.mock import MockLLMClient
from providers.adapters.ollama import OllamaClient
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
    "ProviderInitializationError",
    "LLMProviderFactory",
    "MockLLMClient",
    "OllamaClient",
    "get_llm_client",
    "get_multi_provider_clients",
    "get_strict_json_schema",
    "make_strict_schema",
]
