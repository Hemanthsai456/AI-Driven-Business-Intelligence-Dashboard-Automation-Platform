"""Targeted Test Suite for Multi-Valued Cell Detection and User-Controlled Handling (Data Studio Part 6.3).

Covers all 17 required test cases:
1. comma-delimited multi-values
2. semicolon-delimited values
3. pipe-delimited values
4. numeric comma formatting such as 1,250.50 is not falsely detected
5. split into columns
6. variable number of values
7. generated column name collision
8. expand into rows
9. row count calculation
10. duplicated context columns during expansion
11. keep unchanged
12. custom delimiter
13. invalid column
14. invalid delimiter
15. raw dataset remains unchanged after preview
16. raw dataset remains unchanged after apply
17. deterministic repeated execution
"""

import copy
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from cleaning.multivalue import (
    MultiValueDetector,
    MultiValueExecutionError,
    MultiValueHandler,
    MultiValuedColumnCandidate,
    MultiValuePreviewResult,
)
from ingestion.loaders import CSVLoader
from ingestion.models import CanonicalDataset, DatasetMetadata


@pytest.fixture
def test_client():
    return TestClient(app)


def create_test_canonical(df: pd.DataFrame, name: str = "test_ds", dataset_id: str = "ds_test_123") -> CanonicalDataset:
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


# =========================================================================
# 1. Comma-delimited multi-values
# =========================================================================
def test_1_comma_delimited_detection():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "salaries": ["12,17", "20,25", "30,35", "40"],
    })
    canonical = create_test_canonical(df)
    detector = MultiValueDetector()
    candidates = detector.detect_candidates(canonical)

    assert len(candidates) >= 1
    cand = next(c for c in candidates if c.column_name == "salaries")
    assert cand.detected_delimiter == ","
    assert cand.affected_rows == 3
    assert cand.affected_percentage == 75.0
    assert cand.recommendation in ["SPLIT_COLUMNS", "EXPAND_ROWS"]
    assert cand.confidence == "HIGH"


# =========================================================================
# 2. Semicolon-delimited values
# =========================================================================
def test_2_semicolon_delimited_detection():
    df = pd.DataFrame({
        "employee_id": [101, 102, 103],
        "skills": ["Python;SQL;Java", "Go;Rust", "TypeScript;React;Node;Postgres"],
    })
    canonical = create_test_canonical(df)
    detector = MultiValueDetector()
    candidates = detector.detect_candidates(canonical)

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.column_name == "skills"
    assert cand.detected_delimiter == ";"
    assert cand.affected_rows == 3
    assert cand.max_values_per_row == 4
    assert cand.confidence == "HIGH"


# =========================================================================
# 3. Pipe-delimited values
# =========================================================================
def test_3_pipe_delimited_detection():
    df = pd.DataFrame({
        "item_id": ["A1", "A2", "A3"],
        "colors": ["Red|Green|Blue", "Black|White", "Yellow"],
    })
    canonical = create_test_canonical(df)
    detector = MultiValueDetector()
    candidates = detector.detect_candidates(canonical)

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.column_name == "colors"
    assert cand.detected_delimiter == "|"
    assert cand.affected_rows == 2


# =========================================================================
# 4. Numeric comma formatting (1,250.50) is NOT falsely detected
# =========================================================================
def test_4_numeric_comma_formatting_protection():
    df = pd.DataFrame({
        "item_id": [1, 2, 3, 4, 5],
        "formatted_revenue": ["1,250.50", "1,000,000", "$2,500.00", "750.25", "10,500"],
    })
    canonical = create_test_canonical(df)
    detector = MultiValueDetector()

    # Verify detector correctly identifies thousands formatting
    is_fmt = detector.is_numeric_comma_formatting(df["formatted_revenue"])
    assert is_fmt is True

    # Candidates list must NOT contain formatted_revenue
    candidates = detector.detect_candidates(canonical)
    assert not any(c.column_name == "formatted_revenue" for c in candidates)


