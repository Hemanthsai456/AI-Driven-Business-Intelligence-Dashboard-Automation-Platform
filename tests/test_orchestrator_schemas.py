"""Stage 3 shape tests for orchestrator schemas, config, and Ranker V1 utilities.

Tests verify:
- All Pydantic models instantiate with valid data.
- Enum vocabularies match the architecture diagram and contracts.
- plan_signature() correctly deduplicates structurally identical plans.
- plan_signature() correctly differentiates materially different plans.
- Ranker V1 score formula is applied correctly.
- Candidate Output Consistency Check passes and fails as expected.
- RankerWeights model validator rejects negative weights.
- Config constants have expected types and sensible defaults.
"""

import pytest
from orchestrator.schemas import (
    AggregationType,
    AmbiguityDetail,
    AmbiguityResult,
    AmbiguityStatus,
    AmbiguityType,
    CandidatePlan,
    CandidateConsistencyCheck,
    ColumnContextEntry,
    ComparisonSpec,
    DashboardSpec,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    FilterSpec,
    Granularity,
    LLMContext,
    MetricSpec,
    OrchestratorTrace,
    Pass1aResult,
    Pass1bResult,
    Pass2Result,
    PlanReasoning,
    RankedCandidate,
    RankerWeights,
    ScoreBreakdown,
    ValidationIssue,
    ValidationStatus,
    VisualizationType,
)
from orchestrator import config
from orchestrator.utils import (
    check_candidate_output_consistency,
    compute_score,
    rank_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATASET_ID = "ds-test-001"
INTENT = "What is the total sales by month?"


def make_plan(
    metric_col: str = "TotalSales",
    aggregation: AggregationType = AggregationType.SUM,
    dim_col: str = "Date",
    granularity: Granularity = Granularity.MONTH,
    dataset_id: str = DATASET_ID,
    intent: str = INTENT,
    viz: VisualizationType = VisualizationType.BAR,
) -> CandidatePlan:
    return CandidatePlan(
        dataset_id=dataset_id,
        intent=intent,
        metric=MetricSpec(column=metric_col, aggregation=aggregation),
        dimensions=[DimensionSpec(column=dim_col, granularity=granularity)],
        visualization=viz,
        reasoning=PlanReasoning(
            interpretation="Aggregate total sales by month.",
            evidence=["TotalSales is a MEASURE (HIGH conf)", "Date is a DATETIME (HIGH conf)"],
        ),
    )


def make_execution_result(
    plan_id: str,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    row_count: int = 12,
    columns: list = None,
    failed_cast_count: int = 0,
    failed_cast_rate: float = 0.0,
) -> ExecutionResult:
    if columns is None:
        columns = ["Date", "TotalSales"]
    rows = [{c: i for c in columns} for i in range(row_count)]
    return ExecutionResult(
        plan_id=plan_id,
        status=status,
        rows=rows,
        columns=columns,
        row_count=row_count,
        compiled_sql="SELECT TRY_CAST(Date AS TIMESTAMP), SUM(TotalSales) FROM ds GROUP BY 1",
        failed_cast_count=failed_cast_count,
        failed_cast_rate=failed_cast_rate,
    )


MOCK_SEMANTIC_EVIDENCES = {
    "TotalSales": type("E", (), {"confidence": 0.92})(),
    "Date": type("E", (), {"confidence": 0.92})(),
    "Quantity": type("E", (), {"confidence": 0.88})(),
}


# ---------------------------------------------------------------------------
# Enum Vocabulary Tests
# ---------------------------------------------------------------------------


class TestEnumVocabulary:
    def test_aggregation_type_whitelist(self):
        """All whitelisted aggregation functions present."""
        expected = {"SUM", "AVG", "MIN", "MAX", "COUNT", "COUNT_DISTINCT", "STDDEV", "MEDIAN"}
        actual = {a.value for a in AggregationType}
        assert expected == actual

    def test_granularity_values(self):
        """Temporal granularities cover YEAR through HOUR."""
        expected = {"YEAR", "QUARTER", "MONTH", "WEEK", "DAY", "HOUR"}
        assert {g.value for g in Granularity} == expected

    def test_visualization_types(self):
        """Visualization types include BAR, LINE, TABLE, KPI, SCATTER, PIE, AREA, HEATMAP."""
        assert "BAR" in [v.value for v in VisualizationType]
        assert "TABLE" in [v.value for v in VisualizationType]
        assert "KPI" in [v.value for v in VisualizationType]

    def test_ambiguity_status_values(self):
        assert {s.value for s in AmbiguityStatus} == {"CLEAR", "AMBIGUOUS", "UNANSWERABLE"}

    def test_execution_status_values(self):
        statuses = {s.value for s in ExecutionStatus}
        assert "SUCCESS" in statuses
        assert "TIMEOUT" in statuses
        assert "SYNTAX_ERROR" in statuses


# ---------------------------------------------------------------------------
# CandidatePlan Shape Tests
# ---------------------------------------------------------------------------


class TestCandidatePlanShape:
    def test_minimal_plan_instantiation(self):
        plan = make_plan()
        assert plan.dataset_id == DATASET_ID
        assert plan.intent == INTENT
        assert plan.metric.column == "TotalSales"
        assert plan.metric.aggregation == AggregationType.SUM
        assert len(plan.dimensions) == 1
        assert plan.dimensions[0].granularity == Granularity.MONTH
        assert plan.plan_id is not None

    def test_plan_with_filters(self):
        plan = CandidatePlan(
            dataset_id=DATASET_ID,
            intent=INTENT,
            metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
            dimensions=[DimensionSpec(column="Date", granularity=Granularity.MONTH)],
            filters=[FilterSpec(column="Region", operator="=", value="East")],
            visualization=VisualizationType.LINE,
            reasoning=PlanReasoning(interpretation="Sales by month for East region."),
        )
        assert len(plan.filters) == 1
        assert plan.filters[0].column == "Region"

    def test_plan_with_comparison(self):
        plan = CandidatePlan(
            dataset_id=DATASET_ID,
            intent="Sales YoY comparison",
            metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
            dimensions=[DimensionSpec(column="Date", granularity=Granularity.YEAR)],
            comparison=ComparisonSpec(compare_to="previous year", column="Date", value="2023"),
            visualization=VisualizationType.BAR,
            reasoning=PlanReasoning(interpretation="Year-over-year sales."),
        )
        assert plan.comparison is not None
        assert plan.comparison.compare_to == "previous year"

    def test_plan_is_immutable(self):
        plan = make_plan()
        with pytest.raises(Exception):
            plan.intent = "mutated"  # frozen model


# ---------------------------------------------------------------------------
# plan_signature() Deduplication Tests
# ---------------------------------------------------------------------------


class TestPlanSignature:
    def test_identical_plans_have_same_signature(self):
        plan_a = make_plan()
        plan_b = make_plan()
        assert plan_a.plan_signature() == plan_b.plan_signature()

    def test_different_metric_column_different_signature(self):
        plan_a = make_plan(metric_col="TotalSales")
        plan_b = make_plan(metric_col="Quantity")
        assert plan_a.plan_signature() != plan_b.plan_signature()

    def test_different_aggregation_different_signature(self):
        plan_a = make_plan(aggregation=AggregationType.SUM)
        plan_b = make_plan(aggregation=AggregationType.AVG)
        assert plan_a.plan_signature() != plan_b.plan_signature()

    def test_different_granularity_different_signature(self):
        plan_a = make_plan(granularity=Granularity.MONTH)
        plan_b = make_plan(granularity=Granularity.QUARTER)
        assert plan_a.plan_signature() != plan_b.plan_signature()

    def test_different_dataset_different_signature(self):
        plan_a = make_plan(dataset_id="ds-001")
        plan_b = make_plan(dataset_id="ds-002")
        assert plan_a.plan_signature() != plan_b.plan_signature()

    def test_visualization_does_not_affect_signature(self):
        """Visualization type is not part of the structural signature."""
        plan_a = make_plan(viz=VisualizationType.BAR)
        plan_b = make_plan(viz=VisualizationType.LINE)
        assert plan_a.plan_signature() == plan_b.plan_signature()

    def test_signature_is_deterministic(self):
        plan = make_plan()
        sig1 = plan.plan_signature()
        sig2 = plan.plan_signature()
        assert sig1 == sig2

    def test_signature_is_sha256_hex(self):
        plan = make_plan()
        sig = plan.plan_signature()
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)


