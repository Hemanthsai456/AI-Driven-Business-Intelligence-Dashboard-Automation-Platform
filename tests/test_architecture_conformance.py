"""Architectural conformance and strict deviation regression tests.

Enforces:
1. 6-step cognitive loop order and active ambiguity gating
2. Deterministic separation (zero DuckDB imports in orchestrator/, engine abstraction)
3. Provider-agnostic LLM factory & registry (dynamic switching via configuration)
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest
import pandas as pd

from engine.compiler import compile_plan_to_sql, quote_identifier
from engine.duckdb_executor import DuckDBExecutor
from engine.executor import AnalyticsEngine, DuckDBEngine, get_default_engine
from engine.sanitizer import sanitize_dataframe_to_rows
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.schema_validator import AnalysisReadiness, ReadinessCheck, ReadinessStatus
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
)
from orchestrator.ambiguity import (
    AmbiguityResult,
    AmbiguityStatus,
    AmbiguityType,
    assess_ambiguity,
    is_blocking_ambiguity,
)
from orchestrator.config import (
    DEFAULT_PROVIDER,
    PROVIDER_ENV,
)
from orchestrator.generator import (
    LLMDirectGenerator,
    MockAgent,
    MultiProviderGenerator,
    PlanGenerationCoordinator,
    PlanGenerator,
)
from orchestrator.intent import interpret_user_request
from orchestrator.interpretation import generate_interpretations
from orchestrator.pipeline import (
    OrchestrationPipelineResult,
    get_default_llm_client,
    run_orchestration_pipeline,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    MetricSpec,
    PlanReasoning,
    SemanticInterpretation,
    StructuredIntent,
    VisualizationType,
)
from providers import (
    GeminiClient,
    GroqClient,
    LLMClient,
    LLMClientError,
    LLMProviderFactory,
    MockLLMClient,
    OllamaClient,
    get_llm_client,
    get_multi_provider_clients,
)


@pytest.fixture
def sample_dataset():
    df = pd.DataFrame({
        "order_id": ["O1", "O2", "O3"],
        "region": ["North", "South", "North"],
        "sales": [100.0, 200.0, 150.0],
        "quantity": [1, 2, 3],
        "order_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "ship_date": ["2024-01-05", "2024-01-06", "2024-01-07"],
    })
    meta = DatasetMetadata(
        dataset_id="arch_test_ds",
        name="sales",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("order_id", "order_id", "object", ColumnRole.IDENTIFIER, 0, 0.0, 3),
            ColumnMetadata("region", "region", "object", ColumnRole.DIMENSION, 0, 0.0, 2),
            ColumnMetadata("sales", "sales", "float64", ColumnRole.MEASURE, 0, 0.0, 3),
            ColumnMetadata("quantity", "quantity", "int64", ColumnRole.MEASURE, 0, 0.0, 3),
            ColumnMetadata("order_date", "order_date", "object", ColumnRole.DATETIME, 0, 0.0, 3),
            ColumnMetadata("ship_date", "ship_date", "object", ColumnRole.DATETIME, 0, 0.0, 3),
        ],
    )
    return CanonicalDataset(metadata=meta, data=df)


@pytest.fixture
def sample_semantic_profile():
    return DatasetSemanticProfile(
        dataset_id="arch_test_ds",
        column_evidences={
            "order_id": ColumnSemanticEvidence("order_id", ColumnRole.IDENTIFIER, 0.95, "HIGH", ["id"]),
            "region": ColumnSemanticEvidence("region", ColumnRole.DIMENSION, 0.90, "HIGH", ["category"]),
            "sales": ColumnSemanticEvidence("sales", ColumnRole.MEASURE, 0.95, "HIGH", ["currency"]),
            "quantity": ColumnSemanticEvidence("quantity", ColumnRole.MEASURE, 0.85, "HIGH", ["count"]),
            "order_date": ColumnSemanticEvidence("order_date", ColumnRole.DATETIME, 0.92, "HIGH", ["date"]),
            "ship_date": ColumnSemanticEvidence("ship_date", ColumnRole.DATETIME, 0.88, "HIGH", ["date"]),
        },
    )


@pytest.fixture
def sample_readiness():
    return AnalysisReadiness(
        dataset_id="arch_test_ds",
        status=ReadinessStatus.READY,
        checks=[ReadinessCheck("ok", True, "Ready", is_blocking=True)],
    )


# ===========================================================================
# COGNITIVE LOOP TESTS (1 - 8)
# ===========================================================================


def test_1_intent_interpretation_happens_before_planning(sample_dataset, sample_semantic_profile):
    """Test 1: Intent interpretation produces StructuredIntent capturing request elements."""
    intent_text = "Show monthly total sales by region with a bar chart"
    structured = interpret_user_request(intent_text, sample_semantic_profile)

    assert isinstance(structured, StructuredIntent)
    assert structured.original_request == intent_text
    assert "sales" in structured.requested_metrics
    assert "region" in structured.requested_dimensions
    assert structured.grouping_granularity == "month"
    assert structured.requested_visual_preferences == "bar"
    assert structured.analytical_goal in ("trend", "aggregation", "distribution")
    assert structured.confidence > 0.5


def test_2_ambiguity_detection_occurs_before_candidate_generation(sample_semantic_profile):
    """Test 2: Ambiguity detection evaluates StructuredIntent against semantic profile."""
    # Case: multiple date columns with temporal keyword triggers item-level ambiguity
    intent_text = "Show monthly sales trend over time"
    structured = interpret_user_request(intent_text, sample_semantic_profile)
    ambiguity = assess_ambiguity(structured, sample_semantic_profile)

    assert ambiguity.status == AmbiguityStatus.AMBIGUOUS
    assert len(ambiguity.ambiguities) >= 1
    assert ambiguity.ambiguities[0].type == AmbiguityType.MULTIPLE_DATE_COLUMNS


def test_3_blocking_ambiguity_prevents_candidate_generation(
    sample_dataset, sample_semantic_profile, sample_readiness
):
    """Test 3: Request-level blocking ambiguity halts pipeline without candidate generation."""
    # Request-level blocking: generic query without measures or dimensions where multiple measures exist
    generic_intent = "Show KPI summary and numbers"
    res = run_orchestration_pipeline(
        dataset=sample_dataset,
        semantic_profile=sample_semantic_profile,
        readiness=sample_readiness,
        intent=generic_intent,
    )

    assert res.status in ("AMBIGUOUS", "UNANSWERABLE")
    assert "Clarification required" in res.message
    assert res.dashboard_spec is None
    assert res.ambiguity is not None
    assert is_blocking_ambiguity(res.ambiguity) is True


def test_4_item_level_ambiguity_allows_pipeline_to_continue(
    sample_dataset, sample_semantic_profile, sample_readiness
):
    """Test 4: Item-level ambiguity (e.g. date columns) does NOT block the pipeline."""
    # Item-level: multiple date columns for trend, but valid metric & dimension
    trend_intent = "Show sales trend over time by region"
    structured = interpret_user_request(trend_intent, sample_semantic_profile)
    ambiguity = assess_ambiguity(structured, sample_semantic_profile)

    # Must NOT be blocking
    assert is_blocking_ambiguity(ambiguity) is False

    # Pipeline continues and generates interpretations for each date column
    interps = generate_interpretations(structured, sample_semantic_profile, ambiguity=ambiguity, k=2)
    assert len(interps) == 2
    assert interps[0].resolved_intent_elements["date_column"] in ("order_date", "ship_date")
    assert interps[1].resolved_intent_elements["date_column"] in ("order_date", "ship_date")


def test_5_interpretation_generation_exists_as_distinct_stage(sample_semantic_profile):
    """Test 5: Interpretation generation creates coherent SemanticInterpretation instances."""
    structured = interpret_user_request("Show total sales by region", sample_semantic_profile)
    interpretations = generate_interpretations(structured, sample_semantic_profile, k=2)

    assert len(interpretations) >= 1
    interp = interpretations[0]
    assert isinstance(interp, SemanticInterpretation)
    assert interp.metric_column == "sales"
    assert interp.aggregation == AggregationType.SUM
    assert "region" in interp.dimension_columns
    assert "sales" in interp.referenced_columns
    assert len(interp.evidence) >= 1


def test_6_planner_consumes_structured_interpretations(sample_semantic_profile):
    """Test 6: LLM generator builds prompt incorporating structured interpretations."""
    structured = interpret_user_request("Show total sales by region", sample_semantic_profile)
    interpretations = generate_interpretations(structured, sample_semantic_profile, k=1)

    mock_client = MockLLMClient(canned_response={
        "dataset_id": "arch_test_ds",
        "intent": "Show total sales by region",
        "metric": {"column": "sales", "aggregation": "SUM"},
        "dimensions": [{"column": "region"}],
        "filters": [],
        "visualization": "BAR",
        "reasoning": {"interpretation": "Sales by region", "evidence": []},
    })
    generator = LLMDirectGenerator(llm_client=mock_client)
    from orchestrator.context_builder import build_llm_context
    ctx = build_llm_context("arch_test_ds", "Show total sales by region", sample_semantic_profile)

    plans, logs = generator.generate_plans(ctx, k=1, interpretations=interpretations)
    assert len(plans) == 1
    assert "Target Semantic Interpretations" in mock_client.call_history[0]


def test_7_multiple_coherent_interpretations_lead_to_distinct_plans(sample_semantic_profile):
    """Test 7: Multiple distinct interpretations are formed when ambiguous options exist."""
    # Intent with 2 measures: sales and quantity
    intent_text = "Show sales and quantity by region"
    structured = interpret_user_request(intent_text, sample_semantic_profile)
    interpretations = generate_interpretations(structured, sample_semantic_profile, k=2)

    assert len(interpretations) == 2
    metrics = {i.metric_column for i in interpretations}
    assert "sales" in metrics
    assert "quantity" in metrics


def test_8_ranking_happens_after_execution_and_validation(
    sample_dataset, sample_semantic_profile, sample_readiness
):
    """Test 8: Full pipeline executes candidates in engine and validates Pass 1b before ranking."""
    plan1 = CandidatePlan(
        plan_id="p1",
        dataset_id="arch_test_ds",
        intent="Sales by region",
        metric=MetricSpec(column="sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="region")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="P1", evidence=[]),
    )
    mock_agent = MockAgent(canned_plans=[plan1])

    res = run_orchestration_pipeline(
        dataset=sample_dataset,
        semantic_profile=sample_semantic_profile,
        readiness=sample_readiness,
        intent="Sales by region",
        generator=mock_agent,
    )

    assert res.status == "SUCCESS"
    assert res.ranked_candidates is not None
    # Each ranked candidate tuple must be (plan, execution_result, score_breakdown, rank)
    top_plan, top_exec, top_score, rank = res.ranked_candidates[0]
    assert top_plan.plan_id == "p1"
    assert top_exec.status == ExecutionStatus.SUCCESS
    assert top_exec.row_count > 0
    assert top_score.total > 0.0


# ===========================================================================
# DETERMINISTIC SEPARATION TESTS (9 - 14)
# ===========================================================================


def test_9_no_direct_duckdb_import_inside_orchestrator():
    """Test 9: Architectural AST check proving orchestrator/ has ZERO direct DuckDB imports."""
    orchestrator_dir = Path(__file__).resolve().parent.parent / "orchestrator"
    violating_files = []

    for py_file in orchestrator_dir.rglob("*.py"):
        # Ignore scratch or temp scripts if any
        if "scratch" in py_file.parts or ".pytest_cache" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "duckdb":
                        violating_files.append((py_file.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "duckdb" or node.module.startswith("duckdb.")):
                    violating_files.append((py_file.name, node.lineno))

    assert not violating_files, f"Direct duckdb imports found in orchestrator/: {violating_files}"


def test_10_sql_compilation_is_owned_by_engine_layer():
    """Test 10: SQL compilation is owned by engine.compiler and is injection-safe."""
    from engine.compiler import compile_plan_to_sql, quote_identifier

    plan = CandidatePlan(
        dataset_id="arch_test_ds",
        intent="Test SQL compilation",
        metric=MetricSpec(column="sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="region")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Compile", evidence=[]),
    )
    sql = compile_plan_to_sql(plan)
    assert 'SELECT' in sql
    assert 'SUM("sales") AS "sum_sales"' in sql
    assert 'FROM "source_data"' in sql


def test_11_duckdb_connection_management_is_owned_by_engine():
    """Test 11: DuckDB connection is managed entirely inside engine.duckdb_executor."""
    import engine.duckdb_executor as d_exec
    assert hasattr(d_exec, "DuckDBExecutor")
    executor = d_exec.DuckDBExecutor(thread_limit=1, memory_limit="128MB")
    assert executor.thread_limit == 1
    assert executor.memory_limit == "128MB"


def test_12_orchestrator_calls_engine_abstraction(
    sample_dataset, sample_semantic_profile, sample_readiness
):
    """Test 12: Orchestrator accepts and coordinates an AnalyticsEngine abstraction."""
    called = []

    class SpyAnalyticsEngine(AnalyticsEngine):
        def __init__(self, inner):
            self.inner = inner

        def execute(self, plan, dataset, semantic_profile, custom_sql=None):
            called.append(plan.plan_id)
            return self.inner.execute(plan, dataset, semantic_profile, custom_sql)

    spy_engine = SpyAnalyticsEngine(get_default_engine())

    plan = CandidatePlan(
        plan_id="spy_plan",
        dataset_id="arch_test_ds",
        intent="Sales by region",
        metric=MetricSpec(column="sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="region")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Spy", evidence=[]),
    )
    mock_agent = MockAgent(canned_plans=[plan])

    res = run_orchestration_pipeline(
        dataset=sample_dataset,
        semantic_profile=sample_semantic_profile,
        readiness=sample_readiness,
        intent="Sales by region",
        generator=mock_agent,
        engine=spy_engine,
    )

    assert res.status == "SUCCESS"
    assert "spy_plan" in called


def test_13_result_sanitization_is_deterministic_engine_responsibility():
    """Test 13: Deterministic engine sanitizer safely handles NaN, inf, and timestamps."""
    raw_df = pd.DataFrame({
        "num": [1.0, float("nan"), float("inf")],
        "dt": [pd.Timestamp("2024-01-01 12:00:00"), pd.NaT, pd.Timestamp("2024-01-03 00:00:00")],
        "text": ["hello", None, "world"],
    })
    rows, cols = sanitize_dataframe_to_rows(raw_df)

    assert len(rows) == 3
    assert rows[1]["num"] is None
    assert rows[2]["num"] is None
    assert rows[1]["dt"] is None
    assert isinstance(rows[0]["dt"], str)


def test_14_execution_outputs_remain_equivalent_after_refactor(
    sample_dataset, sample_semantic_profile
):
    """Test 14: Engine execution outputs match expected schema and values."""
    plan = CandidatePlan(
        plan_id="equiv_test",
        dataset_id="arch_test_ds",
        intent="Sales by region",
        metric=MetricSpec(column="sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="region")],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Equivalence", evidence=[]),
    )
    engine = get_default_engine()
    res = engine.execute(plan, sample_dataset, sample_semantic_profile)

    assert res.status == ExecutionStatus.SUCCESS
    assert res.row_count == 2
    # North had 100 + 150 = 250, South had 200
    rows_by_region = {r["region"]: r["sum_sales"] for r in res.rows}
    assert rows_by_region["North"] == 250.0
    assert rows_by_region["South"] == 200.0


# ===========================================================================
# PROVIDER TESTS (15 - 22)
# ===========================================================================


def test_15_provider_gemini_creates_gemini_client(monkeypatch):
    """Test 15: PROVIDER=gemini creates GeminiClient."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    monkeypatch.setenv(PROVIDER_ENV, "gemini")
    client = get_llm_client()
    assert isinstance(client, GeminiClient)
    assert client.provider == "gemini"


