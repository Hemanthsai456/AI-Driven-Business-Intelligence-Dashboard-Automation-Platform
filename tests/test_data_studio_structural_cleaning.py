"""Targeted Test Suite for Structural Cleaning & User-Controlled Semantic Roles (Data Studio Part 6.4).

Covers all 22 required test cases:
1. drop one column
2. drop multiple columns
3. invalid column
4. row filter equals
5. row filter not equals
6. numeric greater-than
7. numeric less-than
8. missing-value row removal
9. contains
10. AND conditions
11. OR conditions
12. invalid operator
13. duplicate removal
14. keep-first
15. keep-last
16. high-missingness recommendation
17. constant-column recommendation
18. identifier recommendation
19. semantic role override
20. raw dataset unchanged after preview
21. raw dataset unchanged after apply
22. deterministic repeated execution
"""

import copy
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from cleaning.structural import (
    FilterCondition,
    StructuralCleaner,
    StructuralExecutionError,
    StructuralQualityRecommendation,
    ColumnDropPreviewResult,
    RowFilterPreviewResult,
    DuplicateRemovalPreviewResult,
    SemanticRoleOverridePreviewResult,
)
from ingestion.loaders import CSVLoader
from ingestion.models import CanonicalDataset, ColumnRole, DatasetMetadata
from intelligence.profiler import DataProfiler
from intelligence.semantic_analyzer import SemanticAnalyzer


@pytest.fixture
def test_client():
    return TestClient(app)


def create_test_canonical(df: pd.DataFrame, name: str = "struct_ds", dataset_id: str = "ds_struct_123") -> CanonicalDataset:
    loader = CSVLoader()
    schema = loader.extract_column_metadata(df)
    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=name,
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    return CanonicalDataset(metadata=meta, data=df)


# -----------------------------------------------------------------------------
# 1. DROP ONE COLUMN
# -----------------------------------------------------------------------------