# ---------------------------------------------------------------------------
# AmbiguityResult Shape Tests
# ---------------------------------------------------------------------------


class TestAmbiguityResultShape:
    def test_clear_result(self):
        result = AmbiguityResult(status=AmbiguityStatus.CLEAR)
        assert result.status == AmbiguityStatus.CLEAR
        assert result.ambiguities == []

    def test_ambiguous_result_with_details(self):
        result = AmbiguityResult(
            status=AmbiguityStatus.AMBIGUOUS,
            ambiguities=[
                AmbiguityDetail(
                    type=AmbiguityType.MULTIPLE_MEASURES,
                    field="metric",
                    alternatives=["TotalSales", "Quantity"],
                )
            ],
            message="Multiple measure candidates found.",
        )
        assert result.status == AmbiguityStatus.AMBIGUOUS
        assert len(result.ambiguities) == 1
        assert result.ambiguities[0].type == AmbiguityType.MULTIPLE_MEASURES

    def test_unanswerable_result(self):
        result = AmbiguityResult(
            status=AmbiguityStatus.UNANSWERABLE,
            ambiguities=[
                AmbiguityDetail(
                    type=AmbiguityType.MISSING_COLUMN,
                    field="Revenue",
                    alternatives=[],
                )
            ],
            message="Column 'Revenue' does not exist in the dataset.",
        )
        assert result.status == AmbiguityStatus.UNANSWERABLE


