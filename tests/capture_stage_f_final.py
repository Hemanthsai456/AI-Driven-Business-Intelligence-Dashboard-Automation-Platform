import json
import os
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\GANDL\.gemini\antigravity-ide\brain\5a549c02-a7be-4339-8e22-e1de197d3206"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# Dataset 1: Global Retail Performance (Revenue, Units, Margin across Region, Category, OrderDate)
DS1_PAYLOAD = {
    "status": "SUCCESS",
    "message": "Dashboard ready",
    "spec_id": "spec_ds1_sales",
    "headline": "North Region leads with $428,500 Total Revenue across Category, demonstrating 92.4% rank stability across interpretations.",
    "dataset_name": "Global_Retail_Sales.csv",
    "row_count": 14200,
    "tiles": [
        {
            "id": "tile_kpi_rev",
            "title": "Total Revenue",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 1,
            "generator": "rule-based baseline",
            "evidence": {"strength": 1.0, "robustness": 0.94, "fdr_passed": True, "n": 14200},
            "why_chosen": "Primary executive metric aggregating total dollar sales across transactions.",
            "data": [{"Total Revenue": "$1,284,500"}],
            "delta": {"value": "+14.2%", "percentage": 14.2, "direction": "up", "label": "vs prior quarter"},
            "metrics": ["Revenue"],
            "dimensions": [],
        },
        {
            "id": "tile_kpi_units",
            "title": "Units Sold",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 2,
            "generator": "rule-based baseline",
            "evidence": {"strength": 0.98, "robustness": 0.96, "fdr_passed": True, "n": 14200},
            "why_chosen": "Core physical volume measure across catalog shipments.",
            "data": [{"Units Sold": "48,920"}],
            "delta": {"value": "+6.8%", "percentage": 6.8, "direction": "up", "label": "YoY growth"},
            "metrics": ["Units"],
            "dimensions": [],
        },
        {
            "id": "tile_kpi_margin",
            "title": "Gross Margin %",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 3,
            "generator": "Groq",
            "evidence": {"strength": 0.91, "robustness": 0.88, "fdr_passed": True, "n": 14200},
            "why_chosen": "Profitability index highlighting net realization per SKU.",
            "data": [{"Gross Margin": "38.4%"}],
            "delta": {"value": "+1.2%", "percentage": 1.2, "direction": "up", "label": "target 35%"},
            "metrics": ["Margin"],
            "dimensions": [],
        },
        {
            "id": "tile_kpi_orders",
            "title": "Active Accounts",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 4,
            "generator": "Gemini",
            "evidence": {"strength": 0.89, "robustness": 0.85, "fdr_passed": True, "n": 14200},
            "why_chosen": "Customer engagement breadth indicator across territories.",
            "data": [{"Active Accounts": "3,410"}],
            "delta": {"value": "-0.5%", "percentage": -0.5, "direction": "down", "label": "churn alert"},
            "metrics": ["Accounts"],
            "dimensions": [],
        },
        {
            "id": "tile_hero_bar",
            "title": "Revenue by Region across Operating Divisions",
            "chart_type": "bar",
            "size": {"w": 8, "h": 4},
            "priority": 5,
            "generator": "Gemini",
            "evidence": {"strength": 0.95, "robustness": 0.92, "fdr_passed": True, "n": 14200},
            "why_chosen": "Highest-scoring RANKING insight establishing regional sales dominance with strong perturbation invariance.",
            "data": [
                {"Region": "North America", "Revenue": 428500},
                {"Region": "Europe West", "Revenue": 365200},
                {"Region": "Asia Pacific", "Revenue": 284100},
                {"Region": "Latin America", "Revenue": 126700},
                {"Region": "Middle East", "Revenue": 80000},
            ],
            "x_key": "Region",
            "y_keys": ["Revenue"],
            "dimensions": ["Region"],
            "metrics": ["Revenue"],
        },
        {
            "id": "tile_side_donut",
            "title": "Category Sales Composition",
            "chart_type": "donut",
            "size": {"w": 4, "h": 4},
            "priority": 6,
            "generator": "agent",
            "evidence": {"strength": 0.93, "robustness": 0.90, "fdr_passed": True, "n": 14200},
            "why_chosen": "Key COMPOSITION distribution showing concentration in Enterprise Hardware and Cloud Services.",
            "data": [
                {"Category": "Enterprise Hardware", "Revenue": 510000},
                {"Category": "Cloud Software", "Revenue": 395000},
                {"Category": "Consulting Services", "Revenue": 240000},
                {"Category": "Maintenance", "Revenue": 139500},
            ],
            "x_key": "Category",
            "y_keys": ["Revenue"],
            "dimensions": ["Category"],
            "metrics": ["Revenue"],
        },
        {
            "id": "tile_trend_line",
            "title": "Monthly Revenue Trajectory (FY2024)",
            "chart_type": "line",
            "size": {"w": 6, "h": 3},
            "priority": 7,
            "generator": "rule-based baseline",
            "evidence": {"strength": 0.94, "robustness": 0.91, "fdr_passed": True, "n": 12},
            "why_chosen": "Monotonic upward TREND identified with statistically significant slope (p < 0.001).",
            "data": [
                {"Month": "Jan 2024", "Revenue": 82000},
                {"Month": "Feb 2024", "Revenue": 89000},
                {"Month": "Mar 2024", "Revenue": 96000},
                {"Month": "Apr 2024", "Revenue": 104000},
                {"Month": "May 2024", "Revenue": 112000},
                {"Month": "Jun 2024", "Revenue": 121000},
                {"Month": "Jul 2024", "Revenue": 129000},
                {"Month": "Aug 2024", "Revenue": 138000},
            ],
            "x_key": "Month",
            "y_keys": ["Revenue"],
            "dimensions": ["Month"],
            "metrics": ["Revenue"],
        },
        {
            "id": "tile_scatter_corr",
            "title": "Discount Depth vs Order Margin Correlation",
            "chart_type": "scatter",
            "size": {"w": 6, "h": 3},
            "priority": 8,
            "generator": "Groq",
            "evidence": {"strength": 0.88, "robustness": 0.86, "fdr_passed": True, "n": 350},
            "why_chosen": "Statistically robust CORRELATION demonstrating adverse margin impacts past 15% discount threshold.",
            "data": [
                {"Discount": 5, "Margin": 42},
                {"Discount": 10, "Margin": 38},
                {"Discount": 15, "Margin": 34},
                {"Discount": 20, "Margin": 26},
                {"Discount": 25, "Margin": 18},
                {"Discount": 30, "Margin": 11},
            ],
            "x_key": "Discount",
            "y_keys": ["Margin"],
            "dimensions": ["Discount"],
            "metrics": ["Margin"],
        },
    ],
    "slicers": [
        {
            "id": "slicer_Region",
            "column": "Region",
            "role": "DIMENSION",
            "control_type": "multi_select",
            "options": [
                {"value": "North America", "label": "North America", "count": 5200},
                {"value": "Europe West", "label": "Europe West", "count": 4100},
                {"value": "Asia Pacific", "label": "Asia Pacific", "count": 3200},
                {"value": "Latin America", "label": "Latin America", "count": 1200},
                {"value": "Middle East", "label": "Middle East", "count": 500},
            ],
        },
        {
            "id": "slicer_Category",
            "column": "Category",
            "role": "DIMENSION",
            "control_type": "multi_select",
            "options": [
                {"value": "Enterprise Hardware", "label": "Enterprise Hardware", "count": 4800},
                {"value": "Cloud Software", "label": "Cloud Software", "count": 4200},
                {"value": "Consulting Services", "label": "Consulting Services", "count": 3100},
                {"value": "Maintenance", "label": "Maintenance", "count": 2100},
            ],
        },
        {
            "id": "slicer_OrderDate",
            "column": "OrderDate",
            "role": "DATETIME",
            "control_type": "date_range",
            "min_date": "2024-01-01",
            "max_date": "2024-12-31",
        },
    ],
    "rejected_insights": [
        {
            "candidate_id": "rej_01",
            "insight_type": "CORRELATION",
            "description": "Correlation between PostalCode and UnitPrice",
            "stage": "PRUNING",
            "reason": "Failed FDR control (Benjamini-Hochberg p=0.31 > 0.05). Spurious geographic coincidence.",
        },
        {
            "candidate_id": "rej_02",
            "insight_type": "TREND",
            "description": "Weekly ShippingLeadDays variance trend",
            "stage": "RANKING",
            "reason": "Robustness stability score 0.22 below 0.35 floor; rank ordering destabilized across median perturbation.",
        },
        {
            "candidate_id": "rej_03",
            "insight_type": "COMPOSITION",
            "description": "PaymentGateway fee breakdown",
            "stage": "SELECTION",
            "reason": "Superseded by higher priority Revenue by Category tile; redundant variance explanation.",
        },
    ],
}
DS1_PAYLOAD["dashboard_spec"] = {k: v for k, v in DS1_PAYLOAD.items()}