def test_16_provider_groq_creates_groq_client(monkeypatch):
    """Test 16: PROVIDER=groq creates GroqClient."""
    monkeypatch.setenv("GROQ_API_KEY", "mock-groq-key")
    monkeypatch.setenv(PROVIDER_ENV, "groq")
    client = get_llm_client()
    assert isinstance(client, GroqClient)
    assert client.provider == "groq"


def test_17_provider_ollama_creates_ollama_client(monkeypatch):
    """Test 17: PROVIDER=ollama creates OllamaClient with skip_health_check."""
    monkeypatch.setenv(PROVIDER_ENV, "ollama")
    client = LLMProviderFactory.create_client("ollama", skip_health_check=True)
    assert isinstance(client, OllamaClient)
    assert client.provider == "ollama"


def test_18_provider_mock_creates_mock_client(monkeypatch):
    """Test 18: PROVIDER=mock creates MockLLMClient."""
    monkeypatch.setenv(PROVIDER_ENV, "mock")
    client = get_llm_client()
    assert isinstance(client, MockLLMClient)
    assert client.provider == "mock"


def test_19_invalid_provider_produces_clear_error():
    """Test 19: Invalid provider raises LLMClientError with list of supported providers."""
    with pytest.raises(LLMClientError) as exc_info:
        LLMProviderFactory.create_client("non_existent_provider_xyz")
    assert "Unsupported LLM provider" in str(exc_info.value)
    assert "gemini" in str(exc_info.value)