# ---------------------------------------------------------------------------
# LLMContext Shape Tests
# ---------------------------------------------------------------------------


class TestLLMContextShape:
    def test_context_instantiation(self):
        ctx = LLMContext(
            dataset_id=DATASET_ID,
            intent=INTENT,
            columns=[
                ColumnContextEntry(
                    column_name="TotalSales",
                    candidate_role="MEASURE",
                    confidence=0.92,
                    confidence_level="HIGH",
                    evidence=["numeric dtype", "name indicator 'totalsales'"],
                    distinct_count=21,
                    null_percentage=0.0,
                    dtype="int64",
                )
            ],
            context_hash=LLMContext.compute_hash(DATASET_ID, INTENT, ["TotalSales"]),
        )
        assert ctx.dataset_id == DATASET_ID
        assert len(ctx.columns) == 1
        assert len(ctx.context_hash) == 64

    def test_context_hash_deterministic(self):
        h1 = LLMContext.compute_hash(DATASET_ID, INTENT, ["TotalSales", "Date"])
        h2 = LLMContext.compute_hash(DATASET_ID, INTENT, ["Date", "TotalSales"])
        assert h1 == h2  # sorted internally


# ---------------------------------------------------------------------------
# ExecutionResult Shape Tests
# ---------------------------------------------------------------------------


class TestExecutionResultShape:
    def test_success_result(self):
        plan = make_plan()
        result = make_execution_result(plan.plan_id)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.row_count == 12
        assert result.failed_cast_count == 0

    def test_timeout_result(self):
        result = ExecutionResult(
            plan_id="p1",
            status=ExecutionStatus.TIMEOUT,
            error_message="Query exceeded 30s timeout.",
        )
        assert result.status == ExecutionStatus.TIMEOUT
        assert result.row_count == 0

    def test_failed_cast_tracking(self):
        plan = make_plan()
        result = make_execution_result(
            plan.plan_id,
            failed_cast_count=50,
            failed_cast_rate=0.10,
        )
        assert result.failed_cast_count == 50
        assert result.failed_cast_rate == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Ranker V1 Tests
