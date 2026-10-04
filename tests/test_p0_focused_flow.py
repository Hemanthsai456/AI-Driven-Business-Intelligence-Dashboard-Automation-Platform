"""Regression tests for P0 Focused Query -> Dashboard Generation and Deterministic Baseline Fallback."""

import pytest
import pandas as pd
from typing import Any, Dict

from ingestion.loaders import load_dataset
from cleaning.cleaner import clean_dataset
from intelligence import profile_dataset, analyze_semantics, assess_readiness
from orchestrator.context_builder import build_llm_context
from orchestrator.generator import MultiProviderGenerator
from orchestrator.pipeline import run_orchestration_pipeline
from providers.base import LLMClient, LLMClientError
from providers.adapters.local import RuleBasedBaselineClient


class MockFailingProviderClient(LLMClient):
    """Mock provider that always raises an LLMClientError to simulate API outages."""

    def __init__(self, provider_name: str, error_message: str):
        super().__init__(provider_name, f"mock-{provider_name}-failing")
        self.error_message = error_message

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: str = None,
        generator_label: str = "llm_direct",
    ):
        raise LLMClientError(f"Simulated outage for {self.provider}: {self.error_message}")


@pytest.fixture
def baseline_dataset_bundle():
    """Load, clean, and profile the standard baseline fixture dataset."""
    raw = load_dataset("tests/fixtures/baseline.csv")
    cleaned, _ = clean_dataset(raw)
    prof = profile_dataset(cleaned)
    sem = analyze_semantics(cleaned, profile=prof)
    ready = assess_readiness(cleaned, profile=prof, semantic_profile=sem)
    return {
        "dataset": cleaned,
        "profile": prof,
        "semantic_profile": sem,
        "readiness": ready,
    }


# ---------------------------------------------------------------------------
# 1. Valid focused analytical request
# ---------------------------------------------------------------------------

def test_valid_focused_analytical_request(baseline_dataset_bundle):
    """Test valid focused analytical request produces valid candidate and dashboard."""
    b = baseline_dataset_bundle
    # Use deterministic baseline client for fast, deterministic unit test
    gen = MultiProviderGenerator(clients=[RuleBasedBaselineClient()])

    result = run_orchestration_pipeline(
        dataset=b["dataset"],
        data_profile=b["profile"],
        semantic_profile=b["semantic_profile"],
        readiness=b["readiness"],
        intent="Total amount by customer_name",
        generator=gen,
        require_clarification=False,
    )

    assert result.status == "SUCCESS"
    assert result.dashboard_spec is not None
    assert len(result.dashboard_spec.tiles) >= 2
    tile = next((t for t in result.dashboard_spec.tiles if t.chart_type in ("bar", "BAR")), None)
    assert tile is not None
    assert tile.chart_type in ("bar", "BAR")
    assert tile.x_key == "customer_name"
    assert "sum_amount" in tile.y_keys
    assert len(tile.data) == 5
    for row in tile.data:
        assert "customer_name" in row
        assert "sum_amount" in row


# ---------------------------------------------------------------------------
# 2. External provider failure with baseline fallback
# ---------------------------------------------------------------------------

def test_external_provider_failure_with_baseline_fallback(baseline_dataset_bundle):
    """Test MultiProviderGenerator falls back to rule_based_baseline when external LLMs fail."""
    b = baseline_dataset_bundle
    gemini_fail = MockFailingProviderClient("gemini", "404 NOT_FOUND")
    groq_fail = MockFailingProviderClient("groq", "400 model_decommissioned")
    ollama_fail = MockFailingProviderClient("ollama", "Connection refused")

    gen = MultiProviderGenerator(clients=[gemini_fail, groq_fail, ollama_fail])

    result = run_orchestration_pipeline(
        dataset=b["dataset"],
        data_profile=b["profile"],
        semantic_profile=b["semantic_profile"],
        readiness=b["readiness"],
        intent="Total amount by customer_name",
        generator=gen,
        require_clarification=False,
    )

    assert result.status == "SUCCESS"
    assert result.dashboard_spec is not None
    winner = result.dashboard_spec.winner
    assert winner.plan.provider == "rule_based_baseline"
    assert winner.plan.generator == "rule_based_baseline"
    assert winner.plan.metric.column == "amount"
    assert winner.plan.dimensions[0].column == "customer_name"

    # Confirm failures were isolated and logged, not swallowed
    trace_logs = result.dashboard_spec.trace.generator_logs
    providers_logged = {l.provider for l in trace_logs}
    assert "gemini" in providers_logged
    assert "groq" in providers_logged
    assert "ollama" in providers_logged
    assert "rule_based_baseline" in providers_logged


