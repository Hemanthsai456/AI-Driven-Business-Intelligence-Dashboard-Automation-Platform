"""Tests for Pass 2 Validation, Rollback Cascade, and DashboardSpec Population.

Architecture references:
- ranker_v1_spec.md §6 (Pass 2 — Winner-Only Validation)
- orchestrator_conformance.md §1 & §4.2 (MAX_CASCADE_DEPTH = 2, FAILED_CAST_RATE_THRESHOLD = 0.05)
"""

from __future__ import annotations

from pathlib import Path
import pytest
import pandas as pd

from engine.executor import get_default_engine
from ingestion.loaders import load_dataset
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import assess_readiness
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.config import FAILED_CAST_RATE_THRESHOLD, MAX_CASCADE_DEPTH
from orchestrator.generator import MockAgent
from orchestrator.pass2 import validate_pass2
from orchestrator.pipeline import run_orchestration_pipeline
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DashboardSpec,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    MetricSpec,
    Pass2Result,
    PassResult,
    PlanReasoning,
    RankedCandidate,
    ScoreBreakdown,
    VisualizationType,
)
from orchestrator.winner import WinnerSelectionError, select_winner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SALES_CSV_PATH = PROJECT_ROOT / "tests" / "real_data" / "Sales_2024.csv"


@pytest.fixture(scope="module")
def real_sales_context():
    """Load and prepare real Sales_2024.csv data."""
    dataset = load_dataset(SALES_CSV_PATH)
    profile = profile_dataset(dataset)
    readiness = assess_readiness(dataset, profile)
    semantic_profile = analyze_semantics(dataset, profile)
    engine = get_default_engine()
    return dataset, profile, readiness, semantic_profile, engine


# ---------------------------------------------------------------------------
# 1. Pass 2 Unit & Integration Tests (Real Sales_2024.csv)
# ---------------------------------------------------------------------------

def test_pass2_real_winning_candidate_passes(real_sales_context):
    """A valid executed candidate on Sales_2024.csv passes Pass 2 with zero issues."""
    dataset, profile, readiness, semantic_profile, engine = real_sales_context

    # BAR chart: TotalSales by ProductID
    plan = CandidatePlan(
        plan_id="plan_real_pass",
        dataset_id="Sales_2024.csv",
        intent="Show total sales by product",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="ProductID")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Sum of TotalSales grouped by ProductID"),
    )

    exec_res = engine.execute(plan, dataset, semantic_profile)
    assert exec_res.status == ExecutionStatus.SUCCESS
    assert exec_res.row_count > 0

    res = validate_pass2(plan, exec_res)
    assert isinstance(res, PassResult)
    assert res.passed is True
    assert len(res.reasons) == 0
    assert res.cascade_triggered is False


def test_pass2_fails_on_all_null_metric(real_sales_context):
    """Pass 2 fails when the metric column contains all null values."""
    dataset, profile, readiness, semantic_profile, engine = real_sales_context

    plan = CandidatePlan(
        plan_id="plan_null_metric",
        dataset_id="Sales_2024.csv",
        intent="Show total sales by product",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="ProductID")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Test all null metric"),
    )

    # Real execution
    exec_res = engine.execute(plan, dataset, semantic_profile)
    assert exec_res.status == ExecutionStatus.SUCCESS

    # Force all metric values to None
    null_rows = [{**r, "TotalSales": None, "sum_totalsales": None, "sum_TotalSales": None} for r in exec_res.rows]
    forced_null_res = exec_res.model_copy(update={"rows": null_rows})

    res = validate_pass2(plan, forced_null_res)
    assert res.passed is False
    assert res.cascade_triggered is True
    assert any("NULL values" in r for r in res.reasons)


