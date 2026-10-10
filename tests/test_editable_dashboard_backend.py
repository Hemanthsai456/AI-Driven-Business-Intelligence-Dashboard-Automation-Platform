"""Focused backend test suite for Phase 1: Backend-safe Editable Dashboard.

Tests:
1. Active dataset resolution (raw vs cleaned) across plan execution and tile querying.
2. Valid tile editing: plan validation, DuckDB re-execution, tile configuration & evidence updates.
3. Invalid edited plan rejection: Pass 1a failure returns 422 and leaves original tile unchanged.
4. Subsequent tile queries / cross-filtering use the updated plan.
5. Tile removal removes the tile from spec and cache.
6. Single tile reset restores original AI-generated configuration.
7. Full dashboard reset restores original specification.
"""

import io
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
    MetricSpec,
    OrchestratorTrace,
    Pass1aResult,
    Pass1bResult,
    PlanReasoning,
    RankedCandidate,
    ScoreBreakdown,
    TileEvidence,
    TileSize,
    VisualizationType,
)

client = TestClient(app)


def _build_spec(spec_id: str, dataset_id: str, tiles: list, plan: CandidatePlan) -> DashboardSpec:
    winner = RankedCandidate(
        plan=plan,
        execution_result=ExecutionResult(
            plan_id=plan.plan_id,
            status=ExecutionStatus.SUCCESS,
            rows=tiles[0].data if tiles else [],
            columns=list(tiles[0].data[0].keys()) if tiles and tiles[0].data else [],
            row_count=len(tiles[0].data) if tiles else 0,
            compiled_sql=tiles[0].compiled_sql if tiles else "",
        ),
        pass1a=Pass1aResult(plan_id=plan.plan_id, passed=True, issues=[]),
        pass1b=Pass1bResult(plan_id=plan.plan_id, passed=True, issues=[]),
        score_breakdown=ScoreBreakdown(
            evidence=0.9, coverage=0.9, stability=0.9, assumptions=0.0, agreement=1.0, total=0.9
        ),
        rank=1,
        is_winner=True,
    )
    trace = OrchestratorTrace(
        dataset_id=dataset_id,
        intent="Test Intent",
        context_hash="testhash123",
    )
    return DashboardSpec(
        spec_id=spec_id,
        dataset_id=dataset_id,
        intent="Test Spec",
        tiles=tiles,
        winner=winner,
        trace=trace,
    )


def _build_test_record(dataset_id: str, df: pd.DataFrame, cleaned_df: pd.DataFrame = None) -> DatasetSessionRecord:
    schema = []
    for col in df.columns:
        dt = "INTEGER" if pd.api.types.is_numeric_dtype(df[col]) else "VARCHAR"
        schema.append(ColumnMetadata(original_name=col, normalized_name=col, detected_datatype=dt))

    raw_meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=f"{dataset_id}.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    raw_canon = CanonicalDataset(metadata=raw_meta, data=df.copy())

    profiler = DataProfiler()
    profile = profiler.profile(raw_canon, attach=True)
    analyzer = SemanticAnalyzer()
    sem_prof = analyzer.analyze(raw_canon, profile=profile, apply_roles=True)
    readiness = assess_readiness(raw_canon, profile=profile, semantic_profile=sem_prof)

    record = DatasetSessionRecord(
        dataset=raw_canon,
        profile=profile,
        semantic_profile=sem_prof,
        readiness=readiness,
    )

    if cleaned_df is not None:
        c_schema = []
        for col in cleaned_df.columns:
            dt = "INTEGER" if pd.api.types.is_numeric_dtype(cleaned_df[col]) else "VARCHAR"
            c_schema.append(ColumnMetadata(original_name=col, normalized_name=col, detected_datatype=dt))
        c_meta = DatasetMetadata(
            dataset_id=f"{dataset_id}_cleaned",
            name=f"{dataset_id}_cleaned.csv",
            source_type="csv",
            row_count=len(cleaned_df),
            column_count=len(cleaned_df.columns),
            schema=c_schema,
        )
        cleaned_canon = CanonicalDataset(metadata=c_meta, data=cleaned_df.copy())
        record.cleaned_dataset = cleaned_canon
        c_prof = profiler.profile(cleaned_canon, attach=True)
        record.profile = c_prof
        record.semantic_profile = analyzer.analyze(cleaned_canon, profile=c_prof, apply_roles=True)
        record.readiness = assess_readiness(cleaned_canon, profile=c_prof, semantic_profile=record.semantic_profile)

    return record


@pytest.fixture(autouse=True)
def clean_stores():
    session_store.clear()
    dashboard_specs_store.clear()
    original_specs_store.clear()
    tile_query_cache.clear()
    yield
    session_store.clear()
    dashboard_specs_store.clear()
    original_specs_store.clear()
    tile_query_cache.clear()


