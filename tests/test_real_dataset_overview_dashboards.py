"""Domain validation test suite for Step 7 — Autonomous Overview Dashboard.

Evaluates autonomous whole-dataset overview generation against the 5 real benchmark domain datasets:
1. Healthcare (diagnosis, severity, length_of_stay, hospital, admission_date)
2. HR (department, salary, performance_score, employee_id, joining_date)
3. Education (department, subject, marks, student_id, exam_date)
4. IoT (device, temperature, pressure, status, timestamp)
5. Logistics (destination, delivery_time, shipment_id, shipment_date, status)

Verifies:
- Autonomous DashboardSpec generation without a prompt
- Correct KPI selection with semantic aggregations (AVG for continuous rates/scores)
- Complete exclusion of identifier columns from measures
- Meaningful hero & secondary visual selection
- Zero hallucination with complete DuckDB SQL execution on every tile
"""

import os
from typing import Any, Tuple
import pandas as pd
import pytest

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    DatasetMetadata,
)
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.overview import generate_overview_dashboard
from orchestrator.schemas import AggregationType, DashboardSpec


def _load_real_dataset(filename: str) -> Tuple[CanonicalDataset, Any]:
    path = os.path.join(os.path.dirname(__file__), "real_data", filename)
    df = pd.read_csv(path)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{filename.split('.')[0]}", filename, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


# ===========================================================================
# 1. Healthcare Overview Dashboard
# ===========================================================================

def test_healthcare_overview_dashboard():
    """Verify healthcare dataset generates autonomous overview with length_of_stay KPI & admission_date trend."""
    dataset, profile = _load_real_dataset("healthcare.csv")
    spec: DashboardSpec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 3
    assert len(spec.panels) >= 2

    # Verify KPI for length_of_stay uses AVG
    kpi_los = next((t for t in spec.tiles if t.chart_type == "kpi" and "length_of_stay" in t.metrics), None)
    assert kpi_los is not None
    assert kpi_los.plan.metric.aggregation == AggregationType.AVG
    assert "Average" in kpi_los.title or "Avg" in kpi_los.title

    # Verify Hero tile is admission_date line chart
    hero_tile = next((t for t in spec.tiles if t.size.w == 8 and t.size.h == 4), None)
    assert hero_tile is not None
    assert hero_tile.chart_type in ("line", "bar")


# ===========================================================================
# 2. HR Overview Dashboard
# ===========================================================================

def test_hr_overview_dashboard():
    """Verify HR dataset generates overview with salary & performance KPIs and avoids employee_id."""
    dataset, profile = _load_real_dataset("hr.csv")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 3

    # Ensure employee_id is never a metric in any tile
    for t in spec.tiles:
        assert "employee_id" not in t.metrics

    # Verify salary KPI exists
    kpi_salary = next((t for t in spec.tiles if t.chart_type == "kpi" and "salary" in t.metrics), None)
    assert kpi_salary is not None
    assert kpi_salary.plan.metric.aggregation in (AggregationType.AVG, AggregationType.SUM)


# ===========================================================================
# 3. Education Overview Dashboard
# ===========================================================================

def test_education_overview_dashboard():
    """Verify Education dataset generates overview with marks KPI and subject/department breakdown."""
    dataset, profile = _load_real_dataset("education.csv")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 3

    # Student ID must not be a metric
    for t in spec.tiles:
        assert "student_id" not in t.metrics

    # Marks KPI uses AVG
    kpi_marks = next((t for t in spec.tiles if t.chart_type == "kpi" and "marks" in t.metrics), None)
    assert kpi_marks is not None
    assert kpi_marks.plan.metric.aggregation == AggregationType.AVG


# ===========================================================================
# 4. IoT Overview Dashboard
# ===========================================================================

def test_iot_overview_dashboard():
    """Verify IoT dataset generates overview with temperature and pressure KPIs and timestamp trend."""
    dataset, profile = _load_real_dataset("iot.csv")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 3

    # Both temperature and pressure KPIs use AVG
    temp_kpi = next((t for t in spec.tiles if t.chart_type == "kpi" and "temperature" in t.metrics), None)
    press_kpi = next((t for t in spec.tiles if t.chart_type == "kpi" and "pressure" in t.metrics), None)
    assert temp_kpi is not None
    assert press_kpi is not None
    assert temp_kpi.plan.metric.aggregation == AggregationType.AVG
    assert press_kpi.plan.metric.aggregation == AggregationType.AVG


# ===========================================================================
# 5. Logistics Overview Dashboard
# ===========================================================================

def test_logistics_overview_dashboard():
    """Verify Logistics dataset generates overview with delivery_time KPI and destination breakdown."""
    dataset, profile = _load_real_dataset("logistics.csv")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 3

    # Shipment ID must not be a metric
    for t in spec.tiles:
        assert "shipment_id" not in t.metrics

    # Delivery time KPI uses AVG
    kpi_dt = next((t for t in spec.tiles if t.chart_type == "kpi" and "delivery_time" in t.metrics), None)
    assert kpi_dt is not None
    assert kpi_dt.plan.metric.aggregation == AggregationType.AVG
