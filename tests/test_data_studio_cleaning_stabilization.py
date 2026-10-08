"""Targeted regression test suite for Part 6.5 — Cleaning State / Performance / Semantic Override Stabilization.

Covers:
1. Opening/loading cleaning recommendations does not create cleaned_dataset.
2. Existing cleaned_dataset is reused.
3. Apply creates/updates cleaned_dataset.
4. Repeated page-load equivalent API calls do not regenerate cleaned state.
5. Semantic role preview does not mutate state.
6. Semantic role apply persists override.
7. Effective role uses user override.
8. User override survives subsequent cleaning operations.
9. User override survives registration.
10. Raw dataset remains strictly unchanged.
11. Cleaning plan generation does not execute transformations.
"""

import copy
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.loaders import CSVLoader
from ingestion.models import CanonicalDataset, ColumnRole, DatasetMetadata
from intelligence.profiler import DataProfiler
from intelligence.semantic_analyzer import SemanticAnalyzer
from intelligence.schema_validator import assess_readiness


@pytest.fixture
def client():
    return TestClient(app)


def build_test_record(dataset_id: str = "ds_stabilization_test") -> DatasetSessionRecord:
    """Construct a representative dataset session record with 1,000 rows and realistic columns."""
    df = pd.DataFrame({
        "S. No": list(range(1, 1001)),
        "Roll-No": [f"RN-{1000 + i}" for i in range(1000)],
        "Student Name": [f"Student {i}" for i in range(1000)],
        "Company Name": [f"Company {i % 20}" for i in range(1000)],
        "LPA/CTC": [5.5 + (i % 30) * 0.5 for i in range(1000)],
        "Pg.No": [1 + (i % 50) for i in range(1000)],
        "On Campus/Off Campus": ["On Campus" if i % 2 == 0 else "Off Campus" for i in range(1000)],
        "Unnamed: 7": [None] * 1000,
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
    canonical = CanonicalDataset(metadata=meta, data=df)

    profiler = DataProfiler()
    profile = profiler.profile(canonical, attach=True)

    analyzer = SemanticAnalyzer()
    semantic_profile = analyzer.analyze(canonical, profile=profile, apply_roles=True)

    readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic_profile)

    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=semantic_profile,
        readiness=readiness,
    )
    session_store.save(record)
    return record


# -----------------------------------------------------------------------------
# Test 1: Opening/loading cleaning recommendations does not create cleaned_dataset
# -----------------------------------------------------------------------------
def test_loading_cleaning_recommendations_does_not_create_cleaned_dataset(client):
    dataset_id = "ds_stab_test_1"
    record = build_test_record(dataset_id)
    assert record.cleaned_dataset is None

    # Simulate opening the Cleaning tab: fetch recommendations, plan, multi-value candidates
    res_plan = client.get(f"/api/datasets/{dataset_id}/cleaning-plan")
    assert res_plan.status_code == 200

    res_mv = client.get(f"/api/datasets/{dataset_id}/cleaning/multivalue/candidates")
    assert res_mv.status_code == 200

    res_struct = client.get(f"/api/datasets/{dataset_id}/cleaning/structural/recommendations")
    assert res_struct.status_code == 200

    # Assert cleaned_dataset is STILL None
    stored = session_store.get(dataset_id)
    assert stored.cleaned_dataset is None


# -----------------------------------------------------------------------------
# Test 2: Existing cleaned_dataset is reused
# -----------------------------------------------------------------------------
def test_existing_cleaned_dataset_is_reused(client):
    dataset_id = "ds_stab_test_2"
    record = build_test_record(dataset_id)

    # Pre-populate cleaned_dataset by dropping "Unnamed: 7"
    drop_res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Unnamed: 7"]},
    )
    assert drop_res.status_code == 200
    stored = session_store.get(dataset_id)
    assert stored.cleaned_dataset is not None
    assert "Unnamed: 7" not in stored.cleaned_dataset.data.columns
    assert len(stored.cleaned_dataset.data.columns) == 7

    cleaned_instance = stored.cleaned_dataset

    # Fetching plan again operates against existing cleaned state without resetting or discarding it
    plan_res = client.get(f"/api/datasets/{dataset_id}/cleaning-plan")
    assert plan_res.status_code == 200
    assert session_store.get(dataset_id).cleaned_dataset is cleaned_instance
    assert "Unnamed: 7" not in session_store.get(dataset_id).cleaned_dataset.data.columns