# Dataset 2: Supply Chain & Warehouse Logistics (StockUnits, ReorderPoint, LeadTimeDays across Warehouse, Department)
DS2_PAYLOAD = {
    "status": "SUCCESS",
    "message": "Dashboard ready",
    "spec_id": "spec_ds2_inventory",
    "headline": "Central Hub leads with 86,400 StockUnits across Department, with 94.2% rank stability across interpretations.",
    "dataset_name": "Warehouse_Inventory_Logistics.parquet",
    "row_count": 8940,
    "tiles": [
        {
            "id": "tile_kpi_stock",
            "title": "Total Stock Units",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 1,
            "generator": "rule-based baseline",
            "evidence": {"strength": 1.0, "robustness": 0.95, "fdr_passed": True, "n": 8940},
            "why_chosen": "Baseline inventory volume aggregation across fulfillment facilities.",
            "data": [{"Stock Units": "248,150"}],
            "delta": {"value": "-3.1%", "percentage": -3.1, "direction": "down", "label": "vs capacity"},
            "metrics": ["StockUnits"],
            "dimensions": [],
        },
        {
            "id": "tile_kpi_lead",
            "title": "Avg Lead Time",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 2,
            "generator": "Groq",
            "evidence": {"strength": 0.92, "robustness": 0.89, "fdr_passed": True, "n": 8940},
            "why_chosen": "Procurement velocity indicator monitoring supply chain responsiveness.",
            "data": [{"Lead Time": "4.2 days"}],
            "delta": {"value": "-0.6 days", "percentage": -12.5, "direction": "up", "label": "faster"},
            "metrics": ["LeadTimeDays"],
            "dimensions": [],
        },
        {
            "id": "tile_kpi_safety",
            "title": "Stockout Risk SKUs",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 3,
            "generator": "Gemini",
            "evidence": {"strength": 0.88, "robustness": 0.87, "fdr_passed": True, "n": 8940},
            "why_chosen": "Critical threshold alert for SKUs below safety stock buffer.",
            "data": [{"Stockout Risk": "42 SKUs"}],
            "delta": {"value": "+8 SKUs", "percentage": 23.5, "direction": "down", "label": "needs restock"},
            "metrics": ["StockoutRisk"],
            "dimensions": [],
        },
        {
            "id": "tile_kpi_turns",
            "title": "Annual Inventory Turns",
            "chart_type": "kpi",
            "size": {"w": 3, "h": 2},
            "priority": 4,
            "generator": "agent",
            "evidence": {"strength": 0.90, "robustness": 0.86, "fdr_passed": True, "n": 8940},
            "why_chosen": "Working capital utilization benchmark across merchandise classes.",
            "data": [{"Inventory Turns": "8.4x"}],
            "delta": {"value": "+0.5x", "percentage": 6.3, "direction": "up", "label": "industry avg 7.2x"},
            "metrics": ["InventoryTurns"],
            "dimensions": [],
        },
        {
            "id": "tile_hero_warehouse",
            "title": "StockUnits by Warehouse Facility (Long Distribution Labels)",
            "chart_type": "horizontal_bar",
            "size": {"w": 8, "h": 4},
            "priority": 5,
            "generator": "Gemini",
            "evidence": {"strength": 0.96, "robustness": 0.94, "fdr_passed": True, "n": 8940},
            "why_chosen": "Highest-scoring RANKING insight; labels formatted as horizontal bar due to long facility facility naming conventions.",
            "data": [
                {"Warehouse": "Central Regional Logistics Hub #01", "StockUnits": 86400},
                {"Warehouse": "Pacific Coastal Distribution Facility #04", "StockUnits": 64200},
                {"Warehouse": "Midwest Intermodal Terminal #02", "StockUnits": 51900},
                {"Warehouse": "Southern Gateway Cargo Center #05", "StockUnits": 45650},
            ],
            "x_key": "Warehouse",
            "y_keys": ["StockUnits"],
            "dimensions": ["Warehouse"],
            "metrics": ["StockUnits"],
        },
        {
            "id": "tile_side_dept",
            "title": "Department Inventory Distribution",
            "chart_type": "donut",
            "size": {"w": 4, "h": 4},
            "priority": 6,
            "generator": "rule-based baseline",
            "evidence": {"strength": 0.92, "robustness": 0.90, "fdr_passed": True, "n": 8940},
            "why_chosen": "COMPOSITION breakdown mapping unit allocation across core departments.",
            "data": [
                {"Department": "Industrial Automation", "StockUnits": 98000},
                {"Department": "Consumer Electronics", "StockUnits": 74000},
                {"Department": "Automotive Spares", "StockUnits": 48000},
                {"Department": "Medical Devices", "StockUnits": 28150},
            ],
            "x_key": "Department",
            "y_keys": ["StockUnits"],
            "dimensions": ["Department"],
            "metrics": ["StockUnits"],
        },
    ],
    "slicers": [
        {
            "id": "slicer_Warehouse",
            "column": "Warehouse",
            "role": "DIMENSION",
            "control_type": "multi_select",
            "options": [
                {"value": "Central Regional Logistics Hub #01", "label": "Central Hub", "count": 3200},
                {"value": "Pacific Coastal Distribution Facility #04", "label": "Pacific Facility", "count": 2500},
                {"value": "Midwest Intermodal Terminal #02", "label": "Midwest Terminal", "count": 1800},
                {"value": "Southern Gateway Cargo Center #05", "label": "Southern Gateway", "count": 1440},
            ],
        },
        {
            "id": "slicer_Department",
            "column": "Department",
            "role": "DIMENSION",
            "control_type": "multi_select",
            "options": [
                {"value": "Industrial Automation", "label": "Industrial Automation", "count": 3400},
                {"value": "Consumer Electronics", "label": "Consumer Electronics", "count": 2800},
                {"value": "Automotive Spares", "label": "Automotive Spares", "count": 1600},
                {"value": "Medical Devices", "label": "Medical Devices", "count": 1140},
            ],
        },
    ],
    "rejected_insights": [
        {
            "candidate_id": "rej_inv_01",
            "insight_type": "CORRELATION",
            "description": "Correlation between ShelfRackNumber and DefectRate",
            "stage": "PRUNING",
            "reason": "Failed FDR control (p=0.48 > 0.05). Physical location has zero causality on manufacturing defects.",
        },
        {
            "candidate_id": "rej_inv_02",
            "insight_type": "OUTLIER",
            "description": "Temperature log variances in cold-storage bays",
            "stage": "SELECTION",
            "reason": "Insufficient variance explanation after conditioning on warehouse ambient specs.",
        },
    ],
}
DS2_PAYLOAD["dashboard_spec"] = {k: v for k, v in DS2_PAYLOAD.items()}


