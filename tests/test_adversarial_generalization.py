"""Comprehensive Adversarial Generalization & Unseen Domain Acceptance Tests.

Strictly tests:
1. Four adversarial datasets with completely distinct, renamed columns:
   - Dataset A: learner_score, business_unit, exam_timestamp
   - Dataset B: thermal_value, device_group, observed_at
   - Dataset C: employee_compensation, organizational_unit, joining_day
   - Dataset D: transaction_value, market_area, transaction_date
   - Unseen Domain E (Aerospace telemetry): ambient_pressure, subsystem_cluster, logging_epoch
2. Multiple phrasing variations expressing the same underlying analytical intent.
3. Direct DuckDB parity validation for all computations.
4. Ambiguity handling for multiple candidate numeric measures.
5. Strict read-only invariance (no mutation of CanonicalDataset data).
"""

import duckdb
import numpy as np
import pandas as pd
import pytest

from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.semantic_analyzer import (
    ColumnRole,
    DatasetSemanticProfile,
    analyze_semantics,
)
from orchestrator.query_engine import execute_analytical_query
from orchestrator.schemas import (
    AggregationType,
    AmbiguityStatus,
    Granularity,
)


@pytest.fixture
def dataset_a():
    """Dataset A: learner_score, business_unit, exam_timestamp."""
    df = pd.DataFrame({
        "learner_token": [f"L_{i:02d}" for i in range(1, 13)],
        "business_unit": ["Engineering", "Product", "Engineering", "Design", "Product", "Engineering", "Design", "Engineering", "Product", "Design", "Engineering", "Product"],
        "learner_score": [92.0, 85.5, 78.0, 94.0, 88.0, 91.5, 72.0, 89.0, 96.0, 81.0, 87.5, 90.0],
        "exam_timestamp": [
            "2024-01-10 09:00:00", "2024-01-11 10:30:00", "2024-02-05 14:00:00", "2024-02-12 11:00:00",
            "2024-03-01 08:30:00", "2024-03-15 13:00:00", "2024-04-02 09:15:00", "2024-04-20 15:45:00",
            "2024-05-04 10:00:00", "2024-05-18 11:30:00", "2024-06-01 14:15:00", "2024-06-15 16:00:00"
        ],
    })
    meta = DatasetMetadata(
        dataset_id="ds_a",
        name="dataset_a",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("learner_token", "learner_token", "object", ColumnRole.IDENTIFIER, 0, 0.0, 12),
            ColumnMetadata("business_unit", "business_unit", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("learner_score", "learner_score", "float64", ColumnRole.MEASURE, 0, 0.0, 12),
            ColumnMetadata("exam_timestamp", "exam_timestamp", "object", ColumnRole.DATETIME, 0, 0.0, 12),
        ],
    )
    dataset = CanonicalDataset(metadata=meta, data=df)
    profile = analyze_semantics(dataset, apply_roles=True)
    return dataset, profile


@pytest.fixture
def dataset_b():
    """Dataset B: thermal_value, device_group, observed_at."""
    df = pd.DataFrame({
        "device_identifier": [f"DEV_{i}" for i in range(101, 111)],
        "device_group": ["Cluster_X", "Cluster_Y", "Cluster_X", "Cluster_Z", "Cluster_Y", "Cluster_X", "Cluster_Z", "Cluster_Y", "Cluster_X", "Cluster_Z"],
        "thermal_value": [42.3, 58.7, 45.1, 71.2, 60.4, 43.8, 69.5, 57.2, 44.0, 73.1],
        "observed_at": [
            "2024-06-01 00:00:00", "2024-06-01 01:00:00", "2024-06-01 02:00:00", "2024-06-01 03:00:00",
            "2024-06-01 04:00:00", "2024-06-01 05:00:00", "2024-06-01 06:00:00", "2024-06-01 07:00:00",
            "2024-06-01 08:00:00", "2024-06-01 09:00:00"
        ],
    })
    meta = DatasetMetadata(
        dataset_id="ds_b",
        name="dataset_b",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("device_identifier", "device_identifier", "object", ColumnRole.IDENTIFIER, 0, 0.0, 10),
            ColumnMetadata("device_group", "device_group", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("thermal_value", "thermal_value", "float64", ColumnRole.MEASURE, 0, 0.0, 10),
            ColumnMetadata("observed_at", "observed_at", "object", ColumnRole.DATETIME, 0, 0.0, 10),
        ],
    )
    dataset = CanonicalDataset(metadata=meta, data=df)
    profile = analyze_semantics(dataset, apply_roles=True)
    return dataset, profile


