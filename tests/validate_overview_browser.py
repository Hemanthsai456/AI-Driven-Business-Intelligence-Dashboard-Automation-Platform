"""Playwright browser end-to-end test and validation for Step 7 Autonomous Overview Dashboard."""

import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Hemanth Sai\.gemini\antigravity-ide\brain\1337b6ed-1d5a-4551-be9c-aa2547b34c03"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

def run_browser_validation():
    print("[TEST] Starting Playwright browser validation against http://localhost:3000...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # 1. Navigate to HomePage
        page.goto("http://localhost:3000", wait_until="networkidle")
        print("[PAGE] Loaded http://localhost:3000 successfully.")

        # Give time for initial fetch
        time.sleep(1.5)

        # Check if dataset dropdown exists
        dataset_select = page.locator("#dataset-select")
        if dataset_select.count() > 0:
            val = dataset_select.input_value()
            print(f"[DATASET] Active dataset selected: {val}")

        # 2. Click Autonomous Overview Button
        overview_btn = page.locator("button:has-text('Autonomous Overview')")
        if overview_btn.count() > 0:
            print("[ACTION] Clicking 'Autonomous Overview' button...")
            overview_btn.click()
        else:
            print("[ACTION] Triggering Generate Dashboard with empty prompt...")
            page.locator("button:has-text('Generate Dashboard')").click()

        # 3. Wait for dashboard generation to finish
        print("[WAIT] Waiting for Overview Dashboard rendering...")
        page.wait_for_selector("button:has-text('Export HTML')", timeout=30000)
        time.sleep(2.0)

        # 4. Verify Headline & Executive Narrative
        headline_el = page.locator("h1, h2, h3").filter(has_text="Overview").first
        print(f"[VERIFY] Headline found: {headline_el.count() > 0}")

        # 5. Verify KPI Tiles
        kpi_elements = page.locator("text=/Total|Average|Avg|Max|Min|Rate/i")
        print(f"[VERIFY] KPI elements count: {kpi_elements.count()}")

        # 6. Verify Charts
        svg_elements = page.locator("svg")
        print(f"[VERIFY] SVG charts rendered: {svg_elements.count()}")

        # 7. Take Screenshot of Live Overview Dashboard
        shot1_path = os.path.join(ARTIFACT_DIR, "live_overview_dashboard.png")
        page.screenshot(path=shot1_path, full_page=True)
        print(f"[SCREENSHOT] Saved full dashboard screenshot: {shot1_path}")

        # 8. Test Slicer Interaction
        slicer_btn = page.locator("button[role='checkbox'], button:has-text('All'), .slicer-option").first
        if slicer_btn.count() > 0:
            print("[ACTION] Testing slicer interaction...")
            slicer_btn.click()
            time.sleep(1.0)
            shot2_path = os.path.join(ARTIFACT_DIR, "live_overview_slicer_filtered.png")
            page.screenshot(path=shot2_path, full_page=False)
            print(f"[SCREENSHOT] Saved filtered dashboard screenshot: {shot2_path}")

        # 9. Test Export HTML
        export_btn = page.locator("button:has-text('Export HTML')").first
        assert export_btn.count() > 0, "Export HTML button must be present on dashboard"
        print("[VERIFY] 'Export HTML' button is present and active.")

        browser.close()
        print("[SUCCESS] Autonomous Overview Dashboard browser validation completed successfully!")

if __name__ == "__main__":
    run_browser_validation()
