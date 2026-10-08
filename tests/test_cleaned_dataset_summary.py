"""Targeted tests for PART 1: Cleaned Dataset Summary before registration."""

import pytest
import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, DatasetMetadata, ColumnMetadata
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from intelligence.schema_validator import assess_readiness


@pytest.fixture
def sample_dataset_session():
    """Create an in-memory session with raw dataset containing missing values and duplicates."""
    df = pd.DataFrame({
        "S. No": [1, 2, 3, 4, 5, 5],
        "Name": ["Alice", "Bob", "Charlie", "David", "Eve", "Eve"],
        "Age": [25.0, None, 30.0, None, 45.0, 45.0],
        "Salary": [50000.0, 60000.0, 70000.0, 80000.0, 90000.0, 90000.0],
        "Unnamed: 4": [None, None, None, None, None, None],
    })

    metadata = DatasetMetadata(
        dataset_id="ds_summary_test_01",
        name="test_summary_dataset.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=[
            ColumnMetadata(
                original_name=c,
                normalized_name=c.lower().replace(" ", "_"),
                detected_datatype="float" if "Age" in c or "Salary" in c else ("int" if "S. No" in c else "string"),
                semantic_role="MEASURE" if "Salary" in c or "Age" in c else ("IDENTIFIER" if "S. No" in c else "DIMENSION"),
                null_count=int(df[c].isna().sum()),
                null_percentage=float(df[c].isna().mean() * 100),
                distinct_count=int(df[c].nunique()),
                is_unique=bool(df[c].is_unique),
                sample_values=df[c].dropna().head(3).tolist(),
            )
            for c in df.columns
        ],
    )

    canonical = CanonicalDataset(metadata=metadata, data=df)
    profile = profile_dataset(canonical)
    semantic_profile = analyze_semantics(canonical, profile=profile, apply_roles=True)
    readiness = assess_readiness(canonical, profile=profile, semantic_profile=semantic_profile)

    record = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=semantic_profile,
        readiness=readiness,
    )
    session_store.save(record)
    return "ds_summary_test_01"


def test_cleaned_dataset_summary_initial_state(sample_dataset_session):
    client = TestClient(app)
    response = client.get(f"/api/datasets/{sample_dataset_session}/cleaning-summary")
    assert response.status_code == 200
    data = response.json()

    assert data["dataset_id"] == sample_dataset_session
    assert data["has_cleaned"] is False
    assert data["status_message"] == "No cleaning changes have been applied yet."
    assert data["raw_data_protection"] == "Original dataset remains unchanged."
    assert data["changes_applied"] == []
    assert data["metrics"]["rows"]["before"] == 6
    assert data["metrics"]["rows"]["after"] == 6
    assert data["metrics"]["rows"]["change"] == 0
    assert data["metrics"]["columns"]["before"] == 5
    assert data["metrics"]["columns"]["after"] == 5
    assert data["metrics"]["columns"]["change"] == 0
    assert data["metrics"]["missing_cells"]["before"] == 8  # 2 in Age + 6 in Unnamed: 4
    assert data["metrics"]["missing_cells"]["after"] == 8
    assert data["metrics"]["duplicate_rows"]["before"] == 1
    assert data["metrics"]["duplicate_rows"]["after"] == 1

    # Remaining quality issues should report existing missing values and duplicates
    assert any("missing" in issue.lower() for issue in data["remaining_quality_issues"])
    assert any("duplicate" in issue.lower() for issue in data["remaining_quality_issues"])


def test_cleaned_dataset_summary_after_drop_columns_and_deduplication(sample_dataset_session):
    client = TestClient(app)

    # 1. Apply column drop for "Unnamed: 4"
    drop_resp = client.post(
        f"/api/datasets/{sample_dataset_session}/cleaning/structural/drop-columns/apply",
        json={"columns": ["Unnamed: 4"]},
    )
    assert drop_resp.status_code == 200

    # 2. Check summary after drop column
    sum_resp1 = client.get(f"/api/datasets/{sample_dataset_session}/cleaning-summary")
    assert sum_resp1.status_code == 200
    data1 = sum_resp1.json()

    assert data1["has_cleaned"] is True
    assert data1["metrics"]["columns"]["before"] == 5
    assert data1["metrics"]["columns"]["after"] == 4
    assert data1["metrics"]["columns"]["change"] == -1
    assert any("column(s) removed (Unnamed: 4)" in c for c in data1["changes_applied"])

    # 3. Apply duplicate removal
    dup_resp = client.post(
        f"/api/datasets/{sample_dataset_session}/cleaning/structural/duplicates/apply",
        json={"keep_strategy": "first"},
    )
    assert dup_resp.status_code == 200

    # 4. Check summary after deduplication
    sum_resp2 = client.get(f"/api/datasets/{sample_dataset_session}/cleaning-summary")
    assert sum_resp2.status_code == 200
    data2 = sum_resp2.json()

    assert data2["has_cleaned"] is True
    assert data2["metrics"]["rows"]["before"] == 6
    assert data2["metrics"]["rows"]["after"] == 5
    assert data2["metrics"]["rows"]["change"] == -1
    assert data2["metrics"]["duplicate_rows"]["after"] == 0
    assert any("duplicate rows removed" in c for c in data2["changes_applied"])
    assert data2["raw_data_protection"] == "Original dataset remains unchanged."

    # 5. Verify the raw dataset remains 100% immutable
    record = session_store.get(sample_dataset_session)
    assert len(record.dataset.data) == 6
    assert len(record.dataset.data.columns) == 5
    assert "Unnamed: 4" in record.dataset.data.columns
    assert len(record.cleaned_dataset.data) == 5
    assert len(record.cleaned_dataset.data.columns) == 4
    assert "Unnamed: 4" not in record.cleaned_dataset.data.columns
