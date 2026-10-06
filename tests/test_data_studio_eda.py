"""Targeted Unit & Integration Tests for Data Studio Exploratory Data Analysis (EDA) Engine.

Validates:
1. Automated EDA summary structure and metrics
2. Numeric distributions (mean, median, std, min, max, 10-bin histogram, skewness)
3. Categorical frequency analysis & top 10 truncation
4. Pearson correlation matrix calculation
5. Insufficient numeric columns (< 2) graceful handling
6. Datetime analysis & temporal span calculation
7. Temporal chronological ordering guarantee
8. Numeric x numeric scatter exploration & correlation
9. Categorical x numeric bar exploration & aggregation
10. Invalid chart combination rejection & error reporting
11. Empty dataset handling
12. Constant numeric column handling (zero variance)
13. Deterministic repeated EDA output guarantee
14. Deterministic sampling for large datasets (> 1000 rows)
15. Automated observations are evidence-grounded
16. Raw dataset remains 100% unchanged (read-only immutability)
17. Cleaned dataset can be analyzed separately
18. Dataset session isolation
"""

import copy
from typing import Optional
import pandas as pd
import numpy as np
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


def make_test_dataset(
    dataset_id: str = "ds_test_eda",
    name: str = "test_eda.csv",
    data: Optional[pd.DataFrame] = None,
) -> CanonicalDataset:
    if data is None:
        data = pd.DataFrame({
            "age": [25, 30, 35, 40, 45, 50, 55, 60],
            "salary": [50000, 60000, 75000, 80000, 95000, 110000, 120000, 135000],
            "department": ["Engineering", "Engineering", "Sales", "Sales", "HR", "HR", "Marketing", "Marketing"],
            "join_date": ["2022-01-15", "2022-03-20", "2022-06-10", "2022-08-05", "2023-01-10", "2023-04-12", "2023-09-01", "2023-11-20"],
        })

    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=name,
        source_type="csv",
        row_count=len(data),
        column_count=len(data.columns),
    )
    return CanonicalDataset(metadata=meta, data=data)


def test_1_automated_eda_summary():
    """Test automated EDA summary generation with complete structure."""
    ds = make_test_dataset()
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    assert isinstance(summary, EDASummary)
    d = summary.to_dict()

    assert d["dataset_id"] == "ds_test_eda"
    assert d["dataset_summary"]["row_count"] == 8
    assert d["dataset_summary"]["column_count"] == 4
    assert d["dataset_summary"]["numeric_columns_count"] == 2
    assert d["dataset_summary"]["categorical_columns_count"] == 1
    assert d["dataset_summary"]["datetime_columns_count"] == 1
    assert len(d["numeric_distributions"]) == 2
    assert len(d["categorical_distributions"]) == 1
    assert d["correlation_analysis"]["is_available"] is True
    assert d["temporal_analysis"]["is_available"] is True
    assert len(d["automated_observations"]) > 0


def test_2_numeric_distribution():
    """Test numeric distribution calculations: mean, median, min, max, std, skewness, 10-bin histogram."""
    ds = make_test_dataset()
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    age_dist = next(d for d in summary.numeric_distributions if d["column_name"] == "age")
    assert age_dist["min"] == 25
    assert age_dist["max"] == 60
    assert age_dist["mean"] == 42.5
    assert age_dist["median"] == 42.5
    assert age_dist["std"] > 0
    assert "histogram" in age_dist
    assert len(age_dist["histogram"]) > 0
    assert "distribution_shape" in age_dist