# ---------------------------------------------------------------------------


class TestRankerV1:
    def test_score_returns_score_breakdown(self):
        plan = make_plan()
        result = make_execution_result(plan.plan_id)
        sb = compute_score(plan, result, MOCK_SEMANTIC_EVIDENCES, ["total", "sales", "month"])
        assert 0.0 <= sb.total <= 1.0
        assert 0.0 <= sb.evidence <= 1.0
        assert 0.0 <= sb.coverage <= 1.0
        assert 0.0 <= sb.stability <= 1.0
        assert 0.0 <= sb.assumptions <= 1.0

    def test_high_confidence_columns_increase_evidence(self):
        plan = make_plan()
        result = make_execution_result(plan.plan_id)
        high_conf = {"TotalSales": type("E", (), {"confidence": 1.0})(),
                     "Date": type("E", (), {"confidence": 1.0})()}
        low_conf = {"TotalSales": type("E", (), {"confidence": 0.1})(),
                    "Date": type("E", (), {"confidence": 0.1})()}
        sb_high = compute_score(plan, result, high_conf, ["total", "sales"])
        sb_low = compute_score(plan, result, low_conf, ["total", "sales"])
        assert sb_high.evidence > sb_low.evidence
        assert sb_high.total > sb_low.total

    def test_failed_cast_rate_reduces_stability(self):
        plan = make_plan()
        clean = make_execution_result(plan.plan_id, failed_cast_rate=0.0)
        dirty = make_execution_result(plan.plan_id, failed_cast_rate=0.8)
        sb_clean = compute_score(plan, clean, MOCK_SEMANTIC_EVIDENCES, ["total", "sales"])
        sb_dirty = compute_score(plan, dirty, MOCK_SEMANTIC_EVIDENCES, ["total", "sales"])
        assert sb_clean.stability > sb_dirty.stability

    def test_timeout_gives_zero_stability(self):
        plan = make_plan()
        result = ExecutionResult(
            plan_id=plan.plan_id,
            status=ExecutionStatus.TIMEOUT,
            error_message="Timeout.",
        )
        sb = compute_score(plan, result, MOCK_SEMANTIC_EVIDENCES, ["total", "sales"])
        assert sb.stability == 0.0

    def test_rank_candidates_sorted_by_score(self):
        plan_a = make_plan(metric_col="TotalSales", aggregation=AggregationType.SUM)
        plan_b = make_plan(metric_col="Quantity", aggregation=AggregationType.SUM)
        result_a = make_execution_result(plan_a.plan_id, row_count=12, failed_cast_rate=0.0)
        result_b = make_execution_result(plan_b.plan_id, row_count=12, failed_cast_rate=0.5)
        candidates = [(plan_a, result_a), (plan_b, result_b)]
        ranked, _ = rank_candidates(candidates, MOCK_SEMANTIC_EVIDENCES, ["total", "sales"])
        assert len(ranked) == 2
        # First should have higher or equal score
        assert ranked[0][2].total >= ranked[1][2].total

    def test_tie_detection_within_epsilon(self):
        """Two identical plans on identical results should be detected as ties."""
        plan_a = make_plan(viz=VisualizationType.BAR)
        plan_b = make_plan(viz=VisualizationType.LINE)
        result_a = make_execution_result(plan_a.plan_id)
        result_b = make_execution_result(plan_b.plan_id)
        candidates = [(plan_a, result_a), (plan_b, result_b)]
        ranked, is_tie = rank_candidates(candidates, MOCK_SEMANTIC_EVIDENCES, ["total", "sales", "month"])
        assert is_tie  # identical score => tie

    def test_empty_candidates_returns_empty(self):
        ranked, is_tie = rank_candidates([], MOCK_SEMANTIC_EVIDENCES, [])
        assert ranked == []
        assert is_tie is False

    def test_single_candidate_no_tie(self):
        plan = make_plan()
        result = make_execution_result(plan.plan_id)
        ranked, is_tie = rank_candidates([(plan, result)], MOCK_SEMANTIC_EVIDENCES, ["total"])
        assert len(ranked) == 1
        assert is_tie is False

    def test_ranker_weights_rejects_negative(self):
        with pytest.raises(Exception):
            RankerWeights(w1_evidence=-0.1, w2_coverage=0.3, w3_stability=0.2, w4_assumptions=0.15)

    def test_custom_weights_applied(self):
        """Custom weights that heavily penalise assumptions should lower score for assumption-heavy plan."""
        plan = make_plan(viz=VisualizationType.TABLE)  # TABLE defaults = more assumptions
        result = make_execution_result(plan.plan_id)
        weights_heavy_penalty = RankerWeights(
            w1_evidence=0.1,
            w2_coverage=0.1,
            w3_stability=0.1,
            w4_assumptions=0.9,  # heavy assumption penalty
        )
        weights_light_penalty = RankerWeights(
            w1_evidence=0.35,
            w2_coverage=0.30,
            w3_stability=0.20,
            w4_assumptions=0.0,  # no assumption penalty
        )
        sb_heavy = compute_score(plan, result, MOCK_SEMANTIC_EVIDENCES, ["total"], weights_heavy_penalty)
        sb_light = compute_score(plan, result, MOCK_SEMANTIC_EVIDENCES, ["total"], weights_light_penalty)
        assert sb_light.total > sb_heavy.total


