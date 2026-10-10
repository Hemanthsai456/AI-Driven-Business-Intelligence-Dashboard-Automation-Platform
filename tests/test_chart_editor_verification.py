"""Targeted verification tests for chart editor configuration, validation safeguards, and preview execution.

Verifies:
1. Previewing an unchanged existing chart (no 200% TRY_CAST false positive when unrelated date columns exist).
2. Previewing an unchanged KPI (scalar aggregation without grouping dimension).
3. Changing an aggregated bar chart's dimension and metric.
4. Configuring a scatter plot with two numeric axes and raw observations (no aggregation or grouping).
5. Configuring a line chart with a valid supported temporal arrangement.
6. Switching chart types and verifying plan execution.
7. Previewing an invalid configuration and confirming validation safeguard blocks it.
8. Confirming execution result has sensible row count, columns, and data points.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app, dashboard_specs_store, original_specs_store, tile_query_cache
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.profiler import DataProfiler
from intelligence.schema_validator import assess_readiness
from intelligence.semantic_analyzer import ColumnRole, SemanticAnalyzer
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DashboardSpec,
    DashboardTile,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    MetricSpec,
    OrchestratorTrace,
    Pass1aResult,
    Pass1bResult,
    PlanReasoning,
    RankedCandidate,
    ScoreBreakdown,
    TileEvidence,
    VisualizationType,
)

client = TestClient(app)


def _setup_multi_column_dataset(dataset_id: str = "ds_sales"):
    """Create a dataset containing dates (DD-MM-YYYY), categories, and multiple numeric metrics."""
    df = pd.DataFrame({
        "Order ID": ["CA-1", "CA-2", "CA-3", "CA-4", "CA-5"],
        "Order Date": ["14-04-2023", "20-05-2023", "11-06-2023", "19-07-2023", "15-08-2023"],
        "Category": ["Furniture", "Technology", "Office Supplies", "Furniture", "Technology"],
        "Sub-Category": ["Chairs", "Phones", "Storage", "Tables", "Accessories"],
        "Sales": [261.96, 731.94, 14.62, 957.57, 48.86],
        "Profit": [41.91, 219.58, 6.87, -383.02, 14.16],
        "Discount": [0.0, 0.2, 0.0, 0.45, 0.0],
        "Quantity": [2, 3, 2, 5, 7],
    })

    schema = []
    for col in df.columns:
        if "Date" in col:
            dt = "DATE"
        elif "Sales" in col or "Profit" in col or "Discount" in col:
            dt = "FLOAT"
        elif "Quantity" in col:
            dt = "INTEGER"
        else:
            dt = "VARCHAR"
        schema.append(ColumnMetadata(original_name=col, normalized_name=col, detected_datatype=dt))

    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=f"{dataset_id}.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    canon = CanonicalDataset(metadata=meta, data=df)
    profiler = DataProfiler()
    profile = profiler.profile(canon, attach=True)
    analyzer = SemanticAnalyzer()
    sem_prof = analyzer.analyze(canon, profile=profile, apply_roles=True)
    if "Order Date" in sem_prof.column_evidences:
        sem_prof.column_evidences["Order Date"].candidate_role = ColumnRole.DATETIME
    readiness = assess_readiness(canon, profile=profile, semantic_profile=sem_prof)

    record = DatasetSessionRecord(
        dataset=canon,
        profile=profile,
        semantic_profile=sem_prof,
        readiness=readiness,
    )
    session_store.save(record)
    return record


@pytest.fixture(autouse=True)
def clean_stores():
    session_store.clear()
    dashboard_specs_store.clear()
    original_specs_store.clear()
    tile_query_cache.clear()
    yield
    session_store.clear()


# =========================================================================
# 1. Preview unchanged existing chart (no 200% TRY_CAST false positive)
# =========================================================================
def test_preview_unchanged_existing_chart():
    _setup_multi_column_dataset("ds_sales")

    unchanged_plan = CandidatePlan(
        plan_id="plan_cat_profit",
        dataset_id="ds_sales",
        intent="Profit by Category",
        metric=MetricSpec(column="Profit", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        filters=[],
        visualization=VisualizationType.BAR,
        generator="llm",
        reasoning=PlanReasoning(interpretation="Profit by Category", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=unchanged_plan.model_dump())
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pass1a"]["passed"] is True
    assert data["execution"]["status"] == "SUCCESS"
    assert data["execution"]["failed_cast_rate"] == 0.0
    assert data["pass1b"]["passed"] is True
    assert len(data["execution"]["rows"]) > 0


# =========================================================================
# 2. Preview unchanged KPI (scalar metric without grouping dimension)
# =========================================================================
def test_preview_unchanged_kpi():
    _setup_multi_column_dataset("ds_sales")

    kpi_plan = CandidatePlan(
        plan_id="plan_kpi_sales",
        dataset_id="ds_sales",
        intent="Total Sales",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
        dimensions=[],  # No grouping dimension for scalar KPI
        filters=[],
        visualization=VisualizationType.KPI,
        generator="llm",
        reasoning=PlanReasoning(interpretation="Total Sales KPI", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=kpi_plan.model_dump())
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pass1a"]["passed"] is True
    assert data["execution"]["status"] == "SUCCESS"
    assert data["pass1b"]["passed"] is True
    assert len(data["execution"]["rows"]) == 1
    assert "sum_Sales" in data["execution"]["rows"][0]
    assert data["execution"]["rows"][0]["sum_Sales"] > 0


# =========================================================================
# 3. Changing an aggregated bar chart's dimension or metric
# =========================================================================
def test_change_aggregated_bar_chart():
    _setup_multi_column_dataset("ds_sales")

    # Initial plan: Category & Profit
    # Changed plan: Sub-Category & Sales
    edited_plan = CandidatePlan(
        plan_id="plan_edited_bar",
        dataset_id="ds_sales",
        intent="Sales by Sub-Category",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.AVG),
        dimensions=[DimensionSpec(column="Sub-Category")],
        filters=[],
        visualization=VisualizationType.BAR,
        generator="user_editor",
        reasoning=PlanReasoning(interpretation="User edited view", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=edited_plan.model_dump())
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pass1a"]["passed"] is True
    assert data["execution"]["status"] == "SUCCESS"
    assert data["pass1b"]["passed"] is True
    rows = data["execution"]["rows"]
    assert len(rows) > 0
    assert "Sub-Category" in rows[0]
    assert "avg_Sales" in rows[0]


# =========================================================================
# 4. Configuring a scatter plot with two numeric axes and raw observations
# =========================================================================
def test_configure_scatter_raw_observations():
    _setup_multi_column_dataset("ds_sales")

    # Scatter plot: Discount (X) vs Profit (Y) without aggregation
    scatter_plan = CandidatePlan(
        plan_id="plan_scatter_raw",
        dataset_id="ds_sales",
        intent="Correlation between Discount and Profit",
        metric=MetricSpec(column="Profit", aggregation=None),  # Raw observations
        dimensions=[DimensionSpec(column="Discount")],
        filters=[],
        visualization=VisualizationType.SCATTER,
        generator="user_editor",
        reasoning=PlanReasoning(interpretation="Scatter correlation", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=scatter_plan.model_dump())
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pass1a"]["passed"] is True
    assert data["execution"]["status"] == "SUCCESS"
    assert "GROUP BY" not in data["execution"]["compiled_sql"]
    assert data["pass1b"]["passed"] is True
    rows = data["execution"]["rows"]
    assert len(rows) == 5  # Raw observations of all 5 rows
    assert "Discount" in rows[0]
    assert "Profit" in rows[0]


# =========================================================================
# 5. Configuring a line chart with supported data arrangement
# =========================================================================
def test_configure_line_chart_arrangement():
    _setup_multi_column_dataset("ds_sales")

    line_plan = CandidatePlan(
        plan_id="plan_line_trend",
        dataset_id="ds_sales",
        intent="Monthly Sales Trend",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Order Date", granularity=Granularity.MONTH)],
        filters=[],
        visualization=VisualizationType.LINE,
        generator="user_editor",
        reasoning=PlanReasoning(interpretation="Monthly trend", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=line_plan.model_dump())
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pass1a"]["passed"] is True
    assert data["execution"]["status"] == "SUCCESS"
    assert data["pass1b"]["passed"] is True
    assert len(data["execution"]["rows"]) > 0


# =========================================================================
# 6. Switching chart types and checking plan execution
# =========================================================================
def test_switch_chart_type_and_execute():
    _setup_multi_column_dataset("ds_sales")

    for viz in [VisualizationType.PIE, VisualizationType.BAR, VisualizationType.LINE, VisualizationType.TABLE]:
        plan = CandidatePlan(
            plan_id=f"plan_viz_{viz.value}",
            dataset_id="ds_sales",
            intent=f"Sales by Category as {viz.value}",
            metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
            dimensions=[DimensionSpec(column="Category")],
            filters=[],
            visualization=viz,
            generator="user_editor",
            reasoning=PlanReasoning(interpretation="Visualization switch", evidence=[]),
        )
        resp = client.post("/api/orchestrator/run-plan", json=plan.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data["pass1a"]["passed"] is True
        assert data["execution"]["status"] == "SUCCESS"


# =========================================================================
# 7. Previewing invalid configuration and confirming safeguard blocks it
# =========================================================================
def test_preview_invalid_configuration_blocked_by_safeguards():
    _setup_multi_column_dataset("ds_sales")

    # Invalid 1: Wildcard '*' with SUM aggregation (illegal DuckDB SQL and invalid in Pass 1a)
    invalid_wildcard_plan = CandidatePlan(
        plan_id="plan_invalid_wildcard",
        dataset_id="ds_sales",
        intent="Invalid Wildcard Sum",
        metric=MetricSpec(column="*", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        filters=[],
        visualization=VisualizationType.BAR,
        generator="user_editor",
        reasoning=PlanReasoning(interpretation="Invalid plan", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=invalid_wildcard_plan.model_dump())
    assert resp.status_code == 200
    data = resp.json()
    assert data["pass1a"]["passed"] is False
    assert any("Wildcard" in issue["message"] for issue in data["pass1a"]["issues"])

    # Invalid 2: Non-existent column in dimension
    invalid_col_plan = CandidatePlan(
        plan_id="plan_invalid_col",
        dataset_id="ds_sales",
        intent="Invalid Column",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="NonExistentColumn")],
        filters=[],
        visualization=VisualizationType.BAR,
        generator="user_editor",
        reasoning=PlanReasoning(interpretation="Invalid plan", evidence=[]),
    )

    resp2 = client.post("/api/orchestrator/run-plan", json=invalid_col_plan.model_dump())
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["pass1a"]["passed"] is False


# =========================================================================
# 8. Confirming preview has sensible dimensions and displays valid results
# =========================================================================
def test_confirm_sensible_dimensions_and_results():
    _setup_multi_column_dataset("ds_sales")

    plan = CandidatePlan(
        plan_id="plan_sensible_check",
        dataset_id="ds_sales",
        intent="Sales by Category",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        filters=[],
        visualization=VisualizationType.BAR,
        generator="user_editor",
        reasoning=PlanReasoning(interpretation="Sensible check", evidence=[]),
    )

    resp = client.post("/api/orchestrator/run-plan", json=plan.model_dump())
    assert resp.status_code == 200
    data = resp.json()
    exec_res = data["execution"]

    assert exec_res["status"] == "SUCCESS"
    assert exec_res["row_count"] == 3  # Furniture, Technology, Office Supplies
    assert len(exec_res["columns"]) == 2
    assert "Category" in exec_res["columns"]
    assert "sum_Sales" in exec_res["columns"]
    # Verify no nulls in required columns
    for row in exec_res["rows"]:
        assert row["Category"] is not None
        assert row["sum_Sales"] is not None
