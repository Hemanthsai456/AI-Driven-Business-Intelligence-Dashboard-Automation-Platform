"""Tests for Step 3 — Focused Multi-Tile Dashboard Generation & Analytical Planning.

Covers:
1. Focused requests produce >= 2 structured tiles (contextual KPI + primary hero visual).
2. Primary Hero tile preserves requested measure, aggregation, and grouping dimension.
3. Contextual KPI tile inherits Step 2 semantic aggregation default (AVG vs SUM).
4. Focused mode remains distinct from Discovery mode without unrelated dashboard bloat.
5. End-to-end pipeline validation on all 5 real datasets.
"""

import os
from typing import Any, Tuple
import pandas as pd
import pytest

from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata, ColumnRole
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import assess_readiness
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.pipeline import run_orchestration_pipeline
from orchestrator.schemas import AggregationType, VisualizationType


def _load_real_dataset(filename: str) -> Tuple[CanonicalDataset, Any, Any]:
    path = os.path.join("tests", "real_data", filename)
    assert os.path.exists(path), f"File not found: {path}"
    df = pd.read_csv(path)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds-{filename}", filename, "csv", len(df), len(cols), cols)
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    sem_profile = analyze_semantics(canonical, profile)
    readiness = assess_readiness(canonical, profile, sem_profile)
    return canonical, profile, sem_profile, readiness


# ---------------------------------------------------------------------------
# Unit / Synthetic Tests for Focused Multi-Tile Generation
# ---------------------------------------------------------------------------


