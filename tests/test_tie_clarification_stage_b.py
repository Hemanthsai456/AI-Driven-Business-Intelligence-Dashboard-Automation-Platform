"""Tests for Stage B: Tie Handling, Clarification, and Run Resolution.

Gate tests verifying:
(a) Tie → NEEDS_CLARIFICATION with >= 2 options (score gap < RANK_TIE_EPSILON,
    winner robustness below floor, or coverage below LOW_COVERAGE_CONFIDENCE_CAP).
(b) Resolve → SUCCESS with chosen plan as winner, Pass 2 execution, reuse of stored state,
    and trace recording resolved_by="user".
(c) Bad run_id, bad plan_id, or expired run → clear typed error responses.
(d) No-tie path unchanged → automatic SUCCESS with winner.
(e) Regression test proving old silent remaining[0] pick no longer happens.
"""

import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
import pandas as pd

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.schema_validator import AnalysisReadiness, ReadinessCheck, ReadinessStatus
from intelligence.semantic_analyzer import ColumnSemanticEvidence, DatasetSemanticProfile
from orchestrator.config import (
    LOW_COVERAGE_CONFIDENCE_CAP,
    RANK_TIE_EPSILON,
    ROBUSTNESS_TIE_FLOOR,
)
from orchestrator.generator import MockAgent
from orchestrator.pipeline import (
    OrchestrationPipelineResult,
    run_orchestration_pipeline,
)
from orchestrator.run_store import (
    PlanNotFoundError,
    RunExpiredError,
    RunNotFoundError,
    RunStore,
    StoredRun,
    default_run_store,
    resolve_pipeline_run,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    RankerWeights,
    ScoreBreakdown,
    VisualizationType,
)


@pytest.fixture
def stage_b_dataset():
    """Canonical dataset with numerical measures, categorical dimension, and dates."""
    df = pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O4", "O5", "O6"],
        "region": ["North", "South", "East", "West", "North", "South"],
        "sales": [120.0, 80.0, 250.0, 95.0, 140.0, 110.0],
        "profit": [30.0, 15.0, 70.0, 20.0, 35.0, 25.0],
        "quantity": [3, 2, 6, 2, 4, 3],
        "order_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06"],
    })
    meta = DatasetMetadata(
        dataset_id="ds_stage_b",
        name="stage_b_sales",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("order_id", "order_id", "object", ColumnRole.IDENTIFIER, 0, 0.0, 6),
            ColumnMetadata("region", "region", "object", ColumnRole.DIMENSION, 0, 0.0, 4),
            ColumnMetadata("sales", "sales", "float64", ColumnRole.MEASURE, 0, 0.0, 6),
            ColumnMetadata("profit", "profit", "float64", ColumnRole.MEASURE, 0, 0.0, 6),
            ColumnMetadata("quantity", "quantity", "int64", ColumnRole.MEASURE, 0, 0.0, 5),
            ColumnMetadata("order_date", "order_date", "object", ColumnRole.DATETIME, 0, 0.0, 6),
        ],
    )
    return CanonicalDataset(metadata=meta, data=df)


@pytest.fixture
def stage_b_profile():
    """Semantic profile for the stage B dataset."""
    return DatasetSemanticProfile(
        dataset_id="ds_stage_b",
        column_evidences={
            "order_id": ColumnSemanticEvidence("order_id", ColumnRole.IDENTIFIER, 0.95, "HIGH", ["id"]),
            "region": ColumnSemanticEvidence("region", ColumnRole.DIMENSION, 0.90, "HIGH", ["region", "geography"]),
            "sales": ColumnSemanticEvidence("sales", ColumnRole.MEASURE, 0.95, "HIGH", ["revenue", "sales"]),
            "profit": ColumnSemanticEvidence("profit", ColumnRole.MEASURE, 0.90, "HIGH", ["profit", "income"]),
            "quantity": ColumnSemanticEvidence("quantity", ColumnRole.MEASURE, 0.70, "MEDIUM", ["count"]),
            "order_date": ColumnSemanticEvidence("order_date", ColumnRole.DATETIME, 0.92, "HIGH", ["date", "timestamp"]),
        },
    )


@pytest.fixture
def stage_b_readiness():
    return AnalysisReadiness(
        dataset_id="ds_stage_b",
        status=ReadinessStatus.READY,
        checks=[ReadinessCheck(check_name="ready", passed=True, message="OK", is_blocking=True)],
    )


