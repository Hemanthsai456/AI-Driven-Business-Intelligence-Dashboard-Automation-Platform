"""Integration tests for FastAPI REST API endpoints.

Validates that HTTP endpoints correctly interface with ingestion, profiling,
semantic analysis, and schema readiness engines without duplicating engine logic.
"""

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import session_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_session_store():
    session_store.clear()
    yield
    session_store.clear()


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "capabilities" in data
    assert len(data["capabilities"]) >= 4


def test_upload_csv_dataset():
    csv_content = b"id,name,cost,date\n1,Alpha,10.5,2023-01-01\n2,Beta,20.0,2023-01-02\n3,Gamma,15.2,2023-01-03\n"
    files = {"file": ("test_upload.csv", csv_content, "text/csv")}
    
    response = client.post("/api/datasets/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert "dataset_id" in data
    assert data["filename"] == "test_upload.csv"
    assert data["source_type"].upper() == "CSV"
    assert data["row_count"] == 3
    assert data["column_count"] == 4
    assert len(data["columns"]) == 4

    dataset_id = data["dataset_id"]

    # Retrieve metadata
    meta_resp = client.get(f"/api/datasets/{dataset_id}")
    assert meta_resp.status_code == 200
    assert meta_resp.json()["dataset_id"] == dataset_id

    # Retrieve preview
    prev_resp = client.get(f"/api/datasets/{dataset_id}/preview")
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["total_rows"] == 3
    assert len(prev_data["rows"]) == 3
    assert "cost" in prev_data["rows"][0]

    # Retrieve profile
    prof_resp = client.get(f"/api/datasets/{dataset_id}/profile")
    assert prof_resp.status_code == 200
    prof_data = prof_resp.json()
    assert prof_data["dataset_id"] == dataset_id
    assert "column_statistics" in prof_data

    # Retrieve semantic analysis
    sem_resp = client.get(f"/api/datasets/{dataset_id}/semantic-analysis")
    assert sem_resp.status_code == 200
    sem_data = sem_resp.json()
    assert sem_data["dataset_id"] == dataset_id
    assert "column_evidences" in sem_data
    assert "id" in sem_data["column_evidences"]
    assert "cost" in sem_data["column_evidences"]

    # Retrieve readiness
    read_resp = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert read_resp.status_code == 200
    read_data = read_resp.json()
    assert read_data["dataset_id"] == dataset_id
    assert "status" in read_data


def test_upload_tsv_dataset():
    tsv_content = b"id\tname\tcost\tdate\n1\tAlpha\t10.5\t2023-01-01\n2\tBeta\t20.0\t2023-01-02\n3\tGamma\t15.2\t2023-01-03\n"
    files = {"file": ("test_upload.tsv", tsv_content, "text/tab-separated-values")}
    
    response = client.post("/api/datasets/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert "dataset_id" in data
    assert data["filename"] == "test_upload.tsv"
    assert data["source_type"].upper() == "TSV"
    assert data["row_count"] == 3
    assert data["column_count"] == 4
    assert len(data["columns"]) == 4

    dataset_id = data["dataset_id"]

    # Retrieve preview
    prev_resp = client.get(f"/api/datasets/{dataset_id}/preview")
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["total_rows"] == 3
    assert len(prev_data["rows"]) == 3
    assert "cost" in prev_data["rows"][0]

    # Retrieve profile
    prof_resp = client.get(f"/api/datasets/{dataset_id}/profile")
    assert prof_resp.status_code == 200
    assert "column_statistics" in prof_resp.json()

    # Retrieve semantic analysis
    sem_resp = client.get(f"/api/datasets/{dataset_id}/semantic-analysis")
    assert sem_resp.status_code == 200
    assert "column_evidences" in sem_resp.json()

    # Retrieve readiness
    read_resp = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert read_resp.status_code == 200
    assert "status" in read_resp.json()


def test_upload_parquet_dataset():
    fixtures_dir = Path(__file__).parent / "fixtures"
    parquet_path = fixtures_dir / "baseline.parquet"
    parquet_content = parquet_path.read_bytes()
    files = {"file": ("baseline.parquet", parquet_content, "application/octet-stream")}
    
    response = client.post("/api/datasets/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert "dataset_id" in data
    assert data["filename"] == "baseline.parquet"
    assert data["source_type"].upper() == "PARQUET"
    assert data["row_count"] == 5
    assert data["column_count"] == 5

    dataset_id = data["dataset_id"]

    # Retrieve preview
    prev_resp = client.get(f"/api/datasets/{dataset_id}/preview")
    assert prev_resp.status_code == 200
    assert prev_resp.json()["total_rows"] == 5

    # Retrieve profile
    prof_resp = client.get(f"/api/datasets/{dataset_id}/profile")
    assert prof_resp.status_code == 200
    assert "column_statistics" in prof_resp.json()

    # Retrieve semantic analysis
    sem_resp = client.get(f"/api/datasets/{dataset_id}/semantic-analysis")
    assert sem_resp.status_code == 200
    assert "column_evidences" in sem_resp.json()

    # Retrieve readiness
    read_resp = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert read_resp.status_code == 200
    assert "status" in read_resp.json()


def test_upload_size_validation_limit_100mb(monkeypatch):
    """Verify upload size validation rejects files exceeding 100MB and communicates the 100 MB limit."""
    from api.main import MAX_FILE_SIZE_BYTES
    assert MAX_FILE_SIZE_BYTES == 100 * 1024 * 1024

    # Test rejection when payload exceeds MAX_FILE_SIZE_BYTES
    monkeypatch.setattr("api.main.MAX_FILE_SIZE_BYTES", 50)
    over_limit_content = b"a,b\n" + b"1,2\n" * 15  # ~64 bytes > 50 bytes
    files = {"file": ("large.csv", over_limit_content, "text/csv")}
    response = client.post("/api/datasets/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert "Maximum file size is 100 MB" in data["message"]

    # Test acceptance when within MAX_FILE_SIZE_BYTES
    under_limit_content = b"a,b\n1,2\n"  # 8 bytes <= 50 bytes
    files = {"file": ("small.csv", under_limit_content, "text/csv")}
    response_ok = client.post("/api/datasets/upload", files=files)
    assert response_ok.status_code == 201


def test_upload_invalid_file_format():
    files = {"file": ("unsupported.txt", b"some plain text", "text/plain")}
    response = client.post("/api/datasets/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert "Unsupported file format" in data["message"]


def test_upload_empty_file():
    files = {"file": ("empty.csv", b"", "text/csv")}
    response = client.post("/api/datasets/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert "empty" in data["message"].lower()


def test_get_nonexistent_dataset():
    response = client.get("/api/datasets/non_existent_id")
    assert response.status_code == 404


def test_list_datasets():
    csv_content = b"a,b\n1,2\n3,4\n"
    files = {"file": ("dataset1.csv", csv_content, "text/csv")}
    client.post("/api/datasets/upload", files=files)

    response = client.get("/api/datasets")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["filename"] == "dataset1.csv"


def test_readiness_zero_warnings():
    """Readiness endpoint returns status READY and empty warnings/blocking_issues lists for clean data."""
    csv_content = b"id,name,cost\n1,Alpha,10.5\n2,Beta,20.0\n3,Gamma,15.2\n"
    files = {"file": ("clean_dataset.csv", csv_content, "text/csv")}
    upload_resp = client.post("/api/datasets/upload", files=files)
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]

    response = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "READY"
    assert data["warnings"] == []
    assert data["blocking_issues"] == []
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) > 0


def test_readiness_one_warning_constant_column():
    """Readiness endpoint returns status READY_WITH_WARNINGS and string list warning for constant column."""
    csv_content = b"title,isbn13\nBook A,978-0131103627\nBook B,978-0131103627\nBook C,978-0131103627\n"
    files = {"file": ("books.csv", csv_content, "text/csv")}
    upload_resp = client.post("/api/datasets/upload", files=files)
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]

    response = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "READY_WITH_WARNINGS"
    assert len(data["warnings"]) == 1
    assert isinstance(data["warnings"][0], str)
    assert data["warnings"][0] == "Column 'isbn13' is constant (only 1 distinct non-null value)."
    assert data["blocking_issues"] == []


def test_readiness_multiple_warnings():
    """Readiness endpoint handles multiple warnings (constant column + high missingness column)."""
    # 10 rows: isbn13 constant, score 60% nulls (6/10)
    lines = ["title,isbn13,score"]
    for i in range(10):
        score_str = "10.0" if i < 4 else ""
        lines.append(f"Title {i},978-0131103627,{score_str}")
    csv_content = "\n".join(lines).encode("utf-8")
    
    files = {"file": ("multi_warnings.csv", csv_content, "text/csv")}
    upload_resp = client.post("/api/datasets/upload", files=files)
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]

    response = client.get(f"/api/datasets/{dataset_id}/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "READY_WITH_WARNINGS"
    assert len(data["warnings"]) >= 2
    for warning in data["warnings"]:
        assert isinstance(warning, str)
    assert any("isbn13" in w and "constant" in w for w in data["warnings"])
    assert any("score" in w and "missingness" in w for w in data["warnings"])


def test_upload_preserves_raw_dataset():
    """Verify that uploading a dataset preserves raw untouched data without automatic cleaning."""
    # CSV containing exact duplicates and untrimmed strings
    csv_content = b"id,city,revenue\n1,  New York  ,100\n2,Chicago,200\n1,  New York  ,100\n"
    files = {"file": ("raw_test.csv", csv_content, "text/csv")}
    upload_resp = client.post("/api/datasets/upload", files=files)
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]

    # Preview should reflect exact raw 3 rows including duplicate row
    prev_resp = client.get(f"/api/datasets/{dataset_id}/preview")
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["total_rows"] == 3
    assert len(prev_data["rows"]) == 3
    assert prev_data["rows"][0]["city"] == "  New York  "
    assert prev_data["rows"][2]["city"] == "  New York  "

    # Profile should detect duplicate row in quality issues without mutating
    prof_resp = client.get(f"/api/datasets/{dataset_id}/profile")
    assert prof_resp.status_code == 200
    prof_data = prof_resp.json()
    assert prof_data["dataset_summary"]["duplicate_row_count"] == 1
    assert prof_data["dataset_summary"]["row_count"] == 3