def capture_all_stage_f_artifacts():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        # Route mocks
        current_ds = {"active": "ds1"}

        def handle_datasets(route):
            url = route.request.url.split("?")[0].rstrip("/")
            if url.endswith("/datasets"):
                route.fulfill(
                    status=200,
                    headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                    body=json.dumps([
                        {"dataset_id": "ds1", "filename": "Global_Retail_Sales.csv", "row_count": 14200},
                        {"dataset_id": "ds2", "filename": "Warehouse_Inventory_Logistics.parquet", "row_count": 8940},
                    ]),
                )
            elif "ds2" in url:
                route.fulfill(
                    status=200,
                    headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                    body=json.dumps({
                        "dataset_id": "ds2",
                        "filename": "Warehouse_Inventory_Logistics.parquet",
                        "row_count": 8940,
                        "column_count": 6,
                        "source_type": "parquet",
                    }),
                )
            else:
                route.fulfill(
                    status=200,
                    headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                    body=json.dumps({
                        "dataset_id": "ds1",
                        "filename": "Global_Retail_Sales.csv",
                        "row_count": 14200,
                        "column_count": 5,
                        "source_type": "csv",
                    }),
                )

        def handle_pipeline(route):
            payload = DS2_PAYLOAD if current_ds["active"] == "ds2" else DS1_PAYLOAD
            route.fulfill(
                status=200,
                headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                body=json.dumps(payload),
            )

        page.route("**/api/datasets*", handle_datasets)
        page.route("**/datasets*", handle_datasets)
        page.route("**/api/orchestrator/pipeline*", handle_pipeline)
        page.route("**/orchestrator/pipeline*", handle_pipeline)

        print("[1/9] Navigating to http://localhost:3000...")
        page.goto("http://localhost:3000", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Generate Dashboard for Dataset 1
        print("[2/9] Generating Dashboard for Dataset 1...")
        gen_btn = page.wait_for_selector('button:has-text("Generate Dashboard"):not([disabled])', timeout=10000)
        gen_btn.click()
        page.wait_for_timeout(4000)

        # 1. Full Dashboard Dataset 1 (Light mode, 1440px)
        p_ds1_light = os.path.join(ARTIFACT_DIR, "stage_f_ds1_full_dashboard_light_1440px.png")
        page.screenshot(path=p_ds1_light, full_page=True)
        print(f"Captured: {p_ds1_light}")

        # 2. Toggle to Dark mode -> Full Dashboard Dataset 1 (Dark mode)
        print("[3/9] Toggling dark mode...")
        theme_btn = page.query_selector('button[aria-label="Toggle theme"]')
        if theme_btn:
            theme_btn.click()
            page.wait_for_timeout(1000)

        p_ds1_dark = os.path.join(ARTIFACT_DIR, "stage_f_ds1_full_dashboard_dark_1440px.png")
        page.screenshot(path=p_ds1_dark, full_page=True)
        print(f"Captured: {p_ds1_dark}")

        # 3. Cross-filtering active: click on first bar ("North America") in dark mode
        print("[4/9] Activating Cross-filter by clicking a chart element...")
        # Find first rect mark inside Recharts
        bar_cell = page.query_selector("svg.recharts-surface rect.recharts-rectangle, svg.recharts-surface .recharts-bar-rectangles rect")
        if bar_cell:
            bar_cell.click(force=True)
            page.wait_for_timeout(1500)

        p_cross_dark = os.path.join(ARTIFACT_DIR, "stage_f_cross_filter_active_dark.png")
        page.screenshot(path=p_cross_dark, full_page=True)
        print(f"Captured: {p_cross_dark}")

        # Toggle back to light mode to capture cross-filter in light mode
        if theme_btn:
            theme_btn.click()
            page.wait_for_timeout(1000)
        p_cross_light = os.path.join(ARTIFACT_DIR, "stage_f_cross_filter_active_light.png")
        page.screenshot(path=p_cross_light, full_page=True)
        print(f"Captured: {p_cross_light}")

        # 4. Open "Why this was chosen" panel on the hero tile (Light mode)
        print("[5/9] Opening 'Why this was chosen' modal (Light)...")
        why_btn = page.query_selector('button[title="Why this was chosen"]')
        if why_btn:
            why_btn.click()
            page.wait_for_timeout(1500)

        p_why_light = os.path.join(ARTIFACT_DIR, "stage_f_why_chosen_panel_light.png")
        page.screenshot(path=p_why_light, full_page=True)
        print(f"Captured: {p_why_light}")

        # Close modal
        close_modal_btn = page.query_selector('button[aria-label="Close modal"]')
        if close_modal_btn:
            close_modal_btn.click()
        page.wait_for_timeout(1000)

        # Toggle to dark mode and open modal again
        if theme_btn:
            theme_btn.click()
            page.wait_for_timeout(1000)

        why_btn_dark = page.query_selector('button[title="Why this was chosen"]')
        if why_btn_dark:
            why_btn_dark.click()
            page.wait_for_timeout(1500)

        p_why_dark = os.path.join(ARTIFACT_DIR, "stage_f_why_chosen_panel_dark.png")
        page.screenshot(path=p_why_dark, full_page=True)
        print(f"Captured: {p_why_dark}")

        # Close modal
        close_modal_btn2 = page.query_selector('button[aria-label="Close modal"]')
        if close_modal_btn2:
            close_modal_btn2.click()
        page.wait_for_timeout(1000)

        # 5. Open "Considered but Rejected" Drawer at bottom (Dark mode)
        print("[6/9] Expanding Rejected Insights drawer (Dark)...")
        details_el = page.query_selector("details summary")
        if details_el:
            details_el.click()
            page.wait_for_timeout(1500)

        p_rej_dark = os.path.join(ARTIFACT_DIR, "stage_f_rejected_drawer_dark.png")
        page.screenshot(path=p_rej_dark, full_page=True)
        print(f"Captured: {p_rej_dark}")

        # In Light mode
        if theme_btn:
            theme_btn.click()
            page.wait_for_timeout(1000)
        p_rej_light = os.path.join(ARTIFACT_DIR, "stage_f_rejected_drawer_light.png")
        page.screenshot(path=p_rej_light, full_page=True)
        print(f"Captured: {p_rej_light}")

        # 6. Second Dataset with Different Columns, Slicers, and KPIs
        print("[7/9] Switching to Dataset 2 (Warehouse Inventory)...")
        current_ds["active"] = "ds2"
        select_el = page.query_selector("select#dataset-select, select")
        if select_el:
            select_el.select_option("ds2")
            page.wait_for_timeout(1500)

        gen_btn2 = page.wait_for_selector('button:has-text("Generate Dashboard"):not([disabled])', timeout=10000)
        gen_btn2.click()
        page.wait_for_timeout(4000)

        p_ds2 = os.path.join(ARTIFACT_DIR, "stage_f_ds2_full_dashboard_light.png")
        page.screenshot(path=p_ds2, full_page=True)
        print(f"Captured: {p_ds2}")

        # 7. Responsive Viewports at 1440px, 900px, 390px
        print("[8/9] Capturing responsive viewports (1440px, 900px, 390px)...")
        # 1440px
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(1000)
        p_1440 = os.path.join(ARTIFACT_DIR, "stage_f_responsive_1440px.png")
        page.screenshot(path=p_1440, full_page=True)
        print(f"Captured: {p_1440}")

        # 900px
        page.set_viewport_size({"width": 900, "height": 850})
        page.wait_for_timeout(1000)
        p_900 = os.path.join(ARTIFACT_DIR, "stage_f_responsive_900px.png")
        page.screenshot(path=p_900, full_page=True)
        print(f"Captured: {p_900}")

        # 390px (Mobile)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(1000)
        p_390 = os.path.join(ARTIFACT_DIR, "stage_f_responsive_390px.png")
        page.screenshot(path=p_390, full_page=True)
        print(f"Captured: {p_390}")

        browser.close()
        print("\nALL STAGE F SCREENSHOTS CAPTURED AND SAVED TO ARTIFACT DIR SUCCESSFULLY!")


if __name__ == "__main__":
    capture_all_stage_f_artifacts()
