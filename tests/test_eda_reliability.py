"""Targeted Regression and Reliability Tests for EDA Engine and API Endpoints.

Tests all requirements from Phase 1, Phase 2, and Phase 3:
1. Issue A: Datetime columns safe classification (no TypeError: dtype bool cannot be converted to datetime64[ns])
2. Issue B: Distribution explore endpoint returns distribution_type, category, bin_label, count, and summary
3. Numeric-only dataset
4. Categorical-only dataset
5. Boolean columns (native bool, nullable boolean, object bool)
6. Datetime columns (tz-naive, tz-aware, text date fallback)
7. Mixed object columns (numbers + strings)
8. Missing values, all-null columns, and 0-row empty datasets
9. Constant columns (zero variance)
10. High-cardinality categorical columns
11. Non-finite numeric values (inf, -inf)
12. Small vs large sampled datasets (> 1000 rows)
13. Cleaned dataset active schema resolution via API
14. Controlled responses on unsupported/invalid chart configurations
"""

import math
from typing import Optional
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, DatasetMetadata
from intelligence.eda import EDAEngine, EDASummary
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics


@pytest.fixture(autouse=True)
def clean_session():
    """Ensure session store is cleared before each test."""
    session_store.clear()
    yield
    session_store.clear()


def create_canonical(df: pd.DataFrame, dataset_id: str = "ds_test_rel") -> CanonicalDataset:
    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=f"{dataset_id}.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
    )
    return CanonicalDataset(metadata=meta, data=df)


# ============================================================================
# PHASE 1 — ISSUE A REGRESSION: DATETIME COLUMN SAFETY
# ============================================================================

def test_issue_a_datetime_column_does_not_crash_summary():
    """Verify datetime columns never trigger TypeError in Boolean detection."""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="D"),
        "sales": [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 550.0],
        "is_active": [True, False, True, False, True, False, True, False, True, False],
        "region": ["North", "South", "East", "West", "North", "South", "East", "West", "North", "South"],
    })
    canonical = create_canonical(df, "ds_issue_a")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary is not None
    assert "timestamp" in summary.temporal_analysis["datetime_column"]
    assert summary.dataset_summary["datetime_columns_count"] == 1
    assert summary.dataset_summary["boolean_columns_count"] == 1
    assert summary.dataset_summary["numeric_columns_count"] == 1
    assert summary.dataset_summary["categorical_columns_count"] == 1


def test_issue_a_tz_aware_datetime_column_safe():
    """Verify timezone-aware datetime column is handled cleanly without PeriodIndex crash."""
    df = pd.DataFrame({
        "utc_time": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
        "val": [10, 20, 30, 40, 50],
    })
    canonical = create_canonical(df, "ds_tz_aware")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary.temporal_analysis is not None
    assert summary.temporal_analysis["is_available"] is True
    assert summary.temporal_analysis["datetime_column"] == "utc_time"


def test_issue_a_all_null_datetime_column():
    """Verify an all-null datetime column does not raise an exception."""
    df = pd.DataFrame({
        "dt_null": pd.Series([pd.NaT, pd.NaT, pd.NaT], dtype="datetime64[ns]"),
        "val": [1, 2, 3],
    })
    canonical = create_canonical(df, "ds_null_dt")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary.dataset_summary["datetime_columns_count"] == 1
    assert summary.dataset_summary["row_count"] == 3


# ============================================================================
# PHASE 1 — ISSUE B REGRESSION: DISTRIBUTION HISTOGRAM CONTRACT & RENDERING
# ============================================================================