# -----------------------------------------------------------------------------
# Test 3: Apply creates/updates cleaned_dataset
# -----------------------------------------------------------------------------
def test_apply_creates_and_updates_cleaned_dataset(client):
    dataset_id = "ds_stab_test_3"
    record = build_test_record(dataset_id)
    assert record.cleaned_dataset is None

    # Apply drop column
    apply_res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Pg.No"]},
    )
    assert apply_res.status_code == 200
    stored = session_store.get(dataset_id)
    assert stored.cleaned_dataset is not None
    assert "Pg.No" not in stored.cleaned_dataset.data.columns
    assert len(stored.cleaned_dataset.data.columns) == 7


# -----------------------------------------------------------------------------
# Test 4: Repeated page-load equivalent API calls do not regenerate cleaned state
# -----------------------------------------------------------------------------
def test_repeated_page_load_calls_do_not_regenerate_cleaned_state(client):
    dataset_id = "ds_stab_test_4"
    record = build_test_record(dataset_id)

    # Initial state
    assert record.cleaned_dataset is None

    for _ in range(5):
        r1 = client.get(f"/api/datasets/{dataset_id}/cleaning-plan")
        r2 = client.get(f"/api/datasets/{dataset_id}/cleaning/multivalue/candidates")
        r3 = client.get(f"/api/datasets/{dataset_id}/cleaning/structural/recommendations")
        r4 = client.get(f"/api/datasets/{dataset_id}/semantic-analysis")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
        assert r4.status_code == 200

    stored = session_store.get(dataset_id)
    assert stored.cleaned_dataset is None


# -----------------------------------------------------------------------------
# Test 5: Semantic role preview does not mutate state
# -----------------------------------------------------------------------------
def test_semantic_role_preview_does_not_mutate_state(client):
    dataset_id = "ds_stab_test_5"
    record = build_test_record(dataset_id)

    # S. No is currently an IDENTIFIER
    orig_ev = record.semantic_profile.get_evidence("S. No")
    orig_role = orig_ev.candidate_role.value

    # Preview changing S. No to MEASURE
    preview_res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/semantic-role/preview",
        json={"column_name": "S. No", "selected_role": "MEASURE"},
    )
    assert preview_res.status_code == 200
    data = preview_res.json()
    assert data["selected_role"] == "MEASURE"
    assert data["system_role"] == orig_role

    # Assert no mutation
    stored = session_store.get(dataset_id)
    assert stored.user_semantic_role_overrides == {}
    curr_ev = stored.semantic_profile.get_evidence("S. No")
    assert curr_ev.candidate_role.value == orig_role
    assert curr_ev.is_user_overridden is False


# -----------------------------------------------------------------------------
# Test 6: Semantic role apply persists override
# -----------------------------------------------------------------------------
def test_semantic_role_apply_persists_override(client):
    dataset_id = "ds_stab_test_6"
    record = build_test_record(dataset_id)

    # Student Name is DIMENSION
    apply_res = client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/semantic-role/apply",
        json={"column_name": "Student Name", "selected_role": "IDENTIFIER"},
    )
    assert apply_res.status_code == 200
    data = apply_res.json()
    assert data["selected_role"] == "IDENTIFIER"
    assert data["system_role"] == "DIMENSION"

    stored = session_store.get(dataset_id)
    assert stored.user_semantic_role_overrides.get("Student Name") == "IDENTIFIER"
    ev = stored.semantic_profile.get_evidence("Student Name")
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.system_role == ColumnRole.DIMENSION
    assert ev.user_override_role == ColumnRole.IDENTIFIER
    assert ev.is_user_overridden is True


# -----------------------------------------------------------------------------
# Test 7: Effective role uses user override
# -----------------------------------------------------------------------------
def test_effective_role_uses_user_override(client):
    dataset_id = "ds_stab_test_7"
    record = build_test_record(dataset_id)

    # LPA/CTC is MEASURE
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/semantic-role/apply",
        json={"column_name": "LPA/CTC", "selected_role": "DIMENSION"},
    )

    # Fetch semantic profile
    res = client.get(f"/api/datasets/{dataset_id}/semantic-analysis")
    assert res.status_code == 200
    sem_data = res.json()
    lpa_ev = sem_data["column_evidences"]["LPA/CTC"]

    assert lpa_ev["candidate_role"] == "DIMENSION"
    assert lpa_ev["system_role"] == "MEASURE"
    assert lpa_ev["user_override_role"] == "DIMENSION"
    assert lpa_ev["is_user_overridden"] is True

    # Check to_metadata_dict reflects effective role
    meta_dict = session_store.get(dataset_id).to_metadata_dict()
    col_dict = next(c for c in meta_dict["columns"] if c["original_name"] == "LPA/CTC")
    assert col_dict["semantic_role"] == "DIMENSION"


