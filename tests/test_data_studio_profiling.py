"""Targeted unit tests for Data Studio Detailed Profiling (Part 3)."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ingestion import CSVLoader, CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence import (
    DataProfiler,
    SemanticAnalyzer,
    analyze_semantics,
    profile_dataset,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_numeric_profiling_detailed_statistics():
    """1. Test numeric profiling: min, max, mean, median, std, q25, q75, zero/neg count, and histogram."""
    df = pd.DataFrame(
        {
            "revenue": [-50.0, 0.0, 100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 1000.0],
        }
    )
    meta = DatasetMetadata("ds-num-prof", "Num Prof", "pandas", 10, 1, [ColumnMetadata("revenue", "revenue", "float64")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["revenue"]

    assert stats["min"] == -50.0
    assert stats["max"] == 1000.0
    assert stats["mean"] == 285.0
    assert stats["median"] == 225.0
    assert stats["zero_count"] == 1
    assert stats["negative_count"] == 1
    assert stats["q25"] == 112.5
    assert stats["q75"] == 375.0
    assert stats["std"] is not None

    # Histogram checks
    assert "histogram" in stats
    hist = stats["histogram"]
    assert isinstance(hist, list)
    assert len(hist) == 10
    total_binned = sum(b["count"] for b in hist)
    assert total_binned == 10
    assert hist[0]["bin_start"] == -50.0
    assert hist[-1]["bin_end"] == 1000.0


def test_categorical_profiling_and_frequencies():
    """2. Test categorical profiling: distinct count, top frequent values, empty strings."""
    df = pd.DataFrame(
        {
            "region": ["North", "North", "North", "South", "South", "East", "  ", None],
        }
    )
    meta = DatasetMetadata("ds-cat-prof", "Cat Prof", "pandas", 8, 1, [ColumnMetadata("region", "region", "object")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["region"]

    assert stats["distinct_count"] == 4  # North, South, East, "  "
    assert stats["null_count"] == 1
    assert stats["empty_string_count"] == 1
    assert len(stats["most_frequent_values"]) > 0
    # North is most frequent (3)
    assert stats["most_frequent_values"][0] == {"value": "North", "count": 3}
    assert stats["most_frequent_values"][1] == {"value": "South", "count": 2}


def test_datetime_profiling_and_temporal_span():
    """3. Test datetime profiling: min/max dates, distinct dates, and temporal span calculation."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-10", "2026-01-31"]),
        }
    )
    meta = DatasetMetadata("ds-dt-prof", "DT Prof", "pandas", 3, 1, [ColumnMetadata("date", "date", "datetime64[ns]")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["date"]

    assert stats["min_datetime"] == "2026-01-01T00:00:00"
    assert stats["max_datetime"] == "2026-01-31T00:00:00"
    assert stats["distinct_dates_count"] == 3
    assert stats["temporal_span_days"] == 30


def test_boolean_profiling():
    """4. Test boolean profiling: true count, false count, null count."""
    df = pd.DataFrame(
        {
            "is_active": [True, True, True, False, False, None],
        }
    )
    meta = DatasetMetadata("ds-bool-prof", "Bool Prof", "pandas", 6, 1, [ColumnMetadata("is_active", "is_active", "boolean")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["is_active"]

    assert stats["true_count"] == 3
    assert stats["false_count"] == 2
    assert stats["null_count"] == 1


def test_missing_value_statistics():
    """5. Test missing value metrics across column and dataset summary levels."""
    df = pd.DataFrame(
        {
            "col_a": [1, None, 3, None, 5],
            "col_b": [None, None, None, None, None],
            "col_c": [1, 2, 3, 4, 5],
        }
    )
    meta = DatasetMetadata("ds-miss-prof", "Miss Prof", "pandas", 5, 3, [
        ColumnMetadata("col_a", "col_a", "float64"),
        ColumnMetadata("col_b", "col_b", "object"),
        ColumnMetadata("col_c", "col_c", "int64"),
    ])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)

    assert profile.dataset_summary["overall_missing_count"] == 7
    assert profile.dataset_summary["overall_missing_percentage"] == pytest.approx(46.67, 0.01)
    assert profile.column_statistics["col_a"]["null_count"] == 2
    assert profile.column_statistics["col_a"]["null_percentage"] == 40.0
    assert profile.column_statistics["col_b"]["null_count"] == 5
    assert profile.column_statistics["col_b"]["null_percentage"] == 100.0
    assert profile.column_statistics["col_c"]["null_count"] == 0
    assert profile.column_statistics["col_c"]["null_percentage"] == 0.0


def test_uniqueness_and_distinct_statistics():
    """6. Test distinct counts, uniqueness percentages, and key detection flags."""
    df = pd.DataFrame(
        {
            "user_id": [101, 102, 103, 104, 105],
            "role": ["Admin", "User", "User", "User", "User"],
        }
    )
    meta = DatasetMetadata("ds-uniq-prof", "Uniq Prof", "pandas", 5, 2, [
        ColumnMetadata("user_id", "user_id", "int64"),
        ColumnMetadata("role", "role", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)

    user_stats = profile.column_statistics["user_id"]
    role_stats = profile.column_statistics["role"]

    assert user_stats["distinct_count"] == 5
    assert user_stats["uniqueness_percentage"] == 100.0
    assert user_stats["is_unique"] is True

    assert role_stats["distinct_count"] == 2
    assert role_stats["uniqueness_percentage"] == 40.0
    assert role_stats["is_unique"] is False


def test_deterministic_top_values():
    """7. Test deterministic ranking and top-value results."""
    df = pd.DataFrame(
        {
            "priority": ["Low", "High", "Medium", "High", "High", "Medium"],
        }
    )
    meta = DatasetMetadata("ds-order-prof", "Order Prof", "pandas", 6, 1, [ColumnMetadata("priority", "priority", "object")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    top_vals = profile.column_statistics["priority"]["most_frequent_values"]

    assert top_vals[0] == {"value": "High", "count": 3}
    assert top_vals[1] == {"value": "Medium", "count": 2}
    assert top_vals[2] == {"value": "Low", "count": 1}


def test_profiling_does_not_mutate_dataset():
    """8. Test that profiling strictly respects the read-only contract on CanonicalDataset."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "name": ["Alpha", "Beta", "Gamma"],
            "score": [95.5, np.nan, 88.0],
        }
    )
    df_snapshot = df.copy(deep=True)

    meta = DatasetMetadata("ds-immutable", "Immutable", "pandas", 3, 3, [
        ColumnMetadata("id", "id", "int64"),
        ColumnMetadata("name", "name", "object"),
        ColumnMetadata("score", "score", "float64"),
    ])
    canonical = CanonicalDataset(meta, df)

    profiler = DataProfiler()
    _ = profiler.profile(canonical, attach=False)

    pd.testing.assert_frame_equal(canonical.data, df_snapshot)
    assert canonical.data["score"].isna().sum() == 1


def test_semantic_role_information_reused_with_profile():
    """9. Test that semantic roles (MEASURE, DIMENSION, DATETIME, IDENTIFIER) integrate seamlessly."""
    df = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4, 5],
            "order_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]),
            "amount": [150.0, 200.0, 75.5, 300.0, 420.0],
            "status": ["Pending", "Shipped", "Shipped", "Delivered", "Delivered"],
        }
    )
    meta = DatasetMetadata("ds-sem-prof", "Sem Prof", "pandas", 5, 4, [
        ColumnMetadata("order_id", "order_id", "int64"),
        ColumnMetadata("order_date", "order_date", "datetime64[ns]"),
        ColumnMetadata("amount", "amount", "float64"),
        ColumnMetadata("status", "status", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    sem_profile = analyze_semantics(canonical)

    assert sem_profile.column_evidences["order_id"].candidate_role.value in ["IDENTIFIER", "DIMENSION"]
    assert sem_profile.column_evidences["order_date"].candidate_role.value == "DATETIME"
    assert sem_profile.column_evidences["amount"].candidate_role.value == "MEASURE"
    assert sem_profile.column_evidences["status"].candidate_role.value == "DIMENSION"


def test_deterministic_output_across_repeated_profiling():
    """10. Test that repeated profiling calls on the same dataset produce identical outputs."""
    df = pd.DataFrame(
        {
            "num": [10, 20, 30, 40, 50],
            "text": ["foo", "bar", "foo", "bar", "baz"],
        }
    )
    meta = DatasetMetadata("ds-repeat", "Repeat", "pandas", 5, 2, [
        ColumnMetadata("num", "num", "int64"),
        ColumnMetadata("text", "text", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    profiler = DataProfiler()
    p1 = profiler.profile(canonical, attach=False)
    p2 = profiler.profile(canonical, attach=False)

    p2.profile_id = p1.profile_id
    p2.generated_at = p1.generated_at

    assert p1.to_dict() == p2.to_dict()
