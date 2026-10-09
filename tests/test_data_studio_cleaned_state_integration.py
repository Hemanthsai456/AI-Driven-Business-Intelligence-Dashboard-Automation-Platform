"""Targeted Integration Test Suite for Cleaned Dataset State, Registration, and Download (Part 6.4 Bug Fix).

Tests all 16 required invariant scenarios:
1. cleaned state creation
2. cumulative datatype transformation
3. cumulative multivalue split
4. cumulative column drop
5. cumulative row filtering
6. cumulative duplicate removal
7. registration uses cleaned state
8. CSV download uses cleaned state
9. XLSX download uses cleaned state
10. multivalue split survives registration
11. multivalue split survives CSV download
12. multivalue split survives XLSX download
13. cumulative transformations survive registration
14. cumulative transformations survive CSV
15. cumulative transformations survive XLSX
16. raw dataset remains unchanged
"""

import io
import copy
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.loaders import CSVLoader
from ingestion.models import CanonicalDataset, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from intelligence.schema_validator import assess_readiness


@pytest.fixture
def client():
    return TestClient(app)


def create_and_store_session(df: pd.DataFrame, dataset_id: str, name: str = "test_data.csv") -> DatasetSessionRecord:
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
    canonical = CanonicalDataset(metadata=meta, data=df.copy(deep=True))
    profile = profile_dataset(canonical)
    semantic_profile = analyze_semantics(canonical, profile=profile)
    readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic_profile)
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=semantic_profile,
        readiness=readiness,
        cleaning_report=None,
    )
    session_store.save(record)
    return record


# -----------------------------------------------------------------------------
# 1. Cleaned State Creation
# -----------------------------------------------------------------------------
def test_cleaned_state_creation(client):
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [10.0, 20.0, 30.0],
    })
    dataset_id = "ds_clean_state_01"
    record = create_and_store_session(df, dataset_id)

    assert record.cleaned_dataset is None

    # Drop column B
    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["B"]},
    )
    assert res.status_code == 200
    assert record.cleaned_dataset is not None
    assert list(record.cleaned_dataset.data.columns) == ["A", "C"]
    assert list(record.dataset.data.columns) == ["A", "B", "C"]


# -----------------------------------------------------------------------------
# 2. Cumulative Datatype Transformation
# -----------------------------------------------------------------------------
def test_cumulative_datatype_transformation(client):
    df = pd.DataFrame({
        "ID": ["1", "2", "3"],
        "Score": ["100.5", "200.5", "300.5"],
    })
    dataset_id = "ds_clean_state_02"
    record = create_and_store_session(df, dataset_id)

    # First apply convert numeric on Score
    res1 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={
            "selected_recommendation_ids": [],
            "custom_transformations": [
                {"column_name": "Score", "operation": "CONVERT_NUMERIC"}
            ],
        },
    )
    assert res1.status_code == 200
    assert record.cleaned_dataset is not None
    assert pd.api.types.is_numeric_dtype(record.cleaned_dataset.data["Score"])

    # Second apply: convert ID to integer
    res2 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={
            "selected_recommendation_ids": [],
            "custom_transformations": [
                {"column_name": "ID", "operation": "CONVERT_INTEGER"}
            ],
        },
    )
    assert res2.status_code == 200
    assert pd.api.types.is_numeric_dtype(record.cleaned_dataset.data["Score"])
    assert pd.api.types.is_integer_dtype(record.cleaned_dataset.data["ID"])


# -----------------------------------------------------------------------------
# 3. Cumulative Multi-Value Split
# -----------------------------------------------------------------------------
def test_cumulative_multivalue_split(client):
    df = pd.DataFrame({
        "Customer": ["A", "B"],
        "Salary": ["12,17", "15"],
    })
    dataset_id = "ds_clean_state_03"
    record = create_and_store_session(df, dataset_id)

    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={
            "column_name": "Salary",
            "action": "SPLIT_COLUMNS",
            "delimiter": ",",
        },
    )
    assert res.status_code == 200
    assert record.cleaned_dataset is not None
    assert "Salary_1" in record.cleaned_dataset.data.columns
    assert "Salary_2" in record.cleaned_dataset.data.columns
    assert "Salary" not in record.cleaned_dataset.data.columns


# -----------------------------------------------------------------------------
# 4. Cumulative Column Drop
# -----------------------------------------------------------------------------
def test_cumulative_column_drop(client):
    df = pd.DataFrame({
        "A": [1, 2],
        "B": [3, 4],
        "C": [5, 6],
    })
    dataset_id = "ds_clean_state_04"
    record = create_and_store_session(df, dataset_id)

    # Drop B
    res1 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["B"]},
    )
    assert res1.status_code == 200
    assert list(record.cleaned_dataset.data.columns) == ["A", "C"]

    # Then drop C
    res2 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["C"]},
    )
    assert res2.status_code == 200
    assert list(record.cleaned_dataset.data.columns) == ["A"]
    # Raw remains A, B, C
    assert list(record.dataset.data.columns) == ["A", "B", "C"]