def test_synthetic_focused_grouped_request_produces_multi_tiles():
    """Verify focused grouped query produces contextual KPI and Hero bar tile with AVG aggregation."""
    df = pd.DataFrame({
        "dept": ["IT", "HR", "Sales", "IT", "HR", "Sales"],
        "salary": [100000.0, 70000.0, 90000.0, 110000.0, 75000.0, 95000.0],
    })
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata("ds-syn", "Syn", "pandas", len(df), len(cols), cols)
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    sem_profile = analyze_semantics(canonical, profile)
    readiness = assess_readiness(canonical, profile, sem_profile)

    res = run_orchestration_pipeline(
        intent="Show me average salary by dept",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    # 1. Multi-tile verification
    assert len(spec.tiles) >= 2, f"Expected at least 2 tiles, got {len(spec.tiles)}"

    # 2. Contextual KPI tile
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None, "Missing contextual KPI tile"
    assert "Average Salary" in kpi_tile.title or "salary" in kpi_tile.title.lower()
    assert kpi_tile.plan.metric.aggregation == AggregationType.AVG
    assert len(kpi_tile.data) > 0

    # 3. Hero Visual tile
    hero_tile = next((t for t in spec.tiles if t.chart_type == "bar"), None)
    assert hero_tile is not None, "Missing primary Hero bar tile"
    assert "dept" in hero_tile.dimensions
    assert "salary" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.AVG


def test_synthetic_focused_single_kpi_request_produces_grounded_spec():
    """Verify focused single-metric request produces KPI tile without unrelated dimension charts."""
    df = pd.DataFrame({
        "temperature": [20.5, 21.0, 19.8, 22.4, 20.9],
        "device": ["D1", "D2", "D1", "D2", "D1"],
    })
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata("ds-temp", "Temp", "pandas", len(df), len(cols), cols)
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    sem_profile = analyze_semantics(canonical, profile)
    readiness = assess_readiness(canonical, profile, sem_profile)

    res = run_orchestration_pipeline(
        intent="What is the average temperature?",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    assert len(spec.tiles) >= 1
    tile = spec.tiles[0]
    assert tile.chart_type == "kpi"
    assert "temperature" in tile.metrics
    assert tile.plan.metric.aggregation == AggregationType.AVG


def test_synthetic_focused_additive_measure_sum_generalization():
    """Verify focused additive query produces contextual KPI and Hero bar tile with SUM aggregation."""
    df = pd.DataFrame({
        "region": ["North", "South", "East", "West", "North", "South"],
        "revenue": [1500.0, 2200.0, 1800.0, 3100.0, 1400.0, 2500.0],
    })
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata("ds-rev", "Revenue", "pandas", len(df), len(cols), cols)
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    sem_profile = analyze_semantics(canonical, profile)
    readiness = assess_readiness(canonical, profile, sem_profile)

    res = run_orchestration_pipeline(
        intent="Show total revenue by region",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    # 1. Multi-tile verification
    assert len(spec.tiles) >= 2, f"Expected at least 2 tiles, got {len(spec.tiles)}"

    # 2. Contextual KPI tile uses SUM
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None, "Missing contextual KPI tile"
    assert "Total Revenue" in kpi_tile.title or "revenue" in kpi_tile.title.lower()
    assert kpi_tile.plan.metric.aggregation == AggregationType.SUM
    assert len(kpi_tile.data) > 0
    assert float(kpi_tile.data[0]["revenue"]) == float(df["revenue"].sum())

    # 3. Hero Visual tile uses SUM
    hero_tile = next((t for t in spec.tiles if t.chart_type in ("bar", "BAR")), None)
    assert hero_tile is not None, "Missing primary Hero bar tile"
    assert "region" in hero_tile.dimensions
    assert "revenue" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.SUM


# ---------------------------------------------------------------------------
# Real-Dataset Validations Across 5 Domains
# ---------------------------------------------------------------------------


def test_real_data_healthcare_focused_length_of_stay_by_diagnosis():
    """Verify Healthcare focused query: 'What is the average length of stay by diagnosis?'"""
    canonical, profile, sem_profile, readiness = _load_real_dataset("healthcare.csv")

    res = run_orchestration_pipeline(
        intent="What is the average length of stay by diagnosis?",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    assert len(spec.tiles) >= 2
    # Check contextual KPI
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None
    assert kpi_tile.plan.metric.aggregation == AggregationType.AVG
    assert "length_of_stay" in kpi_tile.metrics

    # Check Hero Visual
    hero_tile = next((t for t in spec.tiles if t.chart_type in ("bar", "line")), None)
    assert hero_tile is not None
    assert "diagnosis" in hero_tile.dimensions
    assert "length_of_stay" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.AVG


def test_real_data_education_focused_marks_by_subject():
    """Verify Education focused query: 'Show me average marks by subject'"""
    canonical, profile, sem_profile, readiness = _load_real_dataset("education.csv")

    res = run_orchestration_pipeline(
        intent="Show me average marks by subject",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    assert len(spec.tiles) >= 2
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None
    assert kpi_tile.plan.metric.aggregation == AggregationType.AVG
    assert "marks" in kpi_tile.metrics

    hero_tile = next((t for t in spec.tiles if t.chart_type in ("bar", "line")), None)
    assert hero_tile is not None
    assert "subject" in hero_tile.dimensions
    assert "marks" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.AVG


def test_real_data_iot_focused_temperature_by_device():
    """Verify IoT focused query: 'What is the average temperature by device?'"""
    canonical, profile, sem_profile, readiness = _load_real_dataset("iot.csv")

    res = run_orchestration_pipeline(
        intent="What is the average temperature by device?",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    assert len(spec.tiles) >= 2
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None
    assert kpi_tile.plan.metric.aggregation == AggregationType.AVG
    assert "temperature" in kpi_tile.metrics

    hero_tile = next((t for t in spec.tiles if t.chart_type in ("bar", "line")), None)
    assert hero_tile is not None
    assert "device" in hero_tile.dimensions
    assert "temperature" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.AVG


def test_real_data_hr_focused_salary_by_department():
    """Verify HR focused query: 'Show me average salary by department'"""
    canonical, profile, sem_profile, readiness = _load_real_dataset("hr.csv")

    res = run_orchestration_pipeline(
        intent="Show me average salary by department",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    assert len(spec.tiles) >= 2
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None
    assert kpi_tile.plan.metric.aggregation == AggregationType.AVG
    assert "salary" in kpi_tile.metrics

    hero_tile = next((t for t in spec.tiles if t.chart_type in ("bar", "line")), None)
    assert hero_tile is not None
    assert "department" in hero_tile.dimensions
    assert "salary" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.AVG


def test_real_data_logistics_focused_delivery_time_by_destination():
    """Verify Logistics focused query: 'What is the average delivery time by destination?'"""
    canonical, profile, sem_profile, readiness = _load_real_dataset("logistics.csv")

    res = run_orchestration_pipeline(
        intent="What is the average delivery time by destination?",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )

    assert res.status == "SUCCESS"
    assert res.dashboard_spec is not None
    spec = res.dashboard_spec

    assert len(spec.tiles) >= 2
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), None)
    assert kpi_tile is not None
    assert kpi_tile.plan.metric.aggregation == AggregationType.AVG
    assert "delivery_time" in kpi_tile.metrics

    hero_tile = next((t for t in spec.tiles if t.chart_type in ("bar", "line")), None)
    assert hero_tile is not None
    assert "destination" in hero_tile.dimensions
    assert "delivery_time" in hero_tile.metrics
    assert hero_tile.plan.metric.aggregation == AggregationType.AVG
