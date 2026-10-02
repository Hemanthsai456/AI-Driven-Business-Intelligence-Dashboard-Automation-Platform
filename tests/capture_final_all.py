import os
import sys
sys.stdout.reconfigure(line_buffering=True)
import json
import time
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\GANDL\.gemini\antigravity-ide\brain\b2b40f26-a42a-43f8-8175-6d95b7722886"

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
        "headline": "Total Amount is highest for Clothing ($2,100.00), demonstrating 88% stability across rank variants.",
        "panels": [
            {
                "id": "p_winner_bar",
                "panel_type": "BAR",
                "title": "Total Amount by Category",
                "description": "Aggregated sales amount grouped by Category",
                "x_key": "Category",
                "y_keys": ["Amount"],
                "data": [
                    {"Category": "Clothing", "Amount": 2100.00},
                    {"Category": "Electronics", "Amount": 1650.49},
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
                    {"group": "Clothing", "Winner (Base)": 1, "Avg Amount": 1, "Units Count": 1},
                    {"group": "Electronics", "Winner (Base)": 2, "Avg Amount": 2, "Units Count": 2},
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

def set_mode(page, is_dark: bool):
    if is_dark:
        page.evaluate("() => { document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark'); }")
    else:
        page.evaluate("() => { document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light'); }")
    page.wait_for_timeout(400)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        # ------------------------------------------------------------------
        # 1. Home with no dataset (Light & Dark)
        # ------------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 960})
        page = ctx.new_page()
        page.goto("http://localhost:3000")
        page.wait_for_selector("#dataset-select")
        page.evaluate("() => { const s = document.querySelector('#dataset-select'); s.value = ''; s.dispatchEvent(new Event('change', { bubbles: true })); }")
        page.wait_for_timeout(500)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_1a_home_no_dataset_light.png"), full_page=True)
        print("1a. Captured gate_1a_home_no_dataset_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_1b_home_no_dataset_dark.png"), full_page=True)
        print("1b. Captured gate_1b_home_no_dataset_dark.png")
        ctx.close()

        # ------------------------------------------------------------------
        # 2. Dataset loaded & idle (Light & Dark)
        # ------------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 960})
        page = ctx.new_page()
        page.goto("http://localhost:3000")
        page.wait_for_selector("#dataset-select")
        # Select messy_dataset
        page.evaluate("""() => {
            const s = document.querySelector('#dataset-select');
            for (let opt of s.options) {
                if (opt.text.includes('messy_dataset')) {
                    s.value = opt.value;
                    s.dispatchEvent(new Event('change', { bubbles: true }));
                    break;
                }
            }
        }""")
        page.wait_for_timeout(1000)

        # Expand cleaning report row
        cleaning_btn = page.query_selector("button:has-text('changes applied')")
        if cleaning_btn:
            cleaning_btn.click()
            page.wait_for_timeout(400)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_2a_dataset_loaded_idle_light.png"), full_page=True)
        print("2a. Captured gate_2a_dataset_loaded_idle_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_2b_dataset_loaded_idle_dark.png"), full_page=True)
        print("2b. Captured gate_2b_dataset_loaded_idle_dark.png")
        ctx.close()

        # ------------------------------------------------------------------
        # 3. Running state (Pipeline Stepper, Spinner, Elapsed, Cancel button)
        # ------------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        # Hold pipeline request pending so running stepper is active
        held_routes = []
        page.route("*/**/orchestrator/pipeline*", lambda r: held_routes.append(r))
        page.goto("http://localhost:3000")
        page.wait_for_selector("#dataset-select")
        page.evaluate("""() => {
            const s = document.querySelector('#dataset-select');
            for (let opt of s.options) {
                if (opt.text.includes('messy_dataset')) {
                    s.value = opt.value;
                    s.dispatchEvent(new Event('change', { bubbles: true }));
                    break;
                }
            }
        }""")
        page.wait_for_timeout(1000)
        page.get_by_text("Amount by Category").click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="Generate Dashboard").click()
        page.wait_for_selector("text=Pipeline execution in progress", timeout=10000)
        page.wait_for_timeout(1200)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_3a_running_light.png"), full_page=True)
        print("3a. Captured gate_3a_running_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_3b_running_dark.png"), full_page=True)
        print("3b. Captured gate_3b_running_dark.png")
        ctx.close()

        # ------------------------------------------------------------------
        # 4. Result state (Panels, Headline, Recharts, Robustness Heatmap, Alternates)
        # ------------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1250})
        page = ctx.new_page()
        page.route("*/**/orchestrator/pipeline*", lambda r: r.fulfill(
            status=200, headers=MOCK_HEADERS, content_type="application/json", body=json.dumps(MOCK_RESULT)
        ))
        page.goto("http://localhost:3000")
        page.wait_for_selector("#dataset-select")
        page.evaluate("""() => {
            const s = document.querySelector('#dataset-select');
            for (let opt of s.options) {
                if (opt.text.includes('messy_dataset')) {
                    s.value = opt.value;
                    s.dispatchEvent(new Event('change', { bubbles: true }));
                    break;
                }
            }
        }""")
        page.wait_for_timeout(1000)
        page.get_by_text("Amount by Category").click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="Generate Dashboard").click()

        page.wait_for_selector("text=Key Analytical Finding", timeout=15000)
        page.wait_for_timeout(2000)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_4a_result_light.png"), full_page=True)
        print("4a. Captured gate_4a_result_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_4b_result_dark.png"), full_page=True)
        print("4b. Captured gate_4b_result_dark.png")
        ctx.close()

        # -------------------------------------------------------------
        # 5. Clarification state (Attention Palette, Tie Warning, Option Cards)
        # -------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()
        page.route("*/**/orchestrator/pipeline*", lambda r: r.fulfill(
            status=200, headers=MOCK_HEADERS, content_type="application/json", body=json.dumps(MOCK_CLARIFICATION)
        ))
        page.goto("http://localhost:3000")
        page.wait_for_selector("#dataset-select")
        page.evaluate("""() => {
            const s = document.querySelector('#dataset-select');
            for (let opt of s.options) {
                if (opt.text.includes('messy_dataset')) {
                    s.value = opt.value;
                    s.dispatchEvent(new Event('change', { bubbles: true }));
                    break;
                }
            }
        }""")
        page.wait_for_timeout(1000)
        page.get_by_text("Amount by Category").click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="Generate Dashboard").click()

        page.wait_for_selector("text=Clarification Needed", timeout=15000)
        page.wait_for_timeout(2000)

        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_5a_clarification_light.png"), full_page=True)
        print("5a. Captured gate_5a_clarification_light.png")

        set_mode(page, True)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_5b_clarification_dark.png"), full_page=True)
        print("5b. Captured gate_5b_clarification_dark.png")
        ctx.close()

        # ------------------------------------------------------------------
        # 6. Second dataset with visibly different suggestion chips
        # ------------------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 960})
        page = ctx.new_page()
        page.goto("http://localhost:3000")
        page.wait_for_selector("#dataset-select")
        # Select baseline.csv
        page.evaluate("""() => {
            const s = document.querySelector('#dataset-select');
            for (let opt of s.options) {
                if (opt.text.includes('baseline.csv')) {
                    s.value = opt.value;
                    s.dispatchEvent(new Event('change', { bubbles: true }));
                    break;
                }
            }
        }""")
        page.wait_for_timeout(1200)
        set_mode(page, False)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "gate_6_second_dataset_suggestions.png"), full_page=True)
        print("6. Captured gate_6_second_dataset_suggestions.png")
        ctx.close()

        # ------------------------------------------------------------------
        # 7. Responsive widths: 1440px, 900px, 390px
        # ------------------------------------------------------------------
        for w, name in [(1440, "gate_7a_responsive_1440.png"), (900, "gate_7b_responsive_900.png"), (390, "gate_7c_responsive_390.png")]:
            ctx = browser.new_context(viewport={"width": w, "height": 850})
            page = ctx.new_page()
            page.goto("http://localhost:3000")
            page.wait_for_selector("#dataset-select")
            page.wait_for_timeout(1000)
            set_mode(page, False)
            page.screenshot(path=os.path.join(ARTIFACT_DIR, name), full_page=False)
            print(f"7. Captured {name} at {w}px")
            ctx.close()

        browser.close()
        print("ALL GATE SCREENSHOTS CAPTURED!")

if __name__ == "__main__":
    main()
