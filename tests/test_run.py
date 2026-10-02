import sys
sys.stdout.reconfigure(line_buffering=True)
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page()
    page.on('console', lambda msg: print(f'BROWSER CONSOLE: {msg.text}'))
    page.on('pageerror', lambda err: print(f'BROWSER ERROR: {err}'))
    page.route('*/**/orchestrator/pipeline*', lambda r: (
        print('ROUTED REQUEST:', r.request.url),
        r.fulfill(
            status=200,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': '*',
                'Access-Control-Allow-Headers': '*'
            },
            content_type='application/json',
            body='{"status":"SUCCESS","winner":{"plan_id":"p1"},"dashboard_spec":{"headline":"Test Success Headline","panels":[]}}'
        )
    ))
    page.goto('http://localhost:3000')
    page.wait_for_timeout(2000)
    chip = page.query_selector('button:has-text("UnitsSold")')
    print('Chip found:', chip is not None)
    if chip:
        chip.click()
        page.wait_for_timeout(500)
    
    gen_btn = page.query_selector('button:has-text("Generate Dashboard")')
    print('Gen btn found:', gen_btn is not None)
    if gen_btn:
        print('Gen btn disabled?:', gen_btn.is_disabled())
        gen_btn.click()
    
    page.wait_for_timeout(3000)
    browser.close()
    print('Done!')
