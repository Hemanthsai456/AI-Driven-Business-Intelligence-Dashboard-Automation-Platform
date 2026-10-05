import os
import sys
sys.stdout.reconfigure(line_buffering=True)
import json
from playwright.sync_api import sync_playwright
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

MOCK_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
}

MOCK_RESULT = {
    "run_id": "run_test_pass_polish",
    "status": "SUCCESS",
    "dataset_id": "ds_tmpoyoact3u_83bd1e_cleaned",
    "intent": "Amount by Category",
    "winner": {
        "plan_id": "plan_agg_sum_amount",
        "description": "Aggregate sum of Amount grouped by Category",
        "metric": "Amount",
        "dimension": "Category",
        "aggregation": "SUM",
        "score": 0.94,
        "robustness": 0.88,
        "coverage": 1.0,
        "ambiguity": 0.15
    },
    "dashboard_spec": {
        "headline": "Total Amount is highest for Electronics ($1,650.49), demonstrating 88% stability across rank variants.",
        "tiles": [
            {
                "id": "tile_winner_bar",
                "title": "Total Amount by Category",
                "chart_type": "bar",
                "size": {"w": 8, "h": 4},
                "priority": 1,
                "generator": "rule-based baseline",
                "evidence": {"strength": 0.95, "robustness": 0.88, "fdr_passed": True, "n": 3},
                "data": [
                    {"Category": "Electronics", "Amount": 1650.49},
                    {"Category": "Clothing", "Amount": 2100.00},
                    {"Category": "Home & Garden", "Amount": 530.75},
                ],
                "x_key": "Category",
                "y_keys": ["Amount"],
                "dimensions": ["Category"],
                "metrics": ["Amount"],
            }
        ],
        "panels": [
            {
                "id": "p_winner_bar",
                "panel_type": "BAR",
                "title": "Total Amount by Category",
                "description": "Aggregated sales amount grouped by Category",
                "x_key": "Category",
                "y_keys": ["Amount"],
                "data": [
                    {"Category": "Electronics", "Amount": 1650.49},
                    {"Category": "Clothing", "Amount": 2100.00},
                    {"Category": "Home & Garden", "Amount": 530.75}
                ]
            },
            {
                "id": "p_robustness_heatmap",
                "panel_type": "HEATMAP",
                "title": "Variant Robustness Matrix (Group × Interpretation)",
                "description": "Rank stability across metric and aggregation perturbations",
                "y_keys": ["Winner (Base)", "Avg Amount", "Units Count"],
                "metadata": {
                    "stability_score": 0.88
                },
                "data": [
                    {"group": "Electronics", "Winner (Base)": 1, "Avg Amount": 1, "Units Count": 1},
                    {"group": "Clothing", "Winner (Base)": 2, "Avg Amount": 2, "Units Count": 2},
                    {"group": "Home & Garden", "Winner (Base)": 3, "Avg Amount": 3, "Units Count": 3}
                ]
            },
            {
                "id": "p_alternates",
                "panel_type": "ALTERNATES",
                "title": "Evaluated Candidate Interpretations",
                "description": "Non-winning candidate plans ranked by multi-objective consensus",
                "data": [
                    {
                        "plan_id": "alt_1",
                        "visualization": "BAR",
                        "interpretation": "Average Amount by Category",
                        "score": 0.82,
                        "robustness": 0.80,
                        "aggregation": "AVG",
                        "metric": "Amount",
                        "dimension": "Category",
                        "reason_not_winner": "Lower consensus stability score"
                    },
                    {
                        "plan_id": "alt_2",
                        "visualization": "BAR",
                        "interpretation": "Total Units by Category",
                        "score": 0.65,
                        "robustness": 0.60,
                        "aggregation": "SUM",
                        "metric": "Units",
                        "dimension": "Category",
                        "reason_not_winner": "Sub-optimal intent alignment"
                    }
                ]
            }
        ]
    }
}

MOCK_CLARIFICATION = {
    "run_id": "run_test_tie_polish",
    "status": "NEEDS_CLARIFICATION",
    "dataset_id": "ds_tmpoyoact3u_83bd1e_cleaned",
    "intent": "Amount by Category",
    "message": "Top candidate plans produced identical ranking scores within tie epsilon.",
    "clarification_options": [
        {
            "plan_id": "plan_sum_amount",
            "interpretation": "Total Gross Sales Amount by Category",
            "metric": "Amount",
            "dimension": "Category",
            "aggregation": "SUM",
            "score": 0.892,
            "robustness": 0.85
        },
        {
            "plan_id": "plan_avg_discount",
            "interpretation": "Average Discount Percentage by Category",
            "metric": "Discount",
            "dimension": "Category",
            "aggregation": "AVG",
            "score": 0.887,
            "robustness": 0.84
        }
    ]
}

