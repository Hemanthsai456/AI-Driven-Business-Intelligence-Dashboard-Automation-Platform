"""Backend integration tests for Stage F: Power BI-Style Tile Query Endpoint.

Gate Requirements:
1. Tile query with a valid filter returns numbers that match a direct DuckDB calculation on the same filtered frame.
2. Unknown column rejected with typed error (400).
3. Injection-style value rejected with typed error (400).
4. Cache returns identical results.
"""

import duckdb
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


@pytest.fixture
def populated_dashboard():
    """Upload dataset and run discovery pipeline to generate spec and tiles."""
    lines = ["Region,Category,Revenue,Units,OrderDate"]
    for i in range(40):
        lines.append(f"North,Electronics,{1000 + i * 10},{10 + i % 5},2024-01-{(i%28)+1:02d}")
    for i in range(25):
        lines.append(f"South,Furniture,{500 + i * 5},{5 + i % 3},2024-02-{(i%28)+1:02d}")
    for i in range(20):
        lines.append(f"West,Apparel,{300 + i * 4},{8 + i % 4},2024-03-{(i%28)+1:02d}")
    for i in range(15):
        lines.append(f"East,HomeGoods,{200 + i * 2},{3 + i % 2},2024-04-{(i%28)+1:02d}")
    csv_content = ("\n".join(lines) + "\n").encode("utf-8")
    files = {"file": ("sales_f_test.csv", csv_content, "text/csv")}
    upload_resp = client.post("/api/datasets/upload", files=files)
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]

    # Run pipeline in discovery mode
    pipe_resp = client.post(
        "/api/orchestrator/pipeline",
        json={"dataset_id": dataset_id, "intent": ""},
    )
    assert pipe_resp.status_code == 200
    pipe_data = pipe_resp.json()
    spec_id = pipe_data["spec_id"]
    spec = dashboard_specs_store.get(spec_id)
    assert spec is not None
    assert len(spec.tiles) > 0

    return {
        "dataset_id": dataset_id,
        "spec_id": spec_id,
        "spec": spec,
        "csv_content": csv_content,
    }


def test_tile_query_valid_filter_matches_direct_duckdb(populated_dashboard):
    """1. Tile query with a valid filter returns numbers that match a direct DuckDB calculation."""
    spec_id = populated_dashboard["spec_id"]
    spec = populated_dashboard["spec"]

    # Select a visual tile with dimensions
    tile = next((t for t in spec.tiles if t.dimensions and t.data), spec.tiles[0])
    tile_id = tile.id
    filtered_dim = tile.dimensions[0] if tile.dimensions else "Category"

    # Get sample value from tile data
    first_val = tile.data[0].get(tile.x_key or filtered_dim) if tile.data else "Electronics"

    req_body = {
        "filters": [
            {
                "column": filtered_dim,
                "operator": "=",
                "values": [first_val],
            }
        ]
    }

    # Query tile endpoint
    resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile_id}/query", json=req_body)
    assert resp.status_code == 200
    tile_res = resp.json()
    assert tile_res["status"] in ("SUCCESS", "INSUFFICIENT_DATA")

    # Direct DuckDB calculation on the same filtered frame
    import pandas as pd
    import io
    df = pd.read_csv(io.BytesIO(populated_dashboard["csv_content"]))
    filtered_df = df[df[filtered_dim] == first_val]

    metric_col = tile.metrics[0] if tile.metrics else "Revenue"
    # Run direct DuckDB aggregate
    duck_con = duckdb.connect(":memory:")
    duck_con.register("test_frame", filtered_df)
    agg_func = "COUNT" if metric_col == "*" or (tile.plan and tile.plan.metric.aggregation.value in ("COUNT", "COUNT_DISTINCT")) else (tile.plan.metric.aggregation.value if tile.plan else "SUM")
    direct_res = duck_con.execute(f"SELECT {agg_func}({metric_col}) as total FROM test_frame").fetchone()[0]

    # Verify tile result numbers match direct calculation
    if tile_res["data"] and len(tile_res["data"]) > 0:
        y_key = tile.y_keys[0] if tile.y_keys else [k for k in tile_res["data"][0].keys() if k != filtered_dim][0]
        # Sum of the metric in returned rows
        tile_total = sum(float(r[y_key]) for r in tile_res["data"] if r.get(y_key) is not None)
        assert pytest.approx(direct_res, abs=1e-2) == tile_total


def test_tile_query_unknown_column_rejected(populated_dashboard):
    """2. Unknown column rejected with typed error (400)."""
    spec_id = populated_dashboard["spec_id"]
    tile_id = populated_dashboard["spec"].tiles[0].id

    req_body = {
        "filters": [
            {
                "column": "non_existent_column_xyz",
                "operator": "=",
                "value": "AnyValue",
            }
        ]
    }

    resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile_id}/query", json=req_body)
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data or "detail" in data
    err_text = str(data).lower()
    assert "unknown column" in err_text or "not exist" in err_text


def test_tile_query_injection_value_rejected(populated_dashboard):
    """3. Injection-style value rejected with typed error (400)."""
    spec_id = populated_dashboard["spec_id"]
    tile_id = populated_dashboard["spec"].tiles[0].id

    req_body = {
        "filters": [
            {
                "column": "Category",
                "operator": "=",
                "value": "Electronics'; DROP TABLE source_data; --",
            }
        ]
    }

    resp = client.post(f"/api/dashboard/{spec_id}/tile/{tile_id}/query", json=req_body)
    assert resp.status_code == 400
    data = resp.json()
    err_text = str(data).lower()
    assert "injection" in err_text or "invalid" in err_text


def test_tile_query_cache_returns_identical_results(populated_dashboard):
    """4. Cache returns identical results."""
    spec_id = populated_dashboard["spec_id"]
    tile_id = populated_dashboard["spec"].tiles[0].id

    req_body = {
        "filters": [
            {
                "column": "Category",
                "operator": "=",
                "value": "Furniture",
            }
        ]
    }

    # First call - cache miss
    resp1 = client.post(f"/api/dashboard/{spec_id}/tile/{tile_id}/query", json=req_body)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["cached"] is False

    # Second call - cache hit
    resp2 = client.post(f"/api/dashboard/{spec_id}/tile/{tile_id}/query", json=req_body)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data1["row_count"] == data2["row_count"]
    assert data1["data"] == data2["data"]
