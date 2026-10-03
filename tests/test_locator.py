import json
import sys
from playwright.sync_api import sync_playwright

def test_locator():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.route("*/**/orchestrator/pipeline*", lambda r: r.fulfill(
            status=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            },
            content_type="application/json",
            body=json.dumps({
                "status": "SUCCESS",
                "winner": {"plan_id": "p1"},
                "dashboard_spec": {
                    "headline": "Special Headline Finding",
                    "panels": [
                        {
                            "id": "p1",
                            "panel_type": "BAR",
                            "title": "Bar Title Test",
                            "x_key": "cat",
                            "y_keys": ["val"],
                            "data": [{"cat": "A", "val": 10}, {"cat": "B", "val": 20}],
                        }
                    ],
                },
            }),
        ))

        page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        chip = page.query_selector('button:has-text("UnitsSold by ProductCategory")')
        if chip:
            chip.click()
            page.wait_for_timeout(300)
        gen_btn = page.query_selector('button:has-text("Generate Dashboard")')
        if gen_btn and not gen_btn.is_disabled():
            gen_btn.click()
            page.wait_for_timeout(2500)

        browser.close()


if __name__ == "__main__":
    test_locator()