def test_issue_b_numeric_distribution_returns_distribution_type_and_category():
    """Verify explore() distribution returns distribution_type='numeric' and both category and bin_label."""
    df = pd.DataFrame({
        "sales": [10.5, 25.0, 30.2, 45.8, 55.1, 70.0, 85.3, 100.0, 115.4, 130.0],
    })
    canonical = create_canonical(df, "ds_issue_b")
    engine = EDAEngine()
    res = engine.explore(canonical, chart_type="distribution", x_column="sales")

    assert res["is_supported"] is True
    assert res["chart_type"] == "distribution"
    assert res["distribution_type"] == "numeric"
    assert "data" in res
    assert len(res["data"]) > 0

    for row in res["data"]:
        assert "bin_label" in row, "Missing bin_label for Recharts numeric axis"
        assert "category" in row, "Missing category alias for Recharts axis compatibility"
        assert "count" in row
        assert "value" in row
        assert "bin_start" in row
        assert "bin_end" in row
        assert row["bin_label"] == row["category"]

    # Verify summary metrics are populated
    assert "summary" in res
    assert res["summary"]["mean"] is not None
    assert res["summary"]["median"] is not None


def test_issue_b_constant_column_distribution():
    """Verify constant numeric column (zero variance) produces a valid single-bin histogram."""
    df = pd.DataFrame({
        "constant_col": [42.0] * 50,
    })
    canonical = create_canonical(df, "ds_constant_dist")
    engine = EDAEngine()
    res = engine.explore(canonical, chart_type="distribution", x_column="constant_col")

    assert res["is_supported"] is True
    assert res["distribution_type"] == "numeric"
    assert len(res["data"]) == 1
    assert res["data"][0]["count"] == 50
    assert res["data"][0]["percentage"] == 100.0
    assert "bin_label" in res["data"][0]
    assert "category" in res["data"][0]


def test_issue_b_categorical_column_distribution_fallback():
    """Verify selecting a categorical column for distribution returns categorical frequency breakdown."""
    df = pd.DataFrame({
        "category": ["Electronics", "Clothing", "Electronics", "Groceries", "Clothing", "Clothing"],
    })
    canonical = create_canonical(df, "ds_cat_dist")
    engine = EDAEngine()
    res = engine.explore(canonical, chart_type="distribution", x_column="category")

    assert res["is_supported"] is True
    assert res["distribution_type"] == "categorical"
    assert len(res["data"]) == 3
    # Most frequent category first
    assert res["data"][0]["category"] == "Clothing"
    assert res["data"][0]["count"] == 3
    assert "bin_label" in res["data"][0]
    assert res["data"][0]["bin_label"] == "Clothing"


# ============================================================================
# PHASE 3 — DATASET DIVERSITY AUDIT TESTS
# ============================================================================

def test_numeric_only_dataset():
    """Verify dataset with purely numeric columns functions smoothly."""
    df = pd.DataFrame({
        "metric_a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "metric_b": [10.0, 20.0, 15.0, 30.0, 25.0],
        "metric_c": [100.0, 95.0, 90.0, 85.0, 80.0],
    })
    canonical = create_canonical(df, "ds_numeric_only")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary.dataset_summary["numeric_columns_count"] == 3
    assert summary.dataset_summary["categorical_columns_count"] == 0
    assert summary.dataset_summary["datetime_columns_count"] == 0
    assert len(summary.numeric_distributions) == 3
    assert summary.correlation_analysis["is_available"] is True
    assert summary.correlation_analysis["status"] == "SUCCESS"


def test_categorical_only_dataset():
    """Verify dataset with purely categorical columns functions gracefully."""
    df = pd.DataFrame({
        "country": ["USA", "Canada", "UK", "Germany", "France"],
        "plan": ["Free", "Pro", "Enterprise", "Pro", "Free"],
        "status": ["Active", "Pending", "Active", "Inactive", "Active"],
    })
    canonical = create_canonical(df, "ds_cat_only")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary.dataset_summary["categorical_columns_count"] == 3
    assert summary.dataset_summary["numeric_columns_count"] == 0
    assert len(summary.categorical_distributions) == 3
    assert summary.correlation_analysis["is_available"] is False
    assert summary.correlation_analysis["status"] == "INSUFFICIENT_NUMERIC_COLUMNS"


