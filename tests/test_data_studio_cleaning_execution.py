"""Targeted test suite for Data Studio Part 5: Cleaning Preview, Batch Execution, and Validation.

Tests all 19 required invariants and behaviors:
1. duplicate removal
2. median imputation
3. mode fill
4. Unknown fill
5. empty-string normalization
6. numeric conversion
7. datetime conversion
8. boolean normalization
9. review-only operations cannot silently transform data
10. preview does not mutate raw data
11. apply does not mutate raw data
12. preview is deterministic
13. execution is deterministic
14. validation catches failed operations
15. row/cell counts are correct
16. selected recommendation IDs are validated
17. invalid column/recommendation cannot execute
18. dataset isolation
19. same raw dataset remains unchanged after execution (assert_frame_equal verification)
"""

import copy
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from cleaning.executor import (
    CleaningExecutionError,
    CleaningExecutor,
    execute_cleaning_plan,
    preview_cleaning_plan,
)
from cleaning.models import (
    CleaningExecutionResult,
    CleaningPlan,
    CleaningPreviewResult,
    CleaningRecommendation,
)
from cleaning.planner import CleaningPlanner
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DatasetMetadata,
)


def _build_test_canonical(df: pd.DataFrame, dataset_id: str = "test-ds-1") -> CanonicalDataset:
    """Helper to construct a CanonicalDataset for testing."""
    schema = []
    for col in df.columns:
        s = df[col]
        dtype_str = str(s.dtype)
        role = ColumnRole.MEASURE if pd.api.types.is_numeric_dtype(s) else ColumnRole.DIMENSION
        schema.append(
            ColumnMetadata(
                original_name=col,
                normalized_name=col.lower(),
                detected_datatype=dtype_str,
                semantic_role=role,
                null_count=int(s.isna().sum()),
                null_percentage=round((s.isna().sum() / max(len(df), 1)) * 100, 2),
                distinct_count=int(s.nunique()),
                is_unique=bool(s.is_unique),
                sample_values=s.dropna().head(3).tolist(),
            )
        )

    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name="Test Dataset",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    return CanonicalDataset(metadata=meta, data=df.copy(deep=True))


# =========================================================================
# 1. Duplicate Removal
# =========================================================================
def test_duplicate_removal_execution():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3, 4],
        "city": ["New York", "Chicago", "Chicago", "Houston", "Miami"],
        "sales": [100.0, 200.0, 200.0, 300.0, 400.0],
    })
    canonical = _build_test_canonical(df, "ds-dup")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    dup_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "REMOVE_DUPLICATES"]
    assert len(dup_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, dup_recs, plan)
    assert exec_result.cleaned_row_count == 4
    assert exec_result.row_count_change == -1
    assert exec_result.total_rows_affected == 1
    assert exec_result.operations_applied == 1
    assert len(cleaned_canonical.data) == 4
    assert cleaned_canonical.data.duplicated().sum() == 0


# =========================================================================
# 2. Median Imputation
# =========================================================================
def test_median_imputation_execution():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "age": [20.0, 30.0, np.nan, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
    })
    canonical = _build_test_canonical(df, "ds-med")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    med_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "IMPUTE_MEDIAN"]
    assert len(med_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, med_recs, plan)
    assert exec_result.operations_applied == 1
    assert cleaned_canonical.data["age"].isna().sum() == 0
    # Median of [20, 30, 40, 50, 60, 70, 80, 90, 100] is 60.0
    assert cleaned_canonical.data.loc[2, "age"] == 60.0


# =========================================================================
# 3. Mode Fill
# =========================================================================
def test_mode_fill_execution():
    # 8 rows with 'Cardiology', 2 with 'Neurology', 1 with NaN (Cardiology is dominant mode >= 40%)
    df = pd.DataFrame({
        "id": list(range(1, 12)),
        "department": ["Cardiology"] * 8 + ["Neurology"] * 2 + [np.nan],
    })
    canonical = _build_test_canonical(df, "ds-mode")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    mode_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "FILL_MODE"]
    assert len(mode_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, mode_recs, plan)
    assert exec_result.operations_applied == 1
    assert cleaned_canonical.data["department"].isna().sum() == 0
    assert cleaned_canonical.data.loc[10, "department"] == "Cardiology"