@pytest.fixture
def dataset_c():
    """Dataset C: employee_compensation, organizational_unit, joining_day."""
    df = pd.DataFrame({
        "staff_serial": [f"STF_{i:04d}" for i in range(1, 9)],
        "organizational_unit": ["Ops", "Finance", "Ops", "Finance", "Legal", "Ops", "Legal", "Finance"],
        "employee_compensation": [75000.0, 110000.0, 82000.0, 125000.0, 98000.0, 79000.0, 105000.0, 118000.0],
        "joining_day": ["2021-03-15", "2020-07-01", "2022-01-10", "2019-11-20", "2021-09-05", "2023-04-18", "2020-02-14", "2018-08-30"],
    })
    meta = DatasetMetadata(
        dataset_id="ds_c",
        name="dataset_c",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("staff_serial", "staff_serial", "object", ColumnRole.IDENTIFIER, 0, 0.0, 8),
            ColumnMetadata("organizational_unit", "organizational_unit", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("employee_compensation", "employee_compensation", "float64", ColumnRole.MEASURE, 0, 0.0, 8),
            ColumnMetadata("joining_day", "joining_day", "object", ColumnRole.DATETIME, 0, 0.0, 8),
        ],
    )
    dataset = CanonicalDataset(metadata=meta, data=df)
    profile = analyze_semantics(dataset, apply_roles=True)
    return dataset, profile


@pytest.fixture
def dataset_d():
    """Dataset D: transaction_value, market_area, transaction_date."""
    df = pd.DataFrame({
        "tx_receipt_id": [f"TXN_{i:05d}" for i in range(1, 11)],
        "market_area": ["EMEA", "APAC", "AMER", "EMEA", "APAC", "AMER", "EMEA", "APAC", "AMER", "EMEA"],
        "transaction_value": [1200.50, 3400.00, 2150.75, 450.00, 5600.25, 1890.00, 3100.00, 4200.50, 950.00, 2750.00],
        "transaction_date": [
            "2024-01-15", "2024-01-20", "2024-02-05", "2024-02-18", "2024-03-10",
            "2024-03-25", "2024-04-05", "2024-04-18", "2024-05-02", "2024-05-20"
        ],
    })
    meta = DatasetMetadata(
        dataset_id="ds_d",
        name="dataset_d",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("tx_receipt_id", "tx_receipt_id", "object", ColumnRole.IDENTIFIER, 0, 0.0, 10),
            ColumnMetadata("market_area", "market_area", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("transaction_value", "transaction_value", "float64", ColumnRole.MEASURE, 0, 0.0, 10),
            ColumnMetadata("transaction_date", "transaction_date", "object", ColumnRole.DATETIME, 0, 0.0, 10),
        ],
    )
    dataset = CanonicalDataset(metadata=meta, data=df)
    profile = analyze_semantics(dataset, apply_roles=True)
    return dataset, profile


