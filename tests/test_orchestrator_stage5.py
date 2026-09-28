"""Tests for Orchestrator Stage 5: Plan Generators, Injection Defense, Telemetry, and Failure Isolation.

Covers:
- GENERATOR_MODE config handling (llm_only, agent_only, both)
- CandidatePlan attribution (llm_direct, external_agent)
- Agent limits (AGENT_MAX_STEPS, AGENT_MAX_TOKENS, AGENT_TIMEOUT_S)
- Agent read-only metadata tools (no row access, no SQL)
- Output validation against schema with 1-retry then drop
- Failure isolation: Agent timeout or failure does not crash the request
- Context builder injection prevention and control character sanitization
- Decision log telemetry: generator, steps, tokens, latency, cost
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from ingestion.models import ColumnRole
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
)
from orchestrator.config import (
    AGENT_MAX_STEPS,
    AGENT_MAX_TOKENS,
    AGENT_TIMEOUT_S,
    GENERATOR_MODE,
)
from orchestrator.context_builder import build_llm_context, sanitize_text
from orchestrator.generator import (
    ExternalAgentGenerator,
    LLMDirectGenerator,
    MockAgent,
)
from orchestrator.llm import MockLLMClient
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    ColumnContextEntry,
    DimensionSpec,
    GeneratorCallLog,
    LLMContext,
    MetricSpec,
    PlanReasoning,
    VisualizationType,
)


def _make_sample_context(col_name: str = "revenue", intent: str = "Show total revenue by region") -> LLMContext:
    profile = DatasetSemanticProfile(
        dataset_id="test_ds",
        column_evidences={
            col_name: ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=0.95,
                confidence_level="HIGH",
                evidence=["numeric measure token"],
            ),
            "region": ColumnSemanticEvidence(
                column_name="region",
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.9,
                confidence_level="HIGH",
                evidence=["categorical token"],
            ),
        },
    )
    return build_llm_context("test_ds", intent, profile)


def _make_sample_plan(plan_id: str = "plan_1", generator: str = "llm_direct") -> CandidatePlan:
    return CandidatePlan(
        plan_id=plan_id,
        dataset_id="test_ds",
        intent="Show total revenue by region",
        generator=generator,
        metric=MetricSpec(column="revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="region")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(
            interpretation="Summing revenue by region",
            evidence=["numeric measure token"],
        ),
    )


def test_generator_mode_config_defaults():
    """Verify default config has valid generator mode and agent limits."""
    assert GENERATOR_MODE in ("llm_only", "agent_only", "both")
    assert AGENT_MAX_STEPS > 0
    assert AGENT_MAX_TOKENS > 0
    assert AGENT_TIMEOUT_S > 0


def test_context_builder_sanitizes_injection_and_control_chars():
    """Test that context builder strips control characters and wraps injection attempts as data."""
    injection_col = "col'; DROP TABLE analytics; --\x00\x07\x1b[31m"
    dirty_intent = "Show sales \x00\x1f for \x08 region ' OR '1'='1"

    sanitized_col = sanitize_text(injection_col)
    assert "\x00" not in sanitized_col
    assert "\x07" not in sanitized_col
    assert "\x1b" not in sanitized_col

    context = _make_sample_context(col_name=injection_col, intent=dirty_intent)
    assert "\x00" not in context.intent
    assert "\x1f" not in context.intent
    col_names = [c.column_name for c in context.columns]
    assert any("DROP TABLE" in c for c in col_names)
    assert not any("\x00" in c for c in col_names)


def test_context_builder_truncation():
    """Verify long values are truncated with an ellipsis."""
    long_str = "A" * 500
    res = sanitize_text(long_str, max_len=50)
    assert len(res) == 53
    assert res.endswith("...")


def test_llm_direct_generator_attribution_and_logging():
    """Verify LLMDirectGenerator sets generator='llm_direct' and produces call logs."""
    sample_plan = _make_sample_plan()
    client = MockLLMClient(canned_response=sample_plan.model_dump())
    generator = LLMDirectGenerator(client)
    context = _make_sample_context()

    plans, logs = generator.generate_plans(context, k=1)
    assert len(plans) == 1
    assert plans[0].generator == "llm_direct"
    assert len(logs) == 1
    assert logs[0].generator == "llm_direct"
    assert logs[0].steps == 1
    assert logs[0].input_tokens > 0
    assert logs[0].output_tokens > 0
    assert logs[0].latency_seconds >= 0


def test_external_agent_generator_mock_attribution_and_logging():
    """Verify ExternalAgentGenerator sets generator='external_agent' and records agent steps."""
    sample_plan = _make_sample_plan()
    client = MockLLMClient(canned_response=sample_plan.model_dump())
    generator = ExternalAgentGenerator(llm_client=client)
    context = _make_sample_context()

    plans, logs = generator.generate_plans(context, k=1)
    assert len(plans) == 1
    assert plans[0].generator == "external_agent"
    assert len(logs) == 1
    assert logs[0].generator == "external_agent"
    assert logs[0].steps == 2
    assert logs[0].latency_seconds >= 0


def test_mock_agent_class():
    """Verify MockAgent returns canned plans with attribution and records tool calls."""
    sample_plan = _make_sample_plan()
    agent = MockAgent(canned_plans=[sample_plan])
    context = _make_sample_context()

    plans, logs = agent.generate_plans(context, k=1)
    assert len(plans) == 1
    assert plans[0].generator == "external_agent"
    assert "list_columns" in agent.tools_called


def test_agent_read_only_tools_no_sql_no_row_access():
    """Verify agent cannot access raw rows or execute SQL queries."""
    context = _make_sample_context()
    assert not hasattr(context, "rows")
    assert not hasattr(context, "dataframe")
    for col in context.columns:
        assert isinstance(col, ColumnContextEntry)
        assert not hasattr(col, "values")


def test_failure_isolation_agent_timeout_does_not_fail_request():
    """Verify that an external agent timeout is isolated and does not raise an exception."""
    class TimingOutLLM:
        def generate_structured(self, **kwargs):
            time.sleep(0.3)
            return {}, None

    generator = ExternalAgentGenerator(llm_client=TimingOutLLM(), timeout_seconds=0.05)
    context = _make_sample_context()

    plans, logs = generator.generate_plans(context, k=1)
    assert plans == []
    assert len(logs) == 1
    assert logs[0].steps == 1


def test_failure_isolation_agent_crash_does_not_fail_request():
    """Verify that an external agent exception is caught and returns empty plans."""
    class CrashingLLM:
        def generate_structured(self, **kwargs):
            raise RuntimeError("Agent subprocess disconnected!")

    generator = ExternalAgentGenerator(llm_client=CrashingLLM())
    context = _make_sample_context()

    plans, logs = generator.generate_plans(context, k=1)
    assert plans == []
    assert len(logs) == 1
    assert logs[0].steps == 1


def test_output_validation_schema_retry_then_drop():
    """Verify generator validates output against schema, retrying once before dropping."""
    mock_llm = MagicMock()
    valid_candidate = _make_sample_plan().model_dump()

    mock_log = GeneratorCallLog(
        model="mock",
        generator="llm_direct",
        steps=1,
        input_tokens=10,
        output_tokens=10,
        thinking_tokens=0,
        latency_seconds=0.01,
        estimated_cost_usd=0.0001,
    )
    # First response: invalid dict (fails CandidatePlan validation)
    # Second response: valid candidate dict
    mock_llm.generate_structured.side_effect = [
        ({"invalid": "schema"}, mock_log),
        (valid_candidate, mock_log),
    ]

    generator = LLMDirectGenerator(mock_llm)
    context = _make_sample_context()

    plans, logs = generator.generate_plans(context, k=1)
    assert len(plans) == 1
    assert mock_llm.generate_structured.call_count == 2
