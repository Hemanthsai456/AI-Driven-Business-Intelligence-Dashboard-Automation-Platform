import sys
from pathlib import Path

# Add workspace root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import pandas as pd
from ingestion.loaders.csv_loader import CSVLoader
from intelligence.profiler import profile_dataset
from cleaning import clean_dataset

def main():
    loader = CSVLoader()
    fixture_path = Path(__file__).parent / "fixtures" / "messy_dataset.csv"
    
    # 1. Load Raw Messy Dataset
    raw_canonical = loader.load(str(fixture_path))
    raw_copy = raw_canonical.data.copy(deep=True)
    before_profile = profile_dataset(raw_canonical, attach=False)
    
    print("=" * 80)
    print("STAGE 2 GATE: BEFORE PROFILE (Raw Messy Dataset)")
    print("=" * 80)
    print(f"File: {fixture_path.name}")
    print(f"Rows: {before_profile.dataset_summary['row_count']}")
    print(f"Columns: {before_profile.dataset_summary['column_count']}")
    print(f"Duplicate Rows: {before_profile.dataset_summary['duplicate_row_count']} ({before_profile.dataset_summary['duplicate_row_percentage']}%)")
    print(f"Total Missing Cells: {before_profile.dataset_summary['overall_missing_count']} ({before_profile.dataset_summary['overall_missing_percentage']}%)")
    print("-" * 80)
    print(f"{'Column':<16} | {'Raw Dtype':<12} | {'Nulls':<6} | {'Null %':<8} | {'Distinct':<8} | Sample Values")
    print("-" * 80)
    for col, stats in before_profile.column_statistics.items():
        sample = [str(x) for x in raw_canonical.data[col].dropna().head(3).tolist()]
        sample_str = ", ".join(sample)
        print(f"{col:<16} | {stats['detected_datatype']:<12} | {stats['null_count']:<6} | {stats['null_percentage']:<8.1f} | {stats['distinct_count']:<8} | {sample_str}")
    print()

    # 2. Run Cleaning Layer (Stage 2)
    cleaned_canonical, change_report = clean_dataset(raw_canonical)
    after_profile = profile_dataset(cleaned_canonical, attach=False)

    print("=" * 80)
    print("STAGE 2 GATE: CLEANING CHANGE REPORT")
    print("=" * 80)
    print(f"Dataset ID:       {change_report.dataset_id}")
    print(f"Initial Rows:     {change_report.initial_rows} -> Final Rows: {change_report.final_rows}")
    print(f"Initial Columns:  {change_report.initial_columns} -> Final Columns: {change_report.final_columns}")
    print(f"Total Changes:    {change_report.total_changes}")
    print(f"Changes by Rule:  {json.dumps(change_report.changes_by_rule, indent=2)}")
    print("-" * 80)
    print("DETAILED TRANSFORMATION LOG:")
    print(f"{'Rule':<24} | {'Column':<16} | {'Count':<6} | Details")
    print("-" * 80)
    for ch in change_report.changes:
        col_str = ch.column or "(dataset)"
        print(f"{ch.rule:<24} | {col_str:<16} | {ch.count:<6} | {ch.details}")
    print()

    # 3. Immutability Verification
    pd.testing.assert_frame_equal(raw_canonical.data, raw_copy)
    print("[VERIFIED] Input raw dataset remained completely untouched (immutable original invariant preserved).")
    print()

    # 4. Profile Cleaned Dataset
    print("=" * 80)
    print("STAGE 2 GATE: AFTER PROFILE (Cleaned Dataset)")
    print("=" * 80)
    print(f"Rows: {after_profile.dataset_summary['row_count']}")
    print(f"Columns: {after_profile.dataset_summary['column_count']}")
    print(f"Duplicate Rows: {after_profile.dataset_summary['duplicate_row_count']} ({after_profile.dataset_summary['duplicate_row_percentage']}%)")
    print(f"Total Missing Cells: {after_profile.dataset_summary['overall_missing_count']} ({after_profile.dataset_summary['overall_missing_percentage']}%)")
    print("-" * 80)
    print(f"{'Column':<16} | {'Clean Dtype':<14} | {'Nulls':<6} | {'Null %':<8} | {'Distinct':<8} | Sample Values")
    print("-" * 80)
    for col, stats in after_profile.column_statistics.items():
        sample = [str(x) for x in cleaned_canonical.data[col].dropna().head(3).tolist()]
        sample_str = ", ".join(sample)
        print(f"{col:<16} | {stats['detected_datatype']:<14} | {stats['null_count']:<6} | {stats['null_percentage']:<8.1f} | {stats['distinct_count']:<8} | {sample_str}")
    print()

    # 5. Idempotence Verification (Re-running on cleaned output)
    print("=" * 80)
    print("STAGE 2 GATE: IDEMPOTENCE VERIFICATION (Re-running clean on cleaned output)")
    print("=" * 80)
    recleaned_canonical, re_report = clean_dataset(cleaned_canonical)
    print(f"Second Pass Total Changes: {re_report.total_changes}")
    print(f"Second Pass Changes Log:   {re_report.changes}")
    pd.testing.assert_frame_equal(cleaned_canonical.data, recleaned_canonical.data)
    assert re_report.total_changes == 0, f"Expected 0 changes, got {re_report.total_changes}"
    print("[VERIFIED] Idempotence satisfied: 0 changes occurred and DataFrame is bitwise identical.")
    print("=" * 80)

if __name__ == "__main__":
    main()
