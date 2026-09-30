"""Capabilities registry for LLM providers and models."""

from typing import Dict, TypedDict


class ModelCapabilities(TypedDict):
    strict_schema: bool
    tool_calling: bool


PROVIDER_CAPABILITIES: Dict[str, Dict[str, ModelCapabilities]] = {
    "gemini": {
        "gemini-2.5-pro": {"strict_schema": True, "tool_calling": True},
        "gemini-1.5-pro": {"strict_schema": True, "tool_calling": True},
        "gemini-2.5-flash": {"strict_schema": True, "tool_calling": True},
        "default": {"strict_schema": True, "tool_calling": True},
    },
    "groq": {
        "llama3-70b-8192": {"strict_schema": False, "tool_calling": True},
        "default": {"strict_schema": False, "tool_calling": False},
    },
    "ollama": {
        "llama3": {"strict_schema": False, "tool_calling": False},
        "default": {"strict_schema": False, "tool_calling": False},
    },
}


def get_capabilities(provider: str, model: str) -> ModelCapabilities:
    """Get capabilities for a given provider and model."""
    provider_caps = PROVIDER_CAPABILITIES.get(provider.lower(), {})
    return provider_caps.get(
        model.lower(),
        provider_caps.get("default", {"strict_schema": False, "tool_calling": False}),
    )