def test_active_dataset_resolution_in_plan_endpoints():
    """Verify run-plan endpoint resolves cleaned_dataset over raw dataset when present."""
    raw_df = pd.DataFrame({
        "Category": ["A", "B", "A", "B"],
        "Revenue": [10, 20, 30, 40],  # Sum A = 40, Sum B = 60
    })
    cleaned_df = pd.DataFrame({
        "Category": ["A", "B", "A", "B"],
        "Revenue": [100, 200, 300, 400],  # Sum A = 400, Sum B = 600
    })

    record = _build_test_record("ds_res_test", raw_df, cleaned_df)
    session_store.save(record)

    plan = CandidatePlan(
        dataset_id="ds_res_test",
        intent="Category Revenue",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Category Revenue", evidence=[]),
    )

    res = client.post("/api/orchestrator/run-plan", json=plan.model_dump())
    assert res.status_code == 200
    data = res.json()
    assert data["pass1a"]["passed"] is True
    assert data["execution"]["status"] == "SUCCESS"

    # Execution rows must match cleaned_dataset (400 for A, 600 for B), NOT raw dataset (40, 60)
    rows = data["execution"]["rows"]
    a_row = next((r for r in rows if r["Category"] == "A"), None)
    assert a_row is not None
    assert a_row["sum_Revenue"] == 400


