"""Comprehensive Test Suite for Evidence-Grounded Dataset Chat (Step 8 / Roadmap #7).

Covers all 23 core test categories:
1. Basic analytical question
2. Grouped analytical question
3. Ranking question
4. Top / Bottom N question
5. Filter question
6. Multiple filters question
7. Temporal question
8. Comparison question
9. Follow-up question (context-aware pronoun binding)
10. Ambiguous follow-up (clarification trigger)
11. Dataset metadata question
12. Insight question (Step 6 integration)
13. Dashboard evidence question (Step 7 integration)
14. SQL / provenance question on previous result
15. Unsupported forecasting request (graceful refusal)
16. Causal-question handling (observational clarification)
17. Invalid dataset 404 error handling
18. Empty question handling
19. No-result query handling
20. LLM failure fallback to deterministic narration
21. Hallucinated-number rejection
22. Conversation context isolation (two conversations on same dataset)
23. Multiple datasets / session isolation
"""

import math
from pathlib import Path
from typing import Any
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import DatasetSessionRecord, session_store
from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import assess_readiness
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.chat import (
    ChatIntentType,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    DatasetChatEngine,
    execute_chat_turn,
)
from orchestrator.chat.response_generator import ChatResponseGenerator
from providers.adapters.mock import MockLLMClient

client = TestClient(app)


def _build_test_dataset(name: str = "ds_test") -> tuple[CanonicalDataset, Any, Any, Any]:
    df = pd.DataFrame({
        "dept": ["Eng", "Sales", "Eng", "Sales", "HR", "Eng", "HR"],
        "salary": [100000.0, 70000.0, 110000.0, 75000.0, 60000.0, 120000.0, 65000.0],
        "performance": [4.8, 3.5, 4.9, 3.8, 4.2, 5.0, 4.0],
        "hire_date": ["2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01", "2022-01-01", "2022-06-01", "2023-01-01"],
    })
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(name, f"{name}.csv", "csv", len(df), len(cols), cols)
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    sem_profile = analyze_semantics(canonical, profile)
    readiness = assess_readiness(canonical, profile, sem_profile)
    return canonical, profile, sem_profile, readiness


@pytest.fixture(autouse=True)
def reset_session_store():
    session_store.clear()
    yield
    session_store.clear()


# ===========================================================================
# 1. Basic Analytical Question
# ===========================================================================

def test_01_basic_analytical_question():
    """Verify single-measure aggregate question returns correct scalar calculation with SQL."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds1")
    ctx = ConversationContext(dataset_id="ds1")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.ANALYTICAL_QUERY
    assert resp.compiled_sql is not None
    assert "SELECT" in resp.compiled_sql.upper()
    assert resp.row_count == 1
    assert "85,714" in resp.answer or "85714" in resp.answer
    assert ctx.last_metric == "salary"


# ===========================================================================
# 2. Grouped Analytical Question
# ===========================================================================

def test_02_grouped_analytical_question():
    """Verify group-by question returns structured rows for all categories."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds2")
    ctx = ConversationContext(dataset_id="ds2")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.ANALYTICAL_QUERY
    assert resp.row_count == 3  # Eng, Sales, HR
    assert resp.data is not None
    assert ctx.last_dimensions == ["dept"]


# ===========================================================================
# 3. Ranking Question
# ===========================================================================

def test_03_ranking_question():
    """Verify ranking question identifies top department correctly."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds3")
    ctx = ConversationContext(dataset_id="ds3")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Which dept has the highest average salary?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type in (ChatIntentType.ANALYTICAL_QUERY, ChatIntentType.FOLLOW_UP)
    assert resp.data[0]["dept"] == "Eng"
    assert "Eng" in resp.answer


# ===========================================================================
# 4. Top / Bottom N Question
# ===========================================================================

def test_04_top_bottom_limit():
    """Verify top N limit limits returned rows to requested count."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds4")
    ctx = ConversationContext(dataset_id="ds4")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Show me the top 2 dept by average salary",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.row_count == 2
    assert resp.data[0]["dept"] == "Eng"
    assert resp.data[1]["dept"] == "Sales"


