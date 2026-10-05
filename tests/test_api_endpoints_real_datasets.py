"""End-to-end API integration tests for real datasets against analytical query, insights, and overview endpoints.

Validates that:
1. Ingestion creates the canonical record in session_store.
2. /api/query and /api/analytical-query use session_store and execute successfully.
3. /api/insights and /api/discover-insights use session_store and execute successfully.
4. /api/overview and /api/overview-dashboard use session_store and execute successfully.
5. All 5 canonical real datasets (healthcare, hr, education, iot, logistics) work through the API.
6. Nonexistent dataset_ids return 404 with DATASET_NOT_FOUND.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import session_store

client = TestClient(app)

REAL_DATA_DIR = Path(__file__).parent / "real_data"

DATASET_QUESTIONS = {
    "healthcare.csv": "What is the average length of stay by diagnosis?",
    "hr.csv": "What is the average salary by department?",
    "education.csv": "What is the average marks by department?",
    "iot.csv": "What is the average temperature by device?",
    "logistics.csv": "What is the average delivery time by destination?",
}


@pytest.fixture(autouse=True)
def reset_store():
    session_store.clear()
    yield
    session_store.clear()


def test_nonexistent_dataset_404_handling():
    """Verify all affected endpoints return 404 when dataset_id does not exist."""
    fake_id = "ds-nonexistent-12345"

    resp_query = client.post("/api/query", json={"dataset_id": fake_id, "question": "Total rows?"})
    assert resp_query.status_code == 404
    assert resp_query.json()["error"] == "Dataset not found"

    resp_query_alias = client.post("/api/analytical-query", json={"dataset_id": fake_id, "question": "Total rows?"})
    assert resp_query_alias.status_code == 404
    assert resp_query_alias.json()["error"] == "Dataset not found"

    resp_insights = client.post("/api/insights", json={"dataset_id": fake_id, "use_llm": False})
    assert resp_insights.status_code == 404
    assert resp_insights.json()["error"] == "Dataset not found"

    resp_insights_alias = client.post("/api/discover-insights", json={"dataset_id": fake_id, "use_llm": False})
    assert resp_insights_alias.status_code == 404
    assert resp_insights_alias.json()["error"] == "Dataset not found"

    resp_overview = client.post("/api/overview", json={"dataset_id": fake_id, "use_llm": False})
    assert resp_overview.status_code == 404
    assert resp_overview.json()["error"] == "Dataset not found"

    resp_overview_alias = client.post("/api/overview-dashboard", json={"dataset_id": fake_id, "use_llm": False})
    assert resp_overview_alias.status_code == 404
    assert resp_overview_alias.json()["error"] == "Dataset not found"


@pytest.mark.parametrize("filename", [
    "healthcare.csv",
    "hr.csv",
    "education.csv",
    "iot.csv",
    "logistics.csv",
])
def test_real_dataset_api_flow(filename: str):
    """Test full upload and execution of query, insights, and overview through API for real datasets."""
    file_path = REAL_DATA_DIR / filename
    assert file_path.exists(), f"Real dataset file not found: {file_path}"

    # 1. Upload dataset through API
    with open(file_path, "rb") as f:
        upload_resp = client.post(
            "/api/datasets/upload",
            files={"file": (filename, f, "text/csv")},
        )
    assert upload_resp.status_code == 201, f"Upload failed for {filename}: {upload_resp.text}"
    dataset_id = upload_resp.json()["dataset_id"]

    # 2. Verify dataset session record exists in session_store
    record = session_store.get(dataset_id)
    assert record is not None
    assert record.dataset is not None
    assert record.profile is not None
    assert record.semantic_profile is not None

    # 3. Test /api/query and /api/analytical-query
    question = DATASET_QUESTIONS[filename]

    query_resp = client.post("/api/query", json={"dataset_id": dataset_id, "question": question})
    assert query_resp.status_code == 200, f"Query failed for {filename}: {query_resp.text}"
    query_data = query_resp.json()
    assert query_data["status"] == "SUCCESS"
    assert len(query_data["data"]) > 0
    assert query_data["compiled_sql"] is not None
    assert "SELECT" in query_data["compiled_sql"].upper()
    assert query_data["validation_status"] in ("PASSED", "WARNING")

    # Test alias endpoint /api/analytical-query
    query_alias_resp = client.post("/api/analytical-query", json={"dataset_id": dataset_id, "question": question})
    assert query_alias_resp.status_code == 200
    assert query_alias_resp.json()["status"] == "SUCCESS"

    # 4. Test /api/insights and /api/discover-insights
    insights_resp = client.post(
        "/api/insights",
        json={"dataset_id": dataset_id, "max_insights": 5, "use_llm": False},
    )
    assert insights_resp.status_code == 200, f"Insights failed for {filename}: {insights_resp.text}"
    insights_data = insights_resp.json()
    assert insights_data["status"] == "SUCCESS"
    assert insights_data["dataset_id"] == dataset_id
    assert len(insights_data["insights"]) > 0

    # Test alias endpoint /api/discover-insights
    insights_alias_resp = client.post(
        "/api/discover-insights",
        json={"dataset_id": dataset_id, "max_insights": 5, "use_llm": False},
    )
    assert insights_alias_resp.status_code == 200
    assert insights_alias_resp.json()["status"] == "SUCCESS"

    # 5. Test /api/overview and /api/overview-dashboard
    overview_resp = client.post(
        "/api/overview",
        json={"dataset_id": dataset_id, "use_llm": False},
    )
    assert overview_resp.status_code == 200, f"Overview failed for {filename}: {overview_resp.text}"
    overview_data = overview_resp.json()
    assert overview_data["status"] == "SUCCESS"
    assert "panels" in overview_data
    assert len(overview_data["panels"]) > 0

    # Test alias endpoint /api/overview-dashboard
    overview_alias_resp = client.post(
        "/api/overview-dashboard",
        json={"dataset_id": dataset_id, "use_llm": False},
    )
    assert overview_alias_resp.status_code == 200
    assert overview_alias_resp.json()["status"] == "SUCCESS"