def test_boolean_columns_profiling():
    """Verify native bool, pandas nullable boolean, and object bool columns."""
    df = pd.DataFrame({
        "native_bool": [True, False, True, True],
        "nullable_bool": pd.Series([True, None, False, True], dtype="boolean"),
        "object_bool": pd.Series([True, False, True, False], dtype=object),
    })
    canonical = create_canonical(df, "ds_bools")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary.dataset_summary["boolean_columns_count"] == 3
    # Check that boolean columns are also profiled in categorical_distributions
    cat_names = [d["column_name"] for d in summary.categorical_distributions]
    assert "native_bool" in cat_names
    assert "nullable_bool" in cat_names
    assert "object_bool" in cat_names


def test_mixed_object_column():
    """Verify object column containing mixed numbers, strings, and nulls."""
    df = pd.DataFrame({
        "mixed_col": [100, "N/A", 250, "Pending", None, 300],
        "score": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    })
    canonical = create_canonical(df, "ds_mixed")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    assert summary.dataset_summary["categorical_columns_count"] == 1
    assert summary.dataset_summary["numeric_columns_count"] == 1


def test_all_null_and_empty_dataset():
    """Verify empty dataset and all-null columns do not crash."""
    # 1. 0-row empty dataframe
    df_empty = pd.DataFrame({"col_a": [], "col_b": []})
    canonical_empty = create_canonical(df_empty, "ds_empty")
    engine = EDAEngine()
    summary_empty = engine.generate_summary(canonical_empty)
    assert summary_empty.dataset_summary["row_count"] == 0
    assert summary_empty.dataset_summary["column_count"] == 2

    # 2. Explore on empty dataset
    res_empty = engine.explore(canonical_empty, chart_type="distribution", x_column="col_a")
    assert res_empty["is_supported"] is False
    assert "0 rows" in res_empty["error_message"]

    # 3. All-null columns
    df_nulls = pd.DataFrame({
        "null_num": [np.nan, np.nan, np.nan],
        "null_cat": [None, None, None],
    })
    canonical_nulls = create_canonical(df_nulls, "ds_nulls")
    summary_nulls = engine.generate_summary(canonical_nulls)
    assert summary_nulls.dataset_summary["missing_cells_percentage"] == 100.0


def test_non_finite_numeric_values():
    """Verify numeric columns with inf and -inf values are handled safely."""
    df = pd.DataFrame({
        "with_infs": [1.0, np.inf, 3.0, -np.inf, 5.0, 6.0],
        "normal": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    })
    canonical = create_canonical(df, "ds_infs")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    dist = next(d for d in summary.numeric_distributions if d["column_name"] == "with_infs")
    assert dist["mean"] is not None
    assert not math.isinf(dist["mean"])
    assert len(dist["histogram"]) > 0

    # Explore distribution handles infs safely
    res = engine.explore(canonical, chart_type="distribution", x_column="with_infs")
    assert res["is_supported"] is True
    assert res["distribution_type"] == "numeric"


def test_high_cardinality_categorical_column():
    """Verify categorical column with 200 distinct values is flagged as high cardinality."""
    df = pd.DataFrame({
        "high_card": [f"ID_{i}" for i in range(200)],
        "val": list(range(200)),
    })
    canonical = create_canonical(df, "ds_high_card")
    engine = EDAEngine()
    summary = engine.generate_summary(canonical)

    cat_dist = next(d for d in summary.categorical_distributions if d["column_name"] == "high_card")
    assert cat_dist["is_high_cardinality"] is True
    assert len(cat_dist["top_categories"]) <= 10