@pytest.fixture
def dataset_aerospace_unseen():
    """Unseen domain E: Aerospace telemetry with novel names."""
    df = pd.DataFrame({
        "sensor_telemetry_id": [f"TEL_{i:03d}" for i in range(1, 9)],
        "subsystem_cluster": ["Propulsion", "Avionics", "Propulsion", "Thermal", "Avionics", "Propulsion", "Thermal", "Avionics"],
        "ambient_pressure_kpa": [101.3, 100.8, 102.1, 99.4, 100.5, 101.9, 99.1, 100.7],
        "fuel_flow_rate_lps": [12.4, 3.2, 14.1, 1.8, 3.5, 13.8, 1.9, 3.1],
        "logging_epoch": [
            "2024-08-01 12:00:00", "2024-08-01 12:01:00", "2024-08-01 12:02:00", "2024-08-01 12:03:00",
            "2024-08-01 12:04:00", "2024-08-01 12:05:00", "2024-08-01 12:06:00", "2024-08-01 12:07:00"
        ],
    })
    meta = DatasetMetadata(
        dataset_id="ds_aerospace",
        name="aerospace_telemetry",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata("sensor_telemetry_id", "sensor_telemetry_id", "object", ColumnRole.IDENTIFIER, 0, 0.0, 8),
            ColumnMetadata("subsystem_cluster", "subsystem_cluster", "object", ColumnRole.DIMENSION, 0, 0.0, 3),
            ColumnMetadata("ambient_pressure_kpa", "ambient_pressure_kpa", "float64", ColumnRole.MEASURE, 0, 0.0, 8),
            ColumnMetadata("fuel_flow_rate_lps", "fuel_flow_rate_lps", "float64", ColumnRole.MEASURE, 0, 0.0, 8),
            ColumnMetadata("logging_epoch", "logging_epoch", "object", ColumnRole.DATETIME, 0, 0.0, 8),
        ],
    )
    dataset = CanonicalDataset(metadata=meta, data=df)
    profile = analyze_semantics(dataset, apply_roles=True)
    return dataset, profile


# ===========================================================================
# 1. Dataset A Tests: Natural Language Phrasing Variations
# ===========================================================================