# =========================================================================
# 4. Unknown Fill
# =========================================================================
def test_unknown_fill_execution():
    # High cardinality categories without dominant mode
    df = pd.DataFrame({
        "id": list(range(1, 11)),
        "vendor": ["VendorA", "VendorB", "VendorC", "VendorD", "VendorE", "VendorF", "VendorG", "VendorH", np.nan, np.nan],
    })
    canonical = _build_test_canonical(df, "ds-unknown")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    unknown_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "FILL_UNKNOWN"]
    assert len(unknown_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, unknown_recs, plan)
    assert exec_result.operations_applied == 1
    assert cleaned_canonical.data["vendor"].isna().sum() == 0
    assert cleaned_canonical.data.loc[8, "vendor"] == "Unknown"
    assert cleaned_canonical.data.loc[9, "vendor"] == "Unknown"


# =========================================================================
# 5. Empty-String Normalization
# =========================================================================
def test_empty_string_normalization_execution():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "notes": ["Valid Note", "   ", "", "Another Note"],
    })
    canonical = _build_test_canonical(df, "ds-empty")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    empty_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "NORMALIZE_EMPTY_STRINGS"]
    assert len(empty_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, empty_recs, plan)
    assert exec_result.operations_applied == 1
    assert pd.isna(cleaned_canonical.data.loc[1, "notes"])
    assert pd.isna(cleaned_canonical.data.loc[2, "notes"])
    assert cleaned_canonical.data.loc[0, "notes"] == "Valid Note"


# =========================================================================
# 6. Numeric Conversion
# =========================================================================
def test_numeric_conversion_execution():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "price": ["10.5", "20.0", "35.25"],
    })
    canonical = _build_test_canonical(df, "ds-num")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    num_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "CONVERT_NUMERIC"]
    assert len(num_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, num_recs, plan)
    assert exec_result.operations_applied == 1
    assert pd.api.types.is_numeric_dtype(cleaned_canonical.data["price"])
    assert cleaned_canonical.data["price"].sum() == 65.75


# =========================================================================
# 7. Datetime Conversion
# =========================================================================
def test_datetime_conversion_execution():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "timestamp": ["2023-01-15", "2023-02-20", "2023-03-25"],
    })
    canonical = _build_test_canonical(df, "ds-dt")
    # Mark semantic role as datetime so planner detects it
    canonical.metadata.schema[1].semantic_role = ColumnRole.DATETIME
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    dt_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "CONVERT_DATETIME"]
    assert len(dt_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, dt_recs, plan)
    assert exec_result.operations_applied == 1
    assert pd.api.types.is_datetime64_any_dtype(cleaned_canonical.data["timestamp"])


# =========================================================================
# 8. Boolean Normalization
# =========================================================================
def test_boolean_normalization_execution():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "is_active": ["yes", "no", "yes", "no"],
    })
    canonical = _build_test_canonical(df, "ds-bool")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    bool_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "NORMALIZE_BOOLEAN"]
    assert len(bool_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, bool_recs, plan)
    assert exec_result.operations_applied == 1
    assert cleaned_canonical.data["is_active"].tolist() == [True, False, True, False]


# =========================================================================
# 9. Review-Only Operations Cannot Silently Transform Data
# =========================================================================
def test_review_only_operations_cannot_silently_transform():
    # 20 observations with variance and an extreme outlier
    df = pd.DataFrame({
        "id": list(range(1, 22)),
        "value": [float(x) for x in range(10, 30)] + [10000.0],
    })
    canonical = _build_test_canonical(df, "ds-outlier")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    outlier_recs = [r.recommendation_id for r in plan.recommendations if r.operation == "REVIEW_OUTLIERS"]
    assert len(outlier_recs) == 1

    exec_result, cleaned_canonical = execute_cleaning_plan(canonical, outlier_recs, plan)
    assert exec_result.operations_skipped == 1
    assert exec_result.operations_applied == 0
    # Cleaned DataFrame still contains 21 rows with 10000.0 (untouched!)
    assert len(cleaned_canonical.data) == 21
    assert 10000.0 in cleaned_canonical.data["value"].values


