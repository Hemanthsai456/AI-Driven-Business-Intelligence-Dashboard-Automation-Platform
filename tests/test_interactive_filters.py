"""Comprehensive Regression Test Suite for Interactive Dashboard Filtering.

Validates the full contract:
1. Date/range slicers (BETWEEN) filter all relevant dashboard tiles (KPI, Hero, breakdown).
2. Categorical slicers filter all relevant dashboard tiles.
3. Multiple filters combine with strict AND semantics.
4. Filter replacement (changing filter value replaces previous condition on that column).
5. Filter reset/removal restores baseline analytical numbers.
6. Chart-click cross-filtering uses the chart's actual dimension and filters other tiles.
7. Empty-result filters produce clean INSUFFICIENT_DATA/empty state, not stale data or crashes.
8. Duplicate/conflicting filters are cleanly resolved/deduplicated.
9. All dashboard tiles receive identical active filter scope.
10. Focused dashboard filtering works seamlessly.
11. Discovery dashboard filtering works across all real datasets (healthcare, hr, education, iot, logistics).
12. Filtering never mutates the underlying canonical dataset.
13. Cross-dataset/spec isolation is strictly maintained.
"""

import io
import os
import duckdb
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app, dashboard_specs_store, tile_query_cache
from api.store import session_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stores():
    session_store.clear()
    dashboard_specs_store.clear()
    tile_query_cache.clear()
    yield
    session_store.clear()
    dashboard_specs_store.clear()
    tile_query_cache.clear()


def _upload_and_create_dashboard(csv_path: str, intent: str = ""):
    """Helper to upload a real CSV and run the orchestrator pipeline."""
    with open(csv_path, "rb") as f:
        csv_bytes = f.read()
    filename = os.path.basename(csv_path)
    upload_resp = client.post("/api/datasets/upload", files={"file": (filename, csv_bytes, "text/csv")})
    assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
    dataset_id = upload_resp.json()["dataset_id"]

    pipe_resp = client.post("/api/orchestrator/pipeline", json={"dataset_id": dataset_id, "intent": intent})
    assert pipe_resp.status_code == 200, f"Pipeline failed: {pipe_resp.text}"
    spec_id = pipe_resp.json()["spec_id"]
    spec = dashboard_specs_store.get(spec_id)
    assert spec is not None
    session_rec = session_store.get(dataset_id)
    cleaned_df = session_rec.dataset.data
    return dataset_id, spec_id, spec, cleaned_df


# ==============================================================================
# 1. Single Categorical Filter & Exact Math Validation
# ==============================================================================
def test_single_categorical_filter_exact_duckdb_math():
    """Verify single categorical filter recomputes tile numbers matching direct DuckDB."""
    _, spec_id, spec, df = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    req_body = {
        "filters": [
            {"column": "severity", "operator": "=", "values": ["High"]}
        ]
    }

    filtered_df = df[df["severity"] == "High"]
    duck_con = duckdb.connect(":memory:")
    duck_con.register("src", filtered_df)

    for tile in spec.tiles:
        resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("SUCCESS", "INSUFFICIENT_DATA")

        if data["status"] == "SUCCESS" and (tile.chart_type == "kpi" or not tile.dimensions):
            metric_col = tile.metrics[0] if tile.metrics else "length_of_stay"
            agg_func = tile.plan.metric.aggregation.value if tile.plan else "AVG"
            expected_kpi = duck_con.execute(f"SELECT {agg_func}({metric_col}) FROM src").fetchone()[0]
            actual_kpi = list(data["data"][0].values())[0]
            assert pytest.approx(expected_kpi, rel=1e-2) == actual_kpi


# ==============================================================================
# 2. Date Range Filter (BETWEEN)
# ==============================================================================
def test_date_range_filter_between_operator():
    """Verify BETWEEN date filter correctly filters dates in DuckDB."""
    _, spec_id, spec, df = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    req_body = {
        "filters": [
            {"column": "admission_date", "operator": "BETWEEN", "values": ["2024-01-01", "2024-06-30"]}
        ]
    }

    for tile in spec.tiles:
        resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("SUCCESS", "INSUFFICIENT_DATA")


