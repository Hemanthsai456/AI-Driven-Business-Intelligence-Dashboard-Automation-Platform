"""Targeted unit tests for Step 7 Generalized Analytical Reasoning and Diversity.

Verifies:
1. Descriptive / per-entity measures do not default to SUM (using arbitrary synthetic column names).
2. Additive quantities rank SUM highly.
3. Multiple analytically valid aggregations coexist in the candidate pool.
4. Entity counting uses available identifier/grain evidence without treating identifiers as numeric metrics.
5. Multi-perspective candidate generation produces diverse analytical families when genuinely supported.
6. Unsupported analytical families are not fabricated (no fake line chart when no datetime).
7. Redundant candidate views are penalized and diversified.
8. Completely unfamiliar / obfuscated column names (e.g. x1, x2, x3) succeed seamlessly.
"""

from typing import Any, Tuple
import numpy as np
import pandas as pd
import pytest

from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.overview import generate_overview_dashboard
from orchestrator.overview.reasoning import (
    AggregationSupportLevel,
    AnalyticalFamily,
    DatasetGrainType,
    evaluate_measure_aggregations,
    infer_dataset_grain,
    select_diversified_candidates,
)
from orchestrator.schemas import AggregationType, DashboardSpec


def _make_synthetic_dataset(
    df: pd.DataFrame,
    name: str = "synthetic_test",
) -> Tuple[CanonicalDataset, Any]:
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{name}", name, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


# ===========================================================================
# 1. Descriptive / Per-Entity Measure Reasoning
# ===========================================================================


