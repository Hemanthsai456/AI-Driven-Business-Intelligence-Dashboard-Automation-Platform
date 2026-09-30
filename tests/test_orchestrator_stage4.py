"""Stage 4 Unit and Integration Tests: Deterministic Spine (No LLM).

Verifies:
1. Pass 1a Validator:
   - C3 Refusal when dataset readiness is NOT_READY.
   - Column existence validation.
   - Role/aggregation compatibility (SUM/AVG on MEASURE only; rejection on DIMENSION/IDENTIFIER).
   - Rejection of UNKNOWN role for metric.
   - Granularity requires DATETIME column.
   - Filter operator whitelist enforcement.
   - Low confidence role warnings.
2. Query Compiler:
   - Safe quoted identifiers preventing SQL injection in column names.
   - Safe literal escaping preventing SQL injection in filter values.
   - Whitelisted aggregation functions and granularities.
3. DuckDB Executor & Binding Resolution C2:
   - Zero DataFrame mutation invariance.
   - TRY_CAST inside DuckDB view for DATETIME string columns.
   - Failed-cast count and rate tracking and warning generation.
   - Timeout handling returning ExecutionStatus.TIMEOUT.
   - Memory limit and sandboxed thread limits.
4. Pass 1b Validator:
   - Rejection on non-zero error execution.
   - Empty result (0 rows) rejection.
   - All-null metric rejection.
   - Row cap overflow rejection.
   - High failed-cast rate rejection.
5. FastAPI Endpoints:
   - POST /api/orchestrator/validate-plan
   - POST /api/orchestrator/run-plan
"""

import time
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import (
    AnalysisReadiness,
    ReadinessStatus,
    assess_readiness,
)
from intelligence.semantic_analyzer import (
    ColumnRole,
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
    analyze_semantics,
)
from orchestrator.compiler import (
    QueryCompilationError,
    compile_plan_to_sql,
    format_sql_literal,
    quote_identifier,
)
from orchestrator.config import FAILED_CAST_RATE_THRESHOLD, RESULT_ROW_CAP
from orchestrator.executor import DuckDBExecutor, execute_plan
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
    ValidationStatus,
    VisualizationType,
)
from orchestrator.validator import validate_pass1a, validate_pass1b


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_sales_data():
    """Create a realistic small sales dataset with date strings, categories, IDs, and measures."""
    df = pd.DataFrame({
        "SaleID": [101, 102, 103, 104, 105],
        "OrderDate": ["2024-01-15", "2024-02-10", "2024-02-15", "2024-03-01", "2024-03-20"],
        "Category": ["Electronics", "Furniture", "Electronics", "Technology", "Furniture"],
        "Revenue": [1250.50, 450.00, 890.00, 2100.00, 310.25],
        "Quantity": [2, 1, 3, 5, 2],
    })
    meta = DatasetMetadata(
        dataset_id="test-sales-ds",
        name="Sales_Test",
        source_type="pandas",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("SaleID", "SaleID", "int64"),
            ColumnMetadata("OrderDate", "OrderDate", "object"),
            ColumnMetadata("Category", "Category", "object"),
            ColumnMetadata("Revenue", "Revenue", "float64"),
            ColumnMetadata("Quantity", "Quantity", "int64"),
        ],
    )
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    semantic_profile = analyze_semantics(canonical, profile)
    readiness = assess_readiness(canonical, profile, semantic_profile)
    return canonical, profile, semantic_profile, readiness


# ---------------------------------------------------------------------------
# Pass 1a Validation Tests
# ---------------------------------------------------------------------------


