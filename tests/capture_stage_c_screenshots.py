import os
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\GANDL\.gemini\antigravity-ide\brain\b2b40f26-a42a-43f8-8175-6d95b7722886"

def capture_clarification_and_second_dataset():
    with sync_playwright() as p:
        print("[0/2] Launching msedge...")
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        print("[1/2] Navigating to http://localhost:3000...")
        page.goto("http://localhost:3000", wait_until="domcontentloaded")
        page.wait_for_selector("select", timeout=20000)
        time.sleep(2)

        dataset_select = page.locator("select").first
        options = dataset_select.locator("option").all_inner_texts()
        print("Available datasets in UI:", options)
        
        # Select Inventory_Catalog.csv
        for opt in options:
            if "Inventory_Catalog" in opt:
                dataset_select.select_option(label=opt)
                break
        time.sleep(1)

        prompt_input = page.locator("input[aria-label='Analytical Question Brief'], textarea, input[type='text']").first
        prompt_input.fill("Average cost price by department")
        
        submit_btn = page.locator("button:has-text('Generate Insights'), button[type='submit']").first
        submit_btn.click()
        
        print("Waiting for Clarification Needed card (up to 180s)...")
        page.wait_for_selector("text=Clarification Needed", timeout=180000)
        time.sleep(2)
        
        # 4. State 4: Clarification state
        path_s4 = os.path.join(ARTIFACT_DIR, "state4_clarification.png")
        page.screenshot(path=path_s4, full_page=True)
        print(f"Captured State 4 (Clarification): {path_s4}")

        # 5. State 5: Second dataset resolved dashboard
        print("Resolving Clarification with Option 1...")
        resolve_btn = page.locator("button:has-text('Select Option 1'), button:has-text('Select Option')").first
        resolve_btn.click()
        
        print("Waiting for resolved dashboard on Inventory_Catalog.csv (up to 180s)...")
        page.wait_for_selector("text=Robustness Across Variant Interpretations", timeout=180000)
        time.sleep(3)
        
        path_s5 = os.path.join(ARTIFACT_DIR, "state5_second_dataset.png")
        page.screenshot(path=path_s5, full_page=True)
        print(f"Captured State 5 (Second Dataset Result): {path_s5}")

        browser.close()
        print("STATES 4 & 5 SUCCESSFULLY CAPTURED AND VERIFIED!")

if __name__ == "__main__":
    capture_clarification_and_second_dataset()
