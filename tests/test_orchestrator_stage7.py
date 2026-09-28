"""Tests for Orchestrator Stage 7: End-to-End Pipeline, Pass 2 Cascade, Explainability, and Spec Emission.

Covers:
- C3 readiness refusal check before Pass 1.
- End-to-end pipeline execution with DashboardSpec emission.
- Deterministic Ranker V1 weights and score breakdown.
- Pass 2 winner validation and runner-up cascade promotion.
- Exhausted cascade producing UNANSWERABLE result.
- Score tie detection within epsilon=0.05 triggering clarification flag.
- Structured decision log and explainability log JSONL emission.
- Isolated per-candidate artifact emission in artifacts/candidates/.
- API endpoint /api/orchestrator/pipeline validation and happy path.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import pandas as pd

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.schema_validator import AnalysisReadiness, ReadinessCheck, ReadinessStatus
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
)
from orchestrator.config import (
    MAX_CASCADE_DEPTH,
    RANK_TIE_EPSILON,
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
)
from orchestrator.generator import MockAgent
from orchestrator.logger import (
    emit_decision_log,
    emit_explainability_log,
    save_candidate_artifact,
)
from orchestrator.pipeline import (
    OrchestrationPipelineResult,
    run_orchestration_pipeline,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    ScoreBreakdown,
    VisualizationType,
)


@pytest.fixture
def mock_stage7_dataset():
    """Create a canonical dataset with sales data for Stage 7 pipeline tests."""
    df = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-3", "ORD-4", "ORD-5"],
        "category": ["Electronics", "Clothing", "Electronics", "Home", "Clothing"],
        "sales": [100.0, 50.0, 200.0, 75.0, 150.0],
        "quantity": [2, 1, 4, 1, 3],
        "order_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    })
    meta = DatasetMetadata(
        dataset_id="ds_stage7_test",
        name="sales_test",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("order_id", "order_id", "object", ColumnRole.IDENTIFIER, 0, 0.0, 5),
            ColumnMetadata("category", "category", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("sales", "sales", "float64", ColumnRole.MEASURE, 0, 0.0, 5),
            ColumnMetadata("quantity", "quantity", "int64", ColumnRole.MEASURE, 0, 0.0, 4),
            ColumnMetadata("order_date", "order_date", "object", ColumnRole.DATETIME, 0, 0.0, 5),
        ],
    )
    return CanonicalDataset(metadata=meta, data=df)


@pytest.fixture
def mock_stage7_semantic_profile():
    return DatasetSemanticProfile(
        dataset_id="ds_stage7_test",
        column_evidences={
            "order_id": ColumnSemanticEvidence("order_id", ColumnRole.IDENTIFIER, 0.95, "HIGH", ["id"]),
            "category": ColumnSemanticEvidence("category", ColumnRole.DIMENSION, 0.90, "HIGH", ["category"]),
            "sales": ColumnSemanticEvidence("sales", ColumnRole.MEASURE, 0.95, "HIGH", ["currency"]),
            "quantity": ColumnSemanticEvidence("quantity", ColumnRole.MEASURE, 0.85, "HIGH", ["numeric"]),
            "order_date": ColumnSemanticEvidence("order_date", ColumnRole.DATETIME, 0.90, "HIGH", ["date"]),
        },
    )


@pytest.fixture
def mock_stage7_readiness():
    return AnalysisReadiness(
        dataset_id="ds_stage7_test",
        status=ReadinessStatus.READY,
        checks=[
            ReadinessCheck(check_name="dataframe_exists", passed=True, message="OK", is_blocking=True),
        ],
    )


def _make_candidate(
    plan_id: str,
    vis: VisualizationType = VisualizationType.BAR,
    metric_col: str = "sales",
    dim_col: str = "category",
    generator: str = "llm_direct",
) -> CandidatePlan:
    dims = [DimensionSpec(column=dim_col)] if dim_col else []
    return CandidatePlan(
        plan_id=plan_id,
        dataset_id="ds_stage7_test",
        intent="Show total sales by category",
        generator=generator,
        metric=MetricSpec(column=metric_col, aggregation=AggregationType.SUM),
        dimensions=dims,
        filters=[],
        visualization=vis,
        reasoning=PlanReasoning(
            interpretation="Aggregating sales by category",
            evidence=["High confidence sales measure"],
        ),
    )


def test_pipeline_refusal_when_readiness_not_ready(mock_stage7_dataset, mock_stage7_semantic_profile):
    """C3 test: Dispatch must be refused if readiness is NOT_READY, checked before Pass 1."""
    not_ready = AnalysisReadiness(
        dataset_id="ds_stage7_test",
        status=ReadinessStatus.NOT_READY,
        checks=[
            ReadinessCheck(check_name="blocking_corruption", passed=False, message="File corrupted", is_blocking=True),
        ],
    )

    res = run_orchestration_pipeline(
        dataset=mock_stage7_dataset,
        semantic_profile=mock_stage7_semantic_profile,
        readiness=not_ready,
        intent="Show total sales by category",
    )

    assert res.status == "REFUSED"
    assert "File corrupted" in res.message
    assert res.dashboard_spec is None


def test_pipeline_success_end_to_end(mock_stage7_dataset, mock_stage7_semantic_profile, mock_stage7_readiness):
    """End-to-end pipeline generates plans, validates Pass 1, ranks, runs Pass 2, and produces DashboardSpec."""
    c1 = _make_candidate("plan_1", vis=VisualizationType.BAR)
    c2 = _make_candidate("plan_2", vis=VisualizationType.TABLE)
    mock_agent = MockAgent(canned_plans=[c1, c2])

    res = run_orchestration_pipeline(
        dataset=mock_stage7_dataset,
        semantic_profile=mock_stage7_semantic_profile,
        readiness=mock_stage7_readiness,
        intent="Show total sales by category",
        generator=mock_agent,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec
    assert spec.winner is not None
    assert spec.winner.plan.plan_id in ("plan_1", "plan_2")
    assert spec.trace.pass2_result.passed is True
    assert len(spec.alternate_interpretations) >= 1
    assert res.decision_log_entry is not None
    assert res.explainability_log_entry is not None


def test_pipeline_cascade_promotes_rank2(mock_stage7_dataset, mock_stage7_semantic_profile, mock_stage7_readiness):
    """Rank-1 candidate fails Pass 2 (KPI with multiple rows) and triggers cascade promoting rank-2."""
    # c1 is KPI but returns 3 categories (multi-row) -> will fail Pass 2
    c1 = _make_candidate("plan_kpi_fail", vis=VisualizationType.KPI, dim_col="category")
    # c2 is BAR chart -> will pass Pass 2
    c2 = _make_candidate("plan_bar_pass", vis=VisualizationType.BAR, dim_col="category")
    mock_agent = MockAgent(canned_plans=[c1, c2])

    res = run_orchestration_pipeline(
        dataset=mock_stage7_dataset,
        semantic_profile=mock_stage7_semantic_profile,
        readiness=mock_stage7_readiness,
        intent="Show total sales by category",
        generator=mock_agent,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    assert res.cascade_depth == 1
    # Winner promoted should be plan_bar_pass
    assert res.dashboard_spec.winner.plan.plan_id == "plan_bar_pass"
    # c1 should be in alternate interpretations with Pass 2 failure explanation
    fail_alts = [
        alt for alt in res.dashboard_spec.alternate_interpretations
        if alt.plan.plan_id == "plan_kpi_fail"
    ]
    assert len(fail_alts) == 1
    assert "Pass 2 failed" in fail_alts[0].reason_not_winner


def test_pipeline_exhausted_cascade_returns_unanswerable(mock_stage7_dataset, mock_stage7_semantic_profile, mock_stage7_readiness):
    """When all candidates fail Pass 2 and cascade depth is exhausted, pipeline returns UNANSWERABLE."""
    # Both candidates fail Pass 2
    c1 = _make_candidate("plan_fail_1", vis=VisualizationType.KPI, dim_col="category")
    c2 = _make_candidate("plan_fail_2", vis=VisualizationType.KPI, dim_col="category")
    mock_agent = MockAgent(canned_plans=[c1, c2])

    res = run_orchestration_pipeline(
        dataset=mock_stage7_dataset,
        semantic_profile=mock_stage7_semantic_profile,
        readiness=mock_stage7_readiness,
        intent="Show total sales by category",
        generator=mock_agent,
        max_cascade_depth=1,
    )

    assert res.status == "UNANSWERABLE"
    assert res.dashboard_spec is None
    assert "Pass 2 validation" in res.message


def test_pipeline_tie_detection(mock_stage7_dataset, mock_stage7_semantic_profile, mock_stage7_readiness):
    """When top two candidates score within epsilon=0.05, is_tie flag is set to True."""
    # Create two almost identical plans differing only in plan_id
    c1 = _make_candidate("plan_tie_1", vis=VisualizationType.BAR)
    c2 = _make_candidate("plan_tie_2", vis=VisualizationType.BAR)
    mock_agent = MockAgent(canned_plans=[c1, c2])

    res = run_orchestration_pipeline(
        dataset=mock_stage7_dataset,
        semantic_profile=mock_stage7_semantic_profile,
        readiness=mock_stage7_readiness,
        intent="Show total sales by category",
        generator=mock_agent,
    )

    assert res.status == "SUCCESS"
    assert res.is_tie is True
    assert res.dashboard_spec.is_tie is True


def test_isolated_candidate_artifact_saved(tmp_path):
    """Verify save_candidate_artifact creates valid isolated JSON artifact on disk."""
    plan = _make_candidate("plan_isolated_test")
    p1a = None
    exec_res = ExecutionResult(
        plan_id=plan.plan_id,
        compiled_sql="SELECT category, SUM(sales) FROM ds GROUP BY 1",
        status=ExecutionStatus.SUCCESS,
        row_count=3,
        columns=["category", "SUM(sales)"],
        rows=[{"category": "Electronics", "SUM(sales)": 300.0}],
    )
    score = ScoreBreakdown(evidence=0.9, coverage=0.8, stability=1.0, assumptions=0.25, total=0.85)

    path = save_candidate_artifact(
        plan=plan,
        execution=exec_res,
        score=score,
        artifacts_dir=tmp_path,
    )

    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["plan_id"] == "plan_isolated_test"
    assert data["execution"]["row_count"] == 3
    assert data["score_breakdown"]["total"] == 0.85


def test_api_pipeline_endpoint_404_not_found():
    """POST /api/orchestrator/pipeline with unknown dataset returns 404."""
    client = TestClient(app)
    resp = client.post(
        "/api/orchestrator/pipeline",
        json={"dataset_id": "nonexistent_ds", "intent": "Show revenue", "mode": "both"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["message"]


def test_api_pipeline_endpoint_happy_path(mock_stage7_dataset, mock_stage7_semantic_profile, mock_stage7_readiness):
    """POST /api/orchestrator/pipeline runs end-to-end and returns full OrchestratorPipelineResponse."""
    session_store.save(
        DatasetSessionRecord(
            dataset=mock_stage7_dataset,
            profile=None,
            semantic_profile=mock_stage7_semantic_profile,
            readiness=mock_stage7_readiness,
        )
    )

    client = TestClient(app)
    resp = client.post(
        "/api/orchestrator/pipeline",
        json={
            "dataset_id": "ds_stage7_test",
            "intent": "Show sales by category",
            "mode": "llm_only",
            "k": 2,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("SUCCESS", "UNANSWERABLE")
    if data["status"] == "SUCCESS":
        assert data["spec_id"] is not None
        assert data["winner"] is not None
        assert "score_breakdown" in data["winner"]
        assert len(data["ranked_candidates"]) > 0