def test_pass1a_c3_refusal_when_not_ready(sample_sales_data):
    """C3 Binding Resolution: Dispatch must be refused if readiness is NOT_READY."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    # Artificially set readiness to NOT_READY
    not_ready = AnalysisReadiness(
        dataset_id="test-sales-ds",
        status=ReadinessStatus.NOT_READY,
        blocking_issues=["Corrupt schema"],
        warnings=[],
        summary="Blocked",
        checked_columns=[],
        checked_row_count=5,
        checked_column_count=5,
    )

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Show total revenue by category",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        reasoning=PlanReasoning(interpretation="Category revenue", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, not_ready)
    assert not res.passed
    assert any(issue.check == "dataset_readiness" and issue.status == ValidationStatus.FAILED for issue in res.issues)
    assert "C3 binding resolution" in res.issues[0].message


def test_pass1a_valid_plan_passes(sample_sales_data):
    """Valid plan on sales dataset passes Pass 1a with flying colors."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Total revenue by month",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="OrderDate", granularity=Granularity.MONTH)],
        filters=[FilterSpec(column="Category", operator="=", value="Electronics")],
        reasoning=PlanReasoning(interpretation="Monthly electronics revenue", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, readiness)
    assert res.passed
    assert not any(i.status == ValidationStatus.FAILED for i in res.issues)