# -----------------------------------------------------------------------------
# Test 8: User override survives subsequent cleaning operations
# -----------------------------------------------------------------------------
def test_user_override_survives_subsequent_cleaning_operations(client):
    dataset_id = "ds_stab_test_8"
    record = build_test_record(dataset_id)

    # Override Roll-No to DIMENSION
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/semantic-role/apply",
        json={"column_name": "Roll-No", "selected_role": "DIMENSION"},
    )

    # Now apply drop column on "Unnamed: 7"
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Unnamed: 7"]},
    )

    stored = session_store.get(dataset_id)
    assert stored.cleaned_dataset is not None
    assert stored.user_semantic_role_overrides.get("Roll-No") == "DIMENSION"

    ev = stored.semantic_profile.get_evidence("Roll-No")
    assert ev.candidate_role == ColumnRole.DIMENSION
    assert ev.is_user_overridden is True
    assert ev.user_override_role == ColumnRole.DIMENSION


# -----------------------------------------------------------------------------
# Test 9: User override survives registration
# -----------------------------------------------------------------------------
def test_user_override_survives_registration(client):
    dataset_id = "ds_stab_test_9"
    record = build_test_record(dataset_id)

    # Set override on "Company Name" to IDENTIFIER
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/semantic-role/apply",
        json={"column_name": "Company Name", "selected_role": "IDENTIFIER"},
    )

    # Apply a cleaning transformation
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Unnamed: 7"]},
    )

    # Register cleaned dataset
    reg_res = client.post(f"/api/datasets/{dataset_id}/cleaned/register")
    assert reg_res.status_code == 200
    cleaned_id = reg_res.json()["dataset_id"]

    # Verify the new registered record retains the override
    registered_record = session_store.get(cleaned_id)
    assert registered_record is not None
    assert registered_record.user_semantic_role_overrides.get("Company Name") == "IDENTIFIER"

    ev = registered_record.semantic_profile.get_evidence("Company Name")
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.is_user_overridden is True
    assert ev.user_override_role == ColumnRole.IDENTIFIER


# -----------------------------------------------------------------------------
# Test 10: Raw dataset remains unchanged
# -----------------------------------------------------------------------------
def test_raw_dataset_remains_strictly_unchanged(client):
    dataset_id = "ds_stab_test_10"
    record = build_test_record(dataset_id)

    orig_data_shape = record.dataset.data.shape
    orig_cols = list(record.dataset.data.columns)

    # Perform preview operations
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/preview",
        json={"columns": ["Unnamed: 7", "Pg.No"]},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/semantic-role/preview",
        json={"column_name": "Roll-No", "selected_role": "MEASURE"},
    )
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/duplicates/preview",
        json={"keep_strategy": "first"},
    )

    # Perform apply operations
    client.post(
        f"/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Unnamed: 7"]},
    )

    stored = session_store.get(dataset_id)
    assert stored.dataset.data.shape == orig_data_shape
    assert list(stored.dataset.data.columns) == orig_cols


# -----------------------------------------------------------------------------
# Test 11: Cleaning plan generation does not execute transformations
# -----------------------------------------------------------------------------
def test_cleaning_plan_generation_does_not_execute_transformations(client):
    dataset_id = "ds_stab_test_11"
    record = build_test_record(dataset_id)

    assert record.cleaned_dataset is None
    orig_df_hash = pd.util.hash_pandas_object(record.dataset.data).sum()

    res = client.get(f"/api/datasets/{dataset_id}/cleaning-plan")
    assert res.status_code == 200
    plan_data = res.json()
    assert "recommendations" in plan_data
    assert len(plan_data["recommendations"]) > 0

    stored = session_store.get(dataset_id)
    # Assert cleaned_dataset was NOT created
    assert stored.cleaned_dataset is None
    # Assert raw dataframe was not modified in any way
    new_df_hash = pd.util.hash_pandas_object(stored.dataset.data).sum()
    assert orig_df_hash == new_df_hash
