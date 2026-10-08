"""Targeted Integration Test Suite for Data Studio Cleaned State / Dataset ID Synchronization.

Validates all 15 required test scenarios:
1. Column drop updates cleaned state
2. Raw state remains unchanged (immutability)
3. Metadata reflects cleaned schema
4. Profiling reflects cleaned schema
5. Semantic profile reflects cleaned schema
6. Structural recommendations reflect cleaned schema
7. Datatype transformation works after column drop
8. Multivalue transformation works after column drop
9. Row filtering works after column drop
10. Registration uses final cleaned schema
11. CSV download uses final cleaned schema
12. XLSX download uses final cleaned schema
13. Current session does not switch to registered dataset
14. Stale deleted column cannot be selected / produces validation error if attempted
15. Cleaned dataset ID remains valid for current session (no fake temporary unregistered IDs)
"""

import io
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


def create_and_store_user_scenario_session(dataset_id: str = "ds_user_placement_test") -> DatasetSessionRecord:
    """Creates a session with the exact 8 columns described by the user."""
    df = pd.DataFrame({
        "S. No": [1, 2, 3, 4],
        "Roll-No": ["101", "102", "103", "104"],
        "Student Name": ["Alice Smith", "Bob Jones", "Charlie Brown", "Diana Prince"],
        "Company Name": ["Acme Corp", "Tech Solutions", "Global Inno", "Acme Corp"],
        "LPA/CTC": ["12.5", "15.0", "9.8", "18.2"],
        "Pg.No": [1, 1, 2, 2],
        "On Campus/Off Campus": ["On Campus", "Off Campus", "On Campus", "Off Campus"],
        "Unnamed: 7": [None, None, None, None],
    })
    loader = CSVLoader()
    schema = loader.extract_column_metadata(df)
    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name="placement_data.csv",
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


def create_and_store_session_df(df: pd.DataFrame, dataset_id: str) -> DatasetSessionRecord:
    loader = CSVLoader()
    schema = loader.extract_column_metadata(df)
    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name="test_data.csv",
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
# 1. Column drop updates cleaned state
# -----------------------------------------------------------------------------
def test_1_column_drop_updates_cleaned_state(client):
    dataset_id = "ds_test_1_drop_cleaned"
    record = create_and_store_user_scenario_session(dataset_id)

    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    assert res.status_code == 200
    assert record.cleaned_dataset is not None
    assert list(record.cleaned_dataset.data.columns) == [
        "Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"
    ]


# -----------------------------------------------------------------------------
# 2. Raw state remains unchanged
# -----------------------------------------------------------------------------
def test_2_raw_state_remains_unchanged(client):
    dataset_id = "ds_test_2_raw_immutable"
    record = create_and_store_user_scenario_session(dataset_id)

    raw_cols = [
        "S. No", "Roll-No", "Student Name", "Company Name",
        "LPA/CTC", "Pg.No", "On Campus/Off Campus", "Unnamed: 7"
    ]
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    assert list(record.dataset.data.columns) == raw_cols
    assert len(record.dataset.metadata.schema) == 8


# -----------------------------------------------------------------------------
# 3. Metadata reflects cleaned schema
# -----------------------------------------------------------------------------
def test_3_metadata_reflects_cleaned_schema(client):
    dataset_id = "ds_test_3_metadata_sync"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    meta_res = client.get(f"/api/datasets/{dataset_id}")
    assert meta_res.status_code == 200
    meta = meta_res.json()
    assert meta["column_count"] == 5
    col_names = [c["original_name"] if isinstance(c, dict) else c for c in meta["columns"]]
    assert col_names == ["Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"]
    assert "S. No" not in col_names


# -----------------------------------------------------------------------------
# 4. Profiling reflects cleaned schema
# -----------------------------------------------------------------------------
def test_4_profiling_reflects_cleaned_schema(client):
    dataset_id = "ds_test_4_profiling_sync"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    prof_res = client.get(f"/api/datasets/{dataset_id}/profile")
    assert prof_res.status_code == 200
    prof = prof_res.json()
    prof_cols = list(prof.get("column_statistics", {}).keys())
    assert prof_cols == ["Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"]


# -----------------------------------------------------------------------------
# 5. Semantic profile reflects cleaned schema
# -----------------------------------------------------------------------------
def test_5_semantic_profile_reflects_cleaned_schema(client):
    dataset_id = "ds_test_5_semantic_sync"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    sem_res = client.get(f"/api/datasets/{dataset_id}/semantic-analysis")
    assert sem_res.status_code == 200
    sem = sem_res.json()
    sem_cols = list(sem.get("column_evidences", {}).keys())
    assert sem_cols == ["Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"]


# -----------------------------------------------------------------------------
# 6. Structural recommendations reflect cleaned schema
# -----------------------------------------------------------------------------
def test_6_structural_recommendations_reflect_cleaned_schema(client):
    dataset_id = "ds_test_6_recs_sync"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    struct_res = client.get(f"/api/datasets/{dataset_id}/cleaning/structural/recommendations")
    assert struct_res.status_code == 200
    struct_data = struct_res.json()
    recs = struct_data.get("recommendations", [])
    rec_cols = [r["column_name"] for r in recs]
    assert "S. No" not in rec_cols
    assert "Pg.No" not in rec_cols
    assert "Unnamed: 7" not in rec_cols


