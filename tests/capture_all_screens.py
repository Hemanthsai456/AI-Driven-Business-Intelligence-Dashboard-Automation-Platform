import os
import sys
sys.stdout.reconfigure(line_buffering=True)
import time
import json
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\GANDL\.gemini\antigravity-ide\brain\b2b40f26-a42a-43f8-8175-6d95b7722886"

MOCK_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, *",
}

MOCK_RESULT = {
    "run_id": "run_test_pass_polish",
    "status": "SUCCESS",
    "dataset_id": "ds_tmphky79gsx_ce0e49_cleaned",
    "intent": "UnitsSold by ProductCategory",
    "winner": {
        "plan_id": "plan_agg_sum_unitssold",
        "description": "Aggregate sum of UnitsSold grouped by ProductCategory",
        "metric": "UnitsSold",
        "dimension": "ProductCategory",
        "aggregation": "SUM",
        "score": 0.94,
        "robustness": 0.88,
        "coverage": 1.0,
        "ambiguity": 0.15
    },
    "dashboard_spec": {
        "headline": "Total UnitsSold is highest for Electronics (3,450 units), demonstrating 88% stability across rank variants.",
        "panels": [
            {
                "id": "p_winner_bar",
                "panel_type": "BAR",
                "title": "Total UnitsSold by ProductCategory",
                "description": "Aggregated sales volume grouped by ProductCategory",
                "x_key": "ProductCategory",
                "y_keys": ["UnitsSold"],
                "data": [
                    {"ProductCategory": "Electronics", "UnitsSold": 3450},
                    {"ProductCategory": "Apparel", "UnitsSold": 2100},
                    {"ProductCategory": "Home Goods", "UnitsSold": 1820},
                    {"ProductCategory": "Sports", "UnitsSold": 1250},
                    {"ProductCategory": "Books", "UnitsSold": 680}
                ]
            },
            {
                "id": "p_robustness_heatmap",
                "panel_type": "HEATMAP",
                "title": "Variant Robustness Matrix (Group × Interpretation)",
                "description": "Rank stability across metric and aggregation perturbations",
                "y_keys": ["Winner (Base)", "Avg UnitsSold", "Transaction Count"],
                "metadata": {
                    "stability_score": 0.88
                },
                "data": [
                    {"group": "Electronics", "Winner (Base)": 1, "Avg UnitsSold": 1, "Transaction Count": 1},
                    {"group": "Apparel", "Winner (Base)": 2, "Avg UnitsSold": 2, "Transaction Count": 2},
                    {"group": "Home Goods", "Winner (Base)": 3, "Avg UnitsSold": 3, "Transaction Count": 3},
                    {"group": "Sports", "Winner (Base)": 4, "Avg UnitsSold": 4, "Transaction Count": 4},
                    {"group": "Books", "Winner (Base)": 5, "Avg UnitsSold": 5, "Transaction Count": 5}
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
                        "interpretation": "Average UnitsSold by ProductCategory",
                        "score": 0.82,
                        "robustness": 0.80,
                        "aggregation": "AVG",
                        "metric": "UnitsSold",
                        "dimension": "ProductCategory",
                        "reason_not_winner": "Lower consensus stability score"
                    },
                    {
                        "plan_id": "alt_2",
                        "visualization": "BAR",
                        "interpretation": "Total Transaction Count by ProductCategory",
                        "score": 0.65,
                        "robustness": 0.60,
                        "aggregation": "COUNT",
                        "metric": "TransactionID",
                        "dimension": "ProductCategory",
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
    "dataset_id": "ds_tmphky79gsx_ce0e49_cleaned",
    "intent": "UnitsSold by ProductCategory",
    "message": "Top candidates produce identical ranking or score gap < RANK_TIE_EPSILON.",
    "clarification_options": [
        {
            "plan_id": "plan_sum_unitssold",
            "interpretation": "Total UnitsSold Volume by ProductCategory",
            "metric": "UnitsSold",
            "dimension": "ProductCategory",
            "aggregation": "SUM",
            "score": 0.892,
            "robustness": 0.85
        },
        {
            "plan_id": "plan_avg_revenue",
            "interpretation": "Average Revenue Amount by ProductCategory",
            "metric": "Revenue",
            "dimension": "ProductCategory",
            "aggregation": "AVG",
            "score": 0.887,
            "robustness": 0.84
        }
    ]
}

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        def set_mode(page, is_dark: bool):
            if is_dark:
                page.evaluate("() => { document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark'); }")
            else:
                page.evaluate("() => { document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light'); }")
            page.wait_for_timeout(300)

        # -------------------------------------------------------------
        # 4. Result State (All Panels: Headline, Chart, Heatmap, Alternates)
        # -------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1200})
        page = ctx.new_page()
        page.route("*/**/orchestrator/pipeline*", lambda r: (
            print("Routing mock result response"),
            r.fulfill(
                status=200,
                headers=MOCK_HEADERS,
                content_type="application/json",
                body=json.dumps(MOCK_RESULT)
            )
        ))
        page.goto("http://localhost:3000")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        chip = page.query_selector('button:has-text("UnitsSold by ProductCategory")')
        if chip:
            chip.click()
            page.wait_for_timeout(500)

        gen_btn = page.query_selector('button:has-text("Generate Dashboard")')
        if gen_btn:
            gen_btn.click()

        print("Waiting for Key Analytical Finding...")
        page.wait_for_selector("text=Key Analytical Finding", timeout=15000)
        page.wait_for_timeout(1500)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_4a_result_light.png"), full_page=True)
        print("Captured: gate_4a_result_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_4b_result_dark.png"), full_page=True)
        print("Captured: gate_4b_result_dark.png")
        ctx.close()

        # -------------------------------------------------------------
        # 5. Clarification State (Attention Palette, Tie Warning)
        # -------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()
        page.route("*/**/orchestrator/pipeline*", lambda r: (
            print("Routing mock clarification response"),
            r.fulfill(
                status=200,
                headers=MOCK_HEADERS,
                content_type="application/json",
                body=json.dumps(MOCK_CLARIFICATION)
            )
        ))
        page.goto("http://localhost:3000")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        chip = page.query_selector('button:has-text("UnitsSold by ProductCategory")')
        if chip:
            chip.click()
            page.wait_for_timeout(500)

        gen_btn = page.query_selector('button:has-text("Generate Dashboard")')
        if gen_btn:
            gen_btn.click()

        print("Waiting for Clarification Needed...")
        page.wait_for_selector("text=Clarification Needed", timeout=15000)
        page.wait_for_timeout(1500)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_5a_clarification_light.png"), full_page=True)
        print("Captured: gate_5a_clarification_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_5b_clarification_dark.png"), full_page=True)
        print("Captured: gate_5b_clarification_dark.png")
        ctx.close()

        browser.close()
        print("ALL DONE!")

if __name__ == "__main__":
    capture()