def test_3_categorical_frequency_analysis():
    """Test categorical frequency analysis and top 10 truncation."""
    df = pd.DataFrame({
        "category": [f"Cat_{i}" for i in range(25)] * 2,
        "score": list(range(50)),
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    cat_dist = next(d for d in summary.categorical_distributions if d["column_name"] == "category")
    assert cat_dist["distinct_count"] == 25
    assert cat_dist["is_high_cardinality"] is True
    assert len(cat_dist["top_categories"]) <= 10
    assert cat_dist["top_categories"][0]["count"] == 2


def test_4_correlation_matrix():
    """Test Pearson correlation matrix calculation between numeric columns."""
    ds = make_test_dataset()
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    corr = summary.correlation_analysis
    assert corr["is_available"] is True
    assert "age" in corr["matrix"]
    assert "salary" in corr["matrix"]["age"]
    # Age and Salary are perfectly positively correlated (r ~ 1.0)
    assert corr["matrix"]["age"]["salary"] > 0.95
    assert len(corr["strong_pairs"]) > 0
    assert corr["strong_pairs"][0]["strength"] == "Strong"
    assert corr["strong_pairs"][0]["direction"] == "Positive"


def test_5_insufficient_numeric_columns():
    """Test graceful handling when dataset has fewer than 2 usable numeric columns."""
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie"],
        "city": ["New York", "Boston", "Chicago"],
        "age": [25, 30, 35],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    corr = summary.correlation_analysis
    assert corr["is_available"] is False
    assert "at least two" in corr["message"]
    assert corr["matrix"] == {}


def test_6_datetime_analysis():
    """Test datetime analysis and temporal span calculation."""
    ds = make_test_dataset()
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    temp = summary.temporal_analysis
    assert temp["is_available"] is True
    assert temp["datetime_column"] == "join_date"
    assert temp["earliest_date"] == "2022-01-15"
    assert temp["latest_date"] == "2023-11-20"
    assert temp["temporal_span_days"] > 600
    assert len(temp["series"]) > 0


def test_7_temporal_chronological_ordering():
    """Test that time-series analysis series is strictly ordered chronologically."""
    df = pd.DataFrame({
        "timestamp": ["2023-12-01", "2021-05-01", "2022-08-01", "2020-01-01"],
        "value": [100, 20, 50, 10],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    temp = summary.temporal_analysis
    assert temp["is_available"] is True
    periods = [item["period"] for item in temp["series"]]
    assert periods == sorted(periods)


def test_8_numeric_x_numeric_exploration():
    """Test manual bivariate scatter plot generation for numeric x numeric."""
    ds = make_test_dataset()
    engine = EDAEngine()
    res = engine.explore(
        canonical=ds,
        chart_type="scatter",
        x_column="age",
        y_column="salary",
        group_by="department",
    )

    assert res["is_supported"] is True
    assert res["chart_type"] == "scatter"
    assert res["total_points"] == 8
    assert res["rendered_points"] == 8
    assert res["is_sampled"] is False
    assert res["correlation"] is not None
    assert len(res["data"]) == 8
    assert "x" in res["data"][0]
    assert "y" in res["data"][0]
    assert "group" in res["data"][0]


def test_9_categorical_x_numeric_exploration():
    """Test manual grouped bar exploration for categorical x numeric."""
    ds = make_test_dataset()
    engine = EDAEngine()
    res = engine.explore(
        canonical=ds,
        chart_type="bar",
        x_column="department",
        y_column="salary",
        aggregation="mean",
    )

    assert res["is_supported"] is True
    assert res["chart_type"] == "bar"
    assert len(res["data"]) == 4  # 4 distinct departments
    assert "category" in res["data"][0]
    assert "value" in res["data"][0]


def test_10_invalid_chart_combination_rejected():
    """Test that invalid combinations return clear, helpful error states."""
    ds = make_test_dataset()
    engine = EDAEngine()

    # Scatter with non-numeric column
    res1 = engine.explore(
        canonical=ds,
        chart_type="scatter",
        x_column="department",
        y_column="salary",
    )
    assert res1["is_supported"] is False
    assert "must contain numeric" in res1["error_message"]

    # Line chart with non-date column
    res2 = engine.explore(
        canonical=ds,
        chart_type="line",
        x_column="department",
        y_column="salary",
    )
    assert res2["is_supported"] is False
    assert "must contain valid date" in res2["error_message"]

    # Non-existent column
    res3 = engine.explore(
        canonical=ds,
        chart_type="scatter",
        x_column="non_existent",
        y_column="salary",
    )
    assert res3["is_supported"] is False
    assert "does not exist" in res3["error_message"]


def test_11_empty_dataset_handling():
    """Test graceful handling of an empty (0 rows) dataset."""
    df_empty = pd.DataFrame(columns=["col_a", "col_b"])
    ds = make_test_dataset(data=df_empty)
    engine = EDAEngine()

    summary = engine.generate_summary(ds)
    assert summary.dataset_summary["row_count"] == 0
    assert summary.correlation_analysis["is_available"] is False

    explore_res = engine.explore(canonical=ds, chart_type="scatter", x_column="col_a", y_column="col_b")
    assert explore_res["is_supported"] is False
    assert "0 rows" in explore_res["error_message"]


def test_12_constant_numeric_column_handling():
    """Test constant numeric column with zero variance does not crash correlation."""
    df = pd.DataFrame({
        "constant_col": [10, 10, 10, 10, 10],
        "varying_col": [1, 2, 3, 4, 5],
        "other_varying": [10, 20, 30, 40, 50],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    corr = summary.correlation_analysis
    # Constant column has std = 0, so only varying_col and other_varying are usable
    assert "constant_col" not in corr["columns"]
    assert "varying_col" in corr["columns"]
    assert "other_varying" in corr["columns"]
    assert corr["is_available"] is True


def test_13_deterministic_repeated_eda():
    """Test that repeatedly generating EDA produces identical deterministic output."""
    ds = make_test_dataset()
    engine = EDAEngine()

    sum1 = engine.generate_summary(ds).to_dict()
    sum2 = engine.generate_summary(ds).to_dict()

    assert sum1 == sum2


def test_14_deterministic_sampling_large_dataset():
    """Test that datasets with > 1,000 points are deterministically sampled."""
    np.random.seed(42)
    n = 2500
    df_large = pd.DataFrame({
        "x_val": np.linspace(1, 100, n),
        "y_val": np.linspace(10, 500, n) + np.sin(np.linspace(1, 100, n)),
    })
    ds = make_test_dataset(data=df_large)
    engine = EDAEngine()

    res1 = engine.explore(canonical=ds, chart_type="scatter", x_column="x_val", y_column="y_val")
    res2 = engine.explore(canonical=ds, chart_type="scatter", x_column="x_val", y_column="y_val")

    assert res1["is_sampled"] is True
    assert res1["total_points"] == 2500
    assert res1["rendered_points"] <= 1000
    assert res1["data"] == res2["data"]


def test_15_automated_observations_are_evidence_grounded():
    """Test that all automated observations are backed by concrete statistical evidence."""
    ds = make_test_dataset()
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    observations = summary.automated_observations
    assert len(observations) >= 2

    for obs in observations:
        assert "id" in obs
        assert "category" in obs
        assert "text" in obs
        assert "evidence" in obs
        assert isinstance(obs["evidence"], dict)
        assert len(obs["evidence"]) > 0
        # No prohibited causal words
        assert "causes" not in obs["text"].lower()
        assert "because of" not in obs["text"].lower()


def test_16_raw_dataset_remains_unchanged():
    """Test that EDA engine strictly never mutates the raw dataset DataFrame or metadata."""
    ds = make_test_dataset()
    original_df_copy = ds.data.copy(deep=True)
    original_meta_dict = ds.metadata.to_dict()

    engine = EDAEngine()
    _ = engine.generate_summary(ds)
    _ = engine.explore(canonical=ds, chart_type="scatter", x_column="age", y_column="salary")
    _ = engine.explore(canonical=ds, chart_type="line", x_column="join_date", y_column="salary")
    _ = engine.explore(canonical=ds, chart_type="bar", x_column="department", y_column="salary")

    pd.testing.assert_frame_equal(ds.data, original_df_copy)
    assert ds.metadata.to_dict() == original_meta_dict


def test_17_cleaned_dataset_analyzed_separately():
    """Test that cleaned datasets can be registered and analyzed independently in EDA."""
    ds_raw = make_test_dataset(dataset_id="ds_raw", name="raw.csv", data=pd.DataFrame({
        "val": [10, 20, None, 40],
        "cat": ["A", "B", "C", "D"],
    }))
    ds_cleaned = make_test_dataset(dataset_id="ds_cleaned", name="raw_cleaned.csv", data=pd.DataFrame({
        "val": [10, 20, 25, 40],
        "cat": ["A", "B", "C", "D"],
    }))

    engine = EDAEngine()
    summary_raw = engine.generate_summary(ds_raw)
    summary_cleaned = engine.generate_summary(ds_cleaned)

    # Raw has 1 missing value (25%), cleaned has 0 missing
    assert summary_raw.dataset_summary["missing_cells_count"] == 1
    assert summary_cleaned.dataset_summary["missing_cells_count"] == 0


def test_18_dataset_isolation_via_api():
    """Test full HTTP API integration and session isolation across distinct datasets."""
    client = TestClient(app)

    ds1 = make_test_dataset(dataset_id="ds_iso_1", name="dataset1.csv")
    ds2 = make_test_dataset(dataset_id="ds_iso_2", name="dataset2.csv", data=pd.DataFrame({
        "temperature": [20.5, 22.1, 24.8, 19.3],
        "humidity": [60, 65, 55, 70],
    }))

    prof1 = profile_dataset(ds1)
    sem1 = analyze_semantics(ds1, profile=prof1)
    record1 = DatasetSessionRecord(dataset=ds1, profile=prof1, semantic_profile=sem1, readiness=None)
    session_store.save(record1)

    prof2 = profile_dataset(ds2)
    sem2 = analyze_semantics(ds2, profile=prof2)
    record2 = DatasetSessionRecord(dataset=ds2, profile=prof2, semantic_profile=sem2, readiness=None)
    session_store.save(record2)

    # Fetch EDA for Dataset 1
    resp1 = client.get("/api/datasets/ds_iso_1/eda")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["dataset_id"] == "ds_iso_1"
    assert data1["dataset_summary"]["column_count"] == 4

    # Fetch EDA for Dataset 2
    resp2 = client.get("/api/datasets/ds_iso_2/eda")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["dataset_id"] == "ds_iso_2"
    assert data2["dataset_summary"]["column_count"] == 2

    # Explore Endpoint for Dataset 2
    exp_resp = client.post(
        "/api/datasets/ds_iso_2/eda/explore",
        json={
            "chart_type": "scatter",
            "x_column": "temperature",
            "y_column": "humidity",
        },
    )
    assert exp_resp.status_code == 200
    exp_data = exp_resp.json()
    assert exp_data["is_supported"] is True
    assert exp_data["total_points"] == 4


def test_19_canonical_five_real_datasets_eda():
    """Verify automated EDA on the five canonical benchmark datasets without hardcoding."""
    import os
    from ingestion.loaders import load_dataset

    canonical_files = [
        "healthcare.csv",
        "education.csv",
        "iot.csv",
        "hr.csv",
        "logistics.csv",
    ]

    engine = EDAEngine()

    for filename in canonical_files:
        filepath = os.path.join("tests", "real_data", filename)
        if not os.path.exists(filepath):
            continue

        canonical = load_dataset(filepath)
        prof = profile_dataset(canonical)
        sem = analyze_semantics(canonical, profile=prof)

        summary = engine.generate_summary(canonical, profile=prof, semantic_profile=sem)

        assert summary.dataset_id is not None
        assert summary.dataset_summary["row_count"] > 0
        assert summary.dataset_summary["column_count"] > 0
        assert len(summary.automated_observations) > 0

        # Verify no causal language in observations
        for obs in summary.automated_observations:
            assert "causes" not in obs["text"].lower()
            assert "evidence" in obs


def test_20_numeric_distribution_valid_skew():
    """Targeted Test 1: Numeric distribution with valid skew information and canonical fields."""
    df = pd.DataFrame({
        "skewed_right": [1, 2, 2, 3, 3, 3, 10, 50, 100],
        "skewed_left": [100, 99, 98, 97, 95, 90, 50, 10, 1],
        "symmetric": [10, 20, 30, 40, 50, 60, 70, 80, 90],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    dist_map = {d["column_name"]: d for d in summary.numeric_distributions}

    # Right skewed check
    r = dist_map["skewed_right"]
    assert r["skew_label"] == "Right-skewed"
    assert r["distribution_shape"] == "Right-skewed"
    assert r["skewness"] is not None and r["skewness"] > 0.5
    assert r["q1"] is not None and r["q3"] is not None
    assert r["q25"] == r["q1"] and r["q75"] == r["q3"]
    assert r["row_count"] == 9
    assert r["non_null_count"] == 9
    assert len(r["histogram"]) > 0
    assert "bin_label" in r["histogram"][0]
    assert "percentage" in r["histogram"][0]

    # Left skewed check
    l = dist_map["skewed_left"]
    assert l["skew_label"] == "Left-skewed"
    assert l["distribution_shape"] == "Left-skewed"
    assert l["skewness"] is not None and l["skewness"] < -0.5

    # Symmetric check
    s = dist_map["symmetric"]
    assert "Symmetric" in s["skew_label"]
    assert "Symmetric" in s["distribution_shape"]


def test_21_numeric_distribution_unavailable_null_skew():
    """Targeted Test 2: Numeric distribution where skew information is unavailable/null."""
    df = pd.DataFrame({
        "all_null": [np.nan, np.nan, np.nan, np.nan],
        "constant": [42.0, 42.0, 42.0, 42.0],
        "two_points": [10.0, 20.0, np.nan, np.nan],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    dist_map = {d["column_name"]: d for d in summary.numeric_distributions}

    # All null column
    an = dist_map["all_null"]
    assert an["skewness"] is None
    assert an["skew_label"] == "All Null"
    assert an["distribution_shape"] == "All Null"
    assert an["mean"] is None
    assert an["median"] is None
    assert an["std"] is None
    assert an["min"] is None
    assert an["max"] is None
    assert an["q1"] is None
    assert an["q3"] is None
    assert an["non_null_count"] == 0
    assert an["histogram"] == []

    # Constant column (zero variance, std = 0)
    c = dist_map["constant"]
    assert c["skewness"] is None
    assert c["skew_label"] == "Symmetric"  # Zero variance fallback
    assert c["std"] == 0.0
    assert c["min"] == 42.0
    assert c["max"] == 42.0
    assert len(c["histogram"]) == 1
    assert c["histogram"][0]["percentage"] == 100.0

    # Two points (n < 3 for skew calculation)
    tp = dist_map["two_points"]
    assert tp["skewness"] is None
    assert tp["skew_label"] == "Symmetric"
    assert tp["non_null_count"] == 2


def test_22_dataset_with_no_numeric_columns():
    """Targeted Test 3: Dataset with zero numeric columns."""
    df = pd.DataFrame({
        "country": ["USA", "Canada", "Mexico", "UK"],
        "is_active": [True, False, True, False],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    assert summary.dataset_summary["numeric_columns_count"] == 0
    assert len(summary.numeric_distributions) == 0
    assert summary.correlation_analysis["is_available"] is False
    assert summary.correlation_analysis["status"] == "INSUFFICIENT_NUMERIC_COLUMNS"
    assert summary.correlation_analysis["columns"] == []
    assert summary.correlation_analysis["matrix"] == {}


def test_23_dataset_with_categorical_only_columns():
    """Targeted Test 4: Dataset with categorical-only columns."""
    df = pd.DataFrame({
        "category": ["Alpha", "Beta", "Gamma", "Delta", "Alpha"],
        "status": ["Active", "Pending", "Active", "Closed", "Active"],
        "region": ["North", "South", "East", "West", "North"],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    assert summary.dataset_summary["numeric_columns_count"] == 0
    assert summary.dataset_summary["categorical_columns_count"] == 3
    assert len(summary.categorical_distributions) == 3
    for cat_dist in summary.categorical_distributions:
        assert cat_dist["distinct_count"] > 0
        assert len(cat_dist["top_categories"]) > 0
        # Check both category and value fields exist
        for top in cat_dist["top_categories"]:
            assert "category" in top
            assert "value" in top
            assert "percentage" in top


def test_24_dataset_with_datetime_columns():
    """Targeted Test 5: Dataset with datetime columns and temporal analysis."""
    df = pd.DataFrame({
        "timestamp": ["2023-01-01", "2023-02-01", "2023-03-01", "2023-04-01"],
        "metric": [100.0, 150.0, 200.0, 250.0],
    })
    ds = make_test_dataset(data=df)
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    assert summary.dataset_summary["datetime_columns_count"] == 1
    temp = summary.temporal_analysis
    assert temp is not None
    assert temp["is_available"] is True
    assert temp["datetime_column"] == "timestamp"
    assert temp["measure_column"] == "metric"
    assert temp["earliest_date"] == "2023-01-01"
    assert temp["latest_date"] == "2023-04-01"
    assert "date_range" in temp
    assert temp["date_range"]["min_date"] == "2023-01-01"
    assert temp["date_range"]["max_date"] == "2023-04-01"
    assert "trend_direction" in temp
    assert temp["trend_direction"] == "Upward"
    assert len(temp["data_points"]) == 4
    assert len(temp["series"]) == 4


def test_25_normal_mixed_dataset():
    """Targeted Test 6: Normal mixed dataset validating complete frontend/backend contract."""
    ds = make_test_dataset()
    engine = EDAEngine()
    summary = engine.generate_summary(ds)

    d = summary.to_dict()

    # 1. Dataset summary
    assert d["dataset_summary"]["row_count"] == 8
    assert d["dataset_summary"]["column_count"] == 4
    assert d["dataset_summary"]["numeric_columns_count"] == 2
    assert d["dataset_summary"]["categorical_columns_count"] == 1
    assert d["dataset_summary"]["datetime_columns_count"] == 1

    # 2. Numeric distributions contract
    for num in d["numeric_distributions"]:
        assert isinstance(num["column_name"], str)
        assert isinstance(num["skew_label"], str)
        assert isinstance(num["distribution_shape"], str)
        assert "q1" in num and "q3" in num
        assert "q25" in num and "q75" in num
        assert "row_count" in num and "non_null_count" in num
        for bin_item in num["histogram"]:
            assert "bin_label" in bin_item
            assert "percentage" in bin_item

    # 3. Categorical distributions contract
    for cat in d["categorical_distributions"]:
        assert isinstance(cat["column_name"], str)
        assert isinstance(cat["distinct_count"], int)
        for top in cat["top_categories"]:
            assert "category" in top
            assert "value" in top
            assert "count" in top
            assert "percentage" in top

    # 4. Correlation contract
    assert d["correlation_analysis"]["is_available"] is True
    assert "top_correlated_pairs" in d["correlation_analysis"]
    assert "strong_pairs" in d["correlation_analysis"]

    # 5. Temporal contract
    assert d["temporal_analysis"]["is_available"] is True
    assert "date_range" in d["temporal_analysis"]
    assert "data_points" in d["temporal_analysis"]
    assert "total_points" in d["temporal_analysis"]

    # 6. Observations contract
    for obs in d["automated_observations"]:
        assert "id" in obs
        assert "category" in obs
        assert "text" in obs
        assert "observation" in obs
        assert "severity" in obs
        assert "evidence" in obs


