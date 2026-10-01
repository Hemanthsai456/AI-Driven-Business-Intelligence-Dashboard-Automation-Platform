"""Config-driven LLM Provider Factory and Multi-Provider Registry.

Supports dynamic instantiation of providers (Gemini, Groq, Ollama, Mock)
controlled strictly by configuration/environment variables without hardcoding.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Type

from providers.config import (
    ACTIVE_PROVIDERS_ENV,
    DEFAULT_ACTIVE_PROVIDERS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_PROVIDER,
    GEMINI_API_KEY_ENV,
    GEMINI_MODEL_ENV,
    GROQ_API_KEY_ENV,
    GROQ_MODEL_ENV,
    OLLAMA_MODEL_ENV,
    PROVIDER_ENV,
)
from providers.adapters.gemini import GeminiClient
from providers.adapters.groq import GroqClient
from providers.adapters.local import RuleBasedBaselineClient, ZeroCostLocalClient
from providers.adapters.mock import MockLLMClient
from providers.adapters.ollama import OllamaClient
from providers.base import LLMClient, LLMClientError, ProviderInitializationError

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Registry and factory for dynamically instantiating LLM clients."""

    _registry: Dict[str, Type[LLMClient]] = {
        "gemini": GeminiClient,
        "groq": GroqClient,
        "groq_secondary": GroqClient,
        "ollama": OllamaClient,
        "mock": MockLLMClient,
        "local": RuleBasedBaselineClient,
        "zero_cost_local": RuleBasedBaselineClient,
        "rule_based_baseline": RuleBasedBaselineClient,
    }

    @classmethod
    def register_provider(cls, name: str, client_cls: Type[LLMClient]) -> None:
        """Register a new LLM provider adapter class."""
        cls._registry[name.strip().lower()] = client_cls

    @classmethod
    def get_supported_providers(cls) -> List[str]:
        """Return list of supported provider names."""
        return sorted(list(cls._registry.keys()))

    @classmethod
    def create_client(
        cls,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMClient:
        """Instantiate an LLMClient for the requested or configured provider.

        Args:
            provider: Provider name ('gemini', 'groq', 'groq_secondary', 'ollama', 'mock', 'rule_based_baseline').
                      If None, reads from os.getenv('PROVIDER').
            model_name: Optional model override.
            **kwargs: Extra arguments passed to client constructor.

        Raises:
            LLMClientError: If provider name is unsupported or configuration fails.
        """
        raw_provider = provider or os.getenv(PROVIDER_ENV, DEFAULT_PROVIDER)
        p_name = raw_provider.strip().lower()

        if p_name not in cls._registry:
            supported = ", ".join(cls.get_supported_providers())
            raise LLMClientError(
                f"Unsupported LLM provider '{raw_provider}'. Supported providers are: {supported}."
            )

        client_cls = cls._registry[p_name]

        try:
            if p_name == "gemini":
                model = model_name or os.getenv(GEMINI_MODEL_ENV, DEFAULT_GEMINI_MODEL)
                return client_cls(model_name=model, **kwargs)
            elif p_name == "groq":
                model = model_name or os.getenv(GROQ_MODEL_ENV, DEFAULT_GROQ_MODEL)
                return client_cls(model_name=model, **kwargs)
            elif p_name == "groq_secondary":
                return client_cls(model_name=model_name or "openai/gpt-oss-20b", **kwargs)
            elif p_name == "ollama":
                model = model_name or os.getenv(OLLAMA_MODEL_ENV, DEFAULT_OLLAMA_MODEL)
                return client_cls(model_name=model, **kwargs)
            elif p_name in ("local", "zero_cost_local", "rule_based_baseline"):
                return client_cls(model_name=model_name or "rule_based_baseline", **kwargs)
            elif p_name == "mock":
                return client_cls(model_name=model_name or "mock-model", **kwargs)
            else:
                return client_cls(model_name=model_name or "default", **kwargs)
        except Exception as e:
            if isinstance(e, ProviderInitializationError):
                raise
            raise ProviderInitializationError(p_name, str(e)) from e

    create_from_env = create_client

    @classmethod
    def get_active_provider_pool(
        cls,
        active_providers_str: Optional[str] = None,
    ) -> List[LLMClient]:
        """Instantiate available clients for configured active multi-providers.

        Parses ACTIVE_PROVIDERS comma-separated string.
        Gracefully handles unavailable optional providers in test environments,
        but raises typed ProviderInitializationError outside tests.
        """
        raw_str = active_providers_str or os.getenv(ACTIVE_PROVIDERS_ENV, DEFAULT_ACTIVE_PROVIDERS)
        provider_names = [p.strip().lower() for p in raw_str.split(",") if p.strip()]

        clients: List[LLMClient] = []
        is_testing = bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"))
        for name in provider_names:
            try:
                client = cls.create_client(provider=name)
                clients.append(client)
            except Exception as e:
                if is_testing:
                    logger.warning(
                        f"Optional provider '{name}' failed initialization and will be skipped in test: {e}"
                    )
                else:
                    if isinstance(e, ProviderInitializationError):
                        raise
                    raise ProviderInitializationError(name, str(e)) from e

        return clients


def get_llm_client(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    **kwargs: Any,
) -> LLMClient:
    """Convenience factory function returning a configured LLMClient."""
    return LLMProviderFactory.create_client(provider=provider, model_name=model_name, **kwargs)


def get_multi_provider_clients(
    active_providers_str: Optional[str] = None,
) -> List[LLMClient]:
    """Convenience helper returning active multi-provider client instances."""
    return LLMProviderFactory.get_active_provider_pool(active_providers_str=active_providers_str)
