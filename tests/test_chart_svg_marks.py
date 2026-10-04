"""Real browser test: loads a dashboard from a fixture spec and asserts that each bar chart has bar elements with height > 0.

Requirement:
"Add a Playwright or Cypress test that loads a dashboard from a fixture spec and asserts that each bar chart has bar elements with height > 0.
Delete or replace test_chart_svg_marks.py if it doesn't do this. Give the real F0 root cause with the line that was fixed."
"""

import json
import pytest
from playwright.sync_api import sync_playwright
from pathlib import Path

def test_bar_chart_elements_height_greater_than_zero():
    """Load dashboard from fixture spec and assert each bar chart has bar elements with height > 0."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Fixture spec with Bar Chart and Line Chart
        fixture_spec = {
            "status": "SUCCESS",
            "message": "Dashboard ready",
            "spec_id": "fixture_spec_bar_height_test",
            "dashboard_title": "Executive Sales Overview",
            "headline": "North leads with 4,500 in Total Sales, with 88.0% rank stability across variant interpretations.",
            "panels": [
                {
                    "panel_id": "panel_bar_fixture",
                    "panel_type": "BAR",
                    "title": "Revenue by Region",
                    "description": "Total revenue grouped by region",
                    "x_key": "Region",
                    "y_keys": ["Revenue"],
                    "data": [
                        {"Region": "North", "Revenue": 4500},
                        {"Region": "South", "Revenue": 3200},
                        {"Region": "West", "Revenue": 2800},
                        {"Region": "East", "Revenue": 1900},
                    ],
                    "metadata": {
                        "metric": "Revenue",
                        "dimensions": ["Region"],
                        "robustness": 0.88,
                    },
                }
            ],
            "tiles": [
                {
                    "id": "tile_bar_fixture",
                    "title": "Revenue by Region",
                    "chart_type": "bar",
                    "size": {"w": 8, "h": 4},
                    "priority": 1,
                    "generator": "rule-based baseline",
                    "evidence": {"strength": 0.95, "robustness": 0.88, "fdr_passed": True, "n": 4},
                    "data": [
                        {"Region": "North", "Revenue": 4500},
                        {"Region": "South", "Revenue": 3200},
                        {"Region": "West", "Revenue": 2800},
                        {"Region": "East", "Revenue": 1900},
                    ],
                    "x_key": "Region",
                    "y_keys": ["Revenue"],
                    "dimensions": ["Region"],
                    "metrics": ["Revenue"],
                }
            ],
            "slicers": [
                {
                    "id": "slicer_Region",
                    "column": "Region",
                    "role": "DIMENSION",
                    "control_type": "multi_select",
                    "options": [
                        {"value": "North", "label": "North", "count": 45},
                        {"value": "South", "label": "South", "count": 32},
                    ],
                }
            ],
            "ranked_candidates": [],
            "winner": {
                "plan_id": "fixture_plan_1",
                "generator": "rule_baseline",
                "visualization": "BAR",
                "score": 0.92,
                "score_breakdown": {"evidence": 0.9, "coverage": 1.0, "stability": 0.88, "assumptions": 0.0, "total": 0.92},
                "metric": "Revenue",
                "dimensions": ["Region"],
                "reasoning": {"interpretation": "Revenue by Region", "evidence": []},
                "pass2_passed": True,
                "pass2_issues": [],
                "execution": {
                    "rows": [
                        {"Region": "North", "Revenue": 4500},
                        {"Region": "South", "Revenue": 3200},
                        {"Region": "West", "Revenue": 2800},
                        {"Region": "East", "Revenue": 1900},
                    ],
                    "columns": ["Region", "Revenue"],
                    "row_count": 4,
                },
            },
            "is_tie": False,
            "cascade_depth": 0,
            "mode": "discovery",
            "rejected_insights": [],
        }

        fixture_spec["dashboard_spec"] = dict(fixture_spec)

        # Mock API routes
        def handle_datasets(route):
            route.fulfill(
                status=200,
                headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                body=json.dumps([{"dataset_id": "test_ds_1", "filename": "Sales Data.csv", "row_count": 500}]),
            )

        page.route("**/api/datasets*", handle_datasets)
        page.route("**/datasets*", handle_datasets)

        page.route(
            "**/api/orchestrator/pipeline*",
            lambda route: route.fulfill(
                status=200,
                headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                body=json.dumps(fixture_spec),
            ),
        )

        page.route(
            "**/orchestrator/pipeline*",
            lambda route: route.fulfill(
                status=200,
                headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                body=json.dumps(fixture_spec),
            ),
        )

        page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        # Trigger dashboard generation
        gen_btn = page.wait_for_selector('button:has-text("Generate Dashboard"):not([disabled])', timeout=10000)
        assert gen_btn is not None, "Generate button not found or disabled!"
        gen_btn.click()

        # Wait for dashboard cards and SVG to render
        page.wait_for_selector("svg.recharts-surface", timeout=12000)
        page.wait_for_timeout(2500)

        # Save screenshot for audit
        ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=ARTIFACT_DIR / "debug_test_chart.png")

        # Find all bar charts on the page
        bar_charts = page.query_selector_all(".recharts-wrapper:has(.recharts-bar)")
        if not bar_charts:
            bar_charts = page.query_selector_all("svg.recharts-surface:has(.recharts-bar-rectangle), svg.recharts-surface:has(rect.recharts-rectangle)")

        assert len(bar_charts) > 0, "No bar chart elements found on dashboard!"

        for chart_idx, chart in enumerate(bar_charts):
            # Query bar elements (individual bars) in this bar chart (can be rect or path)
            bars = chart.query_selector_all(".recharts-bar-rectangles path, .recharts-bar-rectangles rect, .recharts-bar path, .recharts-bar rect, .recharts-rectangle, rect")
            assert len(bars) > 0, f"Bar chart #{chart_idx + 1} has zero bar elements!"

            for bar_idx, bar in enumerate(bars):
                # Retrieve height via attribute and bounding box
                attr_height = bar.get_attribute("height")
                box = bar.bounding_box()
                box_height = box["height"] if box else 0.0

                measured_height = float(attr_height) if (attr_height and float(attr_height) > 0) else box_height
                print(f"[Chart #{chart_idx+1} Bar #{bar_idx+1}] attr_height={attr_height}, box_height={box_height}")

                assert measured_height > 0, (
                    f"Bar element #{bar_idx + 1} in bar chart #{chart_idx + 1} has height <= 0! "
                    f"(attr_height={attr_height}, box_height={box_height})"
                )

        browser.close()


if __name__ == "__main__":
    test_bar_chart_elements_height_greater_than_zero()
    print("PLAYWRIGHT REAL BROWSER TEST PASSED: All bar charts have bar elements with height > 0!")
