"""Types and schemas for LLM provider execution telemetry."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeneratorCallLog(BaseModel):
    """Execution telemetry for a single generator call (LLM direct or external agent)."""

    model: str = Field(description="Model identifier or agent name.")
    provider: str = Field(default="unknown", description="LLM provider name.")
    generator: str = Field(description="Generator type: 'llm_direct' or 'external_agent'.")
    steps: int = Field(default=1, description="Number of agent reasoning/tool execution steps.")
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    thinking_tokens: int = Field(default=0)
    latency_seconds: float = Field(default=0.0)
    estimated_cost_usd: float = Field(default=0.0)

    model_config = {"frozen": True}