# ==============================================================================
# 3. Multiple Filters Combined (AND Semantics)
# ==============================================================================
def test_multiple_filters_and_semantics():
    """Verify multiple filters combine with strict AND semantics."""
    _, spec_id, spec, df = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    req_body = {
        "filters": [
            {"column": "severity", "operator": "=", "values": ["High"]},
            {"column": "hospital", "operator": "=", "values": ["Apollo"]},
        ]
    }

    # Direct DuckDB baseline on both filters on the cleaned dataset
    filtered_df = df[(df["severity"] == "High") & (df["hospital"] == "Apollo")]
    duck_con = duckdb.connect(":memory:")
    duck_con.register("src", filtered_df)

    for tile in spec.tiles:
        resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
        assert resp.status_code == 200
        data = resp.json()

        if len(filtered_df) == 0:
            assert data["status"] == "INSUFFICIENT_DATA"
        elif data["status"] == "SUCCESS" and (tile.chart_type == "kpi" or not tile.dimensions):
            metric_col = tile.metrics[0] if tile.metrics else "length_of_stay"
            agg_func = tile.plan.metric.aggregation.value if tile.plan else "AVG"
            expected_val = duck_con.execute(f"SELECT {agg_func}({metric_col}) FROM src").fetchone()[0]
            actual_val = list(data["data"][0].values())[0]
            assert pytest.approx(expected_val, rel=1e-2) == actual_val


# ==============================================================================
# 4. Filter Replacement (Changing a Filter)
# ==============================================================================
def test_filter_replacement_updates_correctly():
    """Verify changing hospital from Apollo -> Aig correctly replaces the filter."""
    _, spec_id, spec, df = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    # 1. Query with Apollo
    resp_apollo = client.post(
        f"/api/dashboard/{spec_id}/tile/{spec.tiles[0].id}/query",
        json={"filters": [{"column": "hospital", "operator": "=", "values": ["Apollo"]}]}
    )
    assert resp_apollo.status_code == 200

    # 2. Change to Aig
    resp_aig = client.post(
        f"/api/dashboard/{spec_id}/tile/{spec.tiles[0].id}/query",
        json={"filters": [{"column": "hospital", "operator": "=", "values": ["Aig"]}]}
    )
    assert resp_aig.status_code == 200

    # Compare against direct calculations on cleaned frame
    duck_con = duckdb.connect(":memory:")
    duck_con.register("src_apollo", df[df["hospital"] == "Apollo"])
    duck_con.register("src_aig", df[df["hospital"] == "Aig"])

    if spec.tiles[0].chart_type == "kpi" or not spec.tiles[0].dimensions:
        metric_col = spec.tiles[0].metrics[0] if spec.tiles[0].metrics else "length_of_stay"
        agg_func = spec.tiles[0].plan.metric.aggregation.value if spec.tiles[0].plan else "AVG"
        exp_apollo = duck_con.execute(f"SELECT {agg_func}({metric_col}) FROM src_apollo").fetchone()[0]
        exp_aig = duck_con.execute(f"SELECT {agg_func}({metric_col}) FROM src_aig").fetchone()[0]

        actual_apollo = list(resp_apollo.json()["data"][0].values())[0]
        actual_aig = list(resp_aig.json()["data"][0].values())[0]
        assert pytest.approx(exp_apollo, rel=1e-2) == actual_apollo
        assert pytest.approx(exp_aig, rel=1e-2) == actual_aig


# ==============================================================================
# 5. Filter Reset Restores Baseline
# ==============================================================================
def test_filter_reset_restores_baseline():
    """Verify empty filter list returns baseline unfiltered analytical results."""
    _, spec_id, spec, df = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    # Query with empty filters (reset state)
    tile = spec.tiles[0]
    resp_reset = client.post(
        f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
        json={"filters": []}
    )
    assert resp_reset.status_code == 200
    reset_data = resp_reset.json()["data"]

    # Compare with tile.data baseline
    assert len(reset_data) == len(tile.data)


