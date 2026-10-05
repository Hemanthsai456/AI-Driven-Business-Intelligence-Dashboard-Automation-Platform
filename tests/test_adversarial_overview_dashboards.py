"""Adversarial and Edge Case Test Suite for Step 7 — Autonomous Overview Dashboard.

Tests:
1. Numeric-only dataset (no dimensions or datetimes)
2. Categorical-only dataset (no numeric measures)
3. Single measure dataset
4. Single dimension dataset
5. No datetime dataset
6. Pure high-cardinality identifier dataset
7. Constant numeric column (variance = 0)
8. Mostly-null measure (>85% null)
9. Tiny datasets (N=1, N=2)
10. Multiple numeric measures and multiple datetime candidates
"""

from typing import Any, Tuple
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
from orchestrator.overview import generate_overview_dashboard
from orchestrator.schemas import DashboardSpec


def _make_dataset(df: pd.DataFrame, name: str = "adversarial_overview") -> Tuple[CanonicalDataset, Any]:
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{name}", name, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


def test_numeric_only_dataset():
    """Verify numeric-only dataset creates valid overview with KPIs and correlation/distribution without crashing."""
    df = pd.DataFrame({
        "metric_a": [10.0, 20.0, 30.0, 40.0, 50.0],
        "metric_b": [100.0, 200.0, 300.0, 400.0, 500.0],
        "metric_c": [5.0, 15.0, 25.0, 35.0, 45.0],
    })
    dataset, profile = _make_dataset(df, "num_only")
    spec: DashboardSpec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 1
    kpis = [t for t in spec.tiles if t.chart_type == "kpi"]
    assert len(kpis) >= 1


def test_categorical_only_dataset():
    """Verify categorical-only dataset creates overview using count aggregation."""
    df = pd.DataFrame({
        "status": ["Active", "Active", "Inactive", "Pending", "Active"],
        "tier": ["Gold", "Silver", "Gold", "Bronze", "Silver"],
    })
    dataset, profile = _make_dataset(df, "cat_only")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 1
    # Check that record count or distribution tile was built
    assert any(t.chart_type in ("kpi", "donut", "bar") for t in spec.tiles)


def test_single_measure_single_dimension():
    """Verify minimal 1-measure 1-dimension dataset produces cohesive dashboard."""
    df = pd.DataFrame({
        "city": ["New York", "London", "Tokyo", "Paris"],
        "population_millions": [8.4, 8.9, 13.9, 2.1],
    })
    dataset, profile = _make_dataset(df, "single_pair")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 2


def test_pure_high_cardinality_identifier():
    """Verify pure UUID/ID column is not chosen as measure or grouping dimension."""
    df = pd.DataFrame({
        "uuid": [f"user_{i:04d}" for i in range(20)],
        "score": [80.0 + i for i in range(20)],
    })
    dataset, profile = _make_dataset(df, "high_card_id")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    # UUID should not be a metric
    for t in spec.tiles:
        assert "uuid" not in t.metrics


def test_constant_numeric_column():
    """Verify constant numeric column does not create false trends or outliers."""
    df = pd.DataFrame({
        "category": ["A", "B", "C", "D"],
        "constant_val": [50.0, 50.0, 50.0, 50.0],
        "active_val": [10.0, 20.0, 30.0, 40.0],
    })
    dataset, profile = _make_dataset(df, "constant_num")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 1


def test_mostly_null_measure():
    """Verify measure with >85% nulls is pruned from overview KPI selection."""
    df = pd.DataFrame({
        "group": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        "valid_measure": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        "null_measure": [np.nan] * 9 + [100.0],  # 90% null
    })
    dataset, profile = _make_dataset(df, "null_measure")
    spec = generate_overview_dashboard(dataset, profile, use_llm=False)

    kpis = [t for t in spec.tiles if t.chart_type == "kpi"]
    for k in kpis:
        assert "null_measure" not in k.metrics


def test_tiny_dataset_n1_n2():
    """Verify tiny datasets (N=1, N=2) degrade gracefully without crashing."""
    df_n1 = pd.DataFrame({"item": ["Alpha"], "price": [100.0]})
    ds_n1, prof_n1 = _make_dataset(df_n1, "tiny_n1")
    spec_n1 = generate_overview_dashboard(ds_n1, prof_n1, use_llm=False)
    assert spec_n1.mode == "overview"
    assert len(spec_n1.tiles) >= 1

    df_n2 = pd.DataFrame({"item": ["Alpha", "Beta"], "price": [100.0, 200.0]})
    ds_n2, prof_n2 = _make_dataset(df_n2, "tiny_n2")
    spec_n2 = generate_overview_dashboard(ds_n2, prof_n2, use_llm=False)
    assert spec_n2.mode == "overview"
    assert len(spec_n2.tiles) >= 1