# =========================================================================
# 5. Split into columns
# =========================================================================
def test_5_split_into_columns():
    df = pd.DataFrame({
        "employee": ["Alice", "Bob", "Charlie"],
        "SalaryOffered_LPA": ["12,17", "20,25", "30,35"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    # Preview Split
    preview = handler.preview_split(canonical, "SalaryOffered_LPA", ",")
    assert preview.action == "SPLIT_COLUMNS"
    assert preview.affected_rows == 3
    assert preview.resulting_column_count == 3  # employee, SalaryOffered_LPA_1, SalaryOffered_LPA_2
    assert preview.generated_columns == ["SalaryOffered_LPA_1", "SalaryOffered_LPA_2"]

    # Apply Split
    cleaned_canonical, audit = handler.apply_split(canonical, "SalaryOffered_LPA", ",")
    cleaned_df = cleaned_canonical.data

    assert "SalaryOffered_LPA" not in cleaned_df.columns
    assert "SalaryOffered_LPA_1" in cleaned_df.columns
    assert "SalaryOffered_LPA_2" in cleaned_df.columns
    assert cleaned_df.loc[0, "SalaryOffered_LPA_1"] == "12"
    assert cleaned_df.loc[0, "SalaryOffered_LPA_2"] == "17"
    assert cleaned_df.loc[1, "SalaryOffered_LPA_1"] == "20"
    assert cleaned_df.loc[1, "SalaryOffered_LPA_2"] == "25"


# =========================================================================
# 6. Variable number of values (null-padded)
# =========================================================================
def test_6_variable_number_of_values():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "values": ["12,17,20", "5,10", "99"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    preview = handler.preview_split(canonical, "values", ",")
    assert preview.generated_columns == ["values_1", "values_2", "values_3"]

    cleaned_canonical, _ = handler.apply_split(canonical, "values", ",")
    cleaned_df = cleaned_canonical.data

    assert cleaned_df.loc[0, "values_1"] == "12"
    assert cleaned_df.loc[0, "values_2"] == "17"
    assert cleaned_df.loc[0, "values_3"] == "20"
    # Row 1 only has 2 values -> 3rd is None
    assert cleaned_df.loc[1, "values_1"] == "5"
    assert cleaned_df.loc[1, "values_2"] == "10"
    assert cleaned_df.loc[1, "values_3"] is None
    # Row 2 only has 1 value -> 2nd and 3rd are None
    assert cleaned_df.loc[2, "values_1"] == "99"
    assert cleaned_df.loc[2, "values_2"] is None
    assert cleaned_df.loc[2, "values_3"] is None


# =========================================================================
# 7. Generated column name collision handling
# =========================================================================
def test_7_column_name_collision():
    # Pre-existing column named "skills_1"
    df = pd.DataFrame({
        "skills": ["Python;SQL", "Java;C++"],
        "skills_1": ["Existing1", "Existing2"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    generated_names = handler._generate_collision_safe_column_names(
        list(df.columns), "skills", 2
    )
    # Must not contain duplicate names
    assert len(generated_names) == 2
    assert "skills_1" not in generated_names  # Collides with existing skills_1
    assert all(name != "skills_1" for name in generated_names)

    cleaned_canonical, _ = handler.apply_split(canonical, "skills", ";")
    cleaned_df = cleaned_canonical.data
    # Existing column preserved, new split columns added
    assert "skills_1" in cleaned_df.columns
    assert cleaned_df["skills_1"].iloc[0] == "Existing1"
    assert len(cleaned_df.columns) == 3


# =========================================================================
# 8. Expand into rows
# =========================================================================
def test_8_expand_into_rows():
    df = pd.DataFrame({
        "Customer": ["A", "B"],
        "Mobile": ["9876,8765", "9123"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    preview = handler.preview_expand(canonical, "Mobile", ",")
    assert preview.action == "EXPAND_ROWS"
    assert preview.original_row_count == 2
    assert preview.resulting_row_count == 3
    assert preview.rows_added == 1
    assert "Expanding values duplicates the other fields in affected rows." in preview.warning_message

    cleaned_canonical, audit = handler.apply_expand(canonical, "Mobile", ",")
    cleaned_df = cleaned_canonical.data

    assert len(cleaned_df) == 3
    assert list(cleaned_df["Mobile"]) == ["9876", "8765", "9123"]
    assert list(cleaned_df["Customer"]) == ["A", "A", "B"]


# =========================================================================
# 9. Row count calculation
# =========================================================================
def test_9_row_count_calculation():
    # 10 rows: 3 rows with 3 values, 2 rows with 2 values, 5 rows with 1 value
    # Expected rows: 3*3 + 2*2 + 5*1 = 9 + 4 + 5 = 18 (+8 rows)
    rows_data = ["a,b,c"] * 3 + ["d,e"] * 2 + ["f"] * 5
    df = pd.DataFrame({"col": rows_data, "num": range(10)})
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    preview = handler.preview_expand(canonical, "col", ",")
    assert preview.original_row_count == 10
    assert preview.resulting_row_count == 18
    assert preview.rows_added == 8
    assert preview.affected_rows == 5


# =========================================================================
# 10. Duplicated context columns during expansion
# =========================================================================
def test_10_duplicated_context_columns():
    df = pd.DataFrame({
        "User": ["Alice", "Bob"],
        "City": ["New York", "London"],
        "Role": ["Admin", "User"],
        "Tags": ["python;aws", "sql"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    cleaned_canonical, _ = handler.apply_expand(canonical, "Tags", ";")
    cleaned_df = cleaned_canonical.data

    assert len(cleaned_df) == 3
    # Alice is duplicated across both tags
    alice_rows = cleaned_df[cleaned_df["User"] == "Alice"]
    assert len(alice_rows) == 2
    assert list(alice_rows["City"]) == ["New York", "New York"]
    assert list(alice_rows["Role"]) == ["Admin", "Admin"]
    assert list(alice_rows["Tags"]) == ["python", "aws"]


# =========================================================================
# 11. Keep unchanged
# =========================================================================
def test_11_keep_unchanged():
    df = pd.DataFrame({
        "id": [1, 2],
        "raw_codes": ["100,200", "300,400"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    preview = handler.preview_keep(canonical, "raw_codes", ",")
    assert preview.action == "KEEP"
    assert preview.resulting_row_count == 2
    assert preview.resulting_column_count == 2
    assert preview.rows_added == 0

    cleaned_canonical, audit = handler.apply_keep(canonical, "raw_codes", ",")
    pd.testing.assert_frame_equal(cleaned_canonical.data, canonical.data)
    assert audit["action"] == "KEEP"


# =========================================================================
# 12. Custom delimiter override
# =========================================================================
def test_12_custom_delimiter():
    df = pd.DataFrame({
        "id": [1, 2],
        "multi_slash": ["A/B/C", "D/E"],
    })
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    # Override delimiter to '/'
    preview = handler.preview(canonical, "multi_slash", "SPLIT_COLUMNS", delimiter="/")
    assert preview.generated_columns == ["multi_slash_1", "multi_slash_2", "multi_slash_3"]
    assert preview.affected_rows == 2

    cleaned_canonical, _ = handler.apply(canonical, "multi_slash", "SPLIT_COLUMNS", delimiter="/")
    assert "multi_slash_1" in cleaned_canonical.data.columns
    assert cleaned_canonical.data.loc[0, "multi_slash_1"] == "A"
    assert cleaned_canonical.data.loc[0, "multi_slash_2"] == "B"
    assert cleaned_canonical.data.loc[0, "multi_slash_3"] == "C"


# =========================================================================
# 13. Invalid column validation
# =========================================================================
def test_13_invalid_column():
    df = pd.DataFrame({"colA": [1, 2]})
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    with pytest.raises(MultiValueExecutionError) as exc:
        handler.preview_split(canonical, "non_existent_column", ",")
    assert "does not exist in dataset" in str(exc.value)

    with pytest.raises(MultiValueExecutionError) as exc2:
        handler.apply_expand(canonical, "non_existent_column", ",")
    assert "does not exist in dataset" in str(exc2.value)


# =========================================================================
# 14. Invalid delimiter validation
# =========================================================================
def test_14_invalid_delimiter():
    df = pd.DataFrame({"colA": ["1,2", "3,4"]})
    canonical = create_test_canonical(df)
    handler = MultiValueHandler()

    with pytest.raises(MultiValueExecutionError) as exc:
        handler.preview_split(canonical, "colA", "")
    assert "Delimiter must be a valid non-empty string" in str(exc.value)

    with pytest.raises(MultiValueExecutionError) as exc2:
        handler.apply(canonical, "colA", "SPLIT_COLUMNS", delimiter=None)
    assert "Delimiter must be a valid non-empty string" in str(exc2.value)


# =========================================================================
# 15. Raw dataset remains unchanged after preview
# =========================================================================
def test_15_raw_dataset_unchanged_after_preview():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "tags": ["a,b", "c,d", "e,f"],
    })
    canonical = create_test_canonical(df)
    raw_df_copy = canonical.data.copy(deep=True)

    handler = MultiValueHandler()
    _ = handler.preview_split(canonical, "tags", ",")
    _ = handler.preview_expand(canonical, "tags", ",")
    _ = handler.preview_keep(canonical, "tags", ",")

    pd.testing.assert_frame_equal(canonical.data, raw_df_copy)
    assert list(canonical.data.columns) == ["id", "tags"]
    assert len(canonical.data) == 3


# =========================================================================
# 16. Raw dataset remains unchanged after apply
# =========================================================================
def test_16_raw_dataset_unchanged_after_apply():
    df = pd.DataFrame({
        "id": [1, 2],
        "tags": ["a,b", "c,d"],
    })
    canonical = create_test_canonical(df)
    raw_df_copy = canonical.data.copy(deep=True)

    handler = MultiValueHandler()
    cleaned_canonical, _ = handler.apply_split(canonical, "tags", ",")
    cleaned_canonical_expand, _ = handler.apply_expand(canonical, "tags", ",")

    # Original canonical data must be 100% identical to initial copy
    pd.testing.assert_frame_equal(canonical.data, raw_df_copy)
    assert "tags" in canonical.data.columns
    assert len(canonical.data) == 2

    # Cleaned canonicals must have modified structure
    assert "tags_1" in cleaned_canonical.data.columns
    assert len(cleaned_canonical_expand.data) == 4


# =========================================================================
# 17. Deterministic repeated execution & FastAPI endpoint validation
# =========================================================================
def test_17_deterministic_repeated_execution_and_api(test_client):
    df = pd.DataFrame({
        "user_id": [1, 2, 3],
        "phone_numbers": ["9876543210,8765432109", "9123456780,9876543211", "9988776655"],
    })
    canonical = create_test_canonical(df, dataset_id="ds_multivalue_endpoint_test")
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=None,
        semantic_profile=None,
        readiness=None,
    )
    session_store.save(record)

    handler = MultiValueHandler()
    res1, _ = handler.apply_split(canonical, "phone_numbers", ",")
    res2, _ = handler.apply_split(canonical, "phone_numbers", ",")
    pd.testing.assert_frame_equal(res1.data, res2.data)

    # Test Candidate Endpoint
    resp = test_client.get(f"/api/datasets/{canonical.metadata.dataset_id}/cleaning/multivalue/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates_count"] >= 1
    assert any(c["column_name"] == "phone_numbers" for c in data["candidates"])

    # Test Preview Endpoint
    prev_resp = test_client.post(
        f"/api/datasets/{canonical.metadata.dataset_id}/cleaning/multivalue/preview",
        json={"column_name": "phone_numbers", "action": "SPLIT_COLUMNS", "delimiter": ","},
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["action"] == "SPLIT_COLUMNS"
    assert prev_data["generated_columns"] == ["phone_numbers_1", "phone_numbers_2"]

    # Test Apply Endpoint
    apply_resp = test_client.post(
        f"/api/datasets/{canonical.metadata.dataset_id}/cleaning/multivalue/apply",
        json={"column_name": "phone_numbers", "action": "SPLIT_COLUMNS", "delimiter": ","},
    )
    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()
    assert apply_data["status"] == "SUCCESS"
    assert apply_data["cleaned_column_count"] == 3  # user_id, phone_numbers_1, phone_numbers_2

    # Verify session store cleaned dataset is updated and raw dataset is unchanged
    updated_rec = session_store.get(canonical.metadata.dataset_id)
    assert updated_rec.cleaned_dataset is not None
    assert "phone_numbers_1" in updated_rec.cleaned_dataset.data.columns
    assert "phone_numbers" in updated_rec.dataset.data.columns