# ---------------------------------------------------------------------------
# 3. Zero external providers available
# ---------------------------------------------------------------------------

def test_zero_external_providers_available(baseline_dataset_bundle):
    """Test MultiProviderGenerator handles pool with zero external LLMs via deterministic baseline."""
    b = baseline_dataset_bundle
    # Pass empty client list (no external providers at all)
    gen = MultiProviderGenerator(clients=[])

    result = run_orchestration_pipeline(
        dataset=b["dataset"],
        data_profile=b["profile"],
        semantic_profile=b["semantic_profile"],
        readiness=b["readiness"],
        intent="Total amount by customer_name",
        generator=gen,
        require_clarification=False,
    )

    assert result.status == "SUCCESS"
    assert result.dashboard_spec is not None
    assert result.dashboard_spec.winner.plan.provider == "rule_based_baseline"


# ---------------------------------------------------------------------------
# 4. Successful DashboardSpec creation through fallback
# ---------------------------------------------------------------------------

def test_successful_dashboardspec_creation_through_fallback(baseline_dataset_bundle):
    """Verify detailed structure of DashboardSpec created through baseline fallback."""
    b = baseline_dataset_bundle
    failing_client = MockFailingProviderClient("mock_external", "All external APIs down")
    gen = MultiProviderGenerator(clients=[failing_client])

    result = run_orchestration_pipeline(
        dataset=b["dataset"],
        data_profile=b["profile"],
        semantic_profile=b["semantic_profile"],
        readiness=b["readiness"],
        intent="Total amount by customer_name",
        generator=gen,
        require_clarification=False,
    )

    assert result.status == "SUCCESS"
    spec = result.dashboard_spec
    assert spec is not None
    assert len(spec.tiles) >= 2

    tile = next((t for t in spec.tiles if t.chart_type in ("bar", "BAR", "line", "LINE")), None)
    assert tile is not None
    assert tile.id is not None
    assert tile.chart_type in ("bar", "BAR", "line", "LINE")
    assert tile.x_key == "customer_name"
    assert tile.y_keys == ["sum_amount"]
    assert len(tile.data) > 0

    # Verify execution result
    exec_res = spec.winner.execution_result
    assert exec_res.status.value == "SUCCESS"
    assert exec_res.row_count == len(tile.data)
    assert "SELECT" in exec_res.compiled_sql.upper()


# ---------------------------------------------------------------------------
# 5. Existing Discovery Mode still works
# ---------------------------------------------------------------------------

def test_existing_discovery_mode_still_works(baseline_dataset_bundle):
    """Verify discovery mode generation continues to function without regression."""
    b = baseline_dataset_bundle

    discovery_result = run_orchestration_pipeline(
        dataset=b["dataset"],
        semantic_profile=b["semantic_profile"],
        readiness=b["readiness"],
        data_profile=b["profile"],
        intent="",
    )

    assert discovery_result is not None
    assert discovery_result.status == "SUCCESS"
    assert discovery_result.dashboard_spec is not None
    assert len(discovery_result.dashboard_spec.tiles) > 0
    for tile in discovery_result.dashboard_spec.tiles:
        assert tile.data is not None
        assert len(tile.data) > 0
