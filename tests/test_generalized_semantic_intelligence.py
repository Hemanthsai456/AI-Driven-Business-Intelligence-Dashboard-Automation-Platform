"""Unit tests for Step 2 — Generalized Semantic Intelligence.

Tests cover:
1. Identifier vs Measure disambiguation (high cardinality continuous measures != identifier)
2. Sequential integer indices vs continuous measures
3. Multi-signal aggregation category & default aggregation inference (SUM vs AVG)
4. Conflict recording and explainability
5. Invariance, determinism, and JSON serialization
"""

import json
from typing import Tuple
import pandas as pd
import pytest

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DatasetMetadata,
    DataProfile,
)
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
    SemanticAnalyzer,
    analyze_semantics,
)


def _make_dataset(df: pd.DataFrame, name: str = "test_ds") -> Tuple[CanonicalDataset, DataProfile]:
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds-{name}", name, "pandas", len(df), len(cols), cols)
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)
    return canonical, profile


# ---------------------------------------------------------------------------
# Part B & C: Identifier vs Continuous Numeric Measure Detection
# ---------------------------------------------------------------------------


def test_high_cardinality_salary_is_measure_not_identifier():
    """Verify high-cardinality continuous salary column is MEASURE with AVG default and conflict recorded."""
    # 100 rows with 98 unique values (98% uniqueness)
    salaries = [50000.0 + i * 1234.56 for i in range(98)] + [50000.0, 51234.56]
    df = pd.DataFrame({"salary": salaries, "emp_code": [f"EMP_{i:04d}" for i in range(100)]})
    canonical, profile = _make_dataset(df, "salary_ds")

    sem = analyze_semantics(canonical, profile)
    ev_sal = sem.get_evidence("salary")
    assert ev_sal is not None
    assert ev_sal.candidate_role == ColumnRole.MEASURE
    assert ev_sal.aggregation_default == "AVG"
    assert ev_sal.aggregation_category == "INTENSIVE"
    assert len(ev_sal.conflicts) > 0
    assert any("cardinality ratio" in c.lower() for c in ev_sal.conflicts)

    ev_code = sem.get_evidence("emp_code")
    assert ev_code is not None
    assert ev_code.candidate_role == ColumnRole.IDENTIFIER


def test_unseen_continuous_numeric_measure_without_keywords():
    """Verify an unseen column name with continuous decimal values is classified as MEASURE."""
    vals = [10.23, 15.67, 8.91, 14.52, 99.41, 102.34, 45.12, 67.89, 23.45, 56.78]
    df = pd.DataFrame({"obs_sensor_x": vals})
    canonical, profile = _make_dataset(df, "sensor_x")

    sem = analyze_semantics(canonical, profile)
    ev = sem.get_evidence("obs_sensor_x")
    assert ev is not None
    assert ev.candidate_role == ColumnRole.MEASURE
    assert ev.aggregation_default == "AVG"
    assert ev.aggregation_category == "INTENSIVE"


def test_sequential_integer_index_is_identifier():
    """Verify dense sequential integer sequence (1..N) without measure tokens is IDENTIFIER."""
    df = pd.DataFrame({"row_id": list(range(1, 101)), "val": [10.5] * 100})
    canonical, profile = _make_dataset(df, "seq_idx")

    sem = analyze_semantics(canonical, profile)
    ev = sem.get_evidence("row_id")
    assert ev is not None
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.sub_role == "PRIMARY_KEY"


def test_uuid_identifier_detection():
    """Verify UUID formatted strings are IDENTIFIER with HIGH confidence."""
    uuids = [
        "123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-426614174001",
        "123e4567-e89b-12d3-a456-426614174002",
        "123e4567-e89b-12d3-a456-426614174003",
    ]
    df = pd.DataFrame({"session_token": uuids})
    canonical, profile = _make_dataset(df, "uuid_ds")

    sem = analyze_semantics(canonical, profile)
    ev = sem.get_evidence("session_token")
    assert ev is not None
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.confidence_level == "HIGH"


# ---------------------------------------------------------------------------
# Part D: Aggregation Semantics
# ---------------------------------------------------------------------------


def test_additive_measure_aggregation_sum():
    """Verify revenue, sales, profit, cost, spend are classified as ADDITIVE -> SUM."""
    df = pd.DataFrame({
        "total_revenue": [1000.0, 2500.0, 3200.0, 4100.0],
        "profit": [200.0, 500.0, 700.0, 900.0],
        "ad_spend": [50.0, 120.0, 150.0, 200.0],
    })
    canonical, profile = _make_dataset(df, "financial_ds")

    sem = analyze_semantics(canonical, profile)
    for col in ["total_revenue", "profit", "ad_spend"]:
        ev = sem.get_evidence(col)
        assert ev.candidate_role == ColumnRole.MEASURE
        assert ev.aggregation_category == "ADDITIVE"
        assert ev.aggregation_default == "SUM"


