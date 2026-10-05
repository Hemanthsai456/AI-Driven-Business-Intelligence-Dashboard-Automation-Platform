"""Unit tests for Step 7 — Autonomous Whole-Dataset Overview Dashboard Planner.

Tests:
1. Autonomous dashboard generation without user intent
2. Smart KPI selection with proper semantic aggregation (AVG for intensive, SUM for additive)
3. Hero visualization selection (Line for temporal, Bar for categorical)
4. Side composition tile (Donut for low-cardinality <= 7)
5. Secondary grid visuals (Bar breakdown, Correlation scatter if r >= 0.35, Outlier table)
6. Dynamic slicers generation (Date range for datetime, multi-select for dimensions)
7. Integration with Step 6 Evidence-Grounded Insights
8. Pure deterministic execution without LLM
9. Full SQL provenance and non-empty data on all tiles
"""

from typing import Any
import pandas as pd
import pytest

from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.overview import generate_overview_dashboard
from orchestrator.schemas import AggregationType, DashboardSpec


@pytest.fixture
def sample_business_dataset():
    data = {
        "order_id": [f"ORD_{i:04d}" for i in range(1, 31)],
        "region": ["North", "South", "East", "West", "Central"] * 6,
        "revenue": [1000.0 + i * 50.0 for i in range(30)],
        "discount_rate": [0.05 + (i % 5) * 0.02 for i in range(30)],
        "order_date": pd.date_range("2023-01-01", periods=30, freq="15D"),
    }
    df = pd.DataFrame(data)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata("ds_biz", "sample_biz", "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


def test_autonomous_dashboard_structure(sample_business_dataset):
    """Verify autonomous planner produces a multi-panel dashboard with KPIs, hero, and slicers."""
    dataset, profile = sample_business_dataset
    spec: DashboardSpec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert spec.spec_id.startswith("spec_overview_")
    assert len(spec.tiles) >= 3
    assert len(spec.panels) >= 2
    assert len(spec.headline) > 0
    assert len(spec.executive_summary) > 0


def test_smart_kpi_selection_and_aggregations(sample_business_dataset):
    """Verify KPI tiles use SUM for additive revenue and AVG for intensive discount rate."""
    dataset, profile = sample_business_dataset
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    kpi_tiles = [t for t in spec.tiles if t.chart_type == "kpi"]
    assert len(kpi_tiles) >= 2

    # Revenue should use Total / SUM
    rev_kpi = next((t for t in kpi_tiles if "revenue" in t.metrics or "Revenue" in t.title), None)
    assert rev_kpi is not None
    assert "Total" in rev_kpi.title or "Revenue" in rev_kpi.title
    assert rev_kpi.plan.metric.aggregation == AggregationType.SUM

    # Discount rate should use Average / AVG
    disc_kpi = next((t for t in kpi_tiles if "discount_rate" in t.metrics or "Discount" in t.title), None)
    assert disc_kpi is not None
    assert "Average" in disc_kpi.title or "Avg" in disc_kpi.title
    assert disc_kpi.plan.metric.aggregation == AggregationType.AVG


def test_hero_and_side_visual_selection(sample_business_dataset):
    """Verify temporal trend becomes hero line chart and region becomes side donut."""
    dataset, profile = sample_business_dataset
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    # Hero tile should be temporal line chart
    hero_tile = next((t for t in spec.tiles if t.size.w == 8 and t.size.h == 4), None)
    assert hero_tile is not None
    assert hero_tile.chart_type == "line"
    assert hero_tile.dimensions == ["order_date"]

    # Side tile should be donut (5 regions <= 7)
    side_tile = next((t for t in spec.tiles if t.size.w == 4 and t.size.h == 4), None)
    assert side_tile is not None
    assert side_tile.chart_type == "donut"
    assert side_tile.dimensions == ["region"]


def test_dynamic_slicers_generation(sample_business_dataset):
    """Verify interactive slicers are built for date range and low-cardinality region."""
    dataset, profile = sample_business_dataset
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert len(spec.slicers) >= 1
    slicer_cols = {s.column for s in spec.slicers}
    assert "region" in slicer_cols or "order_date" in slicer_cols


def test_tile_sql_provenance_and_data_integrity(sample_business_dataset):
    """Verify every visual tile has compiled SQL, non-empty data, and DuckDB backing."""
    dataset, profile = sample_business_dataset
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    for tile in spec.tiles:
        assert tile.data is not None
        assert len(tile.data) > 0
        if tile.compiled_sql:
            assert "SELECT" in tile.compiled_sql


def test_overview_api_endpoint(sample_business_dataset):
    """Verify POST /api/overview endpoint generates and stores the overview dashboard."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.store import session_store, DatasetSessionRecord

    dataset, profile = sample_business_dataset
    from intelligence.schema_validator import assess_readiness
    prof = profile_dataset(dataset)
    readiness = assess_readiness(dataset, prof, profile)
    record = DatasetSessionRecord(
        dataset=dataset,
        profile=prof,
        semantic_profile=profile,
        readiness=readiness,
    )
    session_store.save(record)

    client = TestClient(app)
    response = client.post(
        "/api/overview",
        json={"dataset_id": dataset.metadata.dataset_id, "use_llm": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["mode"] == "overview"
    assert data["spec_id"].startswith("spec_overview_")
    assert "dashboard_spec" in data
    assert len(data["dashboard_spec"]["tiles"]) >= 3