def test_pass2_fails_on_empty_result(real_sales_context):
    """Pass 2 fails when execution returns 0 rows."""
    plan = CandidatePlan(
        plan_id="plan_empty_res",
        dataset_id="Sales_2024.csv",
        intent="Show total sales",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[],
        visualization=VisualizationType.KPI,
        reasoning=PlanReasoning(interpretation="KPI test"),
    )

    empty_res = ExecutionResult(
        plan_id="plan_empty_res",
        status=ExecutionStatus.SUCCESS,
        columns=["TotalSales"],
        rows=[],
        row_count=0,
    )

    res = validate_pass2(plan, empty_res)
    assert res.passed is False
    assert any("empty" in r.lower() for r in res.reasons)


def test_pass2_fails_on_cast_failure_rate_exceeded():
    """Pass 2 fails when failed_cast_rate > FAILED_CAST_RATE_THRESHOLD (0.05)."""
    plan = CandidatePlan(
        plan_id="plan_cast_fail",
        dataset_id="Sales_2024.csv",
        intent="Show sales over time",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Date", granularity=Granularity.MONTH)],
        visualization=VisualizationType.LINE,
        reasoning=PlanReasoning(interpretation="Line over date"),
    )

    exec_res = ExecutionResult(
        plan_id="plan_cast_fail",
        status=ExecutionStatus.SUCCESS,
        columns=["Date", "TotalSales"],
        rows=[{"Date": "2024-01-01", "TotalSales": 100.0}],
        row_count=1,
        failed_cast_count=10,
        failed_cast_rate=FAILED_CAST_RATE_THRESHOLD + 0.10,  # Exceeds threshold
    )

    res = validate_pass2(plan, exec_res)
    assert res.passed is False
    assert any("cast" in r.lower() for r in res.reasons)


def test_pass2_chart_type_compatibility():
    """Pass 2 enforces chart-type / data-shape compatibility."""
    # 1. KPI requires exactly 1 row
    kpi_plan = CandidatePlan(
        plan_id="plan_kpi_multi",
        dataset_id="Sales_2024.csv",
        intent="Show KPI",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[],
        visualization=VisualizationType.KPI,
        reasoning=PlanReasoning(interpretation="KPI"),
    )
    multi_row_res = ExecutionResult(
        plan_id="plan_kpi_multi",
        status=ExecutionStatus.SUCCESS,
        columns=["TotalSales"],
        rows=[{"TotalSales": 100.0}, {"TotalSales": 200.0}],
        row_count=2,
    )
    res_kpi = validate_pass2(kpi_plan, multi_row_res)
    assert res_kpi.passed is False
    assert any("KPI" in r for r in res_kpi.reasons)

    # 2. LINE requires temporal/ordered dimension
    line_plan = CandidatePlan(
        plan_id="plan_line_no_dim",
        dataset_id="Sales_2024.csv",
        intent="Show trend",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="StoreID")],  # No granularity
        visualization=VisualizationType.LINE,
        reasoning=PlanReasoning(interpretation="Line without temporal dimension"),
    )
    res_line = validate_pass2(line_plan, multi_row_res)
    assert res_line.passed is False
    assert any("LINE" in r for r in res_line.reasons)

    # 3. BAR requires at least one dimension
    bar_no_dim = CandidatePlan(
        plan_id="plan_bar_no_dim",
        dataset_id="Sales_2024.csv",
        intent="Show bar",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[],  # No dimension
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Bar without dimension"),
    )
    res_bar = validate_pass2(bar_no_dim, multi_row_res)
    assert res_bar.passed is False
    assert any("BAR" in r for r in res_bar.reasons)


# ---------------------------------------------------------------------------
# 2. Rollback Cascade Tests
# ---------------------------------------------------------------------------