def test_result_and_clarification():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)

        def set_mode(page, is_dark: bool):
            if is_dark:
                page.evaluate("() => { document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark'); }")
            else:
                page.evaluate("() => { document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light'); }")
            page.wait_for_timeout(300)

        # -------------------------------------------------------------
        # 4. Result State
        # -------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1200})
        page = ctx.new_page()
        page.route("*/**/orchestrator/pipeline*", lambda r: (
            print("Routing result response"),
            r.fulfill(
                status=200,
                headers=MOCK_HEADERS,
                content_type="application/json",
                body=json.dumps(MOCK_RESULT)
            )
        ))
        def handle_datasets_mock(route):
            url = route.request.url.split("?")[0].rstrip("/")
            if url.endswith("/datasets"):
                route.fulfill(
                    status=200,
                    headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                    body=json.dumps([{"dataset_id": "test_ds_1", "filename": "messy_dataset.csv", "row_count": 500}]),
                )
            else:
                route.fulfill(
                    status=200,
                    headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                    body=json.dumps({
                        "dataset_id": "test_ds_1",
                        "filename": "messy_dataset.csv",
                        "row_count": 500,
                        "column_count": 4,
                        "source_type": "csv",
                    }),
                )

        page.route("**/api/datasets*", handle_datasets_mock)
        page.route("**/datasets*", handle_datasets_mock)
        page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)

        # Select first available dataset
        page.evaluate("""() => {
            const sel = document.querySelector('select');
            if (sel && sel.options.length > 0) {
                sel.selectedIndex = 0;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""")
        page.wait_for_timeout(1000)

        # Set intent
        chip = page.query_selector('button:has-text("Amount by Category")')
        if chip:
            chip.click()
        else:
            textarea = page.query_selector('textarea')
            if textarea:
                textarea.fill("Amount by Category")
        page.wait_for_timeout(500)

        # Click Generate
        gen_btn = page.wait_for_selector('button:has-text("Generate Dashboard"):not([disabled])', timeout=10000)
        gen_btn.click()

        print("Waiting for Result Panels...")
        page.wait_for_selector(".tile-card, svg.recharts-surface, h1, h2, h3", timeout=15000)
        page.wait_for_timeout(1500)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_4a_result_light.png"), full_page=True)
        print("Captured: gate_4a_result_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_4b_result_dark.png"), full_page=True)
        print("Captured: gate_4b_result_dark.png")
        ctx.close()

        # -------------------------------------------------------------
        # 5. Clarification State
        # -------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()
        page.route("*/**/orchestrator/pipeline*", lambda r: (
            print("Routing clarification response"),
            r.fulfill(
                status=200,
                headers=MOCK_HEADERS,
                content_type="application/json",
                body=json.dumps(MOCK_CLARIFICATION)
            )
        ))
        page.route("**/api/datasets*", handle_datasets_mock)
        page.route("**/datasets*", handle_datasets_mock)
        page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)

        page.evaluate("""() => {
            const sel = document.querySelector('select');
            if (sel && sel.options.length > 0) {
                sel.selectedIndex = 0;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""")
        page.wait_for_timeout(1000)

        chip = page.query_selector('button:has-text("Amount by Category")')
        if chip:
            chip.click()
        else:
            textarea = page.query_selector('textarea')
            if textarea:
                textarea.fill("Amount by Category")
        page.wait_for_timeout(500)

        gen_btn = page.wait_for_selector('button:has-text("Generate Dashboard"):not([disabled])', timeout=10000)
        gen_btn.click()

        print("Waiting for Clarification Card...")
        page.wait_for_selector("text=Ambiguous Intent", timeout=15000)
        page.wait_for_timeout(1500)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_5a_clarification_light.png"), full_page=True)
        print("Captured: gate_5a_clarification_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_5b_clarification_dark.png"), full_page=True)
        print("Captured: gate_5b_clarification_dark.png")
        ctx.close()

        browser.close()
        print("RESULT & CLARIFICATION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_result_and_clarification()
