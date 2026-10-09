"""Targeted tests for Data Studio Part 6: Cleaned Dataset Registration & Downloads.

Covers all 18 required behaviors:
1. successful cleaned dataset registration
2. new dataset ID differs from original
3. original dataset remains unchanged
4. cleaned dataset appears in session store
5. cleaned dataset appears in dataset listing
6. cleaned dataset has profile
7. cleaned dataset has semantic profile
8. cleaned dataset has readiness
9. lineage/source_dataset_id is correct
10. registration without successful cleaning is rejected
11. duplicate registration does not create unlimited duplicates (idempotent)
12. CSV download works
13. XLSX download works
14. invalid download format rejected
15. download uses registered dataset only (404 for unknown ID)
16. raw dataset remains unchanged after downloads
17. raw and cleaned datasets can coexist
18. dataset switching resolves the correct dataset
"""

import io
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import session_store, DatasetSessionRecord
from cleaning.executor import execute_cleaning_plan
from cleaning.planner import CleaningPlanner
from ingestion.loaders import CSVLoader, load_dataset
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from intelligence.schema_validator import assess_readiness


@pytest.fixture(autouse=True)
def clean_session_store():
    """Clear session store before each test."""
    session_store.clear()
    yield
    session_store.clear()


def _setup_raw_dataset(dataset_id: str = "ds_test_healthcare", filename: str = "healthcare.csv"):
    """Helper to load and register a raw test dataset in session_store."""
    df = pd.DataFrame({
        "id": [1, 2, 2, 3, 4, 5],
        "department": ["Cardiology", "Neurology", "Neurology", "Cardiology", "  ", None],
        "length_of_stay": [4.0, 5.0, 5.0, None, 10.0, 12.0],
    })
    loader = CSVLoader()
    schema = loader.extract_column_metadata(df)
    
    from ingestion.models import CanonicalDataset, DatasetMetadata
    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=filename,
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    canonical = CanonicalDataset(metadata=meta, data=df.copy(deep=True))
    profile = profile_dataset(canonical)
    semantic = analyze_semantics(canonical, profile=profile)
    readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic)
    
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=semantic,
        readiness=readiness,
        cleaning_report=None,
    )
    session_store.save(record)
    return canonical, record


# =========================================================================
# 1-9: Registration, ID distinction, Immutability, Lineage, Intelligence
# =========================================================================
def test_successful_cleaned_dataset_registration_and_properties():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_test_1", "patients.csv")
    raw_snapshot = canonical.data.copy(deep=True)

    # 1. Apply cleaning
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    
    apply_res = client.post(
        f"/api/datasets/ds_test_1/cleaning/apply",
        json={"selected_recommendation_ids": safe_ids},
    )
    assert apply_res.status_code == 200
    assert record.cleaned_dataset is not None

    # 2. Register cleaned dataset
    reg_res = client.post("/api/datasets/ds_test_1/cleaned/register")
    assert reg_res.status_code == 200
    reg_data = reg_res.json()

    cleaned_id = reg_data["dataset_id"]
    # 2. New ID differs from original
    assert cleaned_id != "ds_test_1"
    assert "cleaned" in cleaned_id
    assert reg_data["filename"] == "patients_cleaned.csv"
    assert reg_data["source_dataset_id"] == "ds_test_1"

    # 3. Original dataset remains unchanged
    assert_frame_equal(record.dataset.data, raw_snapshot)
    assert record.dataset.metadata.dataset_id == "ds_test_1"
    assert record.dataset.metadata.row_count == 6

    # 4. Cleaned dataset appears in session store
    cleaned_record = session_store.get(cleaned_id)
    assert cleaned_record is not None
    assert cleaned_record.dataset.metadata.row_count == 5  # Duplicate removed

    # 5. Cleaned dataset appears in dataset listing
    list_res = client.get("/api/datasets")
    assert list_res.status_code == 200
    list_items = list_res.json()
    listed_ids = [item["dataset_id"] for item in list_items]
    assert "ds_test_1" in listed_ids
    assert cleaned_id in listed_ids

    # 6. Cleaned dataset has profile
    assert cleaned_record.profile is not None
    assert cleaned_record.profile.dataset_id == cleaned_id

    # 7. Cleaned dataset has semantic profile
    assert cleaned_record.semantic_profile is not None
    assert cleaned_record.semantic_profile.dataset_id == cleaned_id

    # 8. Cleaned dataset has readiness
    assert cleaned_record.readiness is not None
    assert cleaned_record.readiness.dataset_id == cleaned_id

    # 9. Lineage metadata is correct
    custom_meta = cleaned_record.dataset.metadata.custom_metadata
    assert custom_meta["source_dataset_id"] == "ds_test_1"
    assert custom_meta["derivation"] == "cleaning"
    assert custom_meta["derived_from_cleaning"] is True