def test_large_dataset_sampling_scatter():
    """Verify scatter plot applies deterministic sampling for > 1000 points."""
    np.random.seed(42)
    n = 2500
    df = pd.DataFrame({
        "x_val": np.random.normal(50, 15, n),
        "y_val": np.random.normal(100, 25, n),
    })
    canonical = create_canonical(df, "ds_large_scatter")
    engine = EDAEngine()
    res = engine.explore(canonical, chart_type="scatter", x_column="x_val", y_column="y_val")

    assert res["is_supported"] is True
    assert res["is_sampled"] is True
    assert res["rendered_points"] <= 1000
    assert len(res["data"]) <= 1000


def test_unsupported_and_invalid_chart_configurations():
    """Verify clear, controlled responses for invalid combinations."""
    df = pd.DataFrame({
        "cat": ["A", "B", "C"],
        "num": [10, 20, 30],
    })
    canonical = create_canonical(df, "ds_invalid")
    engine = EDAEngine()

    # 1. Scatter without Y column
    res1 = engine.explore(canonical, chart_type="scatter", x_column="num")
    assert res1["is_supported"] is False
    assert "requires both" in res1["error_message"]

    # 2. Scatter with non-numeric column
    res2 = engine.explore(canonical, chart_type="scatter", x_column="num", y_column="cat")
    assert res2["is_supported"] is False
    assert "numeric" in res2["error_message"]

    # 3. Non-existent column
    res3 = engine.explore(canonical, chart_type="bar", x_column="missing_col")
    assert res3["is_supported"] is False
    assert "does not exist" in res3["error_message"]

    # 4. Unknown chart type
    res4 = engine.explore(canonical, chart_type="radar", x_column="cat")
    assert res4["is_supported"] is False
    assert "Unsupported chart type" in res4["error_message"]


# ============================================================================
# API INTEGRATION & CLEANED DATASET RESOLUTION
# ============================================================================

def test_api_eda_summary_and_explore_use_cleaned_dataset():
    """Verify GET /api/datasets/{id}/eda and POST /api/datasets/{id}/eda/explore use cleaned dataset when active."""
    raw_df = pd.DataFrame({
        "drop_me": [1, 2, 3, 4],
        "keep_me": [10, 20, 30, 40],
    })
    cleaned_df = pd.DataFrame({
        "keep_me": [10, 20, 30, 40],
    })

    raw_canon = create_canonical(raw_df, "ds_clean_test")
    cleaned_canon = create_canonical(cleaned_df, "ds_clean_test_cleaned")

    record = DatasetSessionRecord(
        dataset=raw_canon,
        profile=None,
        semantic_profile=None,
        readiness=None,
    )
    record.cleaned_dataset = cleaned_canon
    session_store.save(record)

    client = TestClient(app)

    # 1. GET /api/datasets/{id}/eda must reflect cleaned dataset (1 column, not 2)
    res_summary = client.get("/api/datasets/ds_clean_test/eda")
    assert res_summary.status_code == 200
    summary_data = res_summary.json()
    assert summary_data["dataset_summary"]["column_count"] == 1
    num_cols = [d["column_name"] for d in summary_data["numeric_distributions"]]
    assert "keep_me" in num_cols
    assert "drop_me" not in num_cols

    # 2. POST explore on dropped column should fail as non-existent in cleaned dataset
    res_explore_dropped = client.post(
        "/api/datasets/ds_clean_test/eda/explore",
        json={"chart_type": "distribution", "x_column": "drop_me"},
    )
    assert res_explore_dropped.status_code == 200
    assert res_explore_dropped.json()["is_supported"] is False
    assert "does not exist" in res_explore_dropped.json()["error_message"]

    # 3. POST explore on active cleaned column succeeds
    res_explore_active = client.post(
        "/api/datasets/ds_clean_test/eda/explore",
        json={"chart_type": "distribution", "x_column": "keep_me"},
    )
    assert res_explore_active.status_code == 200
    explore_json = res_explore_active.json()
    assert explore_json["is_supported"] is True
    assert explore_json["distribution_type"] == "numeric"
    assert len(explore_json["data"]) > 0
    assert "category" in explore_json["data"][0]
    assert "bin_label" in explore_json["data"][0]
