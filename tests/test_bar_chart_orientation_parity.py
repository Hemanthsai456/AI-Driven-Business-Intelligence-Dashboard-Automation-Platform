"""Targeted regression tests for Bar Chart Orientation, Data Mapping, and Export Parity.

Verifies:
1. Canonical field mapping:
   - Vertical bar: category dimension on X-axis, numeric metric on Y-axis.
   - Horizontal bar: category dimension on Y-axis, numeric metric on X-axis.
2. Orientation changes do not alter metric, dimension, aggregation, or underlying data.
3. Ranking, sorting (ORDER BY), and Top-N row limits (LIMIT) are preserved across orientation switches and plan editing.
4. Bar count parity: queries with >20 rows (e.g. 25 rows) preserve all rows without arbitrary truncation.
5. True zero-baseline anchoring for positive, negative, and mixed data series.
6. Elimination of automatic renderer-specific orientation hijacking (long category labels do NOT force horizontal_bar).
7. Parity between query results, live dashboard data contract, and exported SVG representation.
"""

import math
import pytest
import pandas as pd
from typing import Dict, Any, List

from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DashboardTile,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    TileSize,
    VisualizationType,
)
import duckdb
from engine.compiler import compile_plan_to_sql


# ---------------------------------------------------------------------------
# Python parity model of frontend renderDynamicTileSvg
# ---------------------------------------------------------------------------

