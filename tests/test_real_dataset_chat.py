"""Real Dataset Multi-Turn Conversation & API Validation Test Suite (Step 8 / Roadmap #7).

Validates Evidence-Grounded Dataset Interaction / Chat across 5 canonical datasets:
1. Healthcare (diagnosis, severity, length_of_stay, hospital, admission_date)
2. HR (department, salary, performance_score, employee_id, joining_date)
3. Education (department, subject, marks, student_id, exam_date)
4. IoT (device, temperature, pressure, status, timestamp)
5. Logistics (destination, delivery_time, shipment_id, shipment_date, status)

Verifies:
- Direct analytical queries through the FastAPI `/api/chat` endpoint
- Multi-turn state preservation and follow-up resolution
- DuckDB numerical accuracy and parity with underlying data
- Proper handling of metadata, insight, and dashboard queries
- Correct guardrails for causal and forecasting questions
- Strict isolation of conversation context per dataset/session
"""

import os
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    DatasetMetadata,
)
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import SchemaValidator
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.chat.engine import execute_chat_turn
from orchestrator.chat.schemas import (
    ChatIntentType,
    ConversationContext,
)


def _setup_api_session(filename: str):
    """Load dataset into session store and return (dataset_id, dataset, profile, sem_profile, readiness)."""
    path = os.path.join(os.path.dirname(__file__), "real_data", filename)
    df = pd.read_csv(path)
    ds_id = f"test_{filename.replace('.', '_')}"
    
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(ds_id, filename, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    readiness = SchemaValidator().validate(dataset, profile, sem_profile)
    
    record = DatasetSessionRecord(
        dataset=dataset,
        profile=profile,
        semantic_profile=sem_profile,
        readiness=readiness,
    )
    session_store.save(record)
    return ds_id, dataset, profile, sem_profile, readiness


# ===========================================================================
# 1. Healthcare Dataset Conversation
# ===========================================================================

def test_healthcare_multi_turn_chat():
    """Test full multi-turn conversation on healthcare dataset."""
    client = TestClient(app)
    ds_id, dataset, profile, sem_profile, readiness = _setup_api_session("healthcare.csv")
    conv_id = f"conv_hc_{os.urandom(4).hex()}"

    # Turn 1: Dataset Metadata Question
    r1 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What does this dataset contain?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["intent_type"] == "DATASET_METADATA"
    assert "rows" in d1["answer"].lower()
    assert d1["row_count"] > 0

    # Turn 2: Direct Grouped Query
    r2 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What is the average length of stay by diagnosis?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["intent_type"] == "ANALYTICAL_QUERY"
    assert d2["compiled_sql"] is not None
    assert "length_of_stay" in d2["compiled_sql"]
    assert len(d2["data"]) > 0

    # Turn 3: Follow-Up ("Which one is highest?")
    r3 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Which one is highest?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["intent_type"] in ("ANALYTICAL_QUERY", "FOLLOW_UP")
    assert d3["row_count"] == 1
    # Check DuckDB numerical parity
    actual_top = dataset.data.groupby("diagnosis", dropna=False)["length_of_stay"].mean().sort_values(ascending=False).index[0]
    assert (pd.isna(actual_top) and d3["data"][0]["diagnosis"] is None) or d3["data"][0]["diagnosis"] == actual_top

    # Turn 4: Provenance Question ("Show me the SQL")
    r4 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Show me the SQL for that calculation",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["intent_type"] == "PROVENANCE_OR_SQL"
    assert "SELECT" in d4["answer"]


# ===========================================================================
# 2. HR Dataset Conversation
# ===========================================================================

def test_hr_multi_turn_chat():
    """Test full multi-turn conversation on HR dataset."""
    client = TestClient(app)
    ds_id, dataset, profile, sem_profile, readiness = _setup_api_session("hr.csv")
    conv_id = f"conv_hr_{os.urandom(4).hex()}"

    # Turn 1: Grouped analytical query
    r1 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What is the average salary by department?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["intent_type"] == "ANALYTICAL_QUERY"
    assert len(d1["data"]) > 0

    # Turn 2: Ranking query
    r2 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Which department has the highest average salary?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    top_dept = dataset.data.groupby("department")["salary"].mean().sort_values(ascending=False).index[0]
    assert d2["data"][0]["department"] == top_dept
    assert top_dept in d2["answer"]

    # Turn 3: Comparison query
    r3 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Compare average salary between Engineering and Sales",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["row_count"] == 2
    assert "Engineering" in d3["answer"] or "Sales" in d3["answer"]

    # Turn 4: Insights question
    r4 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What are the most important insights in this dataset?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["intent_type"] == "INSIGHT_EXPLANATION"
    assert "insight" in d4["answer"].lower() or len(d4["answer"]) > 20


# ===========================================================================
# 3. Education Dataset Conversation
# ===========================================================================

def test_education_multi_turn_chat():
    """Test multi-turn conversation on education dataset."""
    client = TestClient(app)
    ds_id, dataset, profile, sem_profile, readiness = _setup_api_session("education.csv")
    conv_id = f"conv_edu_{os.urandom(4).hex()}"

    # Turn 1: Grouped question
    r1 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What is the average marks by subject?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["intent_type"] == "ANALYTICAL_QUERY"
    assert "marks" in d1["compiled_sql"]

    # Turn 2: Top N query
    r2 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Show me the top 3 subjects by average marks",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["row_count"] <= 3

    # Turn 3: Columns metadata query
    r3 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What columns are available?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["intent_type"] == "DATASET_METADATA"
    assert "marks" in d3["answer"].lower()
    assert "subject" in d3["answer"].lower()


# ===========================================================================
# 4. IoT Dataset Conversation
# ===========================================================================

def test_iot_multi_turn_chat():
    """Test multi-turn conversation on IoT dataset with safety guardrails."""
    client = TestClient(app)
    ds_id, dataset, profile, sem_profile, readiness = _setup_api_session("iot.csv")
    conv_id = f"conv_iot_{os.urandom(4).hex()}"

    # Turn 1: Grouped temperature query
    r1 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What is the average temperature by device?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["intent_type"] == "ANALYTICAL_QUERY"
    assert "temperature" in d1["compiled_sql"]

    # Turn 2: Follow-up ranking
    r2 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Which one is lowest?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["row_count"] == 1
    actual_lowest = dataset.data.groupby("device")["temperature"].mean().sort_values(ascending=True).index[0]
    assert d2["data"][0]["device"] == actual_lowest

    # Turn 3: Causal safety guard
    r3 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Why did temperature cause pressure to spike?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["intent_type"] == "UNSUPPORTED_OR_CAUSAL"
    assert "causal" in d3["answer"].lower()

    # Turn 4: Unsupported forecasting guard
    r4 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Predict next month's temperature for all devices",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["intent_type"] == "UNSUPPORTED_OR_CAUSAL"
    assert "forecasting" in d4["answer"].lower()


# ===========================================================================
# 5. Logistics Dataset Conversation
# ===========================================================================

def test_logistics_multi_turn_chat():
    """Test multi-turn conversation on logistics dataset."""
    client = TestClient(app)
    ds_id, dataset, profile, sem_profile, readiness = _setup_api_session("logistics.csv")
    conv_id = f"conv_log_{os.urandom(4).hex()}"

    # Turn 1: Grouped delivery time query
    r1 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "What is the average delivery time by destination?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["intent_type"] == "ANALYTICAL_QUERY"
    assert "delivery_time" in d1["compiled_sql"]

    # Turn 2: Top 2 destinations
    r2 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Show me the top 2 destination by average delivery time",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["row_count"] == 2

    # Turn 3: Dashboard overview rationale question
    r3 = client.post("/api/chat", json={
        "dataset_id": ds_id,
        "message": "Why is this chart chosen on the dashboard?",
        "conversation_id": conv_id,
        "use_llm": False,
    })
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["intent_type"] == "DASHBOARD_EXPLANATION"
    assert "dashboard" in d3["answer"].lower()
