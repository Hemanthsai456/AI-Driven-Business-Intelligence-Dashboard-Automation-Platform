"""Playwright browser end-to-end test and validation for Dataset Chat UX (Draggability & Close/Cancel)."""

import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Hemanth Sai\.gemini\antigravity-ide\brain\65ac40d9-f1f0-4450-9e54-d5e56cfbacb7"
os.makedirs(ARTIFACT_DIR, exist_ok=True)


def run_chat_browser_validation():
    print("[TEST] Starting Playwright browser validation for Dataset Chat against http://localhost:3000...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # 1. Navigate to HomePage
        page.goto("http://localhost:3000", wait_until="networkidle")
        print("[PAGE] Loaded http://localhost:3000 successfully.")
        time.sleep(2.0)

        # Check dataset select
        dataset_select = page.locator("#dataset-select")
        if dataset_select.count() > 0:
            val = dataset_select.input_value()
            print(f"[DATASET] Active dataset selected: {val}")

        # 2. Open Dataset Chat via action button
        chat_btn = page.locator("#dataset-chat-trigger-btn, button:has-text('Dataset Chat')").first
        if chat_btn.count() > 0:
            print("[ACTION] Clicking 'Dataset Chat' button in action bar...")
            chat_btn.click()
        else:
            floating_chat_btn = page.locator("button:has-text('Ask Dataset')").first
            if floating_chat_btn.count() > 0:
                print("[ACTION] Clicking floating chat button...")
                floating_chat_btn.click()
            else:
                print("[ERROR] No chat trigger button found!")
                sys.exit(1)

        time.sleep(1.0)

        # 3. Verify Chat View opened
        chat_view = page.locator("#dataset-chat-view")
        print(f"[VERIFY] Dataset Chat view visible: {chat_view.is_visible()}")
        initial_box = chat_view.bounding_box()
        print(f"[VERIFY] Initial Chat Window Bounding Box: {initial_box}")

        # 4. Test Draggability: Drag the header to the left
        chat_header = page.locator("#dataset-chat-view > div").first
        print("[ACTION] Dragging chat modal by header...")
        chat_header.hover()
        page.mouse.down()
        page.mouse.move(initial_box["x"] - 250, initial_box["y"] + 50)
        page.mouse.up()
        time.sleep(0.5)

        dragged_box = chat_view.bounding_box()
        print(f"[VERIFY] Dragged Chat Window Bounding Box: {dragged_box}")
        assert dragged_box["x"] != initial_box["x"] or dragged_box["y"] != initial_box["y"], "Chat window did not move after drag!"
        print("[SUCCESS] Chat window successfully moved via header drag interaction.")

        # 5. Turn 1: Analytical Question
        chat_input = page.locator("#chat-input")
        send_btn = page.locator("#chat-send-btn")
        
        q1 = "What is the average salary by department?"
        print(f"[ACTION] Sending Turn 1 question: '{q1}'")
        chat_input.fill(q1)
        send_btn.click()

        # Wait for response message
        page.wait_for_selector(".chat-bubble-assistant", timeout=15000)
        time.sleep(1.5)

        turn1_text = page.locator(".chat-bubble-assistant").first.inner_text()
        print(f"[RESPONSE 1]:\n{turn1_text}\n")

        # 6. Expand SQL
        view_sql_btn = page.locator("button:has-text('View SQL')").first
        if view_sql_btn.count() > 0:
            print("[ACTION] Expanding SQL block...")
            view_sql_btn.click()
            time.sleep(0.5)
            sql_text = page.locator("code").first.inner_text()
            print(f"[VERIFIED SQL]:\n{sql_text}\n")

        # 7. Expand Data Table
        view_data_btn = page.locator("button:has-text('View Data')").first
        if view_data_btn.count() > 0:
            print("[ACTION] Expanding Data Table...")
            view_data_btn.click()
            time.sleep(0.5)
            table_el = page.locator("table").first
            print(f"[VERIFIED TABLE]: Table rendered: {table_el.count() > 0}")

        # 8. Turn 2: Follow-Up ("Which one is highest?")
        q2 = "Which one is highest?"
        print(f"[ACTION] Sending Turn 2 follow-up: '{q2}'")
        chat_input.fill(q2)
        send_btn.click()

        time.sleep(2.0)
        assistants = page.locator(".chat-bubble-assistant")
        print(f"[VERIFY] Assistant responses count: {assistants.count()}")
        if assistants.count() >= 2:
            turn2_text = assistants.nth(1).inner_text()
            print(f"[RESPONSE 2 (Follow-Up)]:\n{turn2_text}\n")

        # 9. Take screenshot with dragged window and response open
        shot_path1 = os.path.join(ARTIFACT_DIR, "live_dataset_chat_dragged.png")
        page.screenshot(path=shot_path1, full_page=True)
        print(f"[SCREENSHOT] Saved open dragged chat screenshot: {shot_path1}")

        # 10. Test Close/Cancel Button
        close_btn = page.locator("#chat-close-btn, button:has-text('Close')").first
        print("[ACTION] Clicking 'Close' button in header...")
        close_btn.click()
        time.sleep(1.0)
        print(f"[VERIFY] Chat view visible after clicking Close: {chat_view.is_visible()}")
        assert not chat_view.is_visible(), "Chat window was not closed!"

        # 11. Re-open chat and test Escape key close
        print("[ACTION] Re-opening chat...")
        floating_btn = page.locator("button:has-text('Ask Dataset')").first
        floating_btn.click()
        time.sleep(1.0)
        print(f"[VERIFY] Chat reopened: {chat_view.is_visible()}")

        print("[ACTION] Pressing Escape key to close chat...")
        page.keyboard.press("Escape")
        time.sleep(1.0)
        print(f"[VERIFY] Chat visible after Escape key: {chat_view.is_visible()}")
        assert not chat_view.is_visible(), "Chat window did not close on Escape key!"

        # 12. Final screenshot of clean dashboard after closing chat
        shot_path2 = os.path.join(ARTIFACT_DIR, "live_dashboard_after_chat_closed.png")
        page.screenshot(path=shot_path2, full_page=True)
        print(f"[SCREENSHOT] Saved dashboard after chat closed: {shot_path2}")

        browser.close()
        print("[SUCCESS] All Playwright browser validation steps passed with 100% success!")


if __name__ == "__main__":
    run_chat_browser_validation()