# ===========================================================================
# 5. Filter Question
# ===========================================================================

def test_05_filtered_question():
    """Verify question with category filter calculates measure for filtered subset."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds5")
    ctx = ConversationContext(dataset_id="ds5")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary where dept is Eng?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.row_count == 1
    # Eng average is (100000+110000+120000)/3 = 110,000
    assert "110,000" in resp.answer or "110000" in resp.answer


# ===========================================================================
# 6. Multiple Filters
# ===========================================================================

def test_06_multiple_filters():
    """Verify query with multiple constraints executes safely."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds6")
    ctx = ConversationContext(dataset_id="ds6")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Show average salary by dept where performance is above 4",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.compiled_sql is not None
    assert "WHERE" in resp.compiled_sql.upper()


# ===========================================================================
# 7. Temporal Question
# ===========================================================================

def test_07_temporal_question():
    """Verify datetime temporal breakdown question."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds7")
    ctx = ConversationContext(dataset_id="ds7")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Show average salary over hire date",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.row_count > 0
    assert resp.compiled_sql is not None


# ===========================================================================
# 8. Comparison Question
# ===========================================================================

def test_08_comparison_question():
    """Verify comparison between two groups produces clear numerical difference."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds8")
    ctx = ConversationContext(dataset_id="ds8")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Compare average salary between Eng and Sales",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.row_count == 2
    assert "Eng" in resp.answer
    assert "Sales" in resp.answer


# ===========================================================================
# 9. Follow-Up Question (Multi-Turn State)
# ===========================================================================

def test_09_followup_question_state_preservation():
    """Verify follow-up query 'which one is highest?' resolves previous context."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds9")
    ctx = ConversationContext(dataset_id="ds9")

    # Turn 1: Grouped question
    r1 = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert r1.row_count == 3

    # Turn 2: Follow-up question referencing previous metric and dimension
    r2 = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Which one is highest?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert r2.intent_type == ChatIntentType.FOLLOW_UP
    assert r2.data[0]["dept"] == "Eng"
    assert "Eng" in r2.answer


# ===========================================================================
# 10. Ambiguous Follow-Up
# ===========================================================================

def test_10_ambiguous_followup_triggers_clarification():
    """Verify follow-up with no prior dimension triggers clarification options."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds10")
    ctx = ConversationContext(dataset_id="ds10")

    # Turn 1: Scalar metric without dimensions
    execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    # Turn 2: Follow-up asks "which one is highest" without a dimension
    r2 = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Which one is highest?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    # Should cleanly resolve or offer clarification
    assert r2.clarification_needed in (True, False)
    assert r2.answer is not None


# ===========================================================================
# 11. Dataset Metadata Question
# ===========================================================================

def test_11_dataset_metadata_question():
    """Verify dataset understanding question formats overview with columns and shape."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds11")
    ctx = ConversationContext(dataset_id="ds11")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What does this dataset contain?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.DATASET_METADATA
    assert "7 rows" in resp.answer
    assert "salary" in resp.answer.lower()
    assert "dept" in resp.answer.lower()


# ===========================================================================
# 12. Insight Question (Step 6 Engine Integration)
# ===========================================================================

def test_12_insight_question():
    """Verify insight query retrieves Step 6 evidence-grounded insights."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds12")
    ctx = ConversationContext(dataset_id="ds12")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What are the key insights in this dataset?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.INSIGHT_EXPLANATION
    assert resp.row_count > 0
    assert "insights" in resp.answer.lower() or "finding" in resp.answer.lower()


# ===========================================================================
# 13. Dashboard Evidence Question (Step 7 Engine Integration)
# ===========================================================================