def _build_plan(
    plan_id: str,
    metric_col: str = "sales",
    dim_col: str = "region",
    agg: AggregationType = AggregationType.SUM,
    vis: VisualizationType = VisualizationType.BAR,
    interpretation: str = "Aggregate regional metrics",
) -> CandidatePlan:
    dims = [DimensionSpec(column=dim_col)] if dim_col else []
    return CandidatePlan(
        plan_id=plan_id,
        dataset_id="ds_stage_b",
        intent="Show total sales by region",
        generator="llm_direct",
        metric=MetricSpec(column=metric_col, aggregation=agg),
        dimensions=dims,
        filters=[],
        visualization=vis,
        reasoning=PlanReasoning(
            interpretation=interpretation,
            evidence=[f"{metric_col} is high confidence measure"],
        ),
    )


# ---------------------------------------------------------------------------
# Gate Test (a): Tie Detection → NEEDS_CLARIFICATION with ≥2 Options
# ---------------------------------------------------------------------------


def test_gate_a_tie_score_gap_returns_needs_clarification_with_options(
    stage_b_dataset, stage_b_profile, stage_b_readiness
):
    """(a.1) When top-two candidates score gap < RANK_TIE_EPSILON, pipeline returns

    status='NEEDS_CLARIFICATION', dashboard_spec=None, and >= 2 options with
    required fields: interpretation, metric, dimension, aggregation, score, robustness.
    """
    # Two candidates with identical metric/dimension score within epsilon
    p1 = _build_plan("plan_tied_1", metric_col="sales", dim_col="region", interpretation="Sales revenue by region")
    p2 = _build_plan("plan_tied_2", metric_col="sales", dim_col="region", interpretation="Total revenue aggregated by region")
    agent = MockAgent(canned_plans=[p1, p2])

    res: OrchestrationPipelineResult = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales by region",
        generator=agent,
    )

    assert res.status == "NEEDS_CLARIFICATION"
    assert res.dashboard_spec is None, "A tied run must never produce a winner DashboardSpec"
    assert res.is_tie is True
    assert res.run_id is not None, "Run must be assigned a run_id for subsequent resolution"
    assert res.options is not None
    assert len(res.options) >= 2, f"Expected at least 2 tied options, got {len(res.options)}"

    # Validate required option fields per spec:
    # plain-language interpretation, metric, dimension, aggregation, score, and robustness
    for opt in res.options:
        assert "plan_id" in opt
        assert "interpretation" in opt and isinstance(opt["interpretation"], str) and len(opt["interpretation"]) > 0
        assert "metric" in opt and opt["metric"] == "sales"
        assert "dimension" in opt and opt["dimension"] == "region"
        assert "aggregation" in opt and opt["aggregation"] == "SUM"
        assert "score" in opt and isinstance(opt["score"], (int, float))
        assert "robustness" in opt


def test_gate_a_tie_winner_robustness_below_floor(stage_b_dataset, stage_b_profile, stage_b_readiness):
    """(a.2) When winner robustness is below configurable floor, pipeline triggers NEEDS_CLARIFICATION."""
    # Top plan p1 has distinct score from p2, but we configure robustness_tie_floor higher
    # than p1's achieved robustness to force a tie on robustness
    p1 = _build_plan("plan_rob_1", metric_col="sales", dim_col="region")
    p2 = _build_plan("plan_rob_2", metric_col="quantity", dim_col="region")
    agent = MockAgent(canned_plans=[p1, p2])

    # Run with robustness floor set to 1.1 (impossible for any candidate to meet <= 1.0)
    res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales by region",
        generator=agent,
        robustness_tie_floor=1.10,
    )

    assert res.status == "NEEDS_CLARIFICATION"
    assert res.dashboard_spec is None
    assert res.is_tie is True
    assert len(res.options) >= 2


def test_gate_a_tie_coverage_below_confidence_cap(stage_b_dataset, stage_b_profile, stage_b_readiness):
    """(a.3) When coverage is below LOW_COVERAGE_CONFIDENCE_CAP, pipeline triggers NEEDS_CLARIFICATION."""
    p1 = _build_plan("plan_cov_1", metric_col="sales", dim_col="region")
    p2 = _build_plan("plan_cov_2", metric_col="profit", dim_col="region")
    agent = MockAgent(canned_plans=[p1, p2])

    # Intent with 20 unrelated words so coverage of 'sales' (1/20 = 0.05) is far below 0.40 cap
    long_intent = "Please analyze the comprehensive quarterly corporate operational performance across territory divisions and show sales by region"
    res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent=long_intent,
        generator=agent,
    )

    assert res.status == "NEEDS_CLARIFICATION"
    assert res.dashboard_spec is None
    assert res.is_tie is True
    assert len(res.options) >= 2


# ---------------------------------------------------------------------------
# Gate Test (b): Resolve → SUCCESS with Chosen Plan as Winner
# ---------------------------------------------------------------------------


