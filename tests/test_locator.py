import sys
sys.stdout.reconfigure(line_buffering=True)
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page()

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
                "headline": "Special Headline Finding",
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
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(1500)

    page.get_by_text('UnitsSold by ProductCategory').click()
    page.wait_for_timeout(300)
    page.get_by_role('button', name='Generate Dashboard').click()
    page.wait_for_timeout(3000)

    html = page.evaluate("() => document.querySelectorAll('section')[2].innerHTML")
    print("CARD 3 HTML:\n", html[:1500])
    browser.close()
