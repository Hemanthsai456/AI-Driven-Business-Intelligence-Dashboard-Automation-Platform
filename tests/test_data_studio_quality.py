"""Targeted integration and unit tests for Data Studio Part 2: Overview + Quality assessment.

Validates that Overview and Quality assessments are deterministic, explainable,
strictly read-only, and properly isolated between distinct dataset sessions.
"""

import copy
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, DatasetMetadata, ColumnMetadata, ColumnRole
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from intelligence.schema_validator import assess_readiness, ReadinessStatus
from intelligence.quality_assessor import assess_quality, QualityStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_session():
    session_store.clear()
    yield
    session_store.clear()


def create_mock_dataset(
    dataset_id: str,
    df: pd.DataFrame,
    filename: str = "test.csv",
) -> CanonicalDataset:
    """Helper to build a populated CanonicalDataset from a DataFrame."""
    cols = []
    for col in df.columns:
        s = df[col]
        cols.append(
            ColumnMetadata(
                original_name=str(col),
                normalized_name=str(col),
                detected_datatype=str(s.dtype),
                semantic_role=ColumnRole.UNKNOWN,
                null_count=int(s.isna().sum()),
                null_percentage=round(float(s.isna().sum() / len(df) * 100.0), 2) if len(df) > 0 else 0.0,
                distinct_count=int(s.nunique(dropna=True)),
                is_unique=bool(s.is_unique) if len(df) > 0 else False,
                sample_values=s.dropna().head(3).tolist(),
            )
        )
    meta = DatasetMetadata(
        dataset_id=dataset_id,
        name=filename,
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=cols,
    )
    return CanonicalDataset(data=df.copy(deep=True), metadata=meta)


def setup_session_dataset(dataset_id: str, df: pd.DataFrame, filename: str = "test.csv") -> CanonicalDataset:
    """Helper to register a dataset fully into session_store."""
    canonical = create_mock_dataset(dataset_id, df, filename)
    profile = profile_dataset(canonical, attach=False)
    semantic = analyze_semantics(canonical, profile=profile)
    readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic)
    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=semantic,
        readiness=readiness,
    )
    session_store.save(record)
    return canonical


# ---------------------------------------------------------------------------
# Test 1: Overview & Quality for a Normal Clean Dataset
# ---------------------------------------------------------------------------

def test_quality_and_overview_normal_clean_dataset():
    """Verify Overview & Quality assessment for a clean dataset with zero missing/duplicates."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "category": ["A", "B", "C", "D", "E"],
        "revenue": [100.0, 250.0, 300.0, 150.0, 400.0],
        "created_at": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]),
    })
    setup_session_dataset("ds_normal", df, "normal.csv")

    resp = client.get("/api/datasets/ds_normal/quality-assessment")
    assert resp.status_code == 200
    data = resp.json()

    assert data["dataset_id"] == "ds_normal"
    assert data["status"] == QualityStatus.GOOD.value
    assert data["duplicate_row_count"] == 0
    assert data["duplicate_row_percentage"] == 0.0
    assert data["overall_missing_count"] == 0
    assert data["overall_missing_percentage"] == 0.0
    assert data["completeness_percentage"] == 100.0
    assert data["uniqueness_percentage"] == 100.0
    assert data["affected_missing_columns_count"] == 0
    assert len(data["missing_columns"]) == 0
    assert len(data["numeric_observations"]) >= 1
    assert len(data["datetime_observations"]) == 1
    assert "All quality checks passed" in data["status_reason"]


# ---------------------------------------------------------------------------
# Test 2: Overview & Quality with Missing Values
# ---------------------------------------------------------------------------

def test_quality_detection_for_missing_values():
    """Verify Quality assessment accurately flags missing values and computes completeness."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "score": [10.0, None, 30.0, None, 50.0, 60.0, 70.0, None, 90.0, 100.0], # 3 missing (30%)
        "city": ["NY", "LA", None, "SF", "CHI", "MIA", "SEA", "BOS", None, "DEN"], # 2 missing (20%)
        "status": ["Active"] * 10,
    })
    setup_session_dataset("ds_missing", df, "missing.csv")

    resp = client.get("/api/datasets/ds_missing/quality")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == QualityStatus.NEEDS_ATTENTION.value
    assert data["overall_missing_count"] == 5
    assert data["overall_missing_percentage"] > 0.0
    assert data["affected_missing_columns_count"] == 2
    
    col_names = [c["column_name"] for c in data["missing_columns"]]
    assert "score" in col_names
    assert "city" in col_names

    score_info = next(c for c in data["missing_columns"] if c["column_name"] == "score")
    assert score_info["null_count"] == 3
    assert score_info["null_percentage"] == 30.0
    assert score_info["completeness_percentage"] == 70.0


# ---------------------------------------------------------------------------
# Test 3: Overview & Quality with Duplicate Rows
# ---------------------------------------------------------------------------