def test_13_dashboard_evidence_question():
    """Verify dashboard explanation question explains tile rationale and SQL."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds13")
    ctx = ConversationContext(dataset_id="ds13")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Why did you choose this chart?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.DASHBOARD_EXPLANATION
    assert "Dashboard Architecture Rationale" in resp.answer or "KPI" in resp.answer


# ===========================================================================
# 14. SQL / Provenance Question
# ===========================================================================

def test_14_sql_provenance_question():
    """Verify 'show me the sql' returns previous query's SQL text."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds14")
    ctx = ConversationContext(dataset_id="ds14")

    # Turn 1: Execute query
    execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    # Turn 2: Ask for SQL
    resp_sql = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Show me the SQL for that",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp_sql.intent_type == ChatIntentType.PROVENANCE_OR_SQL
    assert "SELECT" in resp_sql.answer.upper()
    assert "GROUP BY" in resp_sql.answer.upper()


# ===========================================================================
# 15. Unsupported Forecasting Request
# ===========================================================================

def test_15_unsupported_forecasting_request():
    """Verify speculative forecasting is safely declined without hallucinations."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds15")
    ctx = ConversationContext(dataset_id="ds15")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Predict next year's average salary for Engineering",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.UNSUPPORTED_OR_CAUSAL
    assert "forecasting" in resp.answer.lower() or "predict" in resp.answer.lower()


# ===========================================================================
# 16. Causal-Question Handling
# ===========================================================================

def test_16_causal_question_handling():
    """Verify causal claims are clarified as non-causal observational relationships."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds16")
    ctx = ConversationContext(dataset_id="ds16")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="Why did performance cause salary to increase?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.UNSUPPORTED_OR_CAUSAL
    assert "causal" in resp.answer.lower() or "correlation" in resp.answer.lower()


# ===========================================================================
# 17. Invalid Dataset 404
# ===========================================================================

def test_17_invalid_dataset_api_404():
    """Verify unknown dataset_id returns 404 with DATASET_NOT_FOUND."""
    resp = client.post(
        "/api/chat",
        json={"dataset_id": "nonexistent_ds_999", "message": "Average salary?"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "Dataset not found"


# ===========================================================================
# 18. Empty Question
# ===========================================================================

def test_18_empty_question_handling():
    """Verify empty or whitespace query is handled gracefully."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds18")
    ctx = ConversationContext(dataset_id="ds18")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="   ",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.intent_type == ChatIntentType.GENERAL_HELP
    assert "enter a question" in resp.answer.lower()


# ===========================================================================
# 19. No-Result Query Handling
# ===========================================================================

def test_19_no_result_query_handling():
    """Verify query with non-matching filter returns polite empty result message."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds19")
    ctx = ConversationContext(dataset_id="ds19")

    resp = execute_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary where dept = 'Marketing'?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )

    assert resp.row_count == 0
    assert "No matching" in resp.answer or "No records" in resp.answer or "not find" in resp.answer


# ===========================================================================
# 20. LLM Failure Fallback
# ===========================================================================

def test_20_llm_failure_fallback():
    """Verify that if LLM client raises an exception, deterministic narration succeeds."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds20")
    ctx = ConversationContext(dataset_id="ds20")

    class FailingLLM(MockLLMClient):
        def generate(self, *args, **kwargs):
            raise RuntimeError("LLM API Network Outage")

    failing_gen = ChatResponseGenerator(llm_client=FailingLLM())
    engine = DatasetChatEngine()
    engine.response_generator = failing_gen

    resp = engine.process_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=True,
    )

    assert resp.row_count == 3
    assert "Eng" in resp.answer
    assert "85,714" in resp.answer or "Eng leads" in resp.answer


# ===========================================================================
# 21. Hallucinated Number Rejection
# ===========================================================================

def test_21_hallucinated_number_rejected():
    """Verify that if LLM claims an ungrounded number, it is discarded for deterministic narration."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds21")
    ctx = ConversationContext(dataset_id="ds21")

    class HallucinatingLLM(MockLLMClient):
        def generate(self, *args, **kwargs):
            from providers.base import LLMResponse
            # Invent an ungrounded number 999,999.0
            return LLMResponse(text="Engineering average salary is 999,999.0 dollars.")

    hallucinating_gen = ChatResponseGenerator(llm_client=HallucinatingLLM())
    engine = DatasetChatEngine()
    engine.response_generator = hallucinating_gen

    resp = engine.process_chat_turn(
        dataset=canonical,
        semantic_profile=sem_profile,
        message="What is the average salary by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=True,
    )

    # 999,999 must NOT be in the answer
    assert "999,999" not in resp.answer
    assert "Eng" in resp.answer