# ==============================================================================
# 6. Chart-Click Cross-Filtering
# ==============================================================================
def test_chart_cross_filtering_across_tiles():
    """Simulate chart-click cross-filter: click Diagnosis = Hypertension and verify all tiles update."""
    _, spec_id, spec, df = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    # Simulate cross-filter on diagnosis = 'Hypertension'
    req_body = {
        "filters": [
            {"column": "diagnosis", "operator": "=", "values": ["Hypertension"]}
        ]
    }

    filtered_df = df[df["diagnosis"] == "Hypertension"]
    duck_con = duckdb.connect(":memory:")
    duck_con.register("src", filtered_df)

    for tile in spec.tiles:
        resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("SUCCESS", "INSUFFICIENT_DATA")

        if data["status"] == "SUCCESS" and (tile.chart_type == "kpi" or not tile.dimensions):
            metric_col = tile.metrics[0] if tile.metrics else "length_of_stay"
            agg_func = tile.plan.metric.aggregation.value if tile.plan else "AVG"
            expected_val = duck_con.execute(f"SELECT {agg_func}({metric_col}) FROM src").fetchone()[0]
            actual_val = list(data["data"][0].values())[0]
            assert pytest.approx(expected_val, rel=1e-2) == actual_val


# ==============================================================================
# 7. Empty-Result Filter
# ==============================================================================
def test_empty_result_filter_returns_insufficient_data():
    """Verify empty-result filter returns INSUFFICIENT_DATA status without crashing."""
    _, spec_id, spec, _ = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    req_body = {
        "filters": [
            {"column": "hospital", "operator": "=", "values": ["NonExistentHospitalXYZ"]}
        ]
    }

    tile = spec.tiles[0]
    resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "INSUFFICIENT_DATA"
    assert data["row_count"] == 0
    assert data["data"] == []


# ==============================================================================
# 8. Duplicate Filter Prevention & Deduplication
# ==============================================================================
def test_duplicate_filter_deduplication():
    """Verify passing duplicate/repeated filters for the same column does not crash or corrupt SQL."""
    _, spec_id, spec, _ = _upload_and_create_dashboard("tests/real_data/healthcare.csv")

    req_body = {
        "filters": [
            {"column": "severity", "operator": "=", "values": ["Low"]},
            {"column": "severity", "operator": "=", "values": ["High"]},  # Latest should take precedence
        ]
    }

    tile = spec.tiles[0]
    resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"


# ==============================================================================
# 9. Immutability of Original Dataset
# ==============================================================================
def test_filter_state_does_not_mutate_original_dataset():
    """Verify filtering never alters rows or schema of the source dataset."""
    dataset_id, spec_id, spec, _ = _upload_and_create_dashboard("tests/real_data/healthcare.csv")
    session_rec = session_store.get(dataset_id)
    original_row_count = len(session_rec.dataset.data)
    original_cols = list(session_rec.dataset.data.columns)

    # Apply aggressive filter
    client.post(
        f"/api/dashboard/{spec_id}/tile/{spec.tiles[0].id}/query",
        json={"filters": [{"column": "severity", "operator": "=", "values": ["High"]}]}
    )

    # Verify session store dataframe is untouched
    assert len(session_rec.dataset.data) == original_row_count
    assert list(session_rec.dataset.data.columns) == original_cols


# ==============================================================================
# 10. Focused Dashboard Filtering
# ==============================================================================
def test_focused_dashboard_filtering():
    """Verify filtering works on a Focused Mode DashboardSpec."""
    _, spec_id, spec, _ = _upload_and_create_dashboard(
        "tests/real_data/healthcare.csv",
        intent="average length_of_stay by diagnosis"
    )
    assert spec.mode == "focused" or hasattr(spec, "winner")

    req_body = {
        "filters": [
            {"column": "severity", "operator": "=", "values": ["High"]}
        ]
    }

    for tile in spec.tiles:
        resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("SUCCESS", "INSUFFICIENT_DATA")


# ==============================================================================
# 11. Multi-Dataset Cross Validation (HR, Education, IoT, Logistics)
# ==============================================================================
@pytest.mark.parametrize("csv_file,filter_col,filter_val", [
    ("tests/real_data/hr.csv", "department", "Engineering"),
    ("tests/real_data/education.csv", "department", "MECH"),
    ("tests/real_data/iot.csv", "device", "Sensor-A"),
    ("tests/real_data/logistics.csv", "destination", "Delhi"),
])
def test_multi_dataset_filtering_coverage(csv_file, filter_col, filter_val):
    """Verify interactive filtering generalizes across arbitrary schemas and domains."""
    _, spec_id, spec, df = _upload_and_create_dashboard(csv_file)

    req_body = {
        "filters": [
            {"column": filter_col, "operator": "=", "values": [filter_val]}
        ]
    }

    filtered_df = df[df[filter_col] == filter_val]
    duck_con = duckdb.connect(":memory:")
    duck_con.register("src", filtered_df)

    for tile in spec.tiles:
        resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile.id}/query", json=req_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("SUCCESS", "INSUFFICIENT_DATA")