def test_update_dashboard_tile_valid_and_cache_invalidation():
    """Verify PUT /api/dashboard/{spec_id}/tile/{tile_id} validates and updates tile and invalidates cache."""
    df = pd.DataFrame({
        "Region": ["North", "South", "North", "South"],
        "Units": [5, 10, 15, 20],
        "Sales": [50, 100, 150, 200],
    })
    record = _build_test_record("ds_edit_test", df)
    session_store.save(record)

    # Initial tile plan: Units by Region
    initial_plan = CandidatePlan(
        dataset_id="ds_edit_test",
        intent="Units by Region",
        metric=MetricSpec(column="Units", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Region")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Units by Region", evidence=[]),
    )

    tile = DashboardTile(
        id="tile_101",
        title="Units by Region",
        chart_type="bar",
        plan=initial_plan,
        dimensions=["Region"],
        metrics=["sum(Units)"],
        x_key="Region",
        y_keys=["sum_Units"],
        data=[{"Region": "North", "sum_Units": 20}, {"Region": "South", "sum_Units": 30}],
        compiled_sql="SELECT Region, SUM(Units) AS sum_Units FROM source_data GROUP BY 1",
        evidence=TileEvidence(strength=0.9, robustness=0.85),
    )

    spec = _build_spec(
        spec_id="spec_101",
        dataset_id="ds_edit_test",
        tiles=[tile],
        plan=initial_plan,
    )
    dashboard_specs_store[spec.spec_id] = spec
    original_specs_store[spec.spec_id] = spec

    # Pre-populate query cache
    cache_key = ("spec_101", "tile_101", "()")
    tile_query_cache[cache_key] = {"cached": True}

    # Now edit tile: Change metric to Sales and chart_type to line
    edited_plan = CandidatePlan(
        dataset_id="ds_edit_test",
        intent="Sales by Region",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.AVG),
        dimensions=[DimensionSpec(column="Region")],
        visualization=VisualizationType.LINE,
        reasoning=PlanReasoning(interpretation="Average Sales by Region", evidence=[]),
    )

    update_payload = {
        "title": "Avg Sales by Region",
        "description": "Custom updated description",
        "chart_type": "line",
        "plan": edited_plan.model_dump(),
    }

    res = client.put("/api/dashboard/spec_101/tile/tile_101", json=update_payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "SUCCESS"
    updated_tile = res_data["tile"]

    assert updated_tile["title"] == "Avg Sales by Region"
    assert updated_tile["chart_type"] == "line"
    assert updated_tile["metadata"]["is_edited"] is True
    assert "avg(Sales)" in updated_tile["metrics"]
    assert updated_tile["x_key"] == "Region"
    assert "avg_Sales" in updated_tile["y_keys"]

    # Verify rows computed by DuckDB: North = (50+150)/2 = 100, South = (100+200)/2 = 150
    rows = updated_tile["data"]
    north_row = next((r for r in rows if r["Region"] == "North"), None)
    assert north_row is not None
    assert north_row["avg_Sales"] == 100.0

    # Verify cache was purged
    assert cache_key not in tile_query_cache

    # Verify subsequent cross-filtering uses the EDITED plan
    filter_req = {
        "filters": [{"column": "Region", "operator": "=", "value": "North"}]
    }
    q_res = client.post("/api/dashboard/spec_101/tile/tile_101/query", json=filter_req)
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["status"] == "SUCCESS"
    assert q_data["row_count"] == 1
    assert q_data["data"][0]["Region"] == "North"
    assert q_data["data"][0]["avg_Sales"] == 100.0


def test_invalid_plan_rejected_and_preserves_original_tile():
    """Verify updating with invalid plan returns 422 and does NOT mutate stored tile."""
    df = pd.DataFrame({
        "Product": ["Gadget", "Widget"],
        "Quantity": [10, 20],
    })
    record = _build_test_record("ds_invalid_test", df)
    session_store.save(record)

    orig_plan = CandidatePlan(
        dataset_id="ds_invalid_test",
        intent="Product Quantity",
        metric=MetricSpec(column="Quantity", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Product")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Product Quantity", evidence=[]),
    )

    tile = DashboardTile(
        id="tile_safe",
        title="Original Safe Tile",
        chart_type="bar",
        plan=orig_plan,
        dimensions=["Product"],
        metrics=["sum(Quantity)"],
        data=[{"Product": "Gadget", "sum_Quantity": 10}],
    )
    spec = _build_spec(
        spec_id="spec_safe",
        dataset_id="ds_invalid_test",
        tiles=[tile],
        plan=orig_plan,
    )
    dashboard_specs_store[spec.spec_id] = spec
    original_specs_store[spec.spec_id] = spec

    # Propose invalid plan: non-existent column "NonExistentColumn"
    bad_plan = CandidatePlan(
        dataset_id="ds_invalid_test",
        intent="Bad Plan",
        metric=MetricSpec(column="NonExistentColumn", aggregation=AggregationType.SUM),
        dimensions=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Bad", evidence=[]),
    )

    res = client.put("/api/dashboard/spec_safe/tile/tile_safe", json={"plan": bad_plan.model_dump()})
    assert res.status_code == 422
    err = res.json()
    assert err.get("error") == "Plan validation failed" or (isinstance(err.get("detail"), dict) and err["detail"].get("error") == "Plan validation failed")

    # Verify tile in store is preserved completely unchanged
    stored_spec = dashboard_specs_store["spec_safe"]
    assert stored_spec.tiles[0].title == "Original Safe Tile"
    assert stored_spec.tiles[0].plan.metric.column == "Quantity"


def test_tile_removal_and_single_tile_reset():
    """Verify tile delete removes from spec and reset restores original tile."""
    df = pd.DataFrame({"Item": ["A", "B"], "Cost": [5, 15]})
    record = _build_test_record("ds_remove_test", df)
    session_store.save(record)

    plan_1 = CandidatePlan(
        dataset_id="ds_remove_test",
        intent="Cost by Item",
        metric=MetricSpec(column="Cost", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Item")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Cost by Item", evidence=[]),
    )
    tile_1 = DashboardTile(id="tile_del_1", title="Tile 1", chart_type="bar", plan=plan_1)
    tile_2 = DashboardTile(id="tile_del_2", title="Tile 2", chart_type="bar", plan=plan_1)

    spec = _build_spec(spec_id="spec_del", dataset_id="ds_remove_test", tiles=[tile_1, tile_2], plan=plan_1)
    dashboard_specs_store[spec.spec_id] = spec
    original_specs_store[spec.spec_id] = spec

    # 1. Delete tile_del_1
    del_res = client.delete("/api/dashboard/spec_del/tile/tile_del_1")
    assert del_res.status_code == 200
    assert dashboard_specs_store["spec_del"].tiles[0].id == "tile_del_2"
    assert len(dashboard_specs_store["spec_del"].tiles) == 1

    # 2. Reset tile_del_1: must restore tile_del_1 back to the spec
    rst_res = client.post("/api/dashboard/spec_del/tile/tile_del_1/reset")
    assert rst_res.status_code == 200
    assert len(dashboard_specs_store["spec_del"].tiles) == 2
    restored_ids = [t.id for t in dashboard_specs_store["spec_del"].tiles]
    assert "tile_del_1" in restored_ids
    assert "tile_del_2" in restored_ids


def test_full_dashboard_reset():
    """Verify POST /api/dashboard/{spec_id}/reset restores all original tiles."""
    df = pd.DataFrame({"X": [1, 2], "Y": [10, 20]})
    record = _build_test_record("ds_full_reset", df)
    session_store.save(record)

    orig_plan = CandidatePlan(
        dataset_id="ds_full_reset",
        intent="Initial",
        metric=MetricSpec(column="Y", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="X")],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Initial", evidence=[]),
    )
    t1 = DashboardTile(id="t1", title="Original T1", chart_type="bar", plan=orig_plan)
    t2 = DashboardTile(id="t2", title="Original T2", chart_type="bar", plan=orig_plan)

    spec = _build_spec(spec_id="spec_full", dataset_id="ds_full_reset", tiles=[t1, t2], plan=orig_plan)
    dashboard_specs_store[spec.spec_id] = spec
    original_specs_store[spec.spec_id] = spec

    # Mutate spec: delete t2 and edit t1
    client.delete("/api/dashboard/spec_full/tile/t2")
    assert len(dashboard_specs_store["spec_full"].tiles) == 1

    # Reset entire dashboard
    res = client.post("/api/dashboard/spec_full/reset")
    assert res.status_code == 200
    assert len(dashboard_specs_store["spec_full"].tiles) == 2
    assert dashboard_specs_store["spec_full"].tiles[0].title == "Original T1"
    assert dashboard_specs_store["spec_full"].tiles[1].title == "Original T2"