# ---------------------------------------------------------------------------
# Candidate Output Consistency Check Tests
# ---------------------------------------------------------------------------


class TestCandidateOutputConsistencyCheck:
    def test_single_candidate_always_passes(self):
        plan = make_plan()
        result = make_execution_result(plan.plan_id)
        check = check_candidate_output_consistency([(plan, result)])
        assert check.passed is True
        assert check.mismatches == []

    def test_empty_candidates_passes(self):
        check = check_candidate_output_consistency([])
        assert check.passed is True

    def test_consistent_candidates_pass(self):
        plan_a = make_plan(viz=VisualizationType.BAR)
        plan_b = make_plan(viz=VisualizationType.LINE)
        result_a = make_execution_result(plan_a.plan_id, columns=["Date", "TotalSales"])
        result_b = make_execution_result(plan_b.plan_id, columns=["Date", "TotalSales"])
        check = check_candidate_output_consistency([(plan_a, result_a), (plan_b, result_b)])
        assert check.passed is True

    def test_different_metric_columns_fail(self):
        plan_a = make_plan(metric_col="TotalSales")
        plan_b = make_plan(metric_col="Quantity")
        result_a = make_execution_result(plan_a.plan_id, columns=["Date", "TotalSales"])
        result_b = make_execution_result(plan_b.plan_id, columns=["Date", "Quantity"])
        check = check_candidate_output_consistency([(plan_a, result_a), (plan_b, result_b)])
        assert check.passed is False
        assert any("metric column" in m for m in check.mismatches)

    def test_different_granularities_fail(self):
        plan_a = make_plan(granularity=Granularity.MONTH)
        plan_b = make_plan(granularity=Granularity.QUARTER)
        result_a = make_execution_result(plan_a.plan_id, columns=["Date", "TotalSales"])
        result_b = make_execution_result(plan_b.plan_id, columns=["Date", "TotalSales"])
        check = check_candidate_output_consistency([(plan_a, result_a), (plan_b, result_b)])
        assert check.passed is False
        assert any("granularity" in m for m in check.mismatches)

    def test_different_output_schemas_fail(self):
        plan_a = make_plan()
        plan_b = make_plan()
        result_a = make_execution_result(plan_a.plan_id, columns=["Date", "TotalSales"])
        result_b = make_execution_result(plan_b.plan_id, columns=["Month", "TotalSales", "Region"])
        check = check_candidate_output_consistency([(plan_a, result_a), (plan_b, result_b)])
        assert check.passed is False
        assert any("columns" in m or "output" in m for m in check.mismatches)