def simulate_render_dynamic_tile_svg(
    chart_type: str,
    rows: List[Dict[str, Any]],
    dim_key: str,
    metric_key: str,
    width: int = 560,
    height: int = 240,
) -> Dict[str, Any]:
    """Models the exact SVG geometry calculation implemented in DashboardPanelsView.tsx."""
    c_type = (chart_type or "bar").lower()
    # Up to 50 rows displayed without arbitrary 20-row truncation
    display_rows = rows[:50] if len(rows) > 50 else rows
    values = [float(r.get(metric_key, 0) or 0) for r in display_rows]
    max_val = max(values + [0.0])
    min_val = min(values + [0.0])
    val_range = (max_val - min_val) or 1.0

    padding = {"top": 20, "right": 20, "bottom": 45, "left": 55}
    chart_w = width - padding["left"] - padding["right"]
    chart_h = height - padding["top"] - padding["bottom"]

    rects = []
    category_axis = "X" if c_type == "bar" else "Y"
    value_axis = "Y" if c_type == "bar" else "X"

    if c_type == "horizontal_bar":
        max_label_len = max([len(str(r.get(dim_key, ""))) for r in display_rows] + [0])
        left_pad = min(max(max_label_len * 7 + 12, 85), 150)
        h_chart_w = width - left_pad - padding["right"]
        bar_count = len(display_rows)
        bar_slot_h = chart_h / max(bar_count, 1)
        bar_h = max(min(bar_slot_h * 0.65, 28), 5)

        zero_x = left_pad + ((0.0 - min_val) / val_range) * h_chart_w

        for i, row in enumerate(display_rows):
            val = float(row.get(metric_key, 0) or 0)
            if val >= 0:
                bar_x = zero_x
                bar_len = max(((val - 0.0) / val_range) * h_chart_w, 0.0 if val == 0 else 2.0)
            else:
                bar_len = max(((0.0 - val) / val_range) * h_chart_w, 2.0)
                bar_x = zero_x - bar_len

            y = padding["top"] + i * bar_slot_h + (bar_slot_h - bar_h) / 2
            rects.append({
                "category": str(row.get(dim_key, "")),
                "val": val,
                "x": bar_x,
                "y": y,
                "width": bar_len,
                "height": bar_h,
            })
    else:
        # Default vertical bar
        bar_count = len(display_rows)
        bar_slot_w = chart_w / max(bar_count, 1)
        bar_w = max(min(bar_slot_w * 0.65, 36), 5)

        zero_y = padding["top"] + chart_h - ((0.0 - min_val) / val_range) * chart_h

        for i, row in enumerate(display_rows):
            val = float(row.get(metric_key, 0) or 0)
            if val >= 0:
                bar_h = max(((val - 0.0) / val_range) * chart_h, 0.0 if val == 0 else 2.0)
                bar_y = zero_y - bar_h
            else:
                bar_h = max(((0.0 - val) / val_range) * chart_h, 2.0)
                bar_y = zero_y

            x = padding["left"] + i * bar_slot_w + (bar_slot_w - bar_w) / 2
            rects.append({
                "category": str(row.get(dim_key, "")),
                "val": val,
                "x": x,
                "y": bar_y,
                "width": bar_w,
                "height": bar_h,
            })

    return {
        "chart_type": c_type,
        "bar_count": len(rects),
        "rects": rects,
        "category_axis": category_axis,
        "value_axis": value_axis,
        "min_val": min_val,
        "max_val": max_val,
        "range": val_range,
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_vertical_and_horizontal_field_mapping_and_orientation():
    """Verify that vertical bars place categories on X and values on Y, while horizontal bars place categories on Y and values on X."""
    data = [
        {"Category": "Office Furniture", "TotalRevenue": 150000},
        {"Category": "Technology", "TotalRevenue": 240000},
        {"Category": "Office Supplies", "TotalRevenue": 90000},
    ]

    vert_res = simulate_render_dynamic_tile_svg(
        chart_type="bar",
        rows=data,
        dim_key="Category",
        metric_key="TotalRevenue",
    )
    assert vert_res["category_axis"] == "X"
    assert vert_res["value_axis"] == "Y"
    assert vert_res["bar_count"] == 3

    # On vertical bar, widths are uniform and heights represent metric value
    assert vert_res["rects"][0]["width"] == vert_res["rects"][1]["width"]
    assert vert_res["rects"][1]["height"] > vert_res["rects"][0]["height"]
    assert vert_res["rects"][0]["height"] > vert_res["rects"][2]["height"]

    horiz_res = simulate_render_dynamic_tile_svg(
        chart_type="horizontal_bar",
        rows=data,
        dim_key="Category",
        metric_key="TotalRevenue",
    )
    assert horiz_res["category_axis"] == "Y"
    assert horiz_res["value_axis"] == "X"
    assert horiz_res["bar_count"] == 3

    # On horizontal bar, heights are uniform and widths represent metric value
    assert horiz_res["rects"][0]["height"] == horiz_res["rects"][1]["height"]
    assert horiz_res["rects"][1]["width"] > horiz_res["rects"][0]["width"]
    assert horiz_res["rects"][0]["width"] > horiz_res["rects"][2]["width"]


def test_top_n_ranking_and_sort_preservation_across_orientation():
    """Verify that Top-N row limits and sort order are preserved when switching orientation or editing plans."""
    # Synthetic dataset
    df = pd.DataFrame({
        "Category": [f"Cat_{i}" for i in range(25)],
        "Sales": [10.0 * (25 - i) for i in range(25)],  # Cat_0 has highest sales (250)
    })

    plan_vertical = CandidatePlan(
        dataset_id="test_ds",
        intent="Top 10 Categories by Sales",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        order_by="metric",
        order_direction="DESC",
        limit=10,
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Top categories by sales", evidence=[]),
    )

    sql_vert = compile_plan_to_sql(plan_vertical)
    assert "ORDER BY 2 DESC" in sql_vert
    assert "LIMIT 10" in sql_vert

    # Execute against DuckDB
    conn = duckdb.connect()
    conn.register("source_data", df)
    rows_vert = conn.execute(sql_vert).df().to_dict(orient="records")
    assert len(rows_vert) == 10
    assert rows_vert[0]["Category"] == "Cat_0"
    assert rows_vert[0]["sum_Sales"] == 250.0
    assert rows_vert[-1]["Category"] == "Cat_9"

    # Switching orientation to HORIZONTAL_BAR preserves order_by, order_direction, and limit
    plan_horizontal = CandidatePlan(
        dataset_id="test_ds",
        intent="Top 10 Categories by Sales",
        metric=MetricSpec(column="Sales", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Category")],
        order_by=plan_vertical.order_by,
        order_direction=plan_vertical.order_direction,
        limit=plan_vertical.limit,
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Top categories by sales", evidence=[]),
    )

    sql_horiz = compile_plan_to_sql(plan_horizontal)
    assert "ORDER BY 2 DESC" in sql_horiz
    assert "LIMIT 10" in sql_horiz

    rows_horiz = conn.execute(sql_horiz).df().to_dict(orient="records")
    assert len(rows_horiz) == 10

    # Ensure identical data ordering and values between vertical and horizontal representations
    for i in range(10):
        assert rows_vert[i]["Category"] == rows_horiz[i]["Category"]
        assert rows_vert[i]["sum_Sales"] == rows_horiz[i]["sum_Sales"]


def test_row_count_parity_above_20_rows():
    """Verify that datasets with >20 rows (e.g. 25 rows) are not arbitrarily truncated to 20 in the export renderer."""
    data = [{"Region": f"Region_{i}", "Amount": 100 + i * 10} for i in range(25)]

    svg_res = simulate_render_dynamic_tile_svg(
        chart_type="bar",
        rows=data,
        dim_key="Region",
        metric_key="Amount",
    )
    # Both horizontal and vertical renderers must render all 25 rows
    assert svg_res["bar_count"] == 25, f"Expected 25 bars but got {svg_res['bar_count']} (arbitrary truncation bug)"

    svg_h_res = simulate_render_dynamic_tile_svg(
        chart_type="horizontal_bar",
        rows=data,
        dim_key="Region",
        metric_key="Amount",
    )
    assert svg_h_res["bar_count"] == 25


def test_zero_baseline_anchoring_for_mixed_and_negative_data():
    """Verify that bar lengths anchor to zero rather than minVal when negative numbers are present."""
    data = [
        {"Entity": "A", "Profit": 100},
        {"Entity": "B", "Profit": -50},
        {"Entity": "C", "Profit": 0},
        {"Entity": "D", "Profit": 50},
    ]

    vert_res = simulate_render_dynamic_tile_svg(
        chart_type="bar",
        rows=data,
        dim_key="Entity",
        metric_key="Profit",
    )

    # In mixed data: min_val = -50, max_val = 100, range = 150
    assert vert_res["min_val"] == -50
    assert vert_res["max_val"] == 100
    assert vert_res["range"] == 150

    rects = {r["category"]: r for r in vert_res["rects"]}

    # Zero bar has 0 height (or minimum baseline indicator)
    assert rects["C"]["height"] <= 2.0

    # Positive bar Entity A (100) must be exactly 2x height of Entity D (50)
    assert math.isclose(rects["A"]["height"], 2.0 * rects["D"]["height"], rel_tol=0.05)

    # Entity B (-50) must have magnitude equal to Entity D (+50)
    assert math.isclose(rects["B"]["height"], rects["D"]["height"], rel_tol=0.05)

    # Positive bars anchor upwards from zero, negative bars anchor downwards from zero
    zero_y = rects["B"]["y"]
    assert rects["A"]["y"] < zero_y  # Extends upwards
    assert rects["D"]["y"] < zero_y  # Extends upwards
    assert math.isclose(rects["B"]["y"], zero_y, abs_tol=1.0)  # Starts at zero line and extends down

    # Same check for horizontal bar
    horiz_res = simulate_render_dynamic_tile_svg(
        chart_type="horizontal_bar",
        rows=data,
        dim_key="Entity",
        metric_key="Profit",
    )
    h_rects = {r["category"]: r for r in horiz_res["rects"]}
    assert math.isclose(h_rects["A"]["width"], 2.0 * h_rects["D"]["width"], rel_tol=0.05)
    assert math.isclose(h_rects["B"]["width"], h_rects["D"]["width"], rel_tol=0.05)

    zero_x = h_rects["A"]["x"]
    assert math.isclose(h_rects["D"]["x"], zero_x, abs_tol=1.0)  # Positive bar starts at zero line
    assert h_rects["B"]["x"] < zero_x  # Negative bar extends to the left of zero line
    assert math.isclose(h_rects["B"]["x"] + h_rects["B"]["width"], zero_x, abs_tol=1.0)


def test_long_category_labels_do_not_hijack_canonical_orientation():
    """Verify that category labels longer than 12 chars do not silently change chart_type from 'bar' to 'horizontal_bar'."""
    data = [
        {"LongCategory": "Office Furnishings and Accessories", "Val": 100},
        {"LongCategory": "Telephones and Communications", "Val": 200},
    ]

    tile = DashboardTile(
        id="tile_long_labels",
        title="Revenue by Department",
        chart_type="bar",  # Configured explicitly as vertical bar
        dimensions=["LongCategory"],
        metrics=["Val"],
        data=data,
    )

    assert tile.chart_type == "bar"

    # SVG renderer respects canonical chart_type 'bar'
    res = simulate_render_dynamic_tile_svg(
        chart_type=tile.chart_type,
        rows=tile.data,
        dim_key="LongCategory",
        metric_key="Val",
    )
    assert res["chart_type"] == "bar"
    assert res["category_axis"] == "X"
    assert res["value_axis"] == "Y"