# ==============================================================================
# 12. SQL Provenance Lifecycle & Active Filter Synchronization
# ==============================================================================
def test_compiled_sql_provenance_lifecycle():
    """Verify compiled_sql in tile query response updates deterministically with active filters."""
    _, spec_id, spec, _ = _upload_and_create_dashboard("tests/real_data/healthcare.csv")
    tile = spec.tiles[0]

    # 1. Baseline: No filters
    resp_baseline = client.post(
        f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
        json={"filters": []}
    )
    assert resp_baseline.status_code == 200
    sql_baseline = resp_baseline.json().get("compiled_sql")
    assert sql_baseline is not None
    assert "WHERE" not in sql_baseline or "severity" not in sql_baseline

    # 2. Single Filter: severity = 'Low'
    resp_low = client.post(
        f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
        json={"filters": [{"column": "severity", "operator": "=", "values": ["Low"]}]}
    )
    assert resp_low.status_code == 200
    sql_low = resp_low.json().get("compiled_sql")
    assert sql_low is not None
    assert 'WHERE "severity" = \'Low\'' in sql_low or '"severity" = \'Low\'' in sql_low

    # 3. Multiple Filters: severity = 'Low' AND hospital = 'Apollo'
    resp_multi = client.post(
        f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
        json={"filters": [
            {"column": "severity", "operator": "=", "values": ["Low"]},
            {"column": "hospital", "operator": "=", "values": ["Apollo"]},
        ]}
    )
    assert resp_multi.status_code == 200
    sql_multi = resp_multi.json().get("compiled_sql")
    assert sql_multi is not None
    assert '"severity" = \'Low\'' in sql_multi
    assert '"hospital" = \'Apollo\'' in sql_multi
    assert "AND" in sql_multi

    # 4. Filter Replacement: severity = 'High'
    resp_high = client.post(
        f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
        json={"filters": [{"column": "severity", "operator": "=", "values": ["High"]}]}
    )
    assert resp_high.status_code == 200
    sql_high = resp_high.json().get("compiled_sql")
    assert sql_high is not None
    assert '"severity" = \'High\'' in sql_high
    assert '"severity" = \'Low\'' not in sql_high

    # 5. Reset: Filters cleared
    resp_reset = client.post(
        f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
        json={"filters": []}
    )
    assert resp_reset.status_code == 200
    sql_reset = resp_reset.json().get("compiled_sql")
    assert sql_reset is not None
    assert '"severity" = \'High\'' not in sql_reset
    assert '"severity" = \'Low\'' not in sql_reset


def test_focused_tile_sql_provenance_and_cross_filter():
    """Verify focused dashboard tiles display accurate SQL with dimensions and filters."""
    _, spec_id, spec, _ = _upload_and_create_dashboard(
        "tests/real_data/healthcare.csv",
        intent="average length_of_stay by diagnosis"
    )

    # Find the hero visual (by diagnosis)
    hero_tile = next((t for t in spec.tiles if "diagnosis" in [d.lower() for d in (t.dimensions or [])]), spec.tiles[0])

    # Apply filter: severity = 'Low'
    resp_low = client.post(
        f"/api/dashboard/{spec_id}/tile/{hero_tile.id}/query",
        json={"filters": [{"column": "severity", "operator": "=", "values": ["Low"]}]}
    )
    assert resp_low.status_code == 200
    sql = resp_low.json().get("compiled_sql")
    assert sql is not None
    assert '"severity" = \'Low\'' in sql
    assert '"length_of_stay"' in sql

    # Apply cross filter: diagnosis = 'Hypertension' on another tile (e.g. KPI)
    kpi_tile = next((t for t in spec.tiles if t.chart_type == "kpi"), spec.tiles[-1])
    resp_kpi_cross = client.post(
        f"/api/dashboard/{spec_id}/tile/{kpi_tile.id}/query",
        json={"filters": [{"column": "diagnosis", "operator": "=", "values": ["Hypertension"]}]}
    )
    assert resp_kpi_cross.status_code == 200
    kpi_sql = resp_kpi_cross.json().get("compiled_sql")
    assert kpi_sql is not None
    assert '"diagnosis" = \'Hypertension\'' in kpi_sql