# -----------------------------------------------------------------------------
# 7. Datatype transformation works after column drop
# -----------------------------------------------------------------------------
def test_7_datatype_transformation_after_column_drop(client):
    dataset_id = "ds_test_7_dtype_after_drop"
    record = create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={
            "recommendation_ids": [],
            "custom_transformations": [
                {
                    "column_name": "LPA/CTC",
                    "operation": "CONVERT_FLOAT",
                    "source": "USER",
                }
            ],
        },
    )
    assert res.status_code == 200
    assert pd.api.types.is_numeric_dtype(record.cleaned_dataset.data["LPA/CTC"])


# -----------------------------------------------------------------------------
# 8. Multivalue transformation works after column drop
# -----------------------------------------------------------------------------
def test_8_multivalue_transformation_after_column_drop(client):
    df = pd.DataFrame({
        "S. No": [1, 2, 3],
        "Roll-No": ["101", "102", "103"],
        "Skills": ["Python,SQL", "Java,C++", "Python,Go"],
        "Unnamed: 7": [None, None, None],
    })
    dataset_id = "ds_test_8_mv_after_drop"
    record = create_and_store_session_df(df, dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Unnamed: 7"]},
    )
    mv_res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/multivalue/apply",
        json={
            "column_name": "Skills",
            "action": "SPLIT_COLUMNS",
            "delimiter": ",",
        },
    )
    assert mv_res.status_code == 200
    assert list(record.cleaned_dataset.data.columns) == ["Roll-No", "Skills_1", "Skills_2"]


# -----------------------------------------------------------------------------
# 9. Row filtering works after column drop
# -----------------------------------------------------------------------------
def test_9_row_filtering_after_column_drop(client):
    dataset_id = "ds_test_9_filter_after_drop"
    record = create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
        json={
            "conditions": [{"column": "On Campus/Off Campus", "operator": "equals", "value": "On Campus"}],
            "logical_operator": "AND",
        },
    )
    assert res.status_code == 200
    assert len(record.cleaned_dataset.data) == 2
    assert list(record.cleaned_dataset.data.columns) == [
        "Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"
    ]


# -----------------------------------------------------------------------------
# 10. Registration uses final cleaned schema
# -----------------------------------------------------------------------------
def test_10_registration_uses_final_cleaned_schema(client):
    dataset_id = "ds_test_10_reg_schema"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    reg_res = client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    new_id = reg_data["dataset_id"]
    reg_record = session_store.get(new_id)
    assert reg_record is not None
    assert list(reg_record.dataset.data.columns) == [
        "Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"
    ]


# -----------------------------------------------------------------------------
# 11. CSV download uses final cleaned schema
# -----------------------------------------------------------------------------
def test_11_csv_download_uses_final_cleaned_schema(client):
    dataset_id = "ds_test_11_csv_download"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    res = client.get(f"/api/datasets/{dataset_id}/download?format=csv")
    assert res.status_code == 200
    df = pd.read_csv(io.BytesIO(res.content))
    assert list(df.columns) == [
        "Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"
    ]


# -----------------------------------------------------------------------------
# 12. XLSX download uses final cleaned schema
# -----------------------------------------------------------------------------
def test_12_xlsx_download_uses_final_cleaned_schema(client):
    dataset_id = "ds_test_12_xlsx_download"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    res = client.get(f"/api/datasets/{dataset_id}/download?format=xlsx")
    assert res.status_code == 200
    df = pd.read_excel(io.BytesIO(res.content))
    assert list(df.columns) == [
        "Roll-No", "Student Name", "Company Name", "LPA/CTC", "On Campus/Off Campus"
    ]


# -----------------------------------------------------------------------------
# 13. Current session does not switch to registered dataset
# -----------------------------------------------------------------------------
def test_13_current_session_does_not_switch_to_registered_dataset(client):
    dataset_id = "ds_test_13_session_separate"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    reg_res = client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    assert reg_res.status_code == 200
    new_id = reg_res.json()["dataset_id"]

    # Source session dataset_id MUST still exist in session_store with original ID
    source_record = session_store.get(dataset_id)
    assert source_record is not None
    assert source_record.dataset.metadata.dataset_id == dataset_id
    assert source_record.dataset.metadata.dataset_id != new_id


# -----------------------------------------------------------------------------
# 14. Stale deleted column cannot be selected
# -----------------------------------------------------------------------------
def test_14_stale_deleted_column_cannot_be_selected(client):
    dataset_id = "ds_test_14_stale_col_rejection"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No"]},
    )
    res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/apply",
        json={
            "recommendation_ids": [],
            "custom_transformations": [
                {
                    "column_name": "S. No",
                    "operation": "CONVERT_NUMERIC",
                    "source": "USER",
                }
            ],
        },
    )
    assert res.status_code in [400, 422, 500] or (res.status_code == 200 and not res.json().get("success", True))


# -----------------------------------------------------------------------------
# 15. Cleaned dataset ID remains valid for current session
# -----------------------------------------------------------------------------
def test_15_cleaned_dataset_id_remains_valid_for_session(client):
    dataset_id = "ds_test_15_valid_session_id"
    create_and_store_user_scenario_session(dataset_id)

    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["S. No", "Pg.No", "Unnamed: 7"]},
    )
    plan_res = client.get(f"/api/datasets/{dataset_id}/cleaning-plan")
    assert plan_res.status_code == 200
    assert plan_res.json()["dataset_id"] == dataset_id
    assert not plan_res.json()["dataset_id"].endswith("_cleaned")

    read_res = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert read_res.status_code == 200

    eda_res = client.get(f"/api/datasets/{dataset_id}/eda")
    assert eda_res.status_code == 200

    qual_res = client.get(f"/api/datasets/{dataset_id}/quality-assessment")
    assert qual_res.status_code == 200