# -----------------------------------------------------------------------------
# 5. Cumulative Row Filtering
# -----------------------------------------------------------------------------
def test_cumulative_row_filtering(client):
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "status": ["ACTIVE", "INACTIVE", "ACTIVE", "INACTIVE", "ACTIVE"],
        "age": [25, 35, 45, 22, 19],
    })
    dataset_id = "ds_clean_state_05"
    record = create_and_store_session(df, dataset_id)

    # Filter out INACTIVE
    res1 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={
            "conditions": [{"column": "status", "operator": "equals", "value": "INACTIVE"}],
            "logical_operator": "AND",
        },
    )
    assert res1.status_code == 200
    assert len(record.cleaned_dataset.data) == 3

    # Then filter out age < 20 (Eve)
    res2 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={
            "conditions": [{"column": "age", "operator": "less_than", "value": 20}],
            "logical_operator": "AND",
        },
    )
    assert res2.status_code == 200
    assert len(record.cleaned_dataset.data) == 2
    assert list(record.cleaned_dataset.data["name"]) == ["Alice", "Charlie"]


# -----------------------------------------------------------------------------
# 6. Cumulative Duplicate Removal
# -----------------------------------------------------------------------------
def test_cumulative_duplicate_removal(client):
    df = pd.DataFrame({
        "id": [1, 1, 2, 3, 3],
        "val": ["A", "A", "B", "C", "C"],
    })
    dataset_id = "ds_clean_state_06"
    record = create_and_store_session(df, dataset_id)

    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )
    assert res.status_code == 200
    assert len(record.cleaned_dataset.data) == 3
    assert len(record.dataset.data) == 5


# -----------------------------------------------------------------------------
# 7. Registration Uses Cleaned State
# -----------------------------------------------------------------------------
def test_registration_uses_cleaned_state(client):
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [10, 20, 30],
    })
    dataset_id = "ds_clean_state_07"
    record = create_and_store_session(df, dataset_id)

    # Drop column B
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["B"]},
    )

    # Register
    reg_res = client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    new_id = reg_data["dataset_id"]

    # Verify newly registered dataset
    reg_record = session_store.get(new_id)
    assert reg_record is not None
    assert list(reg_record.dataset.data.columns) == ["A", "C"]
    assert "B" not in reg_record.dataset.data.columns


# -----------------------------------------------------------------------------
# 8. CSV Download Uses Cleaned State
# -----------------------------------------------------------------------------
def test_csv_download_uses_cleaned_state(client):
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [10, 20, 30],
    })
    dataset_id = "ds_clean_state_08"
    record = create_and_store_session(df, dataset_id)

    # Drop column B
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["B"]},
    )

    # Download CSV from parent dataset
    dl_res = client.get(f"/api/datasets/{dataset_id}/download?format=csv")
    assert dl_res.status_code == 200
    downloaded_df = pd.read_csv(io.BytesIO(dl_res.content))
    assert list(downloaded_df.columns) == ["A", "C"]
    assert "B" not in downloaded_df.columns


# -----------------------------------------------------------------------------
# 9. XLSX Download Uses Cleaned State
# -----------------------------------------------------------------------------
def test_xlsx_download_uses_cleaned_state(client):
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [10, 20, 30],
    })
    dataset_id = "ds_clean_state_09"
    record = create_and_store_session(df, dataset_id)

    # Drop column B
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["B"]},
    )

    # Download XLSX from parent dataset
    dl_res = client.get(f"/api/datasets/{dataset_id}/download?format=xlsx")
    assert dl_res.status_code == 200
    downloaded_df = pd.read_excel(io.BytesIO(dl_res.content))
    assert list(downloaded_df.columns) == ["A", "C"]
    assert "B" not in downloaded_df.columns


# -----------------------------------------------------------------------------
# 10. Multi-Value Split Survives Registration
# -----------------------------------------------------------------------------
def test_multivalue_split_survives_registration(client):
    df = pd.DataFrame({
        "Customer": ["A", "B"],
        "Salary": ["12,17", "15"],
    })
    dataset_id = "ds_clean_state_10"
    record = create_and_store_session(df, dataset_id)

    # Apply split
    split_res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={
            "column_name": "Salary",
            "action": "SPLIT_COLUMNS",
            "delimiter": ",",
        },
    )
    assert split_res.status_code == 200

    # Register
    reg_res = client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    assert reg_res.status_code == 200
    new_id = reg_res.json()["dataset_id"]

    reg_record = session_store.get(new_id)
    assert reg_record is not None
    assert "Salary_1" in reg_record.dataset.data.columns
    assert "Salary_2" in reg_record.dataset.data.columns
    assert "Salary" not in reg_record.dataset.data.columns
    assert reg_record.dataset.data.iloc[0]["Salary_1"] == "12"
    assert reg_record.dataset.data.iloc[0]["Salary_2"] == "17"


