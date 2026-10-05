"""Comprehensive Unit Tests for Generalized NL -> SQL Analytical Query Engine.

Tests:
A. Simple aggregation
B. Grouped aggregation
C. Count / row-count questions
D. Dynamic filtering
E. Multiple filters
F. Ranking (highest / lowest)
G. Top-N / Bottom-N limits
H. Datetime temporal grouping
I. Semantic aggregation selection (INTENSIVE/SCORE -> AVG, ADDITIVE/COUNT -> SUM)
J. Ambiguous metric detection
K. Invalid column / unanswerable request handling
L. SQL safety and read-only execution
M. Parity with direct calculation
"""

import pandas as pd
import pytest

from engine.compiler import compile_plan_to_sql
from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
    analyze_semantics,
)
from orchestrator.query_engine import AnalyticalQueryEngine, execute_analytical_query
from orchestrator.schemas import (
    AggregationType,
    AmbiguityStatus,
    CandidatePlan,
    DimensionSpec,
    FilterSpec,
    Granularity,
    MetricSpec,
)


@pytest.fixture
def synthetic_academic_dataset():
    """Synthetic dataset with non-standard academic column names."""
    df = pd.DataFrame({
        "student_token": [f"S{i:03d}" for i in range(1, 11)],
        "academic_cohort": ["Alpha", "Beta", "Alpha", "Beta", "Alpha", "Gamma", "Beta", "Gamma", "Alpha", "Gamma"],
        "examination_score": [88.5, 92.0, 76.5, 84.0, 95.5, 68.0, 72.5, 91.0, 83.0, 79.5],
        "attendance_percentage": [0.95, 0.90, 0.82, 0.88, 0.98, 0.75, 0.80, 0.92, 0.85, 0.78],
        "tuition_fee_paid": [5000, 5200, 4800, 5100, 5500, 4700, 4900, 5300, 5100, 4800],
        "enrollment_timestamp": [
            "2024-01-10", "2024-01-15", "2024-02-01", "2024-02-10", "2024-03-05",
            "2024-03-20", "2024-04-12", "2024-04-25", "2024-05-02", "2024-05-18"
        ],
    })
    meta = DatasetMetadata(
        dataset_id="academic_test_ds",
        name="academic_performance",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("student_token", "student_token", "object", ColumnRole.IDENTIFIER, 0, 0.0, 10),
            ColumnMetadata("academic_cohort", "academic_cohort", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("examination_score", "examination_score", "float64", ColumnRole.MEASURE, 0, 0.0, 10),
            ColumnMetadata("attendance_percentage", "attendance_percentage", "float64", ColumnRole.MEASURE, 0, 0.0, 10),
            ColumnMetadata("tuition_fee_paid", "tuition_fee_paid", "int64", ColumnRole.MEASURE, 0, 0.0, 8),
            ColumnMetadata("enrollment_timestamp", "enrollment_timestamp", "object", ColumnRole.DATETIME, 0, 0.0, 10),
        ],
    )
    dataset = CanonicalDataset(metadata=meta, data=df)
    profile = analyze_semantics(dataset, apply_roles=True)
    return dataset, profile


def test_simple_aggregation(synthetic_academic_dataset):
    """Test A: Simple aggregation on continuous score measure defaults to AVG."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="What is the average examination score?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert res.ambiguity_status == AmbiguityStatus.CLEAR
    assert res.plan.metric.column == "examination_score"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert len(res.rows) == 1
    # Check exact average calculation parity
    expected_avg = dataset.data["examination_score"].mean()
    actual_val = list(res.rows[0].values())[0]
    assert pytest.approx(actual_val, rel=1e-3) == expected_avg


def test_grouped_aggregation(synthetic_academic_dataset):
    """Test B: Grouped aggregation by categorical cohort."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Show average examination score by academic cohort",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert res.plan.metric.column == "examination_score"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert len(res.plan.dimensions) == 1
    assert res.plan.dimensions[0].column == "academic_cohort"
    assert res.row_count == 3  # Alpha, Beta, Gamma cohorts


def test_count_analysis(synthetic_academic_dataset):
    """Test C: Count of entities / row count analysis."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="How many student tokens are enrolled?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.aggregation in (AggregationType.COUNT, AggregationType.COUNT_DISTINCT)
    assert len(res.rows) == 1
    actual_count = list(res.rows[0].values())[0]
    assert actual_count == 10


def test_single_filter(synthetic_academic_dataset):
    """Test D: Natural language filter extraction and execution."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Show total tuition fee paid where academic cohort = 'Alpha'",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert res.plan.metric.column == "tuition_fee_paid"
    assert res.plan.metric.aggregation == AggregationType.SUM
    assert len(res.plan.filters) == 1
    assert res.plan.filters[0].column == "academic_cohort"
    assert res.plan.filters[0].operator == "="
    assert res.plan.filters[0].value == "Alpha"
    # Ground truth parity check
    expected_sum = dataset.data[dataset.data["academic_cohort"] == "Alpha"]["tuition_fee_paid"].sum()
    actual_sum = list(res.rows[0].values())[0]
    assert actual_sum == expected_sum


