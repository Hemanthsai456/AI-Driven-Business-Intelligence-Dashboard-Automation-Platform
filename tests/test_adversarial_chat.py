"""Adversarial and Edge-Case Test Suite for Dataset Chat (Step 8 / Roadmap #7).

Covers edge cases and adversarial inputs:
1. Tiny dataset (1-2 rows)
2. All-null measure column
3. Constant measure column
4. Identifier-heavy dataset
5. Missing values in dimension and measure
6. Negative values in measure
7. Ambiguous metric (multiple candidate measures)
8. Ambiguous follow-up (unresolved metric/dimension candidates)
9. Malformed / whitespace-only question
10. Unsupported prediction request
11. Causal claim query
12. No matching rows filter
13. Very high cardinality dimension
14. Dataset with no numeric measures
15. Dataset with no datetime column
16. Multiple possible candidate measures
"""

import numpy as np
import pandas as pd
import pytest

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
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


def _build_adv_dataset(df: pd.DataFrame, dataset_id: str = "adv_ds"):
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(dataset_id, f"{dataset_id}.csv", "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile, apply_roles=True)
    readiness = SchemaValidator().validate(dataset, profile, sem_profile)
    return dataset, profile, sem_profile, readiness


# ===========================================================================
# 1. Tiny Dataset (2 rows)
# ===========================================================================

def test_adversarial_tiny_dataset():
    df = pd.DataFrame({"category": ["Alpha", "Beta"], "amount": [100.0, 200.0]})
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "tiny_ds")
    ctx = ConversationContext(dataset_id="tiny_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the average amount?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 1
    assert "150" in resp.answer


# ===========================================================================
# 2. All-Null Measure
# ===========================================================================

def test_adversarial_all_null_measure():
    df = pd.DataFrame({"category": ["A", "B", "C"], "score": [np.nan, np.nan, np.nan]})
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "null_ds")
    ctx = ConversationContext(dataset_id="null_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the average score by category?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 0 or "NULL" in str(resp.warnings) or "could not execute" in resp.answer.lower() or "no matching" in resp.answer.lower()


# ===========================================================================
# 3. Constant Measure
# ===========================================================================

def test_adversarial_constant_measure():
    df = pd.DataFrame({"dept": ["HR", "Sales", "Eng"], "bonus": [500.0, 500.0, 500.0]})
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "const_ds")
    ctx = ConversationContext(dataset_id="const_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the average bonus by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.answer is not None
    assert resp.intent_type == ChatIntentType.ANALYTICAL_QUERY


# ===========================================================================
# 4. Identifier-Heavy Dataset
# ===========================================================================

def test_adversarial_identifier_heavy_dataset():
    df = pd.DataFrame({
        "id1": [f"ID_{i}" for i in range(10)],
        "id2": [f"UUID_{i*7}" for i in range(10)],
        "category": ["A", "B"] * 5,
        "amount": [10.0 * i for i in range(10)],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "id_ds")
    ctx = ConversationContext(dataset_id="id_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the total amount by category?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 2
    assert resp.compiled_sql is not None


# ===========================================================================
# 5. Missing Values in Dimension and Measure
# ===========================================================================

def test_adversarial_missing_values():
    df = pd.DataFrame({
        "dept": ["HR", None, "Eng", "Sales", None],
        "salary": [50000, 60000, None, 80000, 90000],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "miss_ds")
    ctx = ConversationContext(dataset_id="miss_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the average salary by dept?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count > 0
    assert resp.compiled_sql is not None


# ===========================================================================
# 6. Negative Values in Measure
# ===========================================================================

def test_adversarial_negative_values():
    df = pd.DataFrame({
        "quarter": ["Q1", "Q2", "Q3", "Q4"],
        "net_profit": [-5000.0, 12000.0, -2500.0, 8000.0],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "neg_ds")
    ctx = ConversationContext(dataset_id="neg_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the total net profit by quarter?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 4
    assert resp.compiled_sql is not None


# ===========================================================================
# 7. Ambiguous Metric / Disambiguation
# ===========================================================================

def test_adversarial_ambiguous_metric():
    df = pd.DataFrame({
        "region": ["North", "South", "East", "West"],
        "base_salary": [50000, 60000, 70000, 80000],
        "bonus_salary": [5000, 6000, 7000, 8000],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "ambig_m_ds")
    ctx = ConversationContext(dataset_id="ambig_m_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="Show average salary",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    # Either executes with resolved salary candidate or asks for clarification
    assert resp.answer is not None
    assert resp.intent_type in (ChatIntentType.ANALYTICAL_QUERY, ChatIntentType.AMBIGUOUS_CLARIFICATION)


# ===========================================================================
# 8. Ambiguous Follow-Up
# ===========================================================================

def test_adversarial_ambiguous_followup():
    df = pd.DataFrame({
        "region": ["North", "South"],
        "dept": ["HR", "Eng"],
        "sales": [100, 200],
        "units": [10, 20],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "ambig_fu_ds")
    ctx = ConversationContext(dataset_id="ambig_fu_ds")

    # Turn 1: Scalar without dimension
    r1 = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is total sales?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert r1.row_count == 1

    # Turn 2: Follow-up without specifying dimension ("which is highest?")
    r2 = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="Which one is highest?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert r2.clarification_needed is True or r2.row_count >= 1


# ===========================================================================
# 9. Empty and Whitespace Queries
# ===========================================================================

def test_adversarial_empty_queries():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "empty_ds")
    ctx = ConversationContext(dataset_id="empty_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="   ",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert "enter a question" in resp.answer.lower() or "help" in resp.answer.lower() or "empty" in resp.answer.lower()


# ===========================================================================
# 10. Unsupported Prediction & Causal
# ===========================================================================

def test_adversarial_unsupported_prediction_and_causal():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "guard_ds")
    ctx = ConversationContext(dataset_id="guard_ds")

    r_pred = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="Will sales increase next quarter?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert r_pred.intent_type == ChatIntentType.UNSUPPORTED_OR_CAUSAL
    assert "forecasting" in r_pred.answer.lower()

    r_causal = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="Why did x cause y to drop?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert r_causal.intent_type == ChatIntentType.UNSUPPORTED_OR_CAUSAL
    assert "causal" in r_causal.answer.lower()


# ===========================================================================
# 11. No Matching Rows Filter
# ===========================================================================

def test_adversarial_no_matching_rows():
    df = pd.DataFrame({"dept": ["HR", "Sales"], "salary": [50000, 60000]})
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "no_rows_ds")
    ctx = ConversationContext(dataset_id="no_rows_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the average salary where dept = 'Marketing'?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 0
    assert "no matching" in resp.answer.lower() or "not find" in resp.answer.lower() or "no records" in resp.answer.lower()


# ===========================================================================
# 12. High-Cardinality Dimension
# ===========================================================================

def test_adversarial_high_cardinality_dimension():
    df = pd.DataFrame({
        "city": [f"city_{i % 50}" for i in range(500)],
        "score": [float(i % 100) for i in range(500)],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "card_ds")
    ctx = ConversationContext(dataset_id="card_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="Show top 5 city by average score",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 5


# ===========================================================================
# 13. Dataset with No Numeric Measures
# ===========================================================================

def test_adversarial_no_numeric_measures():
    df = pd.DataFrame({
        "status": ["active", "pending", "active", "closed"],
        "category": ["A", "B", "A", "B"],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "nonum_ds")
    ctx = ConversationContext(dataset_id="nonum_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What columns are in this dataset?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.intent_type == ChatIntentType.DATASET_METADATA
    assert "status" in resp.answer.lower()
    assert "category" in resp.answer.lower()


# ===========================================================================
# 14. Dataset with No Datetime Column
# ===========================================================================

def test_adversarial_no_datetime_column():
    df = pd.DataFrame({
        "product": ["Widget A", "Widget B", "Widget C"],
        "revenue": [1500.0, 2200.0, 1800.0],
    })
    dataset, profile, sem_profile, readiness = _build_adv_dataset(df, "nodate_ds")
    ctx = ConversationContext(dataset_id="nodate_ds")

    resp = execute_chat_turn(
        dataset=dataset,
        semantic_profile=sem_profile,
        message="What is the average revenue by product?",
        context=ctx,
        readiness=readiness,
        data_profile=profile,
        use_llm=False,
    )
    assert resp.row_count == 3
    assert resp.compiled_sql is not None