def test_cascade_top_two_fail_third_passes():
    """Construct 3 ranked candidates where top 2 fail Pass 2 and 3rd passes.
    
    Verifies:
    - Candidate 3 is selected as winner.
    - Cascade depth = 2 is recorded.
    - Candidates 1 and 2 are preserved in alternate_interpretations with Pass 2 failure reasons.
    """
    # Candidate 1: KPI with multiple rows -> Fails Pass 2
    c1 = CandidatePlan(
        plan_id="plan_rank1_fail",
        dataset_id="Sales_2024.csv",
        intent="Sales test",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="StoreID")],
        visualization=VisualizationType.KPI,
        reasoning=PlanReasoning(interpretation="Candidate 1"),
    )
    r1 = ExecutionResult(
        plan_id="plan_rank1_fail",
        status=ExecutionStatus.SUCCESS,
        columns=["StoreID", "TotalSales"],
        rows=[{"StoreID": 1, "TotalSales": 100}, {"StoreID": 2, "TotalSales": 200}],
        row_count=2,
    )
    s1 = ScoreBreakdown(evidence=0.9, coverage=0.9, stability=0.9, assumptions=0.0, agreement=0.9, total=0.95)

    # Candidate 2: All null metric -> Fails Pass 2
    c2 = CandidatePlan(
        plan_id="plan_rank2_fail",
        dataset_id="Sales_2024.csv",
        intent="Sales test",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="StoreID")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Candidate 2"),
    )
    r2 = ExecutionResult(
        plan_id="plan_rank2_fail",
        status=ExecutionStatus.SUCCESS,
        columns=["StoreID", "TotalSales"],
        rows=[{"StoreID": 1, "TotalSales": None}],
        row_count=1,
    )
    s2 = ScoreBreakdown(evidence=0.85, coverage=0.85, stability=0.85, assumptions=0.0, agreement=0.8, total=0.85)

    # Candidate 3: Valid BAR chart -> Passes Pass 2
    c3 = CandidatePlan(
        plan_id="plan_rank3_pass",
        dataset_id="Sales_2024.csv",
        intent="Sales test",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="StoreID")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Candidate 3"),
    )
    r3 = ExecutionResult(
        plan_id="plan_rank3_pass",
        status=ExecutionStatus.SUCCESS,
        columns=["StoreID", "TotalSales"],
        rows=[{"StoreID": 1, "TotalSales": 1000}],
        row_count=1,
    )
    s3 = ScoreBreakdown(evidence=0.8, coverage=0.8, stability=0.8, assumptions=0.0, agreement=0.7, total=0.75)

    ranked = [
        (c1, r1, s1, 1),
        (c2, r2, s2, 2),
        (c3, r3, s3, 3),
    ]

    spec = select_winner(
        ranked=ranked,
        dataset_id="Sales_2024.csv",
        intent="Sales test",
        context_hash="hash_test",
        max_cascade_depth=MAX_CASCADE_DEPTH,
    )

    assert spec.winner.plan.plan_id == "plan_rank3_pass"
    assert spec.trace.cascade_depth == 2
    assert spec.trace.pass2_result.passed is True

    # Confirm candidates 1 and 2 are in alternate_interpretations
    alt_ids = [alt.plan.plan_id for alt in spec.alternate_interpretations]
    assert "plan_rank1_fail" in alt_ids
    assert "plan_rank2_fail" in alt_ids

    # Confirm Pass 2 failure reasons are logged on alternates
    c1_alt = next(a for a in spec.alternate_interpretations if a.plan.plan_id == "plan_rank1_fail")
    assert "Pass 2 failed" in c1_alt.reason_not_winner