# =========================================================================
# 10. Registration without successful cleaning is rejected
# =========================================================================
def test_registration_without_cleaning_rejected():
    client = TestClient(app)
    _setup_raw_dataset("ds_uncleaned", "data.csv")

    # Attempt registration before cleaning execution
    reg_res = client.post("/api/datasets/ds_uncleaned/cleaned/register")
    assert reg_res.status_code == 400
    err_body = reg_res.json()
    err_msg = err_body.get("detail") or err_body.get("message") or err_body.get("error") or ""
    assert "No validated cleaned result is available" in err_msg


# =========================================================================
# 11. Duplicate registration returns existing registered cleaned dataset
# =========================================================================
def test_duplicate_registration_is_idempotent():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_dup_reg", "test.csv")

    # Apply cleaning
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    client.post(
        f"/api/datasets/ds_dup_reg/cleaning/apply",
        json={"selected_recommendation_ids": safe_ids},
    )

    # First registration
    r1 = client.post("/api/datasets/ds_dup_reg/cleaned/register")
    assert r1.status_code == 200
    id1 = r1.json()["dataset_id"]
    assert r1.json()["already_registered"] is False

    # Second registration - must NOT create a third dataset
    r2 = client.post("/api/datasets/ds_dup_reg/cleaned/register")
    assert r2.status_code == 200
    id2 = r2.json()["dataset_id"]
    assert r2.json()["already_registered"] is True
    assert id1 == id2
    assert len(session_store.list_all()) == 2  # Exactly 1 raw + 1 cleaned


# =========================================================================
# 12. CSV Download works
# =========================================================================
def test_csv_download():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_dl_csv", "sales.csv")

    # Apply & register
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    client.post(f"/api/datasets/ds_dl_csv/cleaning/apply", json={"selected_recommendation_ids": safe_ids})
    reg_res = client.post("/api/datasets/ds_dl_csv/cleaned/register")
    cleaned_id = reg_res.json()["dataset_id"]

    # Download CSV
    dl_res = client.get(f"/api/datasets/{cleaned_id}/download?format=csv")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"sales_cleaned.csv\"" in dl_res.headers["content-disposition"]

    # Verify downloaded content is valid CSV
    df_downloaded = pd.read_csv(io.BytesIO(dl_res.content))
    assert len(df_downloaded) == 5
    assert "length_of_stay" in df_downloaded.columns


# =========================================================================
# 13. XLSX Download works
# =========================================================================
def test_xlsx_download():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_dl_xlsx", "sales.csv")

    # Apply & register
    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    client.post(f"/api/datasets/ds_dl_xlsx/cleaning/apply", json={"selected_recommendation_ids": safe_ids})
    reg_res = client.post("/api/datasets/ds_dl_xlsx/cleaned/register")
    cleaned_id = reg_res.json()["dataset_id"]

    # Download XLSX
    dl_res = client.get(f"/api/datasets/{cleaned_id}/download?format=xlsx")
    assert dl_res.status_code == 200
    assert "spreadsheetml" in dl_res.headers["content-type"]
    assert "attachment; filename=\"sales_cleaned.xlsx\"" in dl_res.headers["content-disposition"]

    # Verify downloaded content is valid Excel file
    df_downloaded = pd.read_excel(io.BytesIO(dl_res.content))
    assert len(df_downloaded) == 5
    assert "length_of_stay" in df_downloaded.columns


# =========================================================================
# 14. Invalid download format is rejected
# =========================================================================
def test_invalid_download_format_rejected():
    client = TestClient(app)
    _setup_raw_dataset("ds_inv_fmt", "data.csv")

    res = client.get("/api/datasets/ds_inv_fmt/download?format=pdf")
    assert res.status_code == 400
    err_body = res.json()
    err_msg = err_body.get("detail") or err_body.get("message") or err_body.get("error") or ""
    assert "Unsupported download format 'pdf'" in err_msg


# =========================================================================
# 15. Download uses registered dataset only (404 for unknown)
# =========================================================================
def test_download_unknown_dataset_404():
    client = TestClient(app)
    res = client.get("/api/datasets/ds_non_existent_999/download?format=csv")
    assert res.status_code == 404


# =========================================================================
# 16. Raw dataset remains unchanged after downloads
# =========================================================================
def test_raw_dataset_remains_unchanged_after_downloads():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_immut_dl", "audit.csv")
    raw_snapshot = canonical.data.copy(deep=True)

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    client.post(f"/api/datasets/ds_immut_dl/cleaning/apply", json={"selected_recommendation_ids": safe_ids})
    reg_res = client.post("/api/datasets/ds_immut_dl/cleaned/register")
    cleaned_id = reg_res.json()["dataset_id"]

    # Perform multiple downloads
    client.get(f"/api/datasets/{cleaned_id}/download?format=csv")
    client.get(f"/api/datasets/{cleaned_id}/download?format=xlsx")

    # Raw dataset MUST be 100% byte-for-byte untouched
    assert_frame_equal(record.dataset.data, raw_snapshot)
    assert record.dataset.metadata.row_count == 6