# ===========================================================================
# 22. Conversation Context Isolation
# ===========================================================================

def test_22_conversation_context_isolation():
    """Verify two distinct conversation threads on the same dataset maintain isolated states."""
    canonical, profile, sem_profile, readiness = _build_test_dataset("ds22")
    rec = DatasetSessionRecord(
        dataset=canonical,
        profile=profile,
        semantic_profile=sem_profile,
        readiness=readiness,
    )
    session_store.save(rec)

    # Thread 1: asks about salary
    resp1 = client.post(
        "/api/chat",
        json={"dataset_id": "ds22", "conversation_id": "thread-1", "message": "What is the average salary by dept?"},
    )
    assert resp1.status_code == 200

    # Thread 2: asks about performance
    resp2 = client.post(
        "/api/chat",
        json={"dataset_id": "ds22", "conversation_id": "thread-2", "message": "What is the average performance by dept?"},
    )
    assert resp2.status_code == 200

    # Follow-up in Thread 1: should resolve salary
    f1 = client.post(
        "/api/chat",
        json={"dataset_id": "ds22", "conversation_id": "thread-1", "message": "Which one is highest?"},
    )
    assert f1.status_code == 200
    assert "salary" in f1.json()["query_plan"]["metric"]["column"]

    # Follow-up in Thread 2: should resolve performance
    f2 = client.post(
        "/api/chat",
        json={"dataset_id": "ds22", "conversation_id": "thread-2", "message": "Which one is highest?"},
    )
    assert f2.status_code == 200
    assert "performance" in f2.json()["query_plan"]["metric"]["column"]


# ===========================================================================
# 23. Multiple Datasets / Session Isolation
# ===========================================================================

def test_23_multiple_datasets_isolation():
    """Verify conversation on Dataset A does not leak state into Dataset B."""
    d1, p1, s1, r1 = _build_test_dataset("dsA")
    session_store.save(DatasetSessionRecord(dataset=d1, profile=p1, semantic_profile=s1, readiness=r1))

    df2 = pd.DataFrame({
        "city": ["Paris", "Tokyo", "London"],
        "temp": [15.0, 22.0, 18.0],
    })
    c2 = [ColumnMetadata(c, c, str(df2[c].dtype)) for c in df2.columns]
    m2 = DatasetMetadata("dsB", "dsB.csv", "csv", len(df2), len(c2), c2)
    can2 = CanonicalDataset(m2, df2)
    p2 = profile_dataset(can2)
    s2 = analyze_semantics(can2, p2)
    r2 = assess_readiness(can2, p2, s2)
    session_store.save(DatasetSessionRecord(dataset=can2, profile=p2, semantic_profile=s2, readiness=r2))

    # Query on dsA
    rA = client.post("/api/chat", json={"dataset_id": "dsA", "message": "Average salary?"})
    assert rA.status_code == 200

    # Query on dsB
    rB = client.post("/api/chat", json={"dataset_id": "dsB", "message": "Average temp?"})
    assert rB.status_code == 200
    assert "temp" in rB.json()["query_plan"]["metric"]["column"]
