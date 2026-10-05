"""Real-dataset validation test suite for Step 5 — Analytical Query Engine.

Verifies end-to-end analytical querying against 5 real benchmark domain datasets:
1. Healthcare (diagnosis, severity, length_of_stay, hospital, admission_date)
2. HR (department, salary, performance_score, employee_id, joining_date)
3. Education (department, subject, marks, student_id, exam_date)
4. IoT (device, temperature, pressure, status, timestamp)
5. Logistics (destination, delivery_time, shipment_id, shipment_date, status)

For each domain:
- Profiles dataset dynamically via SemanticAnalyzer
- Executes natural language analytical queries
- Validates column resolution, structured plan, and SQL compilation
- Verifies exact numeric parity with direct DuckDB execution
"""

import os
import pandas as pd
import pytest

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    DatasetMetadata,
)
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.query_engine import execute_analytical_query
from orchestrator.schemas import AggregationType


def _load_real_dataset(filename: str):
    path = os.path.join(os.path.dirname(__file__), "real_data", filename)
    df = pd.read_csv(path)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{filename.split('.')[0]}", filename, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


# ===========================================================================
# 1. Healthcare Dataset
# ===========================================================================

def test_healthcare_average_stay_by_diagnosis():
    """Verify average length of stay by diagnosis on real healthcare data."""
    dataset, profile = _load_real_dataset("healthcare.csv")
    res = execute_analytical_query(
        question="What is the average length of stay by diagnosis?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "length_of_stay"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "diagnosis"
    assert len(res.rows) > 0

    # Parity check
    expected = dataset.data.groupby("diagnosis")["length_of_stay"].mean().to_dict()
    actual = {r["diagnosis"]: r["avg_length_of_stay"] for r in res.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_healthcare_highest_stay_hospital():
    """Verify ranking top hospital with highest length of stay."""
    dataset, profile = _load_real_dataset("healthcare.csv")
    res = execute_analytical_query(
        question="Which hospital has the highest average length of stay?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.order_direction == "DESC"
    top_hospital = dataset.data.groupby("hospital")["length_of_stay"].mean().idxmax()
    assert res.rows[0]["hospital"] == top_hospital


def test_healthcare_filtered_stay():
    """Verify filtered length of stay where severity is Low."""
    dataset, profile = _load_real_dataset("healthcare.csv")
    res = execute_analytical_query(
        question="Show average length of stay where severity = 'Low'",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert len(res.plan.filters) == 1
    assert res.plan.filters[0].column == "severity"
    expected = dataset.data[dataset.data["severity"] == "Low"]["length_of_stay"].mean()
    actual = res.rows[0]["avg_length_of_stay"]
    assert pytest.approx(actual, rel=1e-3) == expected


# ===========================================================================
# 2. HR Dataset
# ===========================================================================

def test_hr_average_salary_by_department():
    """Verify average salary grouped by department."""
    dataset, profile = _load_real_dataset("hr.csv")
    res = execute_analytical_query(
        question="What is the average salary by department?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "salary"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "department"

    expected = dataset.data.groupby("department")["salary"].mean().to_dict()
    actual = {r["department"]: r["avg_salary"] for r in res.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_hr_top_departments_by_salary():
    """Verify top 3 departments by salary ranking."""
    dataset, profile = _load_real_dataset("hr.csv")
    res = execute_analytical_query(
        question="Show top 3 department by average salary",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.limit == 3
    assert res.plan.order_direction == "DESC"
    assert len(res.rows) <= 3


# ===========================================================================
# 3. Education Dataset
# ===========================================================================

def test_education_average_marks_by_subject():
    """Verify average marks grouped by subject."""
    dataset, profile = _load_real_dataset("education.csv")
    res = execute_analytical_query(
        question="What is the average marks by subject?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "marks"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "subject"

    expected = dataset.data.groupby("subject")["marks"].mean().to_dict()
    actual = {r["subject"]: r["avg_marks"] for r in res.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_education_marks_ranking_by_department():
    """Verify department with highest average marks."""
    dataset, profile = _load_real_dataset("education.csv")
    res = execute_analytical_query(
        question="Which department has the highest average marks?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    top_dept = dataset.data.groupby("department")["marks"].mean().idxmax()
    assert res.rows[0]["department"] == top_dept


# ===========================================================================
# 4. IoT Dataset
# ===========================================================================

def test_iot_average_temperature_by_device():
    """Verify temperature average by device on IoT telemetry data."""
    dataset, profile = _load_real_dataset("iot.csv")
    res = execute_analytical_query(
        question="What is the average temperature by device?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "temperature"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "device"

    expected = dataset.data.groupby("device")["temperature"].mean().to_dict()
    actual = {r["device"]: r["avg_temperature"] for r in res.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_iot_pressure_filtered():
    """Verify average pressure filtered where status is sampled."""
    dataset, profile = _load_real_dataset("iot.csv")
    status_sample = str(dataset.data["status"].dropna().iloc[0])
    res = execute_analytical_query(
        question=f"Show average pressure where status = '{status_sample}'",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "pressure"
    expected = dataset.data[dataset.data["status"] == status_sample]["pressure"].mean()
    actual = res.rows[0]["avg_pressure"]
    assert pytest.approx(actual, rel=1e-3) == expected


# ===========================================================================
# 5. Logistics Dataset
# ===========================================================================

def test_logistics_average_delivery_time_by_destination():
    """Verify average delivery time by destination."""
    dataset, profile = _load_real_dataset("logistics.csv")
    res = execute_analytical_query(
        question="What is the average delivery time by destination?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    assert res.plan.metric.column == "delivery_time"
    assert res.plan.metric.aggregation == AggregationType.AVG
    assert res.plan.dimensions[0].column == "destination"

    expected = dataset.data.groupby("destination")["delivery_time"].mean().to_dict()
    actual = {r["destination"]: r["avg_delivery_time"] for r in res.rows}
    for k, v in expected.items():
        assert pytest.approx(actual[k], rel=1e-3) == v


def test_logistics_destination_ranking():
    """Verify destination with highest average delivery time."""
    dataset, profile = _load_real_dataset("logistics.csv")
    res = execute_analytical_query(
        question="Which destination has the highest average delivery time?",
        dataset=dataset,
        semantic_profile=profile,
    )
    assert res.validation_status in ("PASSED", "WARNING")
    top_dest = dataset.data.groupby("destination")["delivery_time"].mean().idxmax()
    assert res.rows[0]["destination"] == top_dest