# -----------------------------------------------------------------------------
# 11. Multi-Value Split Survives CSV Download
# -----------------------------------------------------------------------------
def test_multivalue_split_survives_csv_download(client):
    df = pd.DataFrame({
        "Customer": ["A", "B"],
        "Salary": ["12,17", "15"],
    })
    dataset_id = "ds_clean_state_11"
    record = create_and_store_session(df, dataset_id)

    # Apply split
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={
            "column_name": "Salary",
            "action": "SPLIT_COLUMNS",
            "delimiter": ",",
        },
    )

    dl_res = client.get(f"/api/datasets/{dataset_id}/download?format=csv")
    assert dl_res.status_code == 200
    downloaded_df = pd.read_csv(io.BytesIO(dl_res.content))
    assert "Salary_1" in downloaded_df.columns
    assert "Salary_2" in downloaded_df.columns
    assert "Salary" not in downloaded_df.columns


# -----------------------------------------------------------------------------
# 12. Multi-Value Split Survives XLSX Download
# -----------------------------------------------------------------------------
def test_multivalue_split_survives_xlsx_download(client):
    df = pd.DataFrame({
        "Customer": ["A", "B"],
        "Salary": ["12,17", "15"],
    })
    dataset_id = "ds_clean_state_12"
    record = create_and_store_session(df, dataset_id)

    # Apply split
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={
            "column_name": "Salary",
            "action": "SPLIT_COLUMNS",
            "delimiter": ",",
        },
    )

    dl_res = client.get(f"/api/datasets/{dataset_id}/download?format=xlsx")
    assert dl_res.status_code == 200
    downloaded_df = pd.read_excel(io.BytesIO(dl_res.content))
    assert "Salary_1" in downloaded_df.columns
    assert "Salary_2" in downloaded_df.columns
    assert "Salary" not in downloaded_df.columns


# -----------------------------------------------------------------------------
# 13. Cumulative Transformations Survive Registration
# -----------------------------------------------------------------------------
def test_cumulative_transformations_survive_registration(client):
    # Sequence: Datatype transformation -> Multi-value split -> Column drop -> Row filtering -> Duplicate removal
    raw_df = pd.DataFrame({
        "ID": ["101", "102", "103", "103", "104"],
        "Tags": ["python,sql", "sql,java", "c++,rust", "c++,rust", "go"],
        "Score": ["85.5", "90.0", "70.5", "70.5", "60.0"],
        "Extra": ["drop_me_1", "drop_me_2", "drop_me_3", "drop_me_4", "drop_me_5"],
        "Status": ["ACTIVE", "ACTIVE", "INACTIVE", "INACTIVE", "ACTIVE"],
    })
    dataset_id = "ds_clean_state_13"
    record = create_and_store_session(raw_df, dataset_id)

    # 1. Datatype transformation: Score -> NUMERIC
    res1 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={
            "selected_recommendation_ids": [],
            "custom_transformations": [
                {"column_name": "Score", "operation": "CONVERT_NUMERIC"}
            ],
        },
    )
    assert res1.status_code == 200

    # 2. Multi-value split: Tags -> Tags_1, Tags_2
    res2 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={"column_name": "Tags", "action": "SPLIT_COLUMNS", "delimiter": ","},
    )
    assert res2.status_code == 200

    # 3. Column drop: drop "Extra"
    res3 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Extra"]},
    )
    assert res3.status_code == 200

    # 4. Row filtering: filter out "INACTIVE"
    res4 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={
            "conditions": [{"column": "Status", "operator": "equals", "value": "INACTIVE"}],
            "logical_operator": "AND",
        },
    )
    assert res4.status_code == 200

    # 5. Duplicate removal
    res5 = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )
    assert res5.status_code == 200

    # Verify cumulative state before registration
    expected_cols = ["ID", "Score", "Status", "Tags_1", "Tags_2"]
    assert set(record.cleaned_dataset.data.columns) == set(expected_cols)
    assert len(record.cleaned_dataset.data) == 3

    # Register
    reg_res = client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    assert reg_res.status_code == 200
    new_id = reg_res.json()["dataset_id"]

    reg_record = session_store.get(new_id)
    assert reg_record is not None
    assert set(reg_record.dataset.data.columns) == set(expected_cols)
    assert "Extra" not in reg_record.dataset.data.columns
    assert "Tags" not in reg_record.dataset.data.columns
    assert len(reg_record.dataset.data) == 3
    assert pd.api.types.is_numeric_dtype(reg_record.dataset.data["Score"])