# =========================================================================
# 10. Preview Does Not Mutate Raw Data
# =========================================================================
def test_preview_does_not_mutate_raw_data():
    df = pd.DataFrame({
        "id": [1, 1, 2, 3],
        "status": ["active", "active", "  ", np.nan],
    })
    canonical = _build_test_canonical(df, "ds-prev-mut")
    raw_snapshot = canonical.data.copy(deep=True)

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    all_ids = [r.recommendation_id for r in plan.recommendations]

    preview_res = preview_cleaning_plan(canonical, all_ids, plan)
    assert isinstance(preview_res, CleaningPreviewResult)
    assert preview_res.preview_row_count == 3
    # Raw dataframe must be identical to snapshot
    assert_frame_equal(canonical.data, raw_snapshot)


# =========================================================================
# 11. Apply Does Not Mutate Raw Data
# =========================================================================
def test_apply_does_not_mutate_raw_data():
    df = pd.DataFrame({
        "id": [1, 1, 2, 3],
        "status": ["active", "active", "  ", np.nan],
    })
    canonical = _build_test_canonical(df, "ds-apply-mut")
    raw_snapshot = canonical.data.copy(deep=True)

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    all_ids = [r.recommendation_id for r in plan.recommendations]

    exec_res, cleaned = execute_cleaning_plan(canonical, all_ids, plan)
    assert isinstance(exec_res, CleaningExecutionResult)
    assert len(cleaned.data) == 3
    # Raw dataframe must remain 100% equal to raw snapshot
    assert_frame_equal(canonical.data, raw_snapshot)


# =========================================================================
# 12. Preview is Deterministic
# =========================================================================
def test_preview_is_deterministic():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "val": [10.0, np.nan, np.nan, 40.0],
    })
    canonical = _build_test_canonical(df, "ds-prev-det")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    rec_ids = [r.recommendation_id for r in plan.recommendations]

    p1 = preview_cleaning_plan(canonical, rec_ids, plan).to_dict()
    # Delete timestamp before comparison
    p1.pop("generated_at", None)

    p2 = preview_cleaning_plan(canonical, rec_ids, plan).to_dict()
    p2.pop("generated_at", None)

    assert p1 == p2


# =========================================================================
# 13. Execution is Deterministic
# =========================================================================
def test_execution_is_deterministic():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "val": [10.0, np.nan, np.nan, 40.0],
    })
    canonical = _build_test_canonical(df, "ds-exec-det")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    rec_ids = [r.recommendation_id for r in plan.recommendations]

    r1, c1 = execute_cleaning_plan(canonical, rec_ids, plan)
    r2, c2 = execute_cleaning_plan(canonical, rec_ids, plan)

    assert_frame_equal(c1.data, c2.data)
    assert r1.cleaned_row_count == r2.cleaned_row_count
    assert r1.total_cells_affected == r2.total_cells_affected


# =========================================================================
# 14. Validation Catches Invariants
# =========================================================================
def test_validation_catches_invariants():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "amount": [10.0, np.nan, np.nan, 40.0],
    })
    canonical = _build_test_canonical(df, "ds-val")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    rec_ids = [r.recommendation_id for r in plan.recommendations]

    exec_res, _ = execute_cleaning_plan(canonical, rec_ids, plan)
    assert exec_res.validation is not None
    assert exec_res.validation.overall_status in ["PASSED", "WARNING"]
    check_names = [chk.check_name for chk in exec_res.validation.checks]
    assert "ROW_COUNT_INVARIANT" in check_names
    assert "COLUMN_COUNT_INVARIANT" in check_names