def test_gate_b_resolve_run_via_function(stage_b_dataset, stage_b_profile, stage_b_readiness):
    """(b.1) resolve_pipeline_run reuses stored candidates, skips regeneration,

    runs Pass 2 on the chosen plan, builds DashboardSpec with chosen plan as winner,
    and stamps resolved_by='user' in trace.
    """
    p1 = _build_plan("plan_opt_a", metric_col="sales", dim_col="region", interpretation="Option A: Total sales")
    p2 = _build_plan("plan_opt_b", metric_col="sales", dim_col="region", interpretation="Option B: Alternate sales")
    agent = MockAgent(canned_plans=[p1, p2])

    # Run initial pipeline -> returns NEEDS_CLARIFICATION
    initial_res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales by region",
        generator=agent,
    )
    assert initial_res.status == "NEEDS_CLARIFICATION"
    run_id = initial_res.run_id
    assert run_id is not None

    # Resolve with plan_opt_b
    resolved_res: OrchestrationPipelineResult = resolve_pipeline_run(
        run_id=run_id,
        selected_plan_id="plan_opt_b",
    )

    assert resolved_res.status == "SUCCESS"
    assert resolved_res.dashboard_spec is not None
    spec = resolved_res.dashboard_spec

    # Chosen plan is the promoted winner
    assert spec.winner.plan.plan_id == "plan_opt_b"
    assert spec.winner.is_winner is True
    assert spec.winner.rank == 1

    # Pass 2 was validated
    assert spec.trace.pass2_result is not None
    assert spec.trace.pass2_result.passed is True

    # Trace stamps resolved_by="user"
    assert spec.trace.resolved_by == "user"
    assert spec.trace.run_id == run_id

    # The other candidate is retained in alternate interpretations
    alt_ids = [alt.plan.plan_id for alt in spec.alternate_interpretations]
    assert "plan_opt_a" in alt_ids