# =========================================================================
# 17. Raw and cleaned datasets coexist independently
# =========================================================================
def test_raw_and_cleaned_datasets_coexist():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_coexist_raw", "records.csv")

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    client.post(f"/api/datasets/ds_coexist_raw/cleaning/apply", json={"selected_recommendation_ids": safe_ids})
    reg_res = client.post("/api/datasets/ds_coexist_raw/cleaned/register")
    cleaned_id = reg_res.json()["dataset_id"]

    raw_rec = session_store.get("ds_coexist_raw")
    clean_rec = session_store.get(cleaned_id)

    assert raw_rec is not None
    assert clean_rec is not None
    assert len(raw_rec.dataset.data) == 6
    assert len(clean_rec.dataset.data) == 5
    assert raw_rec.dataset.metadata.name == "records.csv"
    assert clean_rec.dataset.metadata.name == "records_cleaned.csv"


# =========================================================================
# 18. Dataset switching resolves the correct dataset
# =========================================================================
def test_dataset_switching_resolves_correct_dataset():
    client = TestClient(app)
    canonical, record = _setup_raw_dataset("ds_switch_raw", "hospital.csv")

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)
    safe_ids = [r.recommendation_id for r in plan.recommendations if r.default_selected]
    client.post(f"/api/datasets/ds_switch_raw/cleaning/apply", json={"selected_recommendation_ids": safe_ids})
    reg_res = client.post("/api/datasets/ds_switch_raw/cleaned/register")
    cleaned_id = reg_res.json()["dataset_id"]

    # 1. Fetch raw dataset metadata & preview
    raw_meta = client.get("/api/datasets/ds_switch_raw").json()
    raw_prev = client.get("/api/datasets/ds_switch_raw/preview").json()
    assert raw_meta["dataset_id"] == "ds_switch_raw"
    assert raw_meta["row_count"] == 6
    assert raw_prev["total_rows"] == 6

    # 2. Switch to cleaned dataset metadata & preview
    clean_meta = client.get(f"/api/datasets/{cleaned_id}").json()
    clean_prev = client.get(f"/api/datasets/{cleaned_id}/preview").json()
    assert clean_meta["dataset_id"] == cleaned_id
    assert clean_meta["row_count"] == 5
    assert clean_prev["total_rows"] == 5


# =========================================================================
# 19. Review-only operations return REVIEW_ONLY status and do not mutate
# =========================================================================
def test_review_only_operations_status_and_immutability():
    client = TestClient(app)
    
    # Dataset with datetime column with missing values and outliers to trigger REVIEW_ operations
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "created_at": ["2023-01-01", "2023-01-02", None, "2023-01-04", "2023-01-05", "2023-01-06", "2023-01-07", "2023-01-08", "2023-01-09", "2023-01-10"],
        "val": [10.0, 11.0, 12.0, 10.5, 11.2, 10.8, 12.1, 10.9, 11.0, 500000.0],
    })
    loader = CSVLoader()
    schema = loader.extract_column_metadata(df)
    from ingestion.models import CanonicalDataset, DatasetMetadata
    meta = DatasetMetadata(
        dataset_id="ds_review_raw",
        name="review_test.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    canonical = CanonicalDataset(metadata=meta, data=df.copy(deep=True))
    profile = profile_dataset(canonical)
    semantic = analyze_semantics(canonical, profile=profile)
    readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic)
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=semantic,
        readiness=readiness,
        cleaning_report=None,
    )
    session_store.save(record)
    raw_snapshot = canonical.data.copy(deep=True)

    planner = CleaningPlanner()
    plan = planner.generate_plan(canonical)

    # Find review-only recommendations (e.g. REVIEW_DATETIME_MISSING or REVIEW_OUTLIERS)
    review_recs = [r for r in plan.recommendations if r.operation.startswith("REVIEW_")]
    assert len(review_recs) > 0, "Expected at least one REVIEW_ recommendation"

    review_id = review_recs[0].recommendation_id

    # 1. Preview
    prev_res = client.post(
        "/api/datasets/ds_review_raw/cleaning/preview",
        json={"selected_recommendation_ids": [review_id]},
    )
    assert prev_res.status_code == 200
    prev_json = prev_res.json()
    op_result = next(op for op in prev_json["operations"] if op["recommendation_id"] == review_id)
    assert op_result["status"] == "REVIEW_ONLY"
    assert "Selected for review" in op_result["method_used"]
    assert op_result["rows_affected"] == 0
    assert op_result["cells_affected"] == 0

    # 2. Execute / Apply
    apply_res = client.post(
        "/api/datasets/ds_review_raw/cleaning/apply",
        json={"selected_recommendation_ids": [review_id]},
    )
    assert apply_res.status_code == 200
    apply_json = apply_res.json()
    exec_op = next(op for op in apply_json["operations"] if op["recommendation_id"] == review_id)
    assert exec_op["status"] == "REVIEW_ONLY"
    assert "Selected for review" in exec_op["method_used"]

    # 3. Verify raw data remains completely untouched
    current_raw = session_store.get("ds_review_raw").dataset.data
    assert_frame_equal(current_raw, raw_snapshot)