# -----------------------------------------------------------------------------
# 14. Cumulative Transformations Survive CSV Download
# -----------------------------------------------------------------------------
def test_cumulative_transformations_survive_csv(client):
    raw_df = pd.DataFrame({
        "ID": ["101", "102", "103", "103", "104"],
        "Tags": ["python,sql", "sql,java", "c++,rust", "c++,rust", "go"],
        "Score": ["85.5", "90.0", "70.5", "70.5", "60.0"],
        "Extra": ["drop1", "drop2", "drop3", "drop4", "drop5"],
        "Status": ["ACTIVE", "ACTIVE", "INACTIVE", "INACTIVE", "ACTIVE"],
    })
    dataset_id = "ds_clean_state_14"
    record = create_and_store_session(raw_df, dataset_id)

    # Apply chain
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={"selected_recommendation_ids": [], "custom_transformations": [{"column_name": "Score", "operation": "CONVERT_NUMERIC"}]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={"column_name": "Tags", "action": "SPLIT_COLUMNS", "delimiter": ","},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Extra"]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={"conditions": [{"column": "Status", "operator": "equals", "value": "INACTIVE"}], "logical_operator": "AND"},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )

    # Download CSV
    dl_res = client.get(f"/api/datasets/{dataset_id}/download?format=csv")
    assert dl_res.status_code == 200
    downloaded_df = pd.read_csv(io.BytesIO(dl_res.content))
    assert set(downloaded_df.columns) == {"ID", "Score", "Status", "Tags_1", "Tags_2"}
    assert len(downloaded_df) == 3


# -----------------------------------------------------------------------------
# 15. Cumulative Transformations Survive XLSX Download
# -----------------------------------------------------------------------------
def test_cumulative_transformations_survive_xlsx(client):
    raw_df = pd.DataFrame({
        "ID": ["101", "102", "103", "103", "104"],
        "Tags": ["python,sql", "sql,java", "c++,rust", "c++,rust", "go"],
        "Score": ["85.5", "90.0", "70.5", "70.5", "60.0"],
        "Extra": ["drop1", "drop2", "drop3", "drop4", "drop5"],
        "Status": ["ACTIVE", "ACTIVE", "INACTIVE", "INACTIVE", "ACTIVE"],
    })
    dataset_id = "ds_clean_state_15"
    record = create_and_store_session(raw_df, dataset_id)

    # Apply chain
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={"selected_recommendation_ids": [], "custom_transformations": [{"column_name": "Score", "operation": "CONVERT_NUMERIC"}]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={"column_name": "Tags", "action": "SPLIT_COLUMNS", "delimiter": ","},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Extra"]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={"conditions": [{"column": "Status", "operator": "equals", "value": "INACTIVE"}], "logical_operator": "AND"},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )

    # Download XLSX
    dl_res = client.get(f"/api/datasets/{dataset_id}/download?format=xlsx")
    assert dl_res.status_code == 200
    downloaded_df = pd.read_excel(io.BytesIO(dl_res.content))
    assert set(downloaded_df.columns) == {"ID", "Score", "Status", "Tags_1", "Tags_2"}
    assert len(downloaded_df) == 3


# -----------------------------------------------------------------------------
# 16. Raw Dataset Remains Strictly Unchanged
# -----------------------------------------------------------------------------
def test_raw_dataset_remains_unchanged(client):
    raw_df = pd.DataFrame({
        "ID": ["101", "102", "103", "103", "104"],
        "Tags": ["python,sql", "sql,java", "c++,rust", "c++,rust", "go"],
        "Score": ["85.5", "90.0", "70.5", "70.5", "60.0"],
        "Extra": ["drop1", "drop2", "drop3", "drop4", "drop5"],
        "Status": ["ACTIVE", "ACTIVE", "INACTIVE", "INACTIVE", "ACTIVE"],
    })
    dataset_id = "ds_clean_state_16"
    record = create_and_store_session(raw_df, dataset_id)

    # Execute full chain
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={"selected_recommendation_ids": [], "custom_transformations": [{"column_name": "Score", "operation": "CONVERT_NUMERIC"}]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={"column_name": "Tags", "action": "SPLIT_COLUMNS", "delimiter": ","},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Extra"]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={"conditions": [{"column": "Status", "operator": "equals", "value": "INACTIVE"}], "logical_operator": "AND"},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )
    client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    client.get(f"/api/datasets/{dataset_id}/download?format=csv")
    client.get(f"/api/datasets/{dataset_id}/download?format=xlsx")

    # Invariant assertion: record.dataset is strictly equal to raw_df
    pd.testing.assert_frame_equal(record.dataset.data, raw_df)