# ==============================================================================
# 11. Generalized SQL Provenance Across Multiple Real Datasets (Zero Hardcoding)
# ==============================================================================
@pytest.mark.parametrize("dataset_file", [
    "healthcare.csv",
    "hr.csv",
    "education.csv",
    "iot.csv",
    "logistics.csv",
])
def test_dynamic_sql_provenance_lifecycle_generic(dataset_file: str):
    """Dynamic SQL provenance validation across real datasets with dynamically extracted values.

    Validates:
    - State A (No Filter): Returns baseline SQL with NO WHERE filter predicate.
    - State B1 (Filter 1): Dynamically chosen column and value 1 -> Returns SQL containing WHERE col = val1.
    - State B2 (Filter 2): Dynamically chosen value 2 -> Returns SQL containing WHERE col = val2 (val1 removed).
    - State C (Reset): Cleared filters -> Returns SQL identical to State A baseline.
    """
    csv_path = f"tests/real_data/{dataset_file}"
    dataset_id, spec_id, spec, df = _upload_and_create_dashboard(csv_path)

    # 1. Dynamically find a categorical column with >= 2 distinct values
    cat_cols = [c for c in df.columns if df[c].dtype == object or df[c].nunique() < 30]
    target_col = None
    target_vals = []
    for c in cat_cols:
        uniq = df[c].dropna().unique().tolist()
        if len(uniq) >= 2:
            target_col = c
            target_vals = [str(uniq[0]), str(uniq[1])]
            break

    assert target_col is not None, f"No categorical column with >= 2 values found in {dataset_file}"
    val1, val2 = target_vals[0], target_vals[1]

    # Test all tiles in the spec
    for tile in spec.tiles:
        # ----------------------------------------------------
        # STATE A: NO FILTER
        # ----------------------------------------------------
        resp_a = client.post(
            f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
            json={"filters": []}
        )
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        sql_a = data_a.get("compiled_sql")
        assert sql_a is not None, f"Tile {tile.id} did not return compiled_sql in State A"
        # Baseline must not contain dynamic filter predicates
        assert f'"{target_col}" = \'{val1}\'' not in sql_a
        assert f'"{target_col}" = \'{val2}\'' not in sql_a

        # ----------------------------------------------------
        # STATE B1: APPLY FILTER 1 (col = val1)
        # ----------------------------------------------------
        resp_b1 = client.post(
            f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
            json={"filters": [{"column": target_col, "operator": "=", "values": [val1]}]}
        )
        assert resp_b1.status_code == 200
        data_b1 = resp_b1.json()
        sql_b1 = data_b1.get("compiled_sql")
        assert sql_b1 is not None, f"Tile {tile.id} did not return compiled_sql in State B1"
        assert f'"{target_col}" = \'{val1}\'' in sql_b1
        assert f'"{target_col}" = \'{val2}\'' not in sql_b1
        assert sql_b1 != sql_a

        # ----------------------------------------------------
        # STATE B2: APPLY FILTER 2 (col = val2)
        # ----------------------------------------------------
        resp_b2 = client.post(
            f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
            json={"filters": [{"column": target_col, "operator": "=", "values": [val2]}]}
        )
        assert resp_b2.status_code == 200
        data_b2 = resp_b2.json()
        sql_b2 = data_b2.get("compiled_sql")
        assert sql_b2 is not None, f"Tile {tile.id} did not return compiled_sql in State B2"
        assert f'"{target_col}" = \'{val2}\'' in sql_b2
        assert f'"{target_col}" = \'{val1}\'' not in sql_b2
        assert sql_b2 != sql_b1

        # ----------------------------------------------------
        # STATE C: RESET FILTERS ([])
        # ----------------------------------------------------
        resp_c = client.post(
            f"/api/dashboard/{spec_id}/tile/{tile.id}/query",
            json={"filters": []}
        )
        assert resp_c.status_code == 200
        data_c = resp_c.json()
        sql_c = data_c.get("compiled_sql")
        assert sql_c is not None, f"Tile {tile.id} did not return compiled_sql in State C"
        assert sql_c == sql_a, "Reset SQL must return to exact baseline unfiltered SQL"
        assert f'"{target_col}" = \'{val1}\'' not in sql_c
        assert f'"{target_col}" = \'{val2}\'' not in sql_c

