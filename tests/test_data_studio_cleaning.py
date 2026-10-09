"""Targeted unit tests for Data Studio Cleaning Intelligence & Cleaning Plan (Part 4)."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ingestion import CSVLoader, CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence import DataProfiler, SemanticAnalyzer
from cleaning import CleaningPlanner, generate_cleaning_plan

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REAL_DATA_DIR = Path(__file__).parent / "real_data"


def test_duplicate_detection_recommendation():
    """1. Test that exact duplicate rows generate a low-risk, high-confidence REMOVE_DUPLICATES recommendation."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 2, 3, 4],
            "val": ["A", "B", "B", "C", "D"],
        }
    )
    meta = DatasetMetadata("ds-dup", "Dup Test", "pandas", 5, 2, [
        ColumnMetadata("id", "id", "int64"),
        ColumnMetadata("val", "val", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    dup_recs = [r for r in plan.recommendations if r.category == "duplicates"]

    assert len(dup_recs) == 1
    rec = dup_recs[0]
    assert rec.operation == "REMOVE_DUPLICATES"
    assert rec.column_name is None
    assert rec.affected_rows == 1
    assert rec.risk_level == "LOW"
    assert rec.confidence_level == "HIGH"
    assert rec.default_selected is True
    assert rec.requires_review is False
    assert rec.status == "RECOMMENDED"


def test_numeric_missing_value_imputation():
    """2. Test numeric measure low missingness generates an IMPUTE_MEDIAN recommendation."""
    df = pd.DataFrame(
        {
            "revenue": [100.0, 150.0, 200.0, None, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0],
        }
    )
    meta = DatasetMetadata("ds-num-null", "Num Null", "pandas", 10, 1, [
        ColumnMetadata("revenue", "revenue", "float64", ColumnRole.MEASURE),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    null_recs = [r for r in plan.recommendations if r.category == "missing_values" and r.column_name == "revenue"]

    assert len(null_recs) == 1
    rec = null_recs[0]
    assert rec.operation == "IMPUTE_MEDIAN"
    assert rec.affected_rows == 1
    assert rec.risk_level == "LOW"
    assert rec.confidence_level == "HIGH"
    assert rec.default_selected is True
    assert rec.status == "RECOMMENDED"
    assert "median" in rec.rationale.lower()


def test_categorical_missing_value_mode_and_unknown():
    """3. Test categorical missingness recommends mode when dominant, or 'Unknown' otherwise."""
    # Sub-case A: Dominant category (>40%)
    df_dominant = pd.DataFrame(
        {
            "status": ["Active", "Active", "Active", "Active", "Pending", None],
        }
    )
    meta_a = DatasetMetadata("ds-cat-dom", "Cat Dom", "pandas", 6, 1, [
        ColumnMetadata("status", "status", "object", ColumnRole.DIMENSION),
    ])
    canonical_a = CanonicalDataset(meta_a, df_dominant)
    plan_a = generate_cleaning_plan(canonical_a)

    rec_a = next(r for r in plan_a.recommendations if r.column_name == "status")
    assert rec_a.operation == "FILL_MODE"
    assert rec_a.risk_level == "LOW"
    assert rec_a.default_selected is True
    assert rec_a.params.get("fill_value") == "Active"

    # Sub-case B: Uniform categories (no dominant category)
    df_uniform = pd.DataFrame(
        {
            "tier": ["Bronze", "Silver", "Gold", "Platinum", None],
        }
    )
    meta_b = DatasetMetadata("ds-cat-uni", "Cat Uni", "pandas", 5, 1, [
        ColumnMetadata("tier", "tier", "object", ColumnRole.DIMENSION),
    ])
    canonical_b = CanonicalDataset(meta_b, df_uniform)
    plan_b = generate_cleaning_plan(canonical_b)

    rec_b = next(r for r in plan_b.recommendations if r.column_name == "tier")
    assert rec_b.operation == "FILL_UNKNOWN"
    assert rec_b.risk_level == "LOW"
    assert rec_b.default_selected is True
    assert rec_b.params.get("fill_value") == "Unknown"


def test_empty_string_normalization():
    """4. Test whitespace/empty strings are detected and recommended for normalization."""
    df = pd.DataFrame(
        {
            "city": ["New York", "London", "   ", "", "Tokyo"],
        }
    )
    meta = DatasetMetadata("ds-empty", "Empty Test", "pandas", 5, 1, [
        ColumnMetadata("city", "city", "object", ColumnRole.DIMENSION),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    empty_recs = [r for r in plan.recommendations if r.category == "empty_values"]

    assert len(empty_recs) == 1
    rec = empty_recs[0]
    assert rec.operation == "NORMALIZE_EMPTY_STRINGS"
    assert rec.column_name == "city"
    assert rec.affected_rows == 2
    assert rec.risk_level == "LOW"
    assert rec.confidence_level == "HIGH"
    assert rec.default_selected is True


def test_numeric_type_conversion_detection():
    """5. Test numeric strings stored as text are detected for numeric type coercion."""
    df = pd.DataFrame(
        {
            "score_str": ["85.5", "92.0", "78.4", "99.1", "64.0"],
        }
    )
    meta = DatasetMetadata("ds-type-num", "Type Num", "pandas", 5, 1, [
        ColumnMetadata("score_str", "score_str", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    type_recs = [r for r in plan.recommendations if r.operation == "CONVERT_NUMERIC"]

    assert len(type_recs) == 1
    rec = type_recs[0]
    assert rec.column_name == "score_str"
    assert rec.risk_level == "LOW"
    assert rec.confidence_level == "HIGH"
    assert rec.default_selected is True


def test_datetime_conversion_detection():
    """6. Test ISO date strings are detected for datetime type conversion."""
    df = pd.DataFrame(
        {
            "event_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        }
    )
    meta = DatasetMetadata("ds-type-dt", "Type DT", "pandas", 4, 1, [
        ColumnMetadata("event_date", "event_date", "object", ColumnRole.DATETIME),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    dt_recs = [r for r in plan.recommendations if r.operation == "CONVERT_DATETIME"]

    assert len(dt_recs) == 1
    rec = dt_recs[0]
    assert rec.column_name == "event_date"
    assert rec.risk_level == "LOW"
    assert rec.confidence_level == "HIGH"
    assert rec.default_selected is True


def test_boolean_normalization_detection():
    """7. Test boolean-like text (yes/no, true/false) is recommended for boolean normalization."""
    df = pd.DataFrame(
        {
            "subscribed": ["yes", "no", "yes", "yes", "no"],
        }
    )
    meta = DatasetMetadata("ds-bool", "Bool Test", "pandas", 5, 1, [
        ColumnMetadata("subscribed", "subscribed", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    bool_recs = [r for r in plan.recommendations if r.operation == "NORMALIZE_BOOLEAN"]

    assert len(bool_recs) == 1
    rec = bool_recs[0]
    assert rec.column_name == "subscribed"
    assert rec.risk_level == "LOW"
    assert rec.confidence_level == "HIGH"
    assert rec.default_selected is True


def test_outlier_detection_only_flagged_for_review():
    """8. Test outliers are flagged for review only and NOT preselected by default."""
    # Data with extreme statistical outliers
    values = [10.0, 11.0, 12.0, 10.5, 11.2, 10.8, 12.1, 11.5, 10.9, 11.1, 10.2, 11.8, 500.0]
    df = pd.DataFrame({"metric": values})
    meta = DatasetMetadata("ds-outliers", "Outliers", "pandas", len(values), 1, [
        ColumnMetadata("metric", "metric", "float64", ColumnRole.MEASURE),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    outlier_recs = [r for r in plan.recommendations if r.category == "outliers"]

    assert len(outlier_recs) == 1
    rec = outlier_recs[0]
    assert rec.operation == "REVIEW_OUTLIERS"
    assert rec.risk_level == "HIGH"
    assert rec.requires_review is True
    assert rec.default_selected is False
    assert rec.status == "REVIEW_REQUIRED"
    assert "legitimate" in rec.rationale.lower()


def test_ambiguous_values_require_review():
    """9. Test ambiguous values (e.g. partial numeric parse, moderate missingness) become REVIEW_REQUIRED."""
    # 20% unparseable entries
    df = pd.DataFrame(
        {
            "mixed_col": ["10", "20", "30", "40", "50", "60", "70", "80", "90", "N/A_TEXT", "INVALID_ENTRY"],
        }
    )
    meta = DatasetMetadata("ds-mixed", "Mixed", "pandas", 11, 1, [
        ColumnMetadata("mixed_col", "mixed_col", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)
    recs = [r for r in plan.recommendations if r.column_name == "mixed_col"]

    # Partial type conversion should require review
    for rec in recs:
        if rec.operation == "CONVERT_NUMERIC":
            assert rec.requires_review is True
            assert rec.default_selected is False
            assert rec.status == "REVIEW_REQUIRED"


def test_safe_vs_risky_operations_preselection_policy():
    """10 & 11. Test that low-risk safe operations are preselected and risky operations are deselected."""
    df = pd.DataFrame(
        {
            "id": [1, 1, 2, 3, 4],  # 1 duplicate row
            "salary": [50000.0, 50000.0, 60000.0, None, 75000.0],  # 1 null
            "notes": ["ok", "ok", "   ", "fine", "good"],  # 1 empty string
            "key_col": [101, 101, None, 104, 105],  # missing key (risky)
        }
    )
    meta = DatasetMetadata("ds-safe-risk", "Safe Risk", "pandas", 5, 4, [
        ColumnMetadata("id", "id", "int64"),
        ColumnMetadata("salary", "salary", "float64", ColumnRole.MEASURE),
        ColumnMetadata("notes", "notes", "object", ColumnRole.DIMENSION),
        ColumnMetadata("key_col", "key_col", "int64", ColumnRole.IDENTIFIER),
    ])
    canonical = CanonicalDataset(meta, df)

    plan = generate_cleaning_plan(canonical)

    for rec in plan.recommendations:
        if rec.risk_level == "LOW" and rec.status == "RECOMMENDED":
            assert rec.default_selected is True
            assert rec.requires_review is False
        elif rec.risk_level in ["MEDIUM", "HIGH"] or rec.requires_review:
            assert rec.default_selected is False
            assert rec.status == "REVIEW_REQUIRED"


def test_cleaning_recommendations_are_deterministic():
    """12. Test that running cleaning planning multiple times produces identical recommendations."""
    df = pd.DataFrame(
        {
            "dup_a": [1, 1, 2, 3],
            "dup_b": ["x", "x", "y", "z"],
            "measure": [10.0, 10.0, None, 40.0],
        }
    )
    meta = DatasetMetadata("ds-determ", "Determ", "pandas", 4, 3, [
        ColumnMetadata("dup_a", "dup_a", "int64"),
        ColumnMetadata("dup_b", "dup_b", "object"),
        ColumnMetadata("measure", "measure", "float64", ColumnRole.MEASURE),
    ])
    canonical = CanonicalDataset(meta, df)

    planner = CleaningPlanner()
    plan_1 = planner.generate_plan(canonical)
    plan_2 = planner.generate_plan(canonical)

    # Freeze timestamp for dict comparison
    plan_2.generated_at = plan_1.generated_at

    assert plan_1.to_dict() == plan_2.to_dict()


def test_cleaning_plan_does_not_mutate_dataset():
    """13. Test that cleaning planning strictly respects dataset immutability."""
    df = pd.DataFrame(
        {
            "a": [1, 1, 2, None],
            "b": ["  ", "test", "test", "other"],
        }
    )
    df_snapshot = df.copy(deep=True)

    meta = DatasetMetadata("ds-immut", "Immut", "pandas", 4, 2, [
        ColumnMetadata("a", "a", "float64"),
        ColumnMetadata("b", "b", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    _ = generate_cleaning_plan(canonical)

    pd.testing.assert_frame_equal(canonical.data, df_snapshot)
    assert canonical.data["a"].isna().sum() == 1
    assert (canonical.data["b"] == "  ").sum() == 1


def test_switching_datasets_generates_isolated_plans():
    """14. Test that different datasets produce distinct plans without recommendation leakage."""
    df_1 = pd.DataFrame({"col_1": [1, 2, 3]})
    df_2 = pd.DataFrame({"col_2": ["a", "b", None], "empty": ["", "x", "y"]})

    meta_1 = DatasetMetadata("ds-1", "DS 1", "pandas", 3, 1, [ColumnMetadata("col_1", "col_1", "int64")])
    meta_2 = DatasetMetadata("ds-2", "DS 2", "pandas", 3, 2, [
        ColumnMetadata("col_2", "col_2", "object"),
        ColumnMetadata("empty", "empty", "object"),
    ])

    canonical_1 = CanonicalDataset(meta_1, df_1)
    canonical_2 = CanonicalDataset(meta_2, df_2)

    planner = CleaningPlanner()
    plan_1 = planner.generate_plan(canonical_1)
    plan_2 = planner.generate_plan(canonical_2)

    assert plan_1.dataset_id == "ds-1"
    assert plan_2.dataset_id == "ds-2"
    assert plan_1.total_recommendations == 0
    assert plan_2.total_recommendations >= 2
    assert all(r.column_name != "col_1" for r in plan_2.recommendations)


def test_canonical_real_datasets_produce_valid_plans():
    """15. Test cleaning plans across all 5 canonical datasets without crashes."""
    loader = CSVLoader()
    planner = CleaningPlanner()

    dataset_files = ["healthcare.csv", "education.csv", "iot.csv", "hr.csv", "logistics.csv"]

    for filename in dataset_files:
        file_path = REAL_DATA_DIR / filename
        if not file_path.exists():
            continue

        canonical = loader.load(file_path)
        plan = planner.generate_plan(canonical)

        assert plan.dataset_id == canonical.metadata.dataset_id
        assert plan.total_recommendations > 0
        assert plan.safe_count >= 0
        assert isinstance(plan.to_dict(), dict)
