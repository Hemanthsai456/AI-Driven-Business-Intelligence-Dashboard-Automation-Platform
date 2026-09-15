"""Comprehensive unit tests for the deterministic Data Profiling Engine."""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ingestion import CSVLoader, CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence import DataProfiler, profile_dataset

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_basic_profiling_and_read_only_invariance():
    """Verify basic profiling execution and assert underlying DataFrame is NOT mutated."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "sales": [100.0, 200.5, 300.0, 150.25, 500.0],
            "category": ["A", "B", "A", "C", "B"],
        }
    )
    df_copy = df.copy(deep=True)

    meta = DatasetMetadata(
        dataset_id="ds-prof-test",
        name="Prof Test",
        source_type="pandas",
        row_count=5,
        column_count=3,
        schema=[
            ColumnMetadata("id", "id", "int64", ColumnRole.UNKNOWN),
            ColumnMetadata("sales", "sales", "float64", ColumnRole.UNKNOWN),
            ColumnMetadata("category", "category", "object", ColumnRole.UNKNOWN),
        ],
    )
    canonical = CanonicalDataset(metadata=meta, data=df)

    profiler = DataProfiler()
    profile = profiler.profile(canonical, attach=True)

    # 1. Assert DataFrame is untouched (Read-Only)
    pd.testing.assert_frame_equal(canonical.data, df_copy)

    # 2. Check summary
    assert profile.dataset_summary["row_count"] == 5
    assert profile.dataset_summary["column_count"] == 3
    assert profile.dataset_summary["duplicate_row_count"] == 0
    assert profile.dataset_summary["overall_missing_count"] == 0

    # 3. Check profile attachment and audit log
    assert canonical.profile is profile
    assert any(log["action"] == "PROFILED" for log in canonical.audit_logs)


def test_numeric_statistics():
    """Verify numeric column statistics (min, max, mean, median, std, quantiles, zeros, negatives)."""
    df = pd.DataFrame(
        {
            "num_val": [-10, 0, 10, 20, 30],
        }
    )
    meta = DatasetMetadata("ds-num", "Num Test", "pandas", 5, 1, [ColumnMetadata("num_val", "num_val", "int64")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["num_val"]

    assert stats["min"] == -10
    assert stats["max"] == 30
    assert stats["mean"] == 10.0
    assert stats["median"] == 10.0
    assert stats["zero_count"] == 1
    assert stats["negative_count"] == 1
    assert stats["q25"] == 0.0
    assert stats["q75"] == 20.0
    assert stats["std"] > 0.0


def test_categorical_and_text_statistics():
    """Verify text/categorical statistics including top frequent values and empty string counts."""
    df = pd.DataFrame(
        {
            "dept": ["Sales", "Sales", "Sales", "HR", "HR", "  ", None],
        }
    )
    meta = DatasetMetadata("ds-text", "Text Test", "pandas", 7, 1, [ColumnMetadata("dept", "dept", "object")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["dept"]

    assert stats["null_count"] == 1
    assert stats["empty_string_count"] == 1
    assert len(stats["most_frequent_values"]) > 0
    # Sales appears 3 times, HR appears 2 times
    assert stats["most_frequent_values"][0] == {"value": "Sales", "count": 3}
    assert stats["most_frequent_values"][1] == {"value": "HR", "count": 2}


def test_datetime_statistics():
    """Verify datetime column statistics."""
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-01-01", "2026-01-05", "2026-01-10"]),
        }
    )
    meta = DatasetMetadata("ds-dt", "DT Test", "pandas", 3, 1, [ColumnMetadata("ts", "ts", "datetime64[ns]")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["ts"]

    assert stats["min_datetime"] == "2026-01-01T00:00:00"
    assert stats["max_datetime"] == "2026-01-10T00:00:00"
    assert stats["distinct_dates_count"] == 3


def test_boolean_statistics():
    """Verify boolean column statistics."""
    df = pd.DataFrame(
        {
            "active": [True, True, False, True, False],
        }
    )
    meta = DatasetMetadata("ds-bool", "Bool Test", "pandas", 5, 1, [ColumnMetadata("active", "active", "bool")])
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)
    stats = profile.column_statistics["active"]

    assert stats["true_count"] == 3
    assert stats["false_count"] == 2


def test_edge_cases_all_null_and_constant_columns():
    """Verify all-null, constant, and high-missingness observations."""
    df = pd.DataFrame(
        {
            "all_null": [None, None, None, None],
            "const_col": ["Fixed", "Fixed", "Fixed", "Fixed"],
            "high_null": [10.0, None, None, None],
        }
    )
    meta = DatasetMetadata(
        "ds-edge",
        "Edge Test",
        "pandas",
        4,
        3,
        [
            ColumnMetadata("all_null", "all_null", "object"),
            ColumnMetadata("const_col", "const_col", "object"),
            ColumnMetadata("high_null", "high_null", "float64"),
        ],
    )
    canonical = CanonicalDataset(meta, df)

    profile = profile_dataset(canonical)

    assert "all_null_column" in profile.column_statistics["all_null"]["observations"]
    assert profile.column_statistics["all_null"]["is_all_null"] is True

    assert "constant_column" in profile.column_statistics["const_col"]["observations"]
    assert profile.column_statistics["const_col"]["is_constant"] is True

    assert "high_missingness" in profile.column_statistics["high_null"]["observations"]
    assert len(profile.quality_issues) >= 3


def test_empty_dataset_handling():
    """Verify profiling on empty dataset (0 rows, 0 columns / 0 rows N columns) does not crash."""
    df_empty = pd.DataFrame(columns=["a", "b"])
    meta = DatasetMetadata("ds-empty", "Empty", "pandas", 0, 2, [ColumnMetadata("a", "a", "object"), ColumnMetadata("b", "b", "float64")])
    canonical = CanonicalDataset(meta, df_empty)

    profile = profile_dataset(canonical)
    assert profile.dataset_summary["row_count"] == 0
    assert profile.dataset_summary["column_count"] == 2
    assert profile.column_statistics["a"]["total_count"] == 0


def test_deterministic_repeated_profiling():
    """Verify repeated profiling runs on the same CanonicalDataset produce identical DataProfiles."""
    loader = CSVLoader()
    canonical = loader.load(FIXTURES_DIR / "baseline.csv")

    profiler = DataProfiler()
    p1 = profiler.profile(canonical, attach=False)
    p2 = profiler.profile(canonical, attach=False)

    # Force identical profile_id & timestamp for direct dictionary equality assertion
    p2.profile_id = p1.profile_id
    p2.generated_at = p1.generated_at

    assert p1.to_dict() == p2.to_dict()


def test_profile_json_serialization():
    """Verify profile.to_dict() passes json.dumps() without serialization exceptions."""
    loader = CSVLoader()
    canonical = loader.load(FIXTURES_DIR / "missing_values.csv")

    profile = profile_dataset(canonical)
    profile_dict = profile.to_dict()

    json_str = json.dumps(profile_dict)
    assert isinstance(json_str, str)
    assert "dataset_summary" in profile_dict
    assert "column_statistics" in profile_dict