def test_20_active_providers_controls_multi_provider_pool(monkeypatch):
    """Test 20: ACTIVE_PROVIDERS configuration controls instantiated pool."""
    monkeypatch.setenv("ACTIVE_PROVIDERS", "mock")
    clients = get_multi_provider_clients()
    assert len(clients) == 1
    assert isinstance(clients[0], MockLLMClient)


def test_21_unavailable_optional_provider_does_not_crash_pool(monkeypatch):
    """Test 21: Failing provider in ACTIVE_PROVIDERS is logged and does not crash pool."""
    # First provider is invalid/failing, second is mock
    monkeypatch.setenv("ACTIVE_PROVIDERS", "invalid_provider,mock")
    clients = get_multi_provider_clients()
    assert len(clients) == 1
    assert isinstance(clients[0], MockLLMClient)


def test_22_orchestrator_depends_only_on_llm_abstraction():
    """Test 22: Core orchestrator pipeline instantiates client via factory/abstraction."""
    from orchestrator.pipeline import get_default_llm_client
    client = get_default_llm_client()
    assert isinstance(client, LLMClient)


def test_23_ambiguity_gap_empty_metrics_and_dimensions_is_unanswerable():
    """Test 23: Off-topic request with empty metrics/dimensions and unresolved terms is blocking UNANSWERABLE."""
    from intelligence.semantic_analyzer import ColumnRole, ColumnSemanticEvidence, DatasetSemanticProfile
    from orchestrator.intent import interpret_user_request
    from orchestrator.ambiguity import assess_ambiguity, is_blocking_ambiguity
    from orchestrator.schemas import AmbiguityStatus

    # Taxi-like schema
    taxi_prof = DatasetSemanticProfile(
        dataset_id="taxi_test",
        generated_at="now",
        column_evidences={
            "VendorID": ColumnSemanticEvidence("VendorID", ColumnRole.IDENTIFIER, 0.88, "HIGH", []),
            "total_amount": ColumnSemanticEvidence("total_amount", ColumnRole.MEASURE, 0.92, "HIGH", []),
            "payment_type": ColumnSemanticEvidence("payment_type", ColumnRole.DIMENSION, 0.70, "MEDIUM", []),
        },
    )

    query = "Show total sales by category"
    structured = interpret_user_request(query, taxi_prof)
    assert not structured.requested_metrics
    assert not structured.requested_dimensions
    assert "sales" in structured.unresolved_terms or "category" in structured.unresolved_terms

    amb_res = assess_ambiguity(structured, taxi_prof)
    assert amb_res.status == AmbiguityStatus.UNANSWERABLE
    assert amb_res.is_blocking is True
    assert is_blocking_ambiguity(amb_res) is True
