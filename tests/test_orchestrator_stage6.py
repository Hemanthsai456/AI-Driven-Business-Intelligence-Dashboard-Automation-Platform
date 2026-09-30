"""Stage 6 tests: Winner Selection & Pass 2 Cascade.

Tests verified by running pytest -v.  All assertions use real code paths; no mocking of
Pass 2 internals.

Coverage:
  1. validate_pass2 — metric present in result columns (passes)
  2. validate_pass2 — metric absent → cascade_triggered=True
  3. validate_pass2 — KPI with row_count != 1 → fails
  4. validate_pass2 — KPI with row_count == 1 → passes
  5. validate_pass2 — LINE without DATETIME granularity → fails
  6. validate_pass2 — LINE with DATETIME granularity → passes
  7. validate_pass2 — PIE with row_count > 20 → fails
  8. validate_pass2 — PIE with row_count <= 20 → passes
  9. select_winner — rank-1 winner passes Pass 2 → DashboardSpec returned, cascade_depth=0
 10. select_winner — rank-1 fails Pass 2, rank-2 passes → cascade_depth=1
 11. select_winner — all fail Pass 2 → WinnerSelectionError raised
 12. select_winner — tie detection (top-2 within epsilon) → is_tie=True
 13. select_winner — cascade depth cap (max_cascade_depth=0, winner fails) → WinnerSelectionError
 14. Ranker V1: generator field does NOT affect score (spec §Stage 5 requirement)
 15. API endpoint /api/orchestrator/select-winner — 404 on unknown dataset
 16. API endpoint /api/orchestrator/select-winner — winner returned for valid request
 17. API endpoint /api/orchestrator/select-winner — 422 on all-fail Pass 2
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    FilterSpec,
    Granularity,
    MetricSpec,
    PlanReasoning,
    ScoreBreakdown,
    VisualizationType,
)
from orchestrator.utils import compute_score, rank_candidates
from orchestrator.validator import validate_pass2
from orchestrator.winner import WinnerSelectionError, select_winner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(
    dataset_id: str = "ds-test",
    metric_col: str = "Revenue",
    agg: AggregationType = AggregationType.SUM,
    dimensions: Optional[List[DimensionSpec]] = None,
    visualization: VisualizationType = VisualizationType.BAR,
    generator: str = "llm_direct",
    intent: str = "show revenue by category",
) -> CandidatePlan:
    return CandidatePlan(
        plan_id=str(uuid.uuid4()),
        dataset_id=dataset_id,
        intent=intent,
        metric=MetricSpec(column=metric_col, aggregation=agg),
        dimensions=dimensions or [DimensionSpec(column="Category")],
        filters=[],
        visualization=visualization,
        generator=generator,
        reasoning=PlanReasoning(
            interpretation="Aggregated Revenue by Category",
            evidence=["Revenue identified as MEASURE"],
        ),
    )


def _make_exec_result(
    plan_id: str,
    columns: List[str] = None,
    row_count: int = 5,
    rows: Optional[List[Dict[str, Any]]] = None,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
) -> ExecutionResult:
    if columns is None:
        columns = ["Category", "SUM(Revenue)"]
    if rows is None:
        rows = [{"Category": f"Cat{i}", "SUM(Revenue)": float(i * 100)} for i in range(1, row_count + 1)]
    return ExecutionResult(
        plan_id=plan_id,
        status=status,
        columns=columns,
        rows=rows[:row_count],
        row_count=row_count,
        compiled_sql="SELECT ...",
        failed_cast_count=0,
        failed_cast_rate=0.0,
    )


def _make_scored_ranked(
    plan: CandidatePlan,
    exec_result: ExecutionResult,
    total_score: float = 0.7,
    rank: int = 1,
) -> tuple:
    sb = ScoreBreakdown(
        evidence=0.85,
        coverage=0.70,
        stability=0.90,
        assumptions=0.25,
        total=total_score,
    )
    return (plan, exec_result, sb, rank)


# ---------------------------------------------------------------------------
# 1-8: validate_pass2
# ---------------------------------------------------------------------------


def test_pass2_metric_in_columns_passes():
    plan = _make_plan()
    result = _make_exec_result(plan.plan_id, columns=["Category", "SUM(Revenue)"], row_count=5)
    p2 = validate_pass2(plan, result)
    assert p2.passed is True
    assert p2.cascade_triggered is False
    assert p2.plan_id == plan.plan_id


def test_pass2_metric_absent_from_columns_fails():
    plan = _make_plan(metric_col="Revenue")
    # Result has completely unrelated columns
    result = _make_exec_result(plan.plan_id, columns=["City", "Population"], row_count=3)
    p2 = validate_pass2(plan, result)
    assert p2.passed is False
    assert p2.cascade_triggered is True
    checks = [i.check for i in p2.issues]
    assert "plan_result_consistency" in checks


def test_pass2_kpi_wrong_row_count_fails():
    plan = _make_plan(visualization=VisualizationType.KPI, dimensions=[])
    result = _make_exec_result(plan.plan_id, columns=["SUM(Revenue)"], row_count=5)
    p2 = validate_pass2(plan, result)
    assert p2.passed is False
    checks = [i.check for i in p2.issues]
    assert "viz_kpi_single_row" in checks


def test_pass2_kpi_single_row_passes():
    plan = _make_plan(visualization=VisualizationType.KPI, dimensions=[])
    result = _make_exec_result(plan.plan_id, columns=["SUM(Revenue)"], row_count=1, rows=[{"SUM(Revenue)": 999.0}])
    p2 = validate_pass2(plan, result)
    assert p2.passed is True


def test_pass2_line_without_datetime_dim_fails():
    plan = _make_plan(
        visualization=VisualizationType.LINE,
        dimensions=[DimensionSpec(column="Category", granularity=None)],  # no granularity
    )
    result = _make_exec_result(plan.plan_id, columns=["Category", "SUM(Revenue)"], row_count=3)
    p2 = validate_pass2(plan, result)
    assert p2.passed is False
    checks = [i.check for i in p2.issues]
    assert "viz_line_requires_datetime" in checks


def test_pass2_line_with_datetime_granularity_passes():
    plan = _make_plan(
        visualization=VisualizationType.LINE,
        dimensions=[DimensionSpec(column="OrderDate", granularity=Granularity.MONTH)],
    )
    result = _make_exec_result(plan.plan_id, columns=["OrderDate", "SUM(Revenue)"], row_count=12)
    p2 = validate_pass2(plan, result)
    assert p2.passed is True


def test_pass2_pie_too_many_rows_fails():
    plan = _make_plan(visualization=VisualizationType.PIE)
    result = _make_exec_result(plan.plan_id, columns=["Category", "SUM(Revenue)"], row_count=25)
    p2 = validate_pass2(plan, result)
    assert p2.passed is False
    checks = [i.check for i in p2.issues]
    assert "viz_pie_row_limit" in checks


def test_pass2_pie_acceptable_rows_passes():
    plan = _make_plan(visualization=VisualizationType.PIE)
    result = _make_exec_result(plan.plan_id, columns=["Category", "SUM(Revenue)"], row_count=10)
    p2 = validate_pass2(plan, result)
    assert p2.passed is True


# ---------------------------------------------------------------------------
# 9-13: select_winner
# ---------------------------------------------------------------------------


def test_select_winner_rank1_passes_no_cascade():
    plan = _make_plan()
    result = _make_exec_result(plan.plan_id, columns=["Category", "SUM(Revenue)"], row_count=5)
    ranked = [_make_scored_ranked(plan, result, total_score=0.8, rank=1)]

    spec = select_winner(
        ranked=ranked,
        dataset_id="ds-test",
        intent="show revenue by category",
        context_hash="abc123",
    )
    assert spec.winner.plan.plan_id == plan.plan_id
    assert spec.winner.is_winner is True
    assert spec.trace.cascade_depth == 0
    assert spec.trace.pass2_result is not None
    assert spec.trace.pass2_result.passed is True


def test_select_winner_cascade_to_rank2():
    # Rank-1 plan has KPI visualization but 5 rows → fails Pass 2
    plan1 = _make_plan(visualization=VisualizationType.KPI, dimensions=[])
    result1 = _make_exec_result(plan1.plan_id, columns=["SUM(Revenue)"], row_count=5)

    # Rank-2 plan uses BAR (valid for any rows)
    plan2 = _make_plan(visualization=VisualizationType.BAR)
    result2 = _make_exec_result(plan2.plan_id, columns=["Category", "SUM(Revenue)"], row_count=5)

    ranked = [
        _make_scored_ranked(plan1, result1, total_score=0.9, rank=1),
        _make_scored_ranked(plan2, result2, total_score=0.7, rank=2),
    ]

    spec = select_winner(
        ranked=ranked,
        dataset_id="ds-test",
        intent="show revenue",
        context_hash="xyz",
        max_cascade_depth=2,
    )
    # rank-2 should be promoted as winner
    assert spec.winner.plan.plan_id == plan2.plan_id
    assert spec.trace.cascade_depth == 1
    assert spec.trace.pass2_result.passed is True


def test_select_winner_exhausts_cascade_raises():
    # Both plans fail Pass 2 (KPI with multiple rows)
    plan1 = _make_plan(visualization=VisualizationType.KPI, dimensions=[])
    result1 = _make_exec_result(plan1.plan_id, columns=["SUM(Revenue)"], row_count=5)

    plan2 = _make_plan(visualization=VisualizationType.KPI, dimensions=[])
    result2 = _make_exec_result(plan2.plan_id, columns=["SUM(Revenue)"], row_count=3)

    ranked = [
        _make_scored_ranked(plan1, result1, total_score=0.9, rank=1),
        _make_scored_ranked(plan2, result2, total_score=0.7, rank=2),
    ]

    with pytest.raises(WinnerSelectionError) as exc_info:
        select_winner(
            ranked=ranked,
            dataset_id="ds-test",
            intent="show revenue",
            context_hash="xyz",
            max_cascade_depth=2,
        )
    err = exc_info.value
    assert err.cascade_depth >= 1
    assert len(err.failed_pass2_results) >= 1


def test_select_winner_tie_detection():
    """Top-2 candidates within RANK_TIE_EPSILON → is_tie=True."""
    from orchestrator.config import RANK_TIE_EPSILON

    plan1 = _make_plan(metric_col="Revenue")
    result1 = _make_exec_result(plan1.plan_id, columns=["Category", "SUM(Revenue)"], row_count=5)

    plan2 = _make_plan(metric_col="Revenue")
    result2 = _make_exec_result(plan2.plan_id, columns=["Category", "SUM(Revenue)"], row_count=4)

    epsilon_gap = RANK_TIE_EPSILON / 2  # within tie threshold
    ranked = [
        _make_scored_ranked(plan1, result1, total_score=0.80, rank=1),
        _make_scored_ranked(plan2, result2, total_score=0.80 - epsilon_gap, rank=2),
    ]

    spec = select_winner(
        ranked=ranked,
        dataset_id="ds-test",
        intent="revenue by category",
        context_hash="hash",
    )
    assert spec.is_tie is True


def test_select_winner_cascade_depth_cap_zero():
    """max_cascade_depth=0 means no cascade allowed; if rank-1 fails → WinnerSelectionError."""
    plan = _make_plan(visualization=VisualizationType.KPI, dimensions=[])
    result = _make_exec_result(plan.plan_id, columns=["SUM(Revenue)"], row_count=5)
    ranked = [_make_scored_ranked(plan, result, total_score=0.9, rank=1)]

    with pytest.raises(WinnerSelectionError):
        select_winner(
            ranked=ranked,
            dataset_id="ds-test",
            intent="KPI total",
            context_hash="h",
            max_cascade_depth=0,
        )


# ---------------------------------------------------------------------------
# 14: Ranker V1 — generator field does NOT affect score
# ---------------------------------------------------------------------------


def test_ranker_score_identical_when_only_generator_differs():
    """CandidatePlan.generator is attribution only; Ranker V1 score must be identical."""
    plan_llm = _make_plan(generator="llm_direct")
    plan_agent = plan_llm.model_copy(update={"plan_id": str(uuid.uuid4()), "generator": "external_agent"})

    result = _make_exec_result(plan_llm.plan_id, columns=["Category", "SUM(Revenue)"], row_count=5)
    result_agent = _make_exec_result(plan_agent.plan_id, columns=["Category", "SUM(Revenue)"], row_count=5)

    # Empty semantic evidences (no column_evidences available in isolation)
    evidences: dict = {}
    intent_tokens = ["revenue", "by", "category"]

    score_llm = compute_score(plan_llm, result, evidences, intent_tokens)
    score_agent = compute_score(plan_agent, result_agent, evidences, intent_tokens)

    assert score_llm.total == score_agent.total, (
        f"Score should be identical regardless of generator: "
        f"llm={score_llm.total}, agent={score_agent.total}"
    )


# ---------------------------------------------------------------------------
# 15-17: API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client_with_dataset():
    """TestClient with an in-memory dataset loaded into the session store."""
    import io
    from api.main import app

    client = TestClient(app)

    # Upload a minimal CSV dataset
    csv_content = b"Category,Revenue\nElectronics,1000\nClothing,500\nFurniture,750\n"
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("test_stage6.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    dataset_id = resp.json()["dataset_id"]
    return client, dataset_id


def _build_select_winner_payload(dataset_id: str, pass2_should_fail: bool = False):
    """Build a valid SelectWinnerRequest payload for a given dataset_id."""
    plan_id = str(uuid.uuid4())
    plan = {
        "plan_id": plan_id,
        "dataset_id": dataset_id,
        "intent": "show revenue by category",
        "metric": {"column": "Revenue", "aggregation": "SUM"},
        "dimensions": [{"column": "Category", "granularity": None}],
        "filters": [],
        "visualization": "KPI" if pass2_should_fail else "BAR",
        "generator": "llm_direct",
        "reasoning": {
            "interpretation": "Revenue by Category",
            "evidence": ["Revenue is MEASURE"],
        },
    }
    exec_result = {
        "plan_id": plan_id,
        "status": "SUCCESS",
        "columns": ["Category", "SUM(Revenue)"],
        "rows": [
            {"Category": "Electronics", "SUM(Revenue)": 1000},
            {"Category": "Clothing", "SUM(Revenue)": 500},
        ],
        "row_count": 2,  # KPI requires 1 row; 2 rows → fail if KPI
        "compiled_sql": "SELECT Category, SUM(Revenue) FROM source_data GROUP BY Category",
        "failed_cast_count": 0,
        "failed_cast_rate": 0.0,
        "warnings": [],
        "runtime_seconds": 0.01,
    }
    return {
        "dataset_id": dataset_id,
        "intent": "show revenue by category",
        "candidates": [plan],
        "execution_results": {plan_id: exec_result},
        "generator_logs": [],
        "context_hash": "testhash",
    }


def test_api_select_winner_404_unknown_dataset(api_client_with_dataset):
    client, _ = api_client_with_dataset
    payload = _build_select_winner_payload("no-such-dataset-id")
    resp = client.post("/api/orchestrator/select-winner", json=payload)
    assert resp.status_code == 404


def test_api_select_winner_returns_winner(api_client_with_dataset):
    client, dataset_id = api_client_with_dataset
    payload = _build_select_winner_payload(dataset_id, pass2_should_fail=False)
    resp = client.post("/api/orchestrator/select-winner", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "winner_plan_id" in data
    assert data["winner_generator"] == "llm_direct"
    assert data["winner_visualization"] == "BAR"
    assert data["cascade_depth"] == 0
    assert data["pass2_passed"] is True


def test_api_select_winner_422_all_fail_pass2(api_client_with_dataset):
    """KPI plan with 2 rows (not 1) triggers Pass 2 failure; no runner-up → UNANSWERABLE."""
    client, dataset_id = api_client_with_dataset
    payload = _build_select_winner_payload(dataset_id, pass2_should_fail=True)
    resp = client.post("/api/orchestrator/select-winner", json=payload)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    # Error message must mention unanswerable / cascade
    detail = resp.json().get("message", "").lower()
    assert "unanswerable" in detail or "cascade" in detail or "pass 2" in detail.lower()


def test_ranker_gated_agreement_not_dominated_by_low_coverage():
    """Prove two candidates with identical scores except one has agreement=1.0/coverage=0.2

    and the other has agreement=0.33/coverage=0.9 — the second must NOT be dominated by the first.
    """
    from intelligence.semantic_analyzer import ColumnRole, ColumnSemanticEvidence

    sem_ev = {
        "Revenue": ColumnSemanticEvidence("Revenue", ColumnRole.MEASURE, 0.95, "HIGH", []),
        "Category": ColumnSemanticEvidence("Category", ColumnRole.DIMENSION, 0.95, "HIGH", []),
    }
    exec_res = _make_exec_result("p1", columns=["Category", "sum_Revenue"], row_count=5)

    # Candidate 1: agreement=1.0, coverage=0.2
    plan1 = _make_plan(metric_col="Revenue")
    plan1 = plan1.model_copy(update={"supporting_count": 3, "providers_responded": 3})
    sb1 = compute_score(plan1, exec_res, sem_ev, intent_tokens=[], coverage_override=0.2)

    # Candidate 2: agreement=0.33, coverage=0.9
    plan2 = _make_plan(metric_col="Revenue")
    plan2 = plan2.model_copy(update={"supporting_count": 1, "providers_responded": 3})
    sb2 = compute_score(plan2, exec_res, sem_ev, intent_tokens=[], coverage_override=0.9)

    print(f"Candidate 1 (agg=1.0, cov=0.2): score={sb1.total:.4f}")
    print(f"Candidate 2 (agg=0.33, cov=0.9): score={sb2.total:.4f}")

    # The second candidate (higher coverage) must NOT be dominated by the first
    assert sb2.total > sb1.total


def test_ranker_low_coverage_confidence_cap_forces_tie():
    """Verify that candidate with coverage < LOW_COVERAGE_CONFIDENCE_CAP has score capped

    and triggers is_tie = True rather than an outright automatic win, even at agreement=1.0.
    """
    from orchestrator.config import LOW_COVERAGE_CONFIDENCE_CAP
    from intelligence.semantic_analyzer import ColumnRole, ColumnSemanticEvidence

    sem_ev = {
        "Revenue": ColumnSemanticEvidence("Revenue", ColumnRole.MEASURE, 0.95, "HIGH", []),
    }
    exec_res = _make_exec_result("p1", columns=["sum_Revenue"], row_count=1)

    plan = _make_plan(metric_col="Revenue", dimensions=[], visualization=VisualizationType.KPI)
    plan = plan.model_copy(update={"supporting_count": 3, "providers_responded": 3})

    # Coverage 0.2 < LOW_COVERAGE_CONFIDENCE_CAP (0.40)
    sb = compute_score(plan, exec_res, sem_ev, intent_tokens=[], coverage_override=0.2)
    assert sb.total <= LOW_COVERAGE_CONFIDENCE_CAP
    assert sb.total == LOW_COVERAGE_CONFIDENCE_CAP

    ranked, is_tie = rank_candidates(
        candidates=[(plan, exec_res)],
        semantic_evidences=sem_ev,
        intent_tokens=["completely", "unrelated", "tokens", "here", "xyz"],
    )
    assert is_tie is True


def test_compute_coverage_taxi_off_topic_not_inflated_by_intent():
    """Verify that off-topic request against taxi dataset yields near-zero coverage.

    _compute_coverage must not match tokens against plan.intent, which trivially contains itself.
    """
    from orchestrator.utils import _compute_coverage
    from orchestrator.config import LOW_COVERAGE_CONFIDENCE_CAP

    query = "Show total sales by category"
    tokens = query.lower().split()

    # Plan on yellow_tripdata with total_amount and payment_type
    plan = _make_plan(
        metric_col="total_amount",
        dimensions=[DimensionSpec(column="payment_type")],
        intent=query,
    )

    cov = _compute_coverage(plan, tokens)
    # 'sales' and 'category' do not appear in fields; coverage is <= 0.20 (only 'total' in 'total_amount')
    assert cov <= 0.20
    assert cov < LOW_COVERAGE_CONFIDENCE_CAP


def test_pass1a_rejects_malformed_gemini_filter_operator():
    """Verify that Pass 1a rejects malformed filter comparison operators like '====='.

    Uses the exact malformed operator produced by Gemini in real eval prompt 5:
    'WHERE StoreID ===== 101'.
    """
    from orchestrator.validator import validate_pass1a, is_plan_structurally_valid
    from intelligence.semantic_analyzer import DatasetSemanticProfile, ColumnSemanticEvidence, ColumnRole

    sem_profile = DatasetSemanticProfile(
        dataset_id="Sales_2024.csv",
        column_evidences={
            "TotalSales": ColumnSemanticEvidence(column_name="TotalSales", candidate_role=ColumnRole.MEASURE, confidence=0.95, confidence_level="HIGH"),
            "StoreID": ColumnSemanticEvidence(column_name="StoreID", candidate_role=ColumnRole.IDENTIFIER, confidence=0.90, confidence_level="HIGH"),
        },
    )

    malformed_plan = _make_plan(
        dataset_id="Sales_2024.csv",
        metric_col="TotalSales",
        dimensions=[],
        visualization=VisualizationType.KPI,
    ).model_copy(update={
        "filters": [FilterSpec(column="StoreID", operator="=====", value=101)],
    })

    # Structural check rejects it before dedup / agreement
    assert is_plan_structurally_valid(malformed_plan) is False

    # Pass 1a pre-dispatch check flags operator whitelist failure
    res = validate_pass1a(plan=malformed_plan, semantic_profile=sem_profile)
    assert res.passed is False
    assert any(i.check == "filter_operator_whitelist" for i in res.issues)


def test_agreement_incorporates_providers_responded_partial_response():
    """Verify that a solo 1-of-1 response scores lower agreement than full consensus.

    Reflects the Prompt 9/10 partial-response case where Gemini failed due to rate limits
    and only Groq responded. A solo response (1 of 1) must not achieve the same 1.0 agreement
    as unanimous consensus (3 of 3).
    """
    from intelligence.semantic_analyzer import ColumnSemanticEvidence, ColumnRole

    sem_ev = {
        "TotalSales": ColumnSemanticEvidence(column_name="TotalSales", candidate_role=ColumnRole.MEASURE, confidence=0.95, confidence_level="HIGH"),
        "StoreID": ColumnSemanticEvidence(column_name="StoreID", candidate_role=ColumnRole.IDENTIFIER, confidence=0.90, confidence_level="HIGH"),
    }
    exec_res = _make_exec_result("p1", columns=["sum_TotalSales"], row_count=1)

    plan_base = _make_plan(metric_col="TotalSales", dimensions=[DimensionSpec(column="StoreID")])

    # Unanimous consensus: 3 of 3 providers responded and agreed
    full_consensus_plan = plan_base.model_copy(update={"supporting_count": 3, "providers_responded": 3})
    sb_full = compute_score(full_consensus_plan, exec_res, sem_ev, intent_tokens=["totalsales", "storeid"], coverage_override=0.8)

    # Partial response (Prompt 9/10): only 1 provider responded (Gemini down)
    partial_plan = plan_base.model_copy(update={"supporting_count": 1, "providers_responded": 1})
    sb_partial = compute_score(partial_plan, exec_res, sem_ev, intent_tokens=["totalsales", "storeid"], coverage_override=0.8)

    # Solo response must have strictly lower agreement and lower total score than full consensus
    assert sb_partial.agreement < sb_full.agreement
    assert sb_partial.agreement == pytest.approx(1.0 * (1 / 3), rel=1e-3)
    assert sb_full.agreement == pytest.approx(1.0, rel=1e-3)
    assert sb_partial.total < sb_full.total
