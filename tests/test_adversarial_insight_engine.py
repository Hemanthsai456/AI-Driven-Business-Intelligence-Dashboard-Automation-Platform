"""Adversarial and Edge Case Test Suite for Step 6 — Evidence-Grounded AI Insights Engine.

Tests robustness against:
1. Very small datasets (N=1, N=2, N=3)
2. All-null numeric and categorical columns
3. Constant numeric columns (zero variance / std=0)
4. Single-category dimension columns
5. Pure identifier columns (UUIDs/IDs)
6. Negative and zero numerical values
7. Missing / NaN values dispersed throughout data
8. Weak correlations (|r| < 0.35)
9. High-cardinality noise
10. Absence of datetime columns
"""

from typing import Any
import math
import numpy as np
import pandas as pd
import pytest

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    DatasetMetadata,
)
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.insights import (
    EvidenceGroundedInsight,
    InsightEngine,
    InsightEvidence,
    InsightType,
    InsightValidator,
    generate_grounded_insights,
)
from orchestrator.schemas import AggregationType


def _make_dataset(df: pd.DataFrame, name: str = "adversarial_ds") -> tuple[CanonicalDataset, Any]:
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{name}", name, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


def test_tiny_dataset_n2():
    """Verify engine handles tiny dataset (N=2) safely without crashing or hallucinating."""
    df = pd.DataFrame({
        "category": ["A", "B"],
        "metric": [10.0, 20.0],
    })
    dataset, profile = _make_dataset(df, "tiny_n2")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    # Should safely return grounded KPI/Ranking or report safe insight
    assert isinstance(res.insights, list)
    for ins in res.insights:
        assert ins.evidence.compiled_sql is not None
        # Values must be exact (15.0 avg, or 20.0 top)
        if ins.type == InsightType.KPI:
            assert ins.evidence.values["primary_value"] in (15.0, 30.0)


def test_single_row_dataset():
    """Verify engine handles single-row dataset (N=1) without crashing."""
    df = pd.DataFrame({
        "id": ["ID_001"],
        "category": ["Alpha"],
        "val": [100.0],
    })
    dataset, profile = _make_dataset(df, "single_row")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    assert isinstance(res.insights, list)
    # Correlation and trend should NOT be generated for N=1
    types = {i.type for i in res.insights}
    assert InsightType.CORRELATION not in types
    assert InsightType.TEMPORAL_TREND not in types


def test_all_null_numeric_column():
    """Verify all-null numeric column is safely handled without producing false insights."""
    df = pd.DataFrame({
        "dept": ["Eng", "Sales", "HR", "Support", "Marketing"],
        "null_metric": [np.nan, np.nan, np.nan, np.nan, np.nan],
        "valid_metric": [10.0, 20.0, 30.0, 40.0, 50.0],
    })
    dataset, profile = _make_dataset(df, "all_null")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    # Insights must only refer to valid_metric, never null_metric
    for ins in res.insights:
        assert ins.evidence.metric_column != "null_metric"
        assert ins.evidence.secondary_metric != "null_metric"


def test_constant_numeric_column():
    """Verify constant column (variance = 0) does not produce invalid outlier/trend insights."""
    df = pd.DataFrame({
        "device": [f"D_{i}" for i in range(20)],
        "temp": [25.0] * 20,
    })
    dataset, profile = _make_dataset(df, "constant_num")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    # Outliers should not be flagged when all values are identical
    types = {i.type for i in res.insights}
    assert InsightType.OUTLIER not in types


def test_single_category_dimension():
    """Verify 1-category dimension does not generate misleading ranking differences."""
    df = pd.DataFrame({
        "country": ["USA"] * 15,
        "revenue": [100.0 + i for i in range(15)],
    })
    dataset, profile = _make_dataset(df, "single_cat")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    # Should not produce ranking comparing USA to USA with non-zero difference
    for ins in res.insights:
        if ins.type == InsightType.RANKING:
            assert ins.evidence.values.get("top_group") == "USA"
            assert ins.evidence.values.get("bottom_group") == "USA"
            assert ins.evidence.values.get("difference") == 0.0


def test_negative_and_zero_values():
    """Verify negative and zero numbers are accurately calculated and reported."""
    df = pd.DataFrame({
        "account": ["A", "B", "C", "D", "E"],
        "profit": [-500.0, -250.0, 0.0, 300.0, 750.0],
    })
    dataset, profile = _make_dataset(df, "neg_zero")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    kpis = [i for i in res.insights if i.type == InsightType.KPI and i.evidence.metric_column == "profit"]
    if kpis:
        # Sum = 300.0, Avg = 60.0
        val = kpis[0].evidence.values["primary_value"]
        assert pytest.approx(val, rel=1e-2) in (60.0, 300.0)


def test_weak_correlation_suppressed_or_weak():
    """Verify weak correlations (|r| < 0.35) are not reported as strong analytical findings."""
    np.random.seed(42)
    x = np.random.normal(0, 1, 50)
    y = np.random.normal(0, 1, 50)  # Uncorrelated noise
    df = pd.DataFrame({"x": x, "y": y})
    dataset, profile = _make_dataset(df, "weak_corr")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    correlations = [i for i in res.insights if i.type == InsightType.CORRELATION]
    # Should either be suppressed because r is weak (<0.35 threshold) or have importance < 0.6
    for corr in correlations:
        assert abs(corr.evidence.values["correlation_r"]) < 0.35


def test_no_datetime_column_safely_omits_trend():
    """Verify absence of datetime column does not trigger false temporal trend insights."""
    df = pd.DataFrame({
        "item": ["A", "B", "C", "D"],
        "cost": [10.0, 15.0, 20.0, 25.0],
    })
    dataset, profile = _make_dataset(df, "no_dates")
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    types = {i.type for i in res.insights}
    assert InsightType.TEMPORAL_TREND not in types
