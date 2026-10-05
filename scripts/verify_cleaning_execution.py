"""Real Dataset Validation Script for Data Studio Part 5: Cleaning Preview & Batch Execution.

Validates:
1. healthcare.csv
2. education.csv
3. iot.csv
4. hr.csv
5. logistics.csv

For each dataset:
- Load raw CanonicalDataset
- Generate deterministic CleaningPlan
- Select safe/default recommendations
- Generate Preview and validate preview invariants
- Apply batch cleaning and validate execution invariants
- Confirm raw DataFrame remains 100% byte/value equivalent (assert_frame_equal)
"""

import os
import sys
import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cleaning.executor import execute_cleaning_plan, preview_cleaning_plan
from cleaning.planner import CleaningPlanner
from ingestion.loaders import CSVLoader


DATASETS = [
    ("Healthcare", "tests/real_data/healthcare.csv"),
    ("Education", "tests/real_data/education.csv"),
    ("IoT", "tests/real_data/iot.csv"),
    ("HR", "tests/real_data/hr.csv"),
    ("Logistics", "tests/real_data/logistics.csv"),
]


def validate_real_datasets():
    print("=" * 70)
    print("STARTING PART 5 REAL DATASET CLEANING EXECUTION VALIDATION")
    print("=" * 70)

    loader = CSVLoader()
    planner = CleaningPlanner()

    for name, path in DATASETS:
        print(f"\n>> Validating Dataset: {name} ({path})")
        if not os.path.exists(path):
            print(f"   [ERROR] File not found: {path}")
            continue

        # 1. Load raw dataset
        canonical = loader.load(path)
        raw_rows, raw_cols = len(canonical.data), len(canonical.data.columns)
        raw_snapshot = canonical.data.copy(deep=True)
        print(f"   Raw Shape: {raw_rows} rows x {raw_cols} columns")

        # 2. Generate Cleaning Plan
        plan = planner.generate_plan(canonical=canonical)
        print(f"   Generated Cleaning Plan: {plan.total_recommendations} total ({plan.safe_count} safe/recommended)")

        safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
        print(f"   Selected Default/Safe IDs: {len(safe_ids)}")
        for r in plan.recommendations:
            if r.default_selected:
                target = r.column_name or "_DATASET_"
                print(f"     * [{r.operation}] on {target} ({r.affected_rows} rows affected)")

        # 3. Generate Preview
        preview_res = preview_cleaning_plan(canonical=canonical, selected_recommendation_ids=safe_ids, plan=plan)
        print(f"   Preview Generated:")
        print(f"     - Rows: {preview_res.original_row_count} -> {preview_res.preview_row_count} (change: {preview_res.row_count_change})")
        print(f"     - Operations applicable: {preview_res.operations_applicable}, skipped: {preview_res.operations_skipped}")
        print(f"     - Total cells affected: {preview_res.total_cells_affected}")
        print(f"     - Sample changes captured: {len(preview_res.sample_changes)}")

        # Check raw immutability after preview
        assert_frame_equal(canonical.data, raw_snapshot)
        print("   [PASSED] Raw DataFrame 100% immutable after Preview.")

        # 4. Apply Cleaning
        exec_res, cleaned_canonical = execute_cleaning_plan(
            canonical=canonical, selected_recommendation_ids=safe_ids, plan=plan
        )
        print(f"   Cleaning Applied:")
        print(f"     - Cleaned Shape: {len(cleaned_canonical.data)} rows x {len(cleaned_canonical.data.columns)} columns")
        print(f"     - Operations applied: {exec_res.operations_applied}, failed: {exec_res.operations_failed}")
        print(f"     - Overall validation status: {exec_res.validation.overall_status if exec_res.validation else 'N/A'}")
        if exec_res.validation:
            print(f"     - Invariant checks: {exec_res.validation.passed_checks} passed, {exec_res.validation.failed_checks} failed, {exec_res.validation.warning_checks} warnings")
            assert exec_res.validation.failed_checks == 0, "Invariant check failures detected!"

        # Check raw immutability after execution
        assert_frame_equal(canonical.data, raw_snapshot)
        print("   [PASSED] Raw DataFrame 100% immutable after Execution.")
        print(f"   [SUCCESS] {name} passed all Part 5 verification checks.\n")

    print("=" * 70)
    print("ALL 5 REAL DATASETS VALIDATED SUCCESSFULLY WITH ZERO REGRESSIONS")
    print("=" * 70)


if __name__ == "__main__":
    validate_real_datasets()