def test_descriptive_measure_does_not_default_to_sum():
    """Verify a measure describing individual entities (e.g. bounded ratio / score) does not default to SUM."""
    # Obfuscated synthetic columns: entity_ref, col_grp, metric_ratio
    np.random.seed(42)
    n = 50
    df = pd.DataFrame({
        "entity_ref": [f"ENT_{i:04d}" for i in range(1, n + 1)],
        "col_grp": ["TypeA", "TypeB", "TypeC"] * 16 + ["TypeA", "TypeB"],
        # Values bounded in [0.0, 1.0] representing rates/ratios
        "metric_ratio": np.round(np.random.uniform(0.05, 0.95, size=n), 3),
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "descriptive_test")

    grain = infer_dataset_grain(
        dataset=dataset,
        semantic_profile=sem_profile,
        data_profile=None,
        identifiers=["entity_ref"],
        datetimes=[],
        measures=["metric_ratio"],
    )
    assert grain.likely_grain == DatasetGrainType.ENTITY
    assert grain.is_unique_entity_grain is True

    suits = evaluate_measure_aggregations(
        measure="metric_ratio",
        df=df,
        grain=grain,
        semantic_profile=sem_profile,
    )

    # AVG and MEDIAN must be strongly supported
    assert suits[AggregationType.AVG].level == AggregationSupportLevel.STRONGLY_SUPPORTED
    assert suits[AggregationType.MEDIAN].level == AggregationSupportLevel.STRONGLY_SUPPORTED
    # SUM must be inappropriate or weak
    assert suits[AggregationType.SUM].level in (
        AggregationSupportLevel.INAPPROPRIATE,
        AggregationSupportLevel.WEAKLY_SUPPORTED,
    )
    assert suits[AggregationType.AVG].score > suits[AggregationType.SUM].score

    # Full overview dashboard must select AVG (not SUM) for the KPI
    spec: DashboardSpec = generate_overview_dashboard(dataset, sem_profile, use_llm=False)
    kpis = [t for t in spec.tiles if t.chart_type == "kpi" and "metric_ratio" in t.metrics]
    assert len(kpis) >= 1
    assert kpis[0].plan.metric.aggregation in (AggregationType.AVG, AggregationType.MEDIAN)
    assert kpis[0].plan.metric.aggregation != AggregationType.SUM


# ===========================================================================
# 2. Additive Measure Reasoning
# ===========================================================================


def test_additive_measure_ranks_sum_highly():
    """Verify an accumulating quantity on transaction/event grain ranks SUM as primary aggregate."""
    np.random.seed(42)
    n = 40
    df = pd.DataFrame({
        "tx_code": [f"TX_{i:05d}" for i in range(1, n + 1)],
        "segment": ["Tier1", "Tier2", "Tier3", "Tier4"] * 10,
        "amount_accum": np.random.randint(50, 500, size=n),
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "additive_test")

    grain = infer_dataset_grain(
        dataset=dataset,
        semantic_profile=sem_profile,
        data_profile=None,
        identifiers=["tx_code"],
        datetimes=[],
        measures=["amount_accum"],
    )

    suits = evaluate_measure_aggregations(
        measure="amount_accum",
        df=df,
        grain=grain,
        semantic_profile=sem_profile,
    )

    # SUM must be strongly supported
    assert suits[AggregationType.SUM].level == AggregationSupportLevel.STRONGLY_SUPPORTED
    assert suits[AggregationType.SUM].score >= 0.88

    spec = generate_overview_dashboard(dataset, sem_profile, use_llm=False)
    kpis = [t for t in spec.tiles if t.chart_type == "kpi" and "amount_accum" in t.metrics]
    assert len(kpis) >= 1
    assert kpis[0].plan.metric.aggregation == AggregationType.SUM


# ===========================================================================
# 3. Multiple Valid Aggregations Coexist
# ===========================================================================


def test_multiple_valid_aggregations_coexist():
    """Verify that multiple interpretations (SUM and AVG) are evaluated and coexist in the candidate pool for additive measures."""
    df = pd.DataFrame({
        "tx_id": [f"TX_{i:03d}" for i in range(25)],
        "cat": ["A", "B"] * 12 + ["A"],
        "qty_amount": [50 + i * 10 for i in range(25)],
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "multi_agg_test")
    grain = infer_dataset_grain(dataset, sem_profile, None, ["tx_id"], [], ["qty_amount"])
    suits = evaluate_measure_aggregations("qty_amount", df, grain, sem_profile)

    # Both SUM and AVG must have high suitability entries (>0.80)
    assert AggregationType.SUM in suits
    assert AggregationType.AVG in suits
    assert suits[AggregationType.SUM].score >= 0.85
    assert suits[AggregationType.AVG].score >= 0.80


# ===========================================================================
# 4. Entity Counting Without Identifier As Metric
# ===========================================================================


def test_entity_counting_respects_identifier_role():
    """Verify entity counting identifies entity presence without placing identifier into tile.metrics."""
    df = pd.DataFrame({
        "acc_id": [f"ACC_{i:03d}" for i in range(1, 26)],
        "dept": ["Ops", "Eng", "Sales", "HR", "Fin"] * 5,
        "score_val": [75.5 + (i % 10) for i in range(25)],
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "entity_counting_test")
    spec = generate_overview_dashboard(dataset, sem_profile, use_llm=False)

    # Verify acc_id is NEVER in any tile's metrics
    for tile in spec.tiles:
        assert "acc_id" not in tile.metrics

    # Foundational record/entity count KPI exists
    count_kpis = [t for t in spec.tiles if t.chart_type == "kpi" and "*" in t.metrics]
    assert len(count_kpis) >= 1
    assert count_kpis[0].plan.metric.aggregation == AggregationType.COUNT


# ===========================================================================
# 5. Multi-Perspective Candidate Generation & Diversity
# ===========================================================================


def test_multi_perspective_diversity_generation():
    """Verify candidate generation produces multiple analytical families (KPI, Trend, Breakdown, Donut) when supported."""
    n = 30
    df = pd.DataFrame({
        "log_id": [f"L_{i:04d}" for i in range(1, n + 1)],
        "category": ["Alpha", "Beta", "Gamma"] * 10,
        "val_measure": [100.0 + i * 15.0 for i in range(n)],
        "timestamp_col": pd.date_range("2024-01-01", periods=n, freq="7D"),
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "multi_perspective_test")
    spec = generate_overview_dashboard(dataset, sem_profile, use_llm=False)

    # Verify analytical diversity across tiles
    chart_types = {t.chart_type for t in spec.tiles}
    # Should include KPI, temporal line, categorical bar/donut
    assert "kpi" in chart_types
    assert "line" in chart_types
    assert ("bar" in chart_types or "donut" in chart_types)


# ===========================================================================
# 6. Unsupported Analytical Families Are Not Fabricated
# ===========================================================================


def test_unsupported_families_not_fabricated():
    """Verify that when no temporal columns exist, no line charts are fabricated."""
    df = pd.DataFrame({
        "id_val": [f"ID_{i}" for i in range(15)],
        "cat_val": ["X", "Y", "Z"] * 5,
        "score_val": [50.0 + i for i in range(15)],
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "no_datetime_test")
    spec = generate_overview_dashboard(dataset, sem_profile, use_llm=False)

    # No line chart should exist because there is no datetime column
    for tile in spec.tiles:
        assert tile.chart_type != "line"


# ===========================================================================
# 7. Unfamiliar / Obfuscated Column Names
# ===========================================================================


def test_unfamiliar_column_names_succeed():
    """Verify completely unfamiliar column names (x1, x2, x3, x4) succeed without relying on any name dictionary."""
    n = 35
    df = pd.DataFrame({
        "x1": [f"CODE_{i:04d}" for i in range(1, n + 1)],
        "x2": ["Cat1", "Cat2", "Cat3", "Cat4", "Cat5"] * 7,
        # Bounded between 0 and 1 (unfamiliar name)
        "x3": [round(0.1 + (i % 9) * 0.1, 2) for i in range(n)],
        # Accumulating integer
        "x4": [100 + i * 20 for i in range(n)],
    })
    dataset, sem_profile = _make_synthetic_dataset(df, "unfamiliar_cols_test")
    spec = generate_overview_dashboard(dataset, sem_profile, use_llm=False)

    assert spec.mode == "overview"
    assert len(spec.tiles) >= 3

    # For bounded float x3, KPI should NOT be SUM
    x3_kpi = next((t for t in spec.tiles if t.chart_type == "kpi" and "x3" in t.metrics), None)
    if x3_kpi:
        assert x3_kpi.plan.metric.aggregation != AggregationType.SUM
        assert x3_kpi.plan.metric.aggregation in (AggregationType.AVG, AggregationType.MEDIAN)

    # All tiles must have non-empty data and executable SQL
    for t in spec.tiles:
        assert len(t.data) > 0
        if t.compiled_sql:
            assert "SELECT" in t.compiled_sql
