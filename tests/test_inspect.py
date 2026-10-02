import sys
sys.stdout.reconfigure(line_buffering=True)
import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page()
    page.on('console', lambda msg: print('CONSOLE:', msg.text))
    page.on('pageerror', lambda err: print('ERROR:', err))
    page.route('*/**/orchestrator/pipeline*', lambda r: r.fulfill(
        status=200,
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': '*',
            'Access-Control-Allow-Headers': '*'
        },
        content_type='application/json',
        body=json.dumps({
            "status": "SUCCESS",
            "winner": {"plan_id": "p1"},
            "dashboard_spec": {
                "headline": "Special Headline Insight Text",
                "panels": [
                    {
                        "id": "p1",
                        "panel_type": "BAR",
                        "title": "Bar Title Test",
                        "x_key": "cat",
                        "y_keys": ["val"],
                        "data": [{"cat": "A", "val": 10}, {"cat": "B", "val": 20}]
                    }
                ]
            }
        })
    ))
    page.goto('http://localhost:3000')
    page.wait_for_timeout(2000)
    page.click('button:has-text("UnitsSold by ProductCategory")')
    page.wait_for_timeout(300)
    page.click('button:has-text("Generate Dashboard")')
    page.wait_for_timeout(3000)

    # Let's inspect sections
    sections = page.query_selector_all('section')
    print('Sections count:', len(sections))
    if len(sections) >= 3:
        print('Section 3 innerText:\n', sections[2].inner_text())
    page.screenshot(path="tests/test_result_screen.png", full_page=True)
    print("Screenshot saved to tests/test_result_screen.png")
    browser.close()