def test_gate_b_resolve_via_api_endpoint(stage_b_dataset, stage_b_profile, stage_b_readiness):
    """(b.2) POST /pipeline/resolve endpoint resolves run and returns SUCCESS with chosen plan."""
    session_store.save(
        DatasetSessionRecord(
            dataset=stage_b_dataset,
            profile=None,
            semantic_profile=stage_b_profile,
            readiness=stage_b_readiness,
        )
    )

    p1 = _build_plan("plan_api_1", metric_col="sales", dim_col="region", interpretation="Sales interpretation")
    p2 = _build_plan("plan_api_2", metric_col="sales", dim_col="region", interpretation="Alternate interpretation")
    agent = MockAgent(canned_plans=[p1, p2])

    # Initial pipeline run
    init_res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales by region",
        generator=agent,
    )
    run_id = init_res.run_id

    client = TestClient(app)
    # POST to /pipeline/resolve
    resp = client.post(
        "/pipeline/resolve",
        json={"run_id": run_id, "selected_plan_id": "plan_api_2"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["winner"]["plan_id"] == "plan_api_2"
    assert data["resolved_by"] == "user"
    assert data["run_id"] == run_id
    assert data["dashboard_spec"]["trace"]["resolved_by"] == "user"


# ---------------------------------------------------------------------------
# Gate Test (c): Bad run_id or plan_id → Typed Errors
# ---------------------------------------------------------------------------


def test_gate_c_unknown_run_id_returns_404():
    """(c.1) POST /pipeline/resolve with unknown run_id returns 404 with typed error."""
    client = TestClient(app)
    bad_id = str(uuid4())
    resp = client.post(
        "/pipeline/resolve",
        json={"run_id": bad_id, "selected_plan_id": "any_plan"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_type"] == "RUN_NOT_FOUND"
    assert bad_id in data["message"]

    # Also test direct exception
    with pytest.raises(RunNotFoundError) as exc_info:
        resolve_pipeline_run(bad_id, "any_plan")
    assert exc_info.value.error_type == "RUN_NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_gate_c_unknown_plan_id_returns_422(stage_b_dataset, stage_b_profile, stage_b_readiness):
    """(c.2) POST /pipeline/resolve with invalid plan_id returns 422 with typed error."""
    p1 = _build_plan("plan_x1", metric_col="sales", dim_col="region")
    p2 = _build_plan("plan_x2", metric_col="sales", dim_col="region")
    agent = MockAgent(canned_plans=[p1, p2])

    res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales by region",
        generator=agent,
    )
    run_id = res.run_id

    client = TestClient(app)
    resp = client.post(
        "/pipeline/resolve",
        json={"run_id": run_id, "selected_plan_id": "nonexistent_plan_999"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error_type"] == "PLAN_NOT_FOUND"
    assert "nonexistent_plan_999" in data["message"]

    # Also test direct exception
    with pytest.raises(PlanNotFoundError) as exc_info:
        resolve_pipeline_run(run_id, "nonexistent_plan_999")
    assert exc_info.value.error_type == "PLAN_NOT_FOUND"
    assert exc_info.value.status_code == 422


def test_gate_c_expired_run_returns_410(stage_b_dataset, stage_b_profile, stage_b_readiness):
    """(c.3) Resolving an expired run returns 410 RUN_EXPIRED typed error."""
    store = RunStore(default_ttl=10.0)
    p1 = _build_plan("plan_exp_1", metric_col="sales", dim_col="region")
    run_id = str(uuid4())

    expired_run = StoredRun(
        run_id=run_id,
        created_at=time.time() - 100.0,  # Expired
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales",
        context_hash="abc",
        ranked_candidates=[(
            p1,
            ExecutionResult(plan_id="plan_exp_1", compiled_sql="", status=ExecutionStatus.SUCCESS, row_count=1),
            ScoreBreakdown(evidence=0.8, coverage=0.8, assumptions=0.2, total=0.8),
            1,
        )],
        candidate_records=[],
        generator_logs=[],
        weights=RankerWeights(w1_evidence=0.35, w2_coverage=0.30, w3_stability=0.20, w4_assumptions=0.15),
        consistency=None,
        structured_intent=None,
        ambiguity=None,
        interpretations=None,
        plans_generated=1,
        pass1a_counts=1,
        pass1b_counts=1,
        candidate_validations={},
        max_cascade_depth=2,
        options=[],
        ttl_seconds=10.0,
    )
    store.save_run(expired_run)

    with pytest.raises(RunExpiredError) as exc_info:
        resolve_pipeline_run(run_id, "plan_exp_1", store=store)
    assert exc_info.value.error_type == "RUN_EXPIRED"
    assert exc_info.value.status_code == 410

    # Also test via API endpoint
    default_run_store.save_run(expired_run)
    client = TestClient(app)
    resp = client.post(
        "/pipeline/resolve",
        json={"run_id": run_id, "selected_plan_id": "plan_exp_1"},
    )
    assert resp.status_code == 410
    data = resp.json()
    assert data["error_type"] == "RUN_EXPIRED"
    assert "expired" in data["message"].lower()


# ---------------------------------------------------------------------------
# Gate Test (d): No-Tie Path Unchanged → Automatic SUCCESS
# ---------------------------------------------------------------------------


def test_gate_d_no_tie_path_returns_success_automatically(
    stage_b_dataset, stage_b_profile, stage_b_readiness
):
    """(d) When candidate 1 clearly outscores candidate 2 (no tie), pipeline

    automatically returns SUCCESS with candidate 1 as winner, without clarification.
    """
    # p1 uses 'sales' (evidence 0.95), p2 uses 'quantity' (evidence 0.70)
    # The score gap is > 0.10 (well above RANK_TIE_EPSILON=0.05)
    p1 = _build_plan("plan_clear_winner", metric_col="sales", dim_col="region")
    p2 = _build_plan("plan_runner_up", metric_col="quantity", dim_col="region")
    agent = MockAgent(canned_plans=[p1, p2])

    res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show total sales by region",
        generator=agent,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    assert res.dashboard_spec.winner.plan.plan_id == "plan_clear_winner"
    assert res.is_tie is False
    assert res.options is None


# ---------------------------------------------------------------------------
# Gate Test (e): Regression Test — Old Silent remaining[0] Pick No Longer Happens
# ---------------------------------------------------------------------------


def test_gate_e_regression_silent_remaining_pick_eliminated(
    stage_b_dataset, stage_b_profile, stage_b_readiness
):
    """(e) Regression test: Under the old implementation, when require_clarification=False

    (the default), a tied score was silently ignored and select_winner picked remaining[0]
    as winner returning SUCCESS.
    Under Stage B, the pipeline MUST NEVER return SUCCESS with a silent first pick.
    It unconditionally returns NEEDS_CLARIFICATION with dashboard_spec=None.
    """
    # Two identical-scoring plans with require_clarification=False
    p1 = _build_plan("plan_silent_1", metric_col="sales", dim_col="region")
    p2 = _build_plan("plan_silent_2", metric_col="sales", dim_col="region")
    agent = MockAgent(canned_plans=[p1, p2])

    # require_clarification=False explicitly
    res = run_orchestration_pipeline(
        dataset=stage_b_dataset,
        semantic_profile=stage_b_profile,
        readiness=stage_b_readiness,
        intent="Show sales by region",
        generator=agent,
        require_clarification=False,
    )

    # Prove old silent remaining[0] pick no longer happens:
    assert res.status != "SUCCESS", "Tied candidates must NEVER silently return SUCCESS"
    assert res.status == "NEEDS_CLARIFICATION"
    assert res.dashboard_spec is None, "Tied run must have no winner DashboardSpec"
    assert res.is_tie is True
    assert res.run_id is not None
    assert len(res.options) >= 2
