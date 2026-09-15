"""Helper script to generate committed test fixtures for CSV and XLSX ingestion testing."""

from pathlib import Path
import pandas as pd
import openpyxl

FIXTURES_DIR = Path(__file__).parent


def generate_all_fixtures():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Baseline dataset (identical logical data for CSV and XLSX)
    baseline_df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "customer_name": ["Alice", "Bob", "Charlie", "David", "Eve"],
            "amount": [150.50, 200.00, 50.25, 300.00, 125.75],
            "order_date": ["2026-01-10", "2026-01-11", "2026-01-12", "2026-01-13", "2026-01-14"],
            "is_active": [True, False, True, True, False],
        }
    )
    baseline_df.to_csv(FIXTURES_DIR / "baseline.csv", index=False)
    baseline_df.to_excel(FIXTURES_DIR / "baseline.xlsx", index=False)

    # 2. Missing values dataset
    missing_df = pd.DataFrame(
        {
            "item_id": [101, 102, 103, 104],
            "quantity": [10, None, 30, None],
            "category": ["Electronics", "Home", None, "Garden"],
            "ship_date": ["2026-02-01", None, "2026-02-03", None],
        }
    )
    missing_df.to_csv(FIXTURES_DIR / "missing_values.csv", index=False)
    missing_df.to_excel(FIXTURES_DIR / "missing_values.xlsx", index=False)

    # 3. Duplicate headers dataset
    dup_csv_content = "id,name,name\n1,Alpha,Beta\n2,Gamma,Delta\n"
    (FIXTURES_DIR / "duplicate_headers.csv").write_text(dup_csv_content, encoding="utf-8")
    wb_dup = openpyxl.Workbook()
    ws_dup = wb_dup.active
    ws_dup.append(["id", "name", "name"])
    ws_dup.append([1, "Alpha", "Beta"])
    ws_dup.append([2, "Gamma", "Delta"])
    wb_dup.save(FIXTURES_DIR / "duplicate_headers.xlsx")

    # 4. Mixed types column dataset
    mixed_df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "code": ["1001", "INVALID", "1002", "UNKNOWN"],
        }
    )
    mixed_df.to_csv(FIXTURES_DIR / "mixed_types.csv", index=False)
    mixed_df.to_excel(FIXTURES_DIR / "mixed_types.xlsx", index=False)

    # 5. Unusual date representations
    dates_df = pd.DataFrame(
        {
            "event_id": [1, 2, 3],
            "iso_date": ["2026-09-15T10:00:00Z", "2026-09-16T11:30:00Z", "2026-09-17T12:45:00Z"],
            "us_date": ["09/15/2026", "09/16/2026", "09/17/2026"],
        }
    )
    dates_df.to_csv(FIXTURES_DIR / "dates.csv", index=False)
    dates_df.to_excel(FIXTURES_DIR / "dates.xlsx", index=False)

    # 6. Tiny dataset
    tiny_df = pd.DataFrame({"x": [42]})
    tiny_df.to_csv(FIXTURES_DIR / "tiny.csv", index=False)
    tiny_df.to_excel(FIXTURES_DIR / "tiny.xlsx", index=False)

    # 7. Multi-sheet Excel dataset (violates V1 single-sheet rule)
    wb_multi = openpyxl.Workbook()
    ws1 = wb_multi.active
    ws1.title = "Sheet1"
    ws1.append(["col1", "col2"])
    ws1.append([1, 2])
    ws2 = wb_multi.create_sheet(title="Sheet2")
    ws2.append(["colA", "colB"])
    ws2.append(["x", "y"])
    wb_multi.save(FIXTURES_DIR / "multi_sheet.xlsx")

    # 8. Corrupt / unreadable files
    (FIXTURES_DIR / "corrupt.csv").write_bytes(b"\x00\xff\xfe\xfa\xfb\xfe\xff binary junk \x80\x81\x82")
    (FIXTURES_DIR / "corrupt.xlsx").write_text("This is plain text, not a valid zip/xlsx workbook.")


if __name__ == "__main__":
    generate_all_fixtures()
    print("Test fixtures generated successfully in:", FIXTURES_DIR)