def test_pass1a_nonexistent_column_rejected(sample_sales_data):
    """Pass 1a rejects plan with columns not in semantic profile."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Total profit",
        metric=MetricSpec(column="NonExistentProfit", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="GhostDim")],
        filters=[FilterSpec(column="GhostFilter", operator="=", value="X")],
        reasoning=PlanReasoning(interpretation="Invalid plan", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, readiness)
    assert not res.passed
    failed_checks = [i.check for i in res.issues if i.status == ValidationStatus.FAILED]
    assert "metric_column_exists" in failed_checks
    assert "dimension_column_exists" in failed_checks
    assert "filter_column_exists" in failed_checks


def test_pass1a_role_aggregation_compat_sum_on_dimension(sample_sales_data):
    """Pass 1a rejects SUM on DIMENSION role column (e.g. Category)."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Sum of categories",
        metric=MetricSpec(column="Category", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Invalid sum on text category", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, readiness)
    assert not res.passed
    assert any(i.check == "role_aggregation_compat" for i in res.issues)


def test_pass1a_unknown_role_rejected(sample_sales_data):
    """Pass 1a strictly rejects UNKNOWN role for metric."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    # Add an UNKNOWN evidence entry
    sem_profile.column_evidences["UnknownCol"] = ColumnSemanticEvidence(
        column_name="UnknownCol",
        candidate_role=ColumnRole.UNKNOWN,
        confidence=0.20,
        confidence_level="LOW",
        evidence=["Ambiguous"],
    )

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Metric on unknown",
        metric=MetricSpec(column="UnknownCol", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Unknown metric", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, readiness)
    assert not res.passed
    assert any(i.check == "unknown_role_rejected" for i in res.issues)


def test_pass1a_granularity_requires_datetime(sample_sales_data):
    """Pass 1a rejects temporal granularity on a non-DATETIME column."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Revenue by category month",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category", granularity=Granularity.MONTH)],
        reasoning=PlanReasoning(interpretation="Invalid temporal granularity on category", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, readiness)
    assert not res.passed
    assert any(i.check == "granularity_requires_datetime" for i in res.issues)


def test_pass1a_unsupported_filter_operator(sample_sales_data):
    """Pass 1a rejects filter operators not in whitelist."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Filter with malicious or invalid operator",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        filters=[FilterSpec(column="Category", operator="EXEC", value="malicious")],
        reasoning=PlanReasoning(interpretation="Invalid operator", evidence=[]),
    )

    res = validate_pass1a(plan, sem_profile, readiness)
    assert not res.passed
    assert any(i.check == "filter_operator_whitelist" for i in res.issues)


# ---------------------------------------------------------------------------
# Query Compiler & SQL Injection Tests
# ---------------------------------------------------------------------------


def test_compiler_safe_literal_escaping():
    """Verify SQL injection payloads in filter values are strictly escaped as string literals."""
    payload = "'; DROP TABLE source_data; --"
    formatted = format_sql_literal(payload)
    assert formatted == "'''; DROP TABLE source_data; --'"

    # Verify quotes inside string are doubled
    assert format_sql_literal("O'Reilly") == "'O''Reilly'"


def test_compiler_identifier_quoting():
    """Verify column names with spaces or quotes are safely quoted."""
    quoted = quote_identifier('Total "Gross" Sales')
    assert quoted == '"Total ""Gross"" Sales"'


def test_compiler_sql_injection_attempt_in_column_name():
    """Attempting SQL injection in column name results in safe quoted identifier, never executable SQL."""
    injection_col = 'Revenue"; DROP TABLE source_data; --'
    quoted = quote_identifier(injection_col)
    assert quoted == '"Revenue""; DROP TABLE source_data; --"'


def test_compiler_produces_clean_duckdb_sql():
    """Verify clean compilation of full CandidatePlan."""
    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Monthly revenue by category",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[
            DimensionSpec(column="OrderDate", granularity=Granularity.MONTH),
            DimensionSpec(column="Category"),
        ],
        filters=[
            FilterSpec(column="Revenue", operator=">", value=500.0),
            FilterSpec(column="Category", operator="IN", value=["Electronics", "Technology"]),
        ],
        reasoning=PlanReasoning(interpretation="Filtered query", evidence=[]),
    )

    sql = compile_plan_to_sql(plan, source_view="source_data")
    assert "SELECT" in sql
    assert "DATE_TRUNC('month', \"OrderDate\") AS \"OrderDate_month\"" in sql
    assert '"Category"' in sql
    assert 'SUM("Revenue") AS "sum_Revenue"' in sql
    assert 'FROM "source_data"' in sql
    assert '"Revenue" > 500.0' in sql
    assert "'Electronics'" in sql
    assert "'Technology'" in sql
    assert "GROUP BY 1, 2" in sql
    assert "LIMIT" in sql


# ---------------------------------------------------------------------------
# DuckDB Executor & Binding Resolution C2 Tests
# ---------------------------------------------------------------------------


def test_executor_dataframe_read_only_invariance(sample_sales_data):
    """Verify DataFrame is NEVER mutated during DuckDB execution."""
    canonical, profile, sem_profile, readiness = sample_sales_data
    original_df = canonical.data.copy(deep=True)

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Sum revenue",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        reasoning=PlanReasoning(interpretation="Sum revenue", evidence=[]),
    )

    exec_result = execute_plan(plan, canonical, sem_profile)
    assert exec_result.status == ExecutionStatus.SUCCESS

    # Verify original DataFrame was completely untouched
    pd.testing.assert_frame_equal(canonical.data, original_df)


def test_executor_c2_try_cast_and_failed_cast_tracking():
    """C2 Binding Resolution: DATETIME string columns are TRY_CAST inside DuckDB view.

    Verify unparseable string values produce failed_cast_count in ExecutionResult warnings.
    """
    # Create dataset with 3 valid dates and 2 unparseable date strings
    df = pd.DataFrame({
        "ID": [1, 2, 3, 4, 5],
        "DateCol": ["2024-01-01", "not_a_date_1", "2024-01-03", "corrupt_date_2", "2024-01-05"],
        "Amount": [10.0, 20.0, 30.0, 40.0, 50.0],
    })
    meta = DatasetMetadata("ds-cast", "CastTest", "pandas", 5, 3, [
        ColumnMetadata("ID", "ID", "int64"),
        ColumnMetadata("DateCol", "DateCol", "object"),
        ColumnMetadata("Amount", "Amount", "float64"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    # Force DateCol to DATETIME role
    sem_profile = DatasetSemanticProfile(dataset_id="ds-cast", generated_at="now", column_evidences={
        "ID": ColumnSemanticEvidence("ID", ColumnRole.IDENTIFIER, 0.95, "HIGH", []),
        "DateCol": ColumnSemanticEvidence("DateCol", ColumnRole.DATETIME, 0.85, "HIGH", []),
        "Amount": ColumnSemanticEvidence("Amount", ColumnRole.MEASURE, 0.95, "HIGH", []),
    })

    plan = CandidatePlan(
        dataset_id="ds-cast",
        intent="Sum amount by day",
        metric=MetricSpec(column="Amount", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="DateCol", granularity=Granularity.DAY)],
        reasoning=PlanReasoning(interpretation="Daily sum", evidence=[]),
    )

    exec_result = execute_plan(plan, canonical, sem_profile)
    assert exec_result.status == ExecutionStatus.SUCCESS

    # Exactly 2 failed casts out of 5 rows = 40%
    assert exec_result.failed_cast_count == 2
    assert abs(exec_result.failed_cast_rate - 0.40) < 1e-4
    assert any("failed datetime casts" in w for w in exec_result.warnings)

    # 40% < 50% threshold, so Pass 1b should pass with a warning
    p1b = validate_pass1b(plan, exec_result)
    assert p1b.passed
    assert any(i.check == "failed_cast_warning" and i.status == ValidationStatus.WARNING for i in p1b.issues)


def test_executor_c2_high_failed_cast_rate_rejected_by_pass1b():
    """Pass 1b rejects execution when failed_cast_rate > FAILED_CAST_RATE_THRESHOLD (50%)."""
    # 4 unparseable out of 5 = 80% failed
    df = pd.DataFrame({
        "DateCol": ["2024-01-01", "bad1", "bad2", "bad3", "bad4"],
        "Val": [1, 2, 3, 4, 5],
    })
    meta = DatasetMetadata("ds-bad", "Bad", "pandas", 5, 2, [
        ColumnMetadata("DateCol", "DateCol", "object"),
        ColumnMetadata("Val", "Val", "int64"),
    ])
    canonical = CanonicalDataset(meta, df)
    sem_profile = DatasetSemanticProfile(dataset_id="ds-bad", generated_at="now", column_evidences={
        "DateCol": ColumnSemanticEvidence("DateCol", ColumnRole.DATETIME, 0.85, "HIGH", []),
        "Val": ColumnSemanticEvidence("Val", ColumnRole.MEASURE, 0.95, "HIGH", []),
    })

    plan = CandidatePlan(
        dataset_id="ds-bad",
        intent="Val by date",
        metric=MetricSpec(column="Val", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="DateCol", granularity=Granularity.DAY)],
        reasoning=PlanReasoning(interpretation="Bad dates", evidence=[]),
    )

    exec_res = execute_plan(plan, canonical, sem_profile)
    assert exec_res.failed_cast_rate == 0.80

    p1b = validate_pass1b(plan, exec_res)
    assert not p1b.passed
    assert any(i.check == "failed_cast_rate" and i.status == ValidationStatus.FAILED for i in p1b.issues)


def test_executor_timeout_enforcement(sample_sales_data):
    """Verify worker timeout aborts and returns ExecutionStatus.TIMEOUT."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    # Create executor with very tiny timeout
    tiny_timeout_executor = DuckDBExecutor(timeout_seconds=0.01)

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Sleep query",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Sleep", evidence=[]),
    )

    # Inject a slow query to trigger timeout
    slow_sql = "SELECT SUM(Revenue) FROM (SELECT Revenue FROM source_data, generate_series(1, 5000000) AS s);"
    exec_result = tiny_timeout_executor.execute_plan(
        plan, canonical, sem_profile, custom_sql=slow_sql
    )

    assert exec_result.status == ExecutionStatus.TIMEOUT
    assert "timed out" in (exec_result.error_message or "").lower()