def test_discrete_count_measure_aggregation_sum():
    """Verify quantity, units, volume, count are classified as COUNT -> SUM."""
    df = pd.DataFrame({
        "order_quantity": [2, 5, 1, 10, 3],
        "units_sold": [100, 250, 80, 400, 120],
    })
    canonical, profile = _make_dataset(df, "counts_ds")

    sem = analyze_semantics(canonical, profile)
    for col in ["order_quantity", "units_sold"]:
        ev = sem.get_evidence(col)
        assert ev.candidate_role == ColumnRole.MEASURE
        assert ev.aggregation_category == "COUNT"
        assert ev.aggregation_default == "SUM"


def test_intensive_physical_measure_aggregation_avg():
    """Verify temperature, pressure, humidity, speed, voltage are classified as INTENSIVE -> AVG."""
    df = pd.DataFrame({
        "temperature": [22.4, 23.1, 21.8, 24.5, 22.0],
        "pressure": [101.3, 101.5, 101.2, 100.9, 101.4],
        "wind_speed": [12.5, 15.0, 9.8, 14.2, 11.0],
    })
    canonical, profile = _make_dataset(df, "iot_env_ds")

    sem = analyze_semantics(canonical, profile)
    for col in ["temperature", "pressure", "wind_speed"]:
        ev = sem.get_evidence(col)
        assert ev.candidate_role == ColumnRole.MEASURE
        assert ev.aggregation_category == "INTENSIVE"
        assert ev.aggregation_default == "AVG"


def test_duration_measure_aggregation_avg():
    """Verify delivery_time, length_of_stay, latency, wait_time are classified as DURATION -> AVG."""
    df = pd.DataFrame({
        "delivery_time": [2.5, 4.1, 1.8, 3.2, 5.0],
        "length_of_stay": [4.0, 7.0, 2.0, 10.0, 5.0],
        "api_latency": [120.5, 95.2, 310.4, 150.0, 88.6],
    })
    canonical, profile = _make_dataset(df, "duration_ds")

    sem = analyze_semantics(canonical, profile)
    for col in ["delivery_time", "length_of_stay", "api_latency"]:
        ev = sem.get_evidence(col)
        assert ev.candidate_role == ColumnRole.MEASURE
        assert ev.aggregation_category == "DURATION"
        assert ev.aggregation_default == "AVG"


def test_score_and_marks_measure_aggregation_avg():
    """Verify marks, score, performance_score, satisfaction are classified as SCORE -> AVG."""
    df = pd.DataFrame({
        "marks": [85.0, 92.0, 78.0, 65.0, 88.0],
        "performance_score": [7.4, 8.9, 6.2, 9.1, 7.8],
        "csat_score": [4.5, 4.8, 3.9, 5.0, 4.2],
    })
    canonical, profile = _make_dataset(df, "scores_ds")

    sem = analyze_semantics(canonical, profile)
    for col in ["marks", "performance_score", "csat_score"]:
        ev = sem.get_evidence(col)
        assert ev.candidate_role == ColumnRole.MEASURE
        assert ev.aggregation_category == "SCORE"
        assert ev.aggregation_default == "AVG"


def test_rate_percentage_measure_aggregation_avg():
    """Verify margin_pct, discount_rate, conversion_rate are classified as RATE -> AVG."""
    df = pd.DataFrame({
        "profit_margin_pct": [0.15, 0.22, 0.18, 0.25],
        "discount_rate": [0.05, 0.10, 0.0, 0.15],
    })
    canonical, profile = _make_dataset(df, "rates_ds")

    sem = analyze_semantics(canonical, profile)
    for col in ["profit_margin_pct", "discount_rate"]:
        ev = sem.get_evidence(col)
        assert ev.candidate_role == ColumnRole.MEASURE
        assert ev.aggregation_category == "RATE"
        assert ev.aggregation_default == "AVG"


# ---------------------------------------------------------------------------
# Part F & G: Conflicts, Confidence, and Integrity
# ---------------------------------------------------------------------------


def test_conflicts_field_serialization():
    """Verify conflicts field is preserved and JSON serializable in semantic profile dictionary."""
    df = pd.DataFrame({"unique_measure": [10.1 + i * 2.3 for i in range(50)]})
    canonical, profile = _make_dataset(df, "conflicts_ds")

    sem = analyze_semantics(canonical, profile)
    d = sem.to_dict()

    assert "column_evidences" in d
    assert "unique_measure" in d["column_evidences"]
    col_dict = d["column_evidences"]["unique_measure"]
    assert "conflicts" in col_dict
    assert isinstance(col_dict["conflicts"], list)
    assert "aggregation_default" in col_dict
    assert col_dict["aggregation_default"] == "AVG"
    assert "aggregation_category" in col_dict

    # Valid JSON string test
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_input_dataframe_immutability():
    """Verify semantic analyzer does not mutate original input dataframe."""
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "salary": [50000.0, 60000.0, 70000.0],
        "dept": ["IT", "HR", "Sales"],
    })
    df_copy = df.copy(deep=True)
    canonical, profile = _make_dataset(df, "immutability_ds")

    analyze_semantics(canonical, profile)
    pd.testing.assert_frame_equal(df, df_copy)