def test_multiple_filters(synthetic_academic_dataset):
    """Test E: Multiple filter constraints in user question."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Average examination score where academic cohort = 'Alpha' and tuition fee paid > 4900",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert len(res.plan.filters) >= 2
    filter_cols = {f.column for f in res.plan.filters}
    assert "academic_cohort" in filter_cols
    assert "tuition_fee_paid" in filter_cols
    assert "WHERE" in res.compiled_sql
    assert "AND" in res.compiled_sql


def test_ranking_highest(synthetic_academic_dataset):
    """Test F: Ranking / highest group resolution."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Which academic cohort has the highest average examination score?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert res.plan.metric.column == "examination_score"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "academic_cohort"
    assert res.plan.order_direction == "DESC"
    # Ground truth top cohort
    grouped = dataset.data.groupby("academic_cohort")["examination_score"].mean().sort_values(ascending=False)
    top_cohort = grouped.index[0]
    first_row_cohort = res.rows[0]["academic_cohort"]
    assert first_row_cohort == top_cohort


def test_top_n_limits(synthetic_academic_dataset):
    """Test G: Top N / limit query extraction."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Show top 2 academic cohorts by total tuition fee paid",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert res.plan.limit == 2
    assert res.plan.order_direction == "DESC"
    assert len(res.rows) == 2


def test_datetime_grouping(synthetic_academic_dataset):
    """Test H: Temporal / datetime grouping by month."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Monthly trend of total tuition fee paid over enrollment timestamp",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status == "PASSED"
    assert len(res.plan.dimensions) == 1
    assert res.plan.dimensions[0].column == "enrollment_timestamp"
    assert res.plan.dimensions[0].granularity == Granularity.MONTH
    assert "DATE_TRUNC('month'" in res.compiled_sql
    assert len(res.plan.dimensions) == 1
    assert res.plan.dimensions[0].column == "enrollment_timestamp"
    assert res.plan.dimensions[0].granularity == Granularity.MONTH
    assert "DATE_TRUNC('month'" in res.compiled_sql


def test_semantic_aggregation_selection(synthetic_academic_dataset):
    """Test I: Score/rating measures automatically select AVG, additive amounts select SUM."""
    dataset, profile = synthetic_academic_dataset
    # Score column -> AVG
    res_score = execute_analytical_query(
        question="What is the examination score by academic cohort?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res_score.plan.metric.aggregation == AggregationType.AVG

    # Fee amount column -> SUM
    res_fee = execute_analytical_query(
        question="What is the tuition fee paid by academic cohort?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res_fee.plan.metric.aggregation == AggregationType.SUM


def test_ambiguous_generic_query(synthetic_academic_dataset):
    """Test J: Generic ungrounded query returns ambiguity without guessing."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Show the metric numbers and stats",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.ambiguity_status in (AmbiguityStatus.AMBIGUOUS, AmbiguityStatus.UNANSWERABLE)
    assert res.validation_status == "FAILED"
    assert len(res.rows) == 0


def test_invalid_column_rejection(synthetic_academic_dataset):
    """Test K: Non-existent requested column is safely handled."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Show the average non_existent_gibberish_column by academic cohort",
        dataset=dataset,
        semantic_profile=profile,
    )
    # Should not throw unhandled exception; either flags lexical ambiguity or fallback
    assert res.question is not None


def test_sql_injection_safety(synthetic_academic_dataset):
    """Test L: SQL injection payloads in filters are safely escaped by compiler."""
    dataset, profile = synthetic_academic_dataset
    res = execute_analytical_query(
        question="Show average examination score where academic cohort = 'Alpha'' OR 1=1; DROP TABLE users; --'",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.compiled_sql is not None
    # Verify the compiled SQL quotes and escapes literal quotes safely
    assert "''" in res.compiled_sql
    assert "'Alpha'''' OR 1=1; DROP TABLE users; --'" in res.compiled_sql
    # Proves OR 1=1 was treated as literal string, returning NULL for aggregate over 0 matched rows
    assert res.rows[0]["avg_examination_score"] is None