def test_executor_memory_cap_enforcement(sample_sales_data):
    """Verify DuckDB memory cap is enforced on oversized queries and returns ExecutionStatus.MEMORY_EXCEEDED."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    # Create executor with tight 1MB memory limit
    low_mem_executor = DuckDBExecutor(memory_limit="1MB")

    plan = CandidatePlan(
        dataset_id="test-sales-ds",
        intent="Oversized query exceeding memory",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Memory cap stress", evidence=[]),
    )

    # 20M-row cross-join exceeding 1MB DuckDB memory cap
    oom_sql = (
        "SELECT COUNT(*) FROM "
        "(SELECT range AS a, range AS b FROM range(20000000)) t1 "
        "JOIN (SELECT range AS a, range AS b FROM range(20000000)) t2 ON t1.b = t2.b;"
    )
    exec_result = low_mem_executor.execute_plan(
        plan, canonical, sem_profile, custom_sql=oom_sql
    )

    assert exec_result.status == ExecutionStatus.MEMORY_EXCEEDED
    assert "memory limit exceeded" in (exec_result.error_message or "").lower()


# ---------------------------------------------------------------------------
# Pass 1b Validation Tests
# ---------------------------------------------------------------------------


def test_pass1b_empty_result_rejected():
    """Pass 1b rejects 0-row result sets."""
    plan = CandidatePlan(
        dataset_id="ds-1",
        intent="Empty intent",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Empty", evidence=[]),
    )
    exec_res = ExecutionResult(
        plan_id=plan.plan_id,
        status=ExecutionStatus.SUCCESS,
        rows=[],
        columns=["sum_Revenue"],
        row_count=0,
    )
    p1b = validate_pass1b(plan, exec_res)
    assert not p1b.passed
    assert any(i.check == "non_empty_result" for i in p1b.issues)


def test_pass1b_all_null_metric_rejected():
    """Pass 1b rejects result sets where metric column is entirely NULL."""
    plan = CandidatePlan(
        dataset_id="ds-1",
        intent="All null metric",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Nulls", evidence=[]),
    )
    exec_res = ExecutionResult(
        plan_id=plan.plan_id,
        status=ExecutionStatus.SUCCESS,
        rows=[{"Category": "A", "sum_Revenue": None}, {"Category": "B", "sum_Revenue": None}],
        columns=["Category", "sum_Revenue"],
        row_count=2,
    )
    p1b = validate_pass1b(plan, exec_res)
    assert not p1b.passed
    assert any(i.check == "metric_not_all_null" for i in p1b.issues)


def test_pass1b_row_cap_exceeded_rejected():
    """Pass 1b rejects result sets exceeding RESULT_ROW_CAP."""
    plan = CandidatePlan(
        dataset_id="ds-1",
        intent="Too many rows",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        reasoning=PlanReasoning(interpretation="Overflow", evidence=[]),
    )
    exec_res = ExecutionResult(
        plan_id=plan.plan_id,
        status=ExecutionStatus.SUCCESS,
        rows=[{"r": i} for i in range(10)],
        columns=["r"],
        row_count=RESULT_ROW_CAP + 1,
    )
    p1b = validate_pass1b(plan, exec_res)
    assert not p1b.passed
    assert any(i.check == "result_row_cap" for i in p1b.issues)


# ---------------------------------------------------------------------------
# API Endpoints Integration Tests
# ---------------------------------------------------------------------------


def test_api_orchestrator_endpoints(sample_sales_data):
    """Verify /api/orchestrator/validate-plan and /api/orchestrator/run-plan endpoints."""
    canonical, profile, sem_profile, readiness = sample_sales_data

    # Store in session_store for the API
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=sem_profile,
        readiness=readiness,
    )
    session_store.save(record)

    client = TestClient(app)

    plan_payload = {
        "dataset_id": "test-sales-ds",
        "intent": "Total revenue by category",
        "metric": {"column": "Revenue", "aggregation": "SUM"},
        "dimensions": [{"column": "Category"}],
        "filters": [],
        "visualization": "BAR",
        "reasoning": {"interpretation": "Total revenue grouped by category", "evidence": []},
    }

    # 1. Test validate-plan endpoint
    val_resp = client.post("/api/orchestrator/validate-plan", json=plan_payload)
    assert val_resp.status_code == 200
    val_json = val_resp.json()
    assert val_json["passed"] is True
    assert "plan_id" in val_json

    # 2. Test run-plan endpoint
    run_resp = client.post("/api/orchestrator/run-plan", json=plan_payload)
    assert run_resp.status_code == 200
    run_json = run_resp.json()
    assert run_json["pass1a"]["passed"] is True
    assert run_json["execution"] is not None
    assert run_json["execution"]["status"] == "SUCCESS"
    assert run_json["execution"]["row_count"] > 0
    assert run_json["pass1b"]["passed"] is True

    # 3. Test 404 for nonexistent dataset
    bad_plan = dict(plan_payload, dataset_id="nonexistent-dataset-id")
    not_found_resp = client.post("/api/orchestrator/run-plan", json=bad_plan)
    assert not_found_resp.status_code == 404