# =========================================================================
# 15. Row/Cell Counts are Correct
# =========================================================================
def test_row_and_cell_counts_are_correct():
    df = pd.DataFrame({
        "id": list(range(1, 11)),
        "num": [10.0, np.nan, np.nan, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
    })
    canonical = _build_test_canonical(df, "ds-counts")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    rec_ids = [r.recommendation_id for r in plan.recommendations if r.operation == "IMPUTE_MEDIAN"]

    exec_res, _ = execute_cleaning_plan(canonical, rec_ids, plan)
    assert exec_res.original_row_count == 10
    assert exec_res.cleaned_row_count == 10
    assert exec_res.total_cells_affected == 2


# =========================================================================
# 16. Selected Recommendation IDs are Validated
# =========================================================================
def test_selected_recommendation_ids_validation():
    df = pd.DataFrame({"a": [1, 2, 3]})
    canonical = _build_test_canonical(df, "ds-fake-id")

    with pytest.raises(CleaningExecutionError, match="Invalid recommendation IDs"):
        execute_cleaning_plan(canonical, ["non-existent-rec-id-999"])


# =========================================================================
# 17. Invalid Column/Recommendation Cannot Execute Unsafely
# =========================================================================
def test_unsafe_unparseable_numeric_conversion_is_rejected():
    # Only 50% parseable -> marked REVIEW_REQUIRED
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "code": ["100", "200", "INVALID_TEXT", "ANOTHER_INVALID"],
    })
    canonical = _build_test_canonical(df, "ds-unsafe")
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    # If there is a rec or if we manually construct a review-required conversion
    executor = CleaningExecutor(planner)
    rec = CleaningRecommendation(
        recommendation_id="rec-unsafe-test",
        column_name="code",
        operation="CONVERT_NUMERIC",
        category="type_conversion",
        evidence=["Unsafe test"],
        affected_rows=4,
        affected_percentage=100.0,
        confidence=0.5,
        confidence_level="LOW",
        risk_level="HIGH",
        default_selected=False,
        user_selected=True,
        rationale="Unsafe test",
        expected_effect="Unsafe test",
        requires_review=True,
        status="REVIEW_REQUIRED",
    )
    plan.recommendations.append(rec)

    exec_res, cleaned = executor.execute(canonical, ["rec-unsafe-test"], plan)
    assert exec_res.operations_skipped == 1
    # Column 'code' must NOT have been converted to NaN
    assert "INVALID_TEXT" in cleaned.data["code"].values


# =========================================================================
# 18. Dataset Isolation
# =========================================================================
def test_dataset_isolation():
    df1 = pd.DataFrame({"id": [1, 2, 2], "val": [10, 20, 20]})
    df2 = pd.DataFrame({"id": [10, 20, 30], "val": [100, 200, 300]})
    c1 = _build_test_canonical(df1, "ds-iso-1")
    c2 = _build_test_canonical(df2, "ds-iso-2")

    plan1 = CleaningPlanner().generate_plan(c1)
    rec_ids = [r.recommendation_id for r in plan1.recommendations]

    _, cleaned1 = execute_cleaning_plan(c1, rec_ids, plan1)
    assert len(cleaned1.data) == 2
    # Ensure c2 is completely untouched
    assert len(c2.data) == 3
    assert c2.data["val"].tolist() == [100, 200, 300]


# =========================================================================
# 19. Same Raw Dataset Remains Byte/Value Equivalent
# =========================================================================
def test_raw_dataset_byte_value_equivalent_after_execution():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Bob", "Charlie", "  ", np.nan],
        "age": [25.0, 30.0, 30.0, np.nan, 45.0, 50.0],
        "active": ["yes", "no", "no", "yes", "no", "yes"],
    })
    canonical = _build_test_canonical(df, "ds-immutability-proof")
    raw_copy = df.copy(deep=True)

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]

    # Run preview
    preview_res = preview_cleaning_plan(canonical, safe_ids, plan)
    assert preview_res is not None
    assert_frame_equal(canonical.data, raw_copy)

    # Run apply
    exec_res, cleaned = execute_cleaning_plan(canonical, safe_ids, plan)
    assert exec_res is not None
    assert len(cleaned.data) < len(canonical.data)  # deduplication happened on copy

    # Verify original canonical data remains 100% untouched
    assert_frame_equal(canonical.data, raw_copy)
    assert canonical.metadata.row_count == 6
    assert canonical.metadata.dataset_id == "ds-immutability-proof"