def test_cascade_all_fail_returns_clarification_failure():
    """When ALL candidates fail Pass 2, WinnerSelectionError is raised and pipeline returns UNANSWERABLE."""
    c1 = CandidatePlan(
        plan_id="fail_1",
        dataset_id="Sales_2024.csv",
        intent="Test",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="StoreID")],
        visualization=VisualizationType.KPI,
        reasoning=PlanReasoning(interpretation="Fail 1"),
    )
    r1 = ExecutionResult(
        plan_id="fail_1",
        status=ExecutionStatus.SUCCESS,
        columns=["StoreID", "TotalSales"],
        rows=[{"StoreID": 1, "TotalSales": 100}, {"StoreID": 2, "TotalSales": 200}],
        row_count=2,
    )
    s1 = ScoreBreakdown(evidence=0.8, coverage=0.8, stability=0.8, assumptions=0.0, agreement=0.8, total=0.8)

    c2 = CandidatePlan(
        plan_id="fail_2",
        dataset_id="Sales_2024.csv",
        intent="Test",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[],
        visualization=VisualizationType.BAR,  # No dimension for BAR
        reasoning=PlanReasoning(interpretation="Fail 2"),
    )
    r2 = ExecutionResult(
        plan_id="fail_2",
        status=ExecutionStatus.SUCCESS,
        columns=["TotalSales"],
        rows=[{"TotalSales": 500}],
        row_count=1,
    )
    s2 = ScoreBreakdown(evidence=0.7, coverage=0.7, stability=0.7, assumptions=0.0, agreement=0.7, total=0.7)

    ranked = [(c1, r1, s1, 1), (c2, r2, s2, 2)]

    # Direct select_winner raises WinnerSelectionError
    with pytest.raises(WinnerSelectionError) as exc_info:
        select_winner(
            ranked=ranked,
            dataset_id="Sales_2024.csv",
            intent="Test",
            context_hash="hash_test",
            max_cascade_depth=MAX_CASCADE_DEPTH,
        )
    assert exc_info.value.cascade_depth >= 1


# ---------------------------------------------------------------------------
# 3. DashboardSpec Full Trace Population & Schema Integrity
# ---------------------------------------------------------------------------

def test_dashboardspec_full_trace_population(real_sales_context):
    """End-to-end pipeline run populates complete DashboardSpec with all stages in trace."""
    dataset, profile, readiness, semantic_profile, engine = real_sales_context

    c1 = CandidatePlan(
        plan_id="p_kpi_fail",
        dataset_id="Sales_2024.csv",
        intent="Show total sales by product",
        generator="test",
        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="ProductID")],
        visualization=VisualizationType.KPI,  # Fails Pass 2 (multi-row KPI)
        reasoning=PlanReasoning(interpretation="Product KPI"),
    )
    c2 = CandidatePlan(
        plan_id="p_bar_pass",
        dataset_id="Sales_2024.csv",
        intent="Show total sales by product",
        generator="test",
        metric=MetricSpec(column="Quantity", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="ProductID")],
        visualization=VisualizationType.BAR,  # Passes Pass 2
        reasoning=PlanReasoning(interpretation="Product BAR"),
    )

    mock_agent = MockAgent(canned_plans=[c1, c2])

    res = run_orchestration_pipeline(
        dataset=dataset,
        semantic_profile=semantic_profile,
        readiness=readiness,
        intent="Show total sales by product",
        generator=mock_agent,
        robustness_tie_floor=0.25,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    # 1. Canonical winner
    assert spec.winner.plan.plan_id == "p_bar_pass"
    assert spec.winner.is_winner is True
    assert spec.winner.rank == 1

    # 2. Alternate interpretations (the runner up that failed Pass 2)
    assert len(spec.alternate_interpretations) == 1
    alt = spec.alternate_interpretations[0]
    assert alt.plan.plan_id == "p_kpi_fail"
    assert "Pass 2 failed" in alt.reason_not_winner

    # 3. Full trace with every stage
    trace = spec.trace
    assert trace.intent == "Show total sales by product"
    assert trace.structured_intent is not None
    assert trace.ambiguity_result is not None
    assert trace.plans_generated == 2
    assert trace.plans_passed_pass1a == 2
    assert trace.plans_passed_pass1b == 2
    assert trace.cascade_depth == 1
    assert trace.pass2_result is not None
    assert trace.pass2_result.passed is True
    assert len(trace.candidate_records) == 2
    assert trace.candidate_records[0]["plan_id"] in ("p_kpi_fail", "p_bar_pass")
    assert "pass1a" in trace.candidate_records[0]
    assert "pass1b" in trace.candidate_records[0]