# ---------------------------------------------------------------------------
# Config Constants Tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_max_k_is_3(self):
        assert config.MAX_K == 3

    def test_ai_max_retries_is_1(self):
        assert config.AI_MAX_RETRIES == 1

    def test_pass1_reprompt_max_positive(self):
        assert config.PASS1_REPROMPT_MAX > 0

    def test_max_cascade_depth_positive(self):
        assert config.MAX_CASCADE_DEPTH > 0

    def test_rank_tie_epsilon_small_positive(self):
        assert 0.0 < config.RANK_TIE_EPSILON < 0.5

    def test_weights_are_floats(self):
        for attr in ("RANK_W1_EVIDENCE", "RANK_W2_COVERAGE", "RANK_W3_STABILITY", "RANK_W4_ASSUMPTIONS"):
            assert isinstance(getattr(config, attr), float)

    def test_result_row_cap_positive(self):
        assert config.RESULT_ROW_CAP > 0

    def test_failed_cast_threshold_between_0_and_1(self):
        assert 0.0 < config.FAILED_CAST_RATE_THRESHOLD <= 1.0

    def test_duckdb_timeout_positive(self):
        assert config.DUCKDB_TIMEOUT_SECONDS > 0.0

    def test_duckdb_memory_limit_string(self):
        assert isinstance(config.DUCKDB_MEMORY_LIMIT, str)
        assert "MB" in config.DUCKDB_MEMORY_LIMIT or "GB" in config.DUCKDB_MEMORY_LIMIT


# ---------------------------------------------------------------------------
# Pass 1a / 1b / 2 Shape Tests
# ---------------------------------------------------------------------------


class TestValidationSchemas:
    def test_pass1a_passed(self):
        result = Pass1aResult(plan_id="p1", passed=True, issues=[])
        assert result.passed is True

    def test_pass1a_failed_with_issues(self):
        result = Pass1aResult(
            plan_id="p1",
            passed=False,
            issues=[
                ValidationIssue(
                    check="column_exists",
                    status=ValidationStatus.FAILED,
                    message="Column 'Revenue' not found in DatasetSemanticProfile.",
                    column="Revenue",
                )
            ],
        )
        assert result.passed is False
        assert result.issues[0].check == "column_exists"

    def test_pass2_cascade_flag(self):
        result = Pass2Result(plan_id="p1", passed=False, cascade_triggered=True)
        assert result.cascade_triggered is True


# ---------------------------------------------------------------------------
# DashboardSpec Shape Test
# ---------------------------------------------------------------------------


class TestDashboardSpecShape:
    def test_dashboard_spec_instantiation(self):
        plan = make_plan()
        execution_result = make_execution_result(plan.plan_id)
        sb = compute_score(plan, execution_result, MOCK_SEMANTIC_EVIDENCES, ["total", "sales"])
        ranked_candidate = RankedCandidate(
            plan=plan,
            execution_result=execution_result,
            pass1a=Pass1aResult(plan_id=plan.plan_id, passed=True),
            pass1b=Pass1bResult(plan_id=plan.plan_id, passed=True),
            score_breakdown=sb,
            rank=1,
            is_winner=True,
        )
        trace = OrchestratorTrace(
            dataset_id=DATASET_ID,
            intent=INTENT,
            context_hash=LLMContext.compute_hash(DATASET_ID, INTENT, ["TotalSales"]),
            plans_generated=1,
            plans_passed_pass1a=1,
            plans_passed_pass1b=1,
        )
        spec = DashboardSpec(
            dataset_id=DATASET_ID,
            intent=INTENT,
            winner=ranked_candidate,
            trace=trace,
        )
        assert spec.winner.is_winner is True
        assert spec.alternate_interpretations == []
        assert spec.is_tie is False
        assert len(spec.spec_id) > 0