def test_drop_one_column():
    df = pd.DataFrame({
        "internal_id": [101, 102, 103],
        "name": ["Alice", "Bob", "Charlie"],
        "salary": [70000, 80000, 90000],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Preview
    preview = cleaner.preview_drop_columns(canonical, ["internal_id"])
    assert preview.original_column_count == 3
    assert preview.resulting_column_count == 2
    assert preview.columns_to_drop == ["internal_id"]
    assert preview.remaining_columns == ["name", "salary"]
    assert preview.original_row_count == 3
    assert preview.resulting_row_count == 3

    # Apply
    cleaned, audit = cleaner.apply_drop_columns(canonical, ["internal_id"])
    assert "internal_id" not in cleaned.data.columns
    assert list(cleaned.data.columns) == ["name", "salary"]
    assert len(cleaned.data) == 3
    assert audit["action"] == "DROP_COLUMNS"


# -----------------------------------------------------------------------------
# 2. DROP MULTIPLE COLUMNS
# -----------------------------------------------------------------------------

def test_drop_multiple_columns():
    df = pd.DataFrame({
        "internal_id": [1, 2, 3],
        "unused_notes": ["a", "b", "c"],
        "salary": [50000, 60000, 70000],
        "department": ["HR", "IT", "Sales"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    preview = cleaner.preview_drop_columns(canonical, ["internal_id", "unused_notes"])
    assert preview.original_column_count == 4
    assert preview.resulting_column_count == 2
    assert set(preview.columns_to_drop) == {"internal_id", "unused_notes"}
    assert preview.remaining_columns == ["salary", "department"]

    cleaned, audit = cleaner.apply_drop_columns(canonical, ["internal_id", "unused_notes"])
    assert set(cleaned.data.columns) == {"salary", "department"}
    assert audit["columns_dropped_count"] == 2


# -----------------------------------------------------------------------------
# 3. INVALID COLUMN
# -----------------------------------------------------------------------------

def test_invalid_column_drop():
    df = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    with pytest.raises(StructuralExecutionError, match="Target column 'nonexistent_col' does not exist"):
        cleaner.preview_drop_columns(canonical, ["nonexistent_col"])

    with pytest.raises(StructuralExecutionError, match="At least one column must be specified"):
        cleaner.preview_drop_columns(canonical, [])

    with pytest.raises(StructuralExecutionError, match="Cannot drop all columns"):
        cleaner.preview_drop_columns(canonical, ["col_a", "col_b"])


# -----------------------------------------------------------------------------
# 4. ROW FILTER EQUALS
# -----------------------------------------------------------------------------

def test_row_filter_equals():
    df = pd.DataFrame({
        "status": ["Active", "Invalid", "Active", "Unknown", "Active"],
        "age": [25, 30, 35, 40, 45],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    condition = FilterCondition(column="status", operator="equals", value="Invalid")
    preview = cleaner.preview_filter_rows(canonical, [condition])

    assert preview.original_row_count == 5
    assert preview.rows_removed == 1
    assert preview.resulting_row_count == 4
    assert len(preview.sample_matching_rows) == 1
    assert preview.sample_matching_rows[0]["status"] == "Invalid"

    cleaned, audit = cleaner.apply_filter_rows(canonical, [condition])
    assert len(cleaned.data) == 4
    assert "Invalid" not in cleaned.data["status"].values


# -----------------------------------------------------------------------------
# 5. ROW FILTER NOT EQUALS
# -----------------------------------------------------------------------------

def test_row_filter_not_equals():
    df = pd.DataFrame({
        "status": ["Active", "Inactive", "Pending", "Active", "Archived"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Filter out rows where status != "Active"
    condition = FilterCondition(column="status", operator="not equals", value="Active")
    preview = cleaner.preview_filter_rows(canonical, [condition])

    assert preview.original_row_count == 5
    assert preview.rows_removed == 3
    assert preview.resulting_row_count == 2

    cleaned, audit = cleaner.apply_filter_rows(canonical, [condition])
    assert len(cleaned.data) == 2
    assert list(cleaned.data["status"].unique()) == ["Active"]


# -----------------------------------------------------------------------------
# 6. NUMERIC GREATER-THAN
# -----------------------------------------------------------------------------

def test_numeric_greater_than():
    df = pd.DataFrame({
        "item": ["A", "B", "C", "D"],
        "price": [10.0, 50.0, 150.0, 200.0],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Filter out rows where price > 100
    condition = FilterCondition(column="price", operator="greater than", value=100)
    preview = cleaner.preview_filter_rows(canonical, [condition])

    assert preview.original_row_count == 4
    assert preview.rows_removed == 2
    assert preview.resulting_row_count == 2

    cleaned, _ = cleaner.apply_filter_rows(canonical, [condition])
    assert len(cleaned.data) == 2
    assert (cleaned.data["price"] <= 100).all()


# -----------------------------------------------------------------------------
# 7. NUMERIC LESS-THAN
# -----------------------------------------------------------------------------

def test_numeric_less_than():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "David"],
        "age": [-5, 25, -1, 30],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Filter out rows where age < 0
    condition = FilterCondition(column="age", operator="less than", value=0)
    preview = cleaner.preview_filter_rows(canonical, [condition])

    assert preview.original_row_count == 4
    assert preview.rows_removed == 2
    assert preview.resulting_row_count == 2

    cleaned, _ = cleaner.apply_filter_rows(canonical, [condition])
    assert len(cleaned.data) == 2
    assert (cleaned.data["age"] >= 0).all()


# -----------------------------------------------------------------------------
# 8. MISSING-VALUE ROW REMOVAL
# -----------------------------------------------------------------------------

def test_missing_value_row_removal():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "email": ["a@x.com", None, "c@x.com", "", "  "],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Filter out rows where email is missing
    condition = FilterCondition(column="email", operator="is missing")
    preview = cleaner.preview_filter_rows(canonical, [condition])

    assert preview.original_row_count == 5
    assert preview.rows_removed == 3
    assert preview.resulting_row_count == 2

    cleaned, _ = cleaner.apply_filter_rows(canonical, [condition])
    assert len(cleaned.data) == 2
    assert list(cleaned.data["id"]) == [1, 3]


# -----------------------------------------------------------------------------
# 9. CONTAINS
# -----------------------------------------------------------------------------

def test_row_filter_contains():
    df = pd.DataFrame({
        "ticket": ["ERROR_404", "WARN_101", "ERROR_500", "INFO_OK"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Filter out rows where ticket contains "ERROR"
    condition = FilterCondition(column="ticket", operator="contains", value="error")
    preview = cleaner.preview_filter_rows(canonical, [condition])

    assert preview.original_row_count == 4
    assert preview.rows_removed == 2
    assert preview.resulting_row_count == 2

    cleaned, _ = cleaner.apply_filter_rows(canonical, [condition])
    assert len(cleaned.data) == 2
    assert list(cleaned.data["ticket"]) == ["WARN_101", "INFO_OK"]


# -----------------------------------------------------------------------------
# 10. AND CONDITIONS
# -----------------------------------------------------------------------------

def test_and_conditions():
    df = pd.DataFrame({
        "age": [-5, -2, 25, 30],
        "salary": [-1000, 50000, -500, 60000],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Remove rows where age < 0 AND salary < 0
    cond1 = FilterCondition(column="age", operator="less than", value=0)
    cond2 = FilterCondition(column="salary", operator="less than", value=0)

    preview = cleaner.preview_filter_rows(canonical, [cond1, cond2], logical_operator="AND")
    assert preview.original_row_count == 4
    assert preview.rows_removed == 1  # Only row 0 matches both
    assert preview.resulting_row_count == 3

    cleaned, _ = cleaner.apply_filter_rows(canonical, [cond1, cond2], logical_operator="AND")
    assert len(cleaned.data) == 3


# -----------------------------------------------------------------------------
# 11. OR CONDITIONS
# -----------------------------------------------------------------------------

def test_or_conditions():
    df = pd.DataFrame({
        "status": ["Invalid", "Active", "Unknown", "Active", "Error"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Remove rows where status == "Invalid" OR status == "Unknown"
    cond1 = FilterCondition(column="status", operator="equals", value="Invalid")
    cond2 = FilterCondition(column="status", operator="equals", value="Unknown")

    preview = cleaner.preview_filter_rows(canonical, [cond1, cond2], logical_operator="OR")
    assert preview.original_row_count == 5
    assert preview.rows_removed == 2
    assert preview.resulting_row_count == 3

    cleaned, _ = cleaner.apply_filter_rows(canonical, [cond1, cond2], logical_operator="OR")
    assert len(cleaned.data) == 3
    assert set(cleaned.data["status"]) == {"Active", "Error"}


# -----------------------------------------------------------------------------
# 12. INVALID OPERATOR
# -----------------------------------------------------------------------------

def test_invalid_operator():
    df = pd.DataFrame({"col": [1, 2, 3]})
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    cond = FilterCondition(column="col", operator="regex_match", value=".*")
    with pytest.raises(StructuralExecutionError, match="Unsupported filter operator"):
        cleaner.preview_filter_rows(canonical, [cond])


# -----------------------------------------------------------------------------
# 13. DUPLICATE REMOVAL
# -----------------------------------------------------------------------------

def test_duplicate_removal():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3, 3, 3],
        "name": ["A", "B", "B", "C", "C", "C"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    preview = cleaner.preview_remove_duplicates(canonical, keep_strategy="first")
    assert preview.original_row_count == 6
    assert preview.duplicate_rows_count == 3
    assert preview.rows_removed == 3
    assert preview.resulting_row_count == 3

    cleaned, audit = cleaner.apply_remove_duplicates(canonical, keep_strategy="first")
    assert len(cleaned.data) == 3
    assert audit["rows_removed"] == 3


# -----------------------------------------------------------------------------
# 14. KEEP-FIRST
# -----------------------------------------------------------------------------

def test_duplicate_removal_keep_first():
    df = pd.DataFrame({
        "id": [1, 2, 2],
        "val": ["first_entry", "dup_1", "dup_1"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    cleaned, audit = cleaner.apply_remove_duplicates(canonical, keep_strategy="first")
    assert len(cleaned.data) == 2
    assert cleaned.data.iloc[1]["val"] == "dup_1"
    assert audit["keep_strategy"] == "first"


# -----------------------------------------------------------------------------
# 15. KEEP-LAST
# -----------------------------------------------------------------------------

def test_duplicate_removal_keep_last():
    df = pd.DataFrame({
        "id": [1, 2, 2],
        "val": ["first_entry", "dup_1", "dup_1"],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    preview = cleaner.preview_remove_duplicates(canonical, keep_strategy="last")
    assert preview.rows_removed == 1
    assert preview.keep_strategy == "last"

    cleaned, audit = cleaner.apply_remove_duplicates(canonical, keep_strategy="last")
    assert len(cleaned.data) == 2
    assert audit["keep_strategy"] == "last"


# -----------------------------------------------------------------------------
# 16. HIGH-MISSINGNESS RECOMMENDATION
# -----------------------------------------------------------------------------

def test_high_missingness_recommendation():
    # 95% missing values
    values = [None] * 95 + ["valid"] * 5
    df = pd.DataFrame({
        "id": list(range(100)),
        "notes": values,
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    recs = cleaner.get_structural_recommendations(canonical)
    notes_recs = [r for r in recs if r.column_name == "notes" and r.issue_type == "HIGH_MISSINGNESS"]
    assert len(notes_recs) == 1
    assert notes_recs[0].suggested_action == "DROP_COLUMN"
    assert "DROP_COLUMN" in notes_recs[0].allowed_actions
    assert notes_recs[0].metrics["null_percentage"] == 95.0


# -----------------------------------------------------------------------------
# 17. CONSTANT-COLUMN RECOMMENDATION
# -----------------------------------------------------------------------------

def test_constant_column_recommendation():
    df = pd.DataFrame({
        "id": list(range(50)),
        "constant_col": ["FixedValue"] * 50,
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    recs = cleaner.get_structural_recommendations(canonical)
    const_recs = [r for r in recs if r.column_name == "constant_col" and r.issue_type == "CONSTANT_COLUMN"]
    assert len(const_recs) == 1
    assert const_recs[0].suggested_action == "DROP_COLUMN"
    assert "0 variance" in const_recs[0].reason or "constant" in const_recs[0].reason.lower()


# -----------------------------------------------------------------------------
# 18. IDENTIFIER RECOMMENDATION
# -----------------------------------------------------------------------------

def test_identifier_recommendation():
    df = pd.DataFrame({
        "customer_uuid": [f"uuid-{i}" for i in range(100)],
        "amount": [10.5 * i for i in range(100)],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    recs = cleaner.get_structural_recommendations(canonical)
    id_recs = [r for r in recs if r.column_name == "customer_uuid" and r.issue_type == "LIKELY_IDENTIFIER"]
    assert len(id_recs) == 1
    assert id_recs[0].suggested_action == "MARK_IDENTIFIER"
    assert "MARK_IDENTIFIER" in id_recs[0].allowed_actions


# -----------------------------------------------------------------------------
# 19. SEMANTIC ROLE OVERRIDE
# -----------------------------------------------------------------------------

def test_semantic_role_override():
    df = pd.DataFrame({
        "Roll-No": [1001, 1002, 1003, 1004],
        "Score": [88, 92, 79, 95],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Preview
    preview = cleaner.preview_semantic_role_override(
        canonical=canonical,
        column_name="Roll-No",
        selected_role="IDENTIFIER",
    )
    assert preview.column_name == "Roll-No"
    assert preview.selected_role == "IDENTIFIER"
    assert preview.physical_dtype == "int64"

    # Apply
    user_overrides = {}
    updated_sem, audit = cleaner.apply_semantic_role_override(
        canonical=canonical,
        column_name="Roll-No",
        selected_role="IDENTIFIER",
        user_role_overrides_dict=user_overrides,
    )
    assert user_overrides["Roll-No"] == "IDENTIFIER"
    ev = updated_sem.get_evidence("Roll-No")
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.is_user_overridden is True
    # Physical dtype remains int64
    assert str(canonical.data["Roll-No"].dtype) == "int64"


# -----------------------------------------------------------------------------
# 20. RAW DATASET UNCHANGED AFTER PREVIEW
# -----------------------------------------------------------------------------

def test_raw_dataset_unchanged_after_preview():
    df = pd.DataFrame({
        "internal_id": [1, 2, 3, 3],
        "age": [-1, 20, 30, 30],
        "notes": [None, None, None, None],
    })
    raw_copy = df.copy(deep=True)
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Column drop preview
    cleaner.preview_drop_columns(canonical, ["internal_id"])
    pd.testing.assert_frame_equal(canonical.data, raw_copy)

    # Row filter preview
    cleaner.preview_filter_rows(canonical, [FilterCondition(column="age", operator="less than", value=0)])
    pd.testing.assert_frame_equal(canonical.data, raw_copy)

    # Duplicate removal preview
    cleaner.preview_remove_duplicates(canonical, keep_strategy="first")
    pd.testing.assert_frame_equal(canonical.data, raw_copy)

    # Semantic override preview
    cleaner.preview_semantic_role_override(canonical, "internal_id", "IDENTIFIER")
    pd.testing.assert_frame_equal(canonical.data, raw_copy)


# -----------------------------------------------------------------------------
# 21. RAW DATASET UNCHANGED AFTER APPLY
# -----------------------------------------------------------------------------

def test_raw_dataset_unchanged_after_apply():
    df = pd.DataFrame({
        "col_drop": [1, 2, 2],
        "val": [10, 20, 20],
    })
    raw_copy = df.copy(deep=True)
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    # Apply column drop
    cleaned1, _ = cleaner.apply_drop_columns(canonical, ["col_drop"])
    pd.testing.assert_frame_equal(canonical.data, raw_copy)
    assert "col_drop" not in cleaned1.data.columns

    # Apply duplicate removal
    cleaned2, _ = cleaner.apply_remove_duplicates(canonical, keep_strategy="first")
    pd.testing.assert_frame_equal(canonical.data, raw_copy)
    assert len(cleaned2.data) == 2


# -----------------------------------------------------------------------------
# 22. DETERMINISTIC REPEATED EXECUTION
# -----------------------------------------------------------------------------

def test_deterministic_repeated_execution():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3, 4],
        "status": ["Active", "Invalid", "Invalid", "Unknown", "Active"],
        "temp": [98.6, -999.0, -999.0, 99.1, 98.4],
    })
    canonical = create_test_canonical(df)
    cleaner = StructuralCleaner()

    conditions = [
        FilterCondition(column="status", operator="equals", value="Invalid"),
        FilterCondition(column="temp", operator="less than", value=0),
    ]

    # Run filter multiple times
    res1, _ = cleaner.apply_filter_rows(canonical, conditions, logical_operator="OR")
    res2, _ = cleaner.apply_filter_rows(canonical, conditions, logical_operator="OR")
    pd.testing.assert_frame_equal(res1.data, res2.data)

    # Run duplicate removal multiple times
    dup1, _ = cleaner.apply_remove_duplicates(canonical, keep_strategy="first")
    dup2, _ = cleaner.apply_remove_duplicates(canonical, keep_strategy="first")
    pd.testing.assert_frame_equal(dup1.data, dup2.data)


# -----------------------------------------------------------------------------
# END-TO-END FASTAPI INTEGRATION TESTS
# -----------------------------------------------------------------------------

def test_api_structural_endpoints(test_client):
    df = pd.DataFrame({
        "customer_id": [101, 102, 103, 103],
        "notes": [None, None, None, None],
        "amount": [-50.0, 100.0, 200.0, 200.0],
    })
    canonical = create_test_canonical(df, dataset_id="ds_api_struct_test")
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=None,
        semantic_profile=None,
        readiness=None,
    )
    session_store.save(record)

    # 1. Recommendations Endpoint
    rec_res = test_client.get(f"/api/datasets/ds_api_struct_test/cleaning/structural/recommendations")
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert rec_data["dataset_id"] == "ds_api_struct_test"
    assert rec_data["total_recommendations"] >= 1

    # 2. Drop Columns Preview & Apply
    drop_prev_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/drop-columns/preview",
        json={"columns": ["notes"]},
    )
    assert drop_prev_res.status_code == 200
    assert drop_prev_res.json()["resulting_column_count"] == 2

    drop_apply_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/drop-columns/apply",
        json={"columns": ["notes"]},
    )
    assert drop_apply_res.status_code == 200
    assert drop_apply_res.json()["cleaned_column_count"] == 2

    # 3. Filter Rows Preview & Apply
    filter_prev_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/filter-rows/preview",
        json={
            "conditions": [{"column": "amount", "operator": "less than", "value": 0}],
            "logical_operator": "AND",
        },
    )
    assert filter_prev_res.status_code == 200
    assert filter_prev_res.json()["rows_removed"] == 1

    filter_apply_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/filter-rows/apply",
        json={
            "conditions": [{"column": "amount", "operator": "less than", "value": 0}],
            "logical_operator": "AND",
        },
    )
    assert filter_apply_res.status_code == 200
    assert filter_apply_res.json()["cleaned_row_count"] == 3

    # 4. Duplicate Rows Preview & Apply
    dup_prev_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/duplicates/preview",
        json={"keep_strategy": "first"},
    )
    assert dup_prev_res.status_code == 200
    assert dup_prev_res.json()["duplicate_rows_count"] == 1

    dup_apply_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )
    assert dup_apply_res.status_code == 200
    assert dup_apply_res.json()["cleaned_row_count"] == 2

    # 5. Semantic Role Override Preview & Apply
    sem_prev_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/semantic-role/preview",
        json={"column_name": "customer_id", "selected_role": "IDENTIFIER"},
    )
    assert sem_prev_res.status_code == 200
    assert sem_prev_res.json()["selected_role"] == "IDENTIFIER"

    sem_apply_res = test_client.post(
        f"/api/datasets/ds_api_struct_test/cleaning/structural/semantic-role/apply",
        json={"column_name": "customer_id", "selected_role": "IDENTIFIER"},
    )
    assert sem_apply_res.status_code == 200
    assert sem_apply_res.json()["selected_role"] == "IDENTIFIER"
    assert record.user_semantic_role_overrides["customer_id"] == "IDENTIFIER"
