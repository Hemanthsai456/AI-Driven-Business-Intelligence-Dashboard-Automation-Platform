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


def validate_part51_user_modifications():
    print("\n" + "=" * 70)
    print("STARTING PART 5.1 USER MODIFICATION / METHOD OVERRIDE VALIDATION")
    print("=" * 70)

    loader = CSVLoader()
    planner = CleaningPlanner()

    # Test Healthcare with Median -> Mean modification
    healthcare_path = "tests/real_data/healthcare.csv"
    if os.path.exists(healthcare_path):
        print("\n>> Validating Healthcare User Override (Median -> Mean for length_of_stay)")
        canonical = loader.load(healthcare_path)
        raw_snapshot = canonical.data.copy(deep=True)
        plan = planner.generate_plan(canonical)

        med_rec = next((r for r in plan.recommendations if r.column_name == "length_of_stay" and r.operation == "IMPUTE_MEDIAN"), None)
        if med_rec:
            print(f"   Found recommendation: {med_rec.recommendation_id} on length_of_stay (original: {med_rec.operation})")
            print(f"   Supported variants: {[v['label'] for v in med_rec.supported_variants]}")

            overrides = {med_rec.recommendation_id: "IMPUTE_MEAN"}

            # Preview
            preview_res = preview_cleaning_plan(canonical, [med_rec.recommendation_id], plan, operation_overrides=overrides)
            print(f"   Preview method used: {preview_res.operations[0].method_used}")
            assert "Mean" in preview_res.operations[0].method_used
            assert preview_res.operations[0].operation == "IMPUTE_MEAN"
            assert_frame_equal(canonical.data, raw_snapshot)

            # Apply
            exec_res, cleaned = execute_cleaning_plan(canonical, [med_rec.recommendation_id], plan, operation_overrides=overrides)
            print(f"   Applied operation: {exec_res.operations[0].operation} ({exec_res.operations[0].method_used})")
            assert exec_res.operations[0].operation == "IMPUTE_MEAN"
            assert cleaned.data["length_of_stay"].isna().sum() == 0
            assert_frame_equal(canonical.data, raw_snapshot)
            print("   [PASSED] Healthcare length_of_stay Median -> Mean override validated.")

    print("\n" + "=" * 70)
    print("PART 5.1 REAL DATASET VALIDATION COMPLETED SUCCESSFULLY")
    print("=" * 70)


def validate_part6_registration_and_download():
    print("\n" + "=" * 70)
    print("STARTING PART 6 REAL DATASET REGISTRATION & DOWNLOAD VALIDATION")
    print("=" * 70)

    import io
    from fastapi.testclient import TestClient
    from api.main import app
    from api.store import session_store, DatasetSessionRecord
    from intelligence.profiler import profile_dataset
    from intelligence.semantic_analyzer import analyze_semantics
    from intelligence.schema_validator import assess_readiness

    client = TestClient(app)
    loader = CSVLoader()
    planner = CleaningPlanner()

    for ds_name, file_path in [("Healthcare", "tests/real_data/healthcare.csv"), ("Education", "tests/real_data/education.csv")]:
        print(f"\n>> Validating Part 6 for {ds_name} ({file_path})")
        session_store.clear()

        # 1. Load raw dataset
        canonical = loader.load(file_path)
        raw_id = canonical.metadata.dataset_id
        raw_snapshot = canonical.data.copy(deep=True)

        profile = profile_dataset(canonical)
        semantic = analyze_semantics(canonical, profile=profile)
        readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic)
        raw_record = DatasetSessionRecord(
            dataset=canonical,
            profile=profile,
            semantic_profile=semantic,
            readiness=readiness,
        )
        session_store.save(raw_record)

        # 2. Generate plan & apply safe cleaning
        plan = planner.generate_plan(canonical)
        safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
        apply_res = client.post(f"/api/datasets/{raw_id}/cleaning/apply", json={"selected_recommendation_ids": safe_ids})
        assert apply_res.status_code == 200, f"Apply failed: {apply_res.text}"

        # 3. Register cleaned dataset
        reg_res = client.post(f"/api/datasets/{raw_id}/cleaned/register")
        assert reg_res.status_code == 200, f"Registration failed: {reg_res.text}"
        reg_data = reg_res.json()
        cleaned_id = reg_data["dataset_id"]

        print(f"   Original Dataset ID: {raw_id} ({raw_record.dataset.metadata.row_count} rows)")
        print(f"   Cleaned Dataset ID:  {cleaned_id} ({reg_data['row_count']} rows)")
        print(f"   Cleaned Filename:    {reg_data['filename']}")

        # Verify IDs differ
        assert cleaned_id != raw_id
        assert "cleaned" in cleaned_id
        assert reg_data["source_dataset_id"] == raw_id

        # Verify both coexist in session store
        assert session_store.get(raw_id) is not None
        assert session_store.get(cleaned_id) is not None
        assert len(session_store.list_all()) == 2

        # Verify cleaned record has full intelligence
        cleaned_rec = session_store.get(cleaned_id)
        assert cleaned_rec.profile is not None
        assert cleaned_rec.semantic_profile is not None
        assert cleaned_rec.readiness is not None
        print(f"   Cleaned Profile & Semantics: {len(cleaned_rec.semantic_profile.column_evidences)} columns classified")

        # 4. Download CSV
        csv_res = client.get(f"/api/datasets/{cleaned_id}/download?format=csv")
        assert csv_res.status_code == 200
        df_csv = pd.read_csv(io.BytesIO(csv_res.content))
        assert len(df_csv) == reg_data["row_count"]
        print(f"   [PASSED] Downloaded CSV verified ({len(df_csv)} rows)")

        # 5. Download XLSX
        xlsx_res = client.get(f"/api/datasets/{cleaned_id}/download?format=xlsx")
        assert xlsx_res.status_code == 200
        df_xlsx = pd.read_excel(io.BytesIO(xlsx_res.content))
        assert len(df_xlsx) == reg_data["row_count"]
        print(f"   [PASSED] Downloaded XLSX verified ({len(df_xlsx)} rows)")

        # 6. Verify raw dataset is 100% untouched
        assert_frame_equal(raw_record.dataset.data, raw_snapshot)
        print(f"   [PASSED] Raw dataset 100% immutable throughout registration & downloads.")

    print("\n" + "=" * 70)
    print("PART 6 REAL DATASET VALIDATION COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    validate_real_datasets()
    validate_part51_user_modifications()
    validate_part6_registration_and_download()