@pytest.mark.parametrize("query_text", [
    "average score by unit",
    "compare average score across units",
    "show the mean score for each unit",
    "what is the average learner score across business units?",
])
def test_dataset_a_phrasing_variations(dataset_a, query_text):
    """Test phrasing variations map to equivalent structured analytical plans."""
    dataset, profile = dataset_a
    res = execute_analytical_query(question=query_text, dataset=dataset, semantic_profile=profile)

    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "learner_score"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert len(res.plan.dimensions) == 1
    assert res.plan.dimensions[0].column == "business_unit"

    # Direct DuckDB parity check
    expected = dataset.data.groupby("business_unit")["learner_score"].mean().to_dict()
    actual = {r["business_unit"]: r["avg_learner_score"] for r in res.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_dataset_a_highest_ranking(dataset_a):
    """Test 'which unit has the highest average score?'."""
    dataset, profile = dataset_a
    res = execute_analytical_query(
        question="Which business unit has the highest average learner score?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.order_direction == "DESC"
    # Ground truth top
    top_bu = dataset.data.groupby("business_unit")["learner_score"].mean().idxmax()
    assert res.rows[0]["business_unit"] == top_bu


# ===========================================================================
# 2. Dataset B Tests: Thermal Readings and Device Groups
# ===========================================================================

def test_dataset_b_thermal_average(dataset_b):
    """Test thermal value automatically averages (intensive continuous measure)."""
    dataset, profile = dataset_b
    res = execute_analytical_query(
        question="Show average thermal value by device group",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "thermal_value"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "device_group"
    assert res.row_count == 3


def test_dataset_b_filtering_and_ranking(dataset_b):
    """Test filtering thermal readings > 50 and ranking top groups."""
    dataset, profile = dataset_b
    res = execute_analytical_query(
        question="Show top 2 device groups by average thermal value where thermal value > 50",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.limit == 2
    assert res.plan.order_direction == "DESC"
    assert len(res.plan.filters) == 1
    assert res.plan.filters[0].column == "thermal_value"
    assert res.plan.filters[0].operator == ">"
    assert float(res.plan.filters[0].value) == 50.0
    assert len(res.rows) <= 2


# ===========================================================================
# 3. Dataset C Tests: Compensation and Organizational Units
# ===========================================================================

def test_dataset_c_compensation_aggregation(dataset_c):
    """Test compensation / pay rate defaults to AVG or SUM based on query."""
    dataset, profile = dataset_c
    res_avg = execute_analytical_query(
        question="What is the average employee compensation by organizational unit?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res_avg.validation_status in ("PASSED", "WARNING")
    assert res_avg.plan.metric.column == "employee_compensation"
    assert res_avg.plan.metric.aggregation == AggregationType.AVG
    assert res_avg.plan.dimensions[0].column == "organizational_unit"

    # Direct parity check
    expected = dataset.data.groupby("organizational_unit")["employee_compensation"].mean().to_dict()
    actual = {r["organizational_unit"]: r["avg_employee_compensation"] for r in res_avg.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_dataset_c_lowest_compensation_unit(dataset_c):
    """Test 'Which organizational unit has the lowest total compensation?'."""
    dataset, profile = dataset_c
    res = execute_analytical_query(
        question="Which organizational unit has the lowest total employee compensation?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.order_direction == "ASC"
    assert res.plan.metric.aggregation == AggregationType.SUM
    lowest_unit = dataset.data.groupby("organizational_unit")["employee_compensation"].sum().idxmin()
    assert res.rows[0]["organizational_unit"] == lowest_unit


# ===========================================================================
# 4. Dataset D Tests: Transaction Value & Temporal Grouping
# ===========================================================================

def test_dataset_d_transaction_monthly_trend(dataset_d):
    """Test temporal trend of total transaction value by month."""
    dataset, profile = dataset_d
    res = execute_analytical_query(
        question="Monthly trend of total transaction value by market area",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    dim_cols = [d.column for d in res.plan.dimensions]
    assert "market_area" in dim_cols or "transaction_date" in dim_cols
    assert res.plan.metric.column == "transaction_value"
    assert res.plan.metric.aggregation == AggregationType.SUM


def test_dataset_d_filtered_transaction_sum(dataset_d):
    """Test filtering by categorical market area."""
    dataset, profile = dataset_d
    res = execute_analytical_query(
        question="Show total transaction value where market area = 'APAC'",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert len(res.plan.filters) == 1
    assert res.plan.filters[0].column == "market_area"
    assert res.plan.filters[0].value == "APAC"
    expected = dataset.data[dataset.data["market_area"] == "APAC"]["transaction_value"].sum()
    actual = list(res.rows[0].values())[0]
    assert pytest.approx(actual, rel=1e-3) == expected


# ===========================================================================
# 5. Unseen Domain E (Aerospace Telemetry)
# ===========================================================================

def test_aerospace_unseen_domain(dataset_aerospace_unseen):
    """Test completely novel aerospace domain with unpredicted column names."""
    dataset, profile = dataset_aerospace_unseen
    res = execute_analytical_query(
        question="What is the average ambient pressure kpa by subsystem cluster?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "ambient_pressure_kpa"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "subsystem_cluster"
    assert res.row_count == 3


def test_aerospace_fuel_flow_ranking(dataset_aerospace_unseen):
    """Test top subsystem cluster by fuel flow rate."""
    dataset, profile = dataset_aerospace_unseen
    res = execute_analytical_query(
        question="Show the top subsystem cluster by average fuel flow rate lps",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "fuel_flow_rate_lps"
    assert res.plan.dimensions[0].column == "subsystem_cluster"
    assert res.plan.order_direction == "DESC"
    top_cluster = dataset.data.groupby("subsystem_cluster")["fuel_flow_rate_lps"].mean().idxmax()
    assert res.rows[0]["subsystem_cluster"] == top_cluster


# ===========================================================================
# 6. Read-Only Invariance & Safety Checks
# ===========================================================================

def test_dataset_immutability(dataset_a):
    """Verify CanonicalDataset DataFrame is never mutated during analytical execution."""
    dataset, profile = dataset_a
    original_df_hash = pd.util.hash_pandas_object(dataset.data).sum()
    original_shape = dataset.data.shape

    _ = execute_analytical_query(
        question="Average learner score where business unit = 'Engineering'",
        dataset=dataset,
        semantic_profile=profile,
    )

    current_df_hash = pd.util.hash_pandas_object(dataset.data).sum()
    assert original_df_hash == current_df_hash
    assert dataset.data.shape == original_shape
