"""Capabilities registry for LLM providers and models.

Re-exports from providers.capabilities for backward compatibility.
"""

from providers.capabilities import (
    ModelCapabilities,
    PROVIDER_CAPABILITIES,
    get_capabilities,
)

__all__ = [
    "ModelCapabilities",
    "PROVIDER_CAPABILITIES",
    "get_capabilities",
]