def test_quality_detection_for_duplicate_rows():
    """Verify Quality assessment detects duplicate rows without mutating."""
    df = pd.DataFrame({
        "id": [1, 2, 1, 3, 1], # 2 duplicate rows
        "name": ["Alpha", "Beta", "Alpha", "Gamma", "Alpha"],
        "val": [10, 20, 10, 30, 10],
    })
    setup_session_dataset("ds_dups", df, "dups.csv")

    resp = client.get("/api/datasets/ds_dups/quality")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == QualityStatus.NEEDS_ATTENTION.value
    assert data["duplicate_row_count"] == 2
    assert data["duplicate_row_percentage"] == 40.0
    assert data["uniqueness_percentage"] == 60.0
    assert "duplicate row(s) detected" in data["status_reason"]


# ---------------------------------------------------------------------------
# Test 4: Quality Critical Status for Severe Problems
# ---------------------------------------------------------------------------

def test_quality_critical_for_all_null_column():
    """Verify that a 100% all-null column triggers CRITICAL quality status."""
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "dead_column": [None, None, None],
        "amount": [10.0, 20.0, 30.0],
    })
    setup_session_dataset("ds_critical", df, "critical.csv")

    resp = client.get("/api/datasets/ds_critical/quality")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == QualityStatus.CRITICAL.value
    assert "100% missing values" in data["status_reason"]


# ---------------------------------------------------------------------------
# Test 5: Numeric Quality Observations (Zeros, Negatives, Extremes)
# ---------------------------------------------------------------------------

def test_numeric_quality_observations():
    """Verify numeric quality stats properly capture zero_count and negative_count."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "balance": [-50.0, 0.0, 100.0, -20.0, 0.0], # 2 zeros, 2 negatives
    })
    setup_session_dataset("ds_numeric", df, "numeric.csv")

    resp = client.get("/api/datasets/ds_numeric/quality")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["numeric_observations"]) >= 1
    bal_info = next(n for n in data["numeric_observations"] if n["column_name"] == "balance")
    assert bal_info["zero_count"] == 2
    assert bal_info["zero_percentage"] == 40.0
    assert bal_info["negative_count"] == 2
    assert bal_info["negative_percentage"] == 40.0
    assert bal_info["min"] == -50.0
    assert bal_info["max"] == 100.0


# ---------------------------------------------------------------------------
# Test 6: Datetime Quality Observations
# ---------------------------------------------------------------------------

def test_datetime_quality_observations():
    """Verify datetime quality stats capture temporal boundaries and distinct dates."""
    df = pd.DataFrame({
        "event_id": [101, 102, 103],
        "timestamp": pd.to_datetime(["2024-05-01 10:00:00", "2024-05-02 11:30:00", "2024-05-03 14:15:00"]),
    })
    setup_session_dataset("ds_datetime", df, "events.csv")

    resp = client.get("/api/datasets/ds_datetime/quality")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["datetime_observations"]) == 1
    dt_info = data["datetime_observations"][0]
    assert dt_info["column_name"] == "timestamp"
    assert "2024-05-01" in dt_info["min_datetime"]
    assert "2024-05-03" in dt_info["max_datetime"]
    assert dt_info["distinct_dates_count"] == 3


# ---------------------------------------------------------------------------
# Test 7: Dataset Switching / Session Isolation
# ---------------------------------------------------------------------------

def test_session_isolation_multiple_datasets():
    """Verify that inspecting quality on dataset A does not leak into dataset B."""
    df_a = pd.DataFrame({"id": [1, 2, 3], "col_a": [10, 20, 30]})
    df_b = pd.DataFrame({"id": [1, 2, 3, 4], "col_b": [None, None, 100, 200]})

    setup_session_dataset("ds_alpha", df_a, "alpha.csv")
    setup_session_dataset("ds_beta", df_b, "beta.csv")

    resp_a = client.get("/api/datasets/ds_alpha/quality")
    resp_b = client.get("/api/datasets/ds_beta/quality")

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    data_a = resp_a.json()
    data_b = resp_b.json()

    assert data_a["dataset_id"] == "ds_alpha"
    assert data_a["total_rows"] == 3
    assert data_a["status"] == QualityStatus.GOOD.value

    assert data_b["dataset_id"] == "ds_beta"
    assert data_b["total_rows"] == 4
    assert data_b["status"] == QualityStatus.NEEDS_ATTENTION.value
    assert data_b["overall_missing_count"] == 2


# ---------------------------------------------------------------------------
# Test 8: Raw Dataset Invariant (Zero Mutations)
# ---------------------------------------------------------------------------

def test_raw_dataset_untouched_after_quality_assessment():
    """Verify that calling quality assessment leaves the original DataFrame exactly identical."""
    df = pd.DataFrame({
        "id": [1, 2, 1], # duplicate row
        "text": ["  spaces  ", None, "  spaces  "],
        "num": [10.5, 20.0, 10.5],
    })
    original_df_copy = df.copy(deep=True)
    setup_session_dataset("ds_immutability", df, "immutability.csv")

    # Perform quality call
    resp = client.get("/api/datasets/ds_immutability/quality")
    assert resp.status_code == 200

    # Retrieve from session_store and assert exact DataFrame equality
    record = session_store.get("ds_immutability")
    assert record is not None
    stored_df = record.dataset.data

    # Shape and values must be 100% identical to original
    pd.testing.assert_frame_equal(stored_df, original_df_copy)
    assert stored_df.iloc[0]["text"] == "  spaces  "
    assert pd.isna(stored_df.iloc[1]["text"])
    assert len(stored_df) == 3
