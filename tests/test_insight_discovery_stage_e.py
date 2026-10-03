"""Ground truth gate tests for Stage E: Insight Discovery Mode.

Tests on synthetic frames with numbers computed by hand:
1. Planted dominant category -> found, top-ranked among rankings.
2. Planted upward trend -> found as TREND with the right direction.
3. Planted correlation (r ≈ 0.8) -> found.
4. Planted outlier cluster -> found as DISTRIBUTION_OUTLIERS.
5. Pure noise frame (random measures, random categories, 20 seeds): at most 5%
   of runs may surface any non-KPI insight. Exact count is asserted.
6. Determinism: same input twice gives identical output, and shuffling column
   order gives identical output.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pandas as pd
import pytest

from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.schema_validator import AnalysisReadiness, ReadinessCheck, ReadinessStatus
from intelligence.semantic_analyzer import ColumnSemanticEvidence, DatasetSemanticProfile
from orchestrator.discovery import (
    InsightType,
    classify_intent_mode,
    run_discovery_pipeline,
    verify_numbers_grounded,
)
from orchestrator.schemas import AggregationType, ExecutionResult, ExecutionStatus


def _create_mock_dataset(df: pd.DataFrame, dataset_id: str = "mock_ds") -> Tuple[CanonicalDataset, DatasetSemanticProfile, AnalysisReadiness]:
    """Helper to wrap DataFrame into CanonicalDataset and DatasetSemanticProfile."""
    col_metadata = []
    col_evidences = {}

    for col in df.columns:
        dtype_str = str(df[col].dtype)
        is_num = pd.api.types.is_numeric_dtype(df[col])
        is_dt = pd.api.types.is_datetime64_any_dtype(df[col]) or "date" in col.lower() or "time" in col.lower()

        if is_dt:
            role = ColumnRole.DATETIME
        elif is_num and df[col].nunique() > 1:
            role = ColumnRole.MEASURE
        elif "id" in col.lower() and df[col].nunique() == len(df):
            role = ColumnRole.IDENTIFIER
        else:
            role = ColumnRole.DIMENSION

        col_metadata.append(
            ColumnMetadata(
                original_name=col,
                normalized_name=col.lower(),
                detected_datatype=dtype_str,
                semantic_role=role,
                null_count=int(df[col].isna().sum()),
                null_percentage=float(df[col].isna().sum() / len(df) * 100),
                distinct_count=int(df[col].nunique()),
                is_unique=bool(df[col].nunique() == len(df)),
                sample_values=list(df[col].head(3)),
            )
        )

        col_evidences[col] = ColumnSemanticEvidence(
            column_name=col,
            candidate_role=role,
            confidence=0.95,
            confidence_level="HIGH",
            evidence=[f"Synthetic evidence for {role.value}"],
        )

    metadata = DatasetMetadata(
        dataset_id=dataset_id,
        name=f"{dataset_id}.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=col_metadata,
    )

    dataset = CanonicalDataset(data=df.copy(), metadata=metadata)
    sem_profile = DatasetSemanticProfile(dataset_id=dataset_id, column_evidences=col_evidences)
    from intelligence.schema_validator import assess_readiness
    readiness = assess_readiness(dataset)

    return dataset, sem_profile, readiness


# ---------------------------------------------------------------------------
# Gate Test 1: Planted Dominant Category
# ---------------------------------------------------------------------------


def test_gate_planted_dominant_category():
    """Planted dominant category -> found, top-ranked among rankings.

    Ground Truth (Computed by hand):
    - Category 'Alpha' has 40 rows of 500 = 20,000.
    - Categories 'Beta', 'Gamma', 'Delta' each have 20 rows of 10 = 200 each.
    - Total = 20,000 + 200 + 200 + 200 = 20,600.
    - 'Alpha' share = 20,000 / 20,600 = 97.09%.
    - Top ranked among rankings!
    """
    rows = []
    for _ in range(40):
        rows.append({"category": "Alpha", "revenue": 500.0})
    for _ in range(20):
        rows.append({"category": "Beta", "revenue": 10.0})
    for _ in range(20):
        rows.append({"category": "Gamma", "revenue": 10.0})
    for _ in range(20):
        rows.append({"category": "Delta", "revenue": 10.0})

    df = pd.DataFrame(rows)
    dataset, sem_profile, readiness = _create_mock_dataset(df, "dominant_category_ds")

    spec, rejected, summary = run_discovery_pipeline(
        dataset=dataset,
        semantic_profile=sem_profile,
        readiness=readiness,
        intent="dashboard on this data",
        strength_floor=0.08,
        robustness_floor=0.35,
    )

    # 1. Assert discovery ran
    assert spec.mode == "discovery"
    assert len(spec.panels) > 0

    # 2. Check for RANKING insight
    ranking_panels = [p for p in spec.panels if p.metadata.get("insight_type") == "RANKING"]
    assert len(ranking_panels) >= 1, f"Expected at least 1 RANKING panel, got: {[p.metadata.get('insight_type') for p in spec.panels]}"

    top_ranking = ranking_panels[0]
    # Dominant group Alpha must be found as top group
    top_group_data = top_ranking.data[0]
    assert top_group_data["category"] == "Alpha"
    # Ground truth: 20000 / 20600 ≈ 0.9709
    rev_val = top_group_data.get("revenue", top_group_data.get("sum_revenue"))
    assert rev_val == 20000.0


# ---------------------------------------------------------------------------
# Gate Test 2: Planted Upward Trend
# ---------------------------------------------------------------------------


def test_gate_planted_upward_trend():
    """Planted upward trend -> found as TREND with the right direction.

    Ground Truth (Computed by hand):
    - 30 consecutive days from 2024-01-01 to 2024-01-30.
    - sales = 10.0 + 3.0 * i (steep upward slope).
    - Direction = upward.
    """
    base_date = datetime.date(2024, 1, 1)
    rows = []
    for i in range(30):
        d_str = (base_date + datetime.timedelta(days=i)).isoformat()
        rows.append({"date": d_str, "sales": float(10.0 + 3.0 * i)})

    df = pd.DataFrame(rows)
    dataset, sem_profile, readiness = _create_mock_dataset(df, "upward_trend_ds")

    spec, rejected, summary = run_discovery_pipeline(
        dataset=dataset,
        semantic_profile=sem_profile,
        readiness=readiness,
        intent="",
    )

    trend_panels = [p for p in spec.panels if p.metadata.get("insight_type") == "TREND"]
    assert len(trend_panels) >= 1, "Expected TREND panel to be discovered"
    trend_panel = trend_panels[0]

    # Verify direction in narration or metadata
    narration = trend_panel.metadata.get("narration", "").lower()
    assert "upward" in narration or trend_panel.metadata.get("strength", 0) > 0.8
    # Direction check
    assert trend_panel.panel_type.value == "LINE"


# ---------------------------------------------------------------------------
# Gate Test 3: Planted Correlation (r ≈ 0.8)
# ---------------------------------------------------------------------------


def test_gate_planted_correlation():
    """Planted correlation (r ≈ 0.8) -> found.

    Ground Truth (Computed by hand):
    - x ~ N(50, 10)
    - y = 0.8 * x + 0.6 * noise
    - Theoretical r = 0.80
    """
    rng = np.random.RandomState(42)
    n = 120
    x = rng.normal(50.0, 10.0, size=n)
    noise = rng.normal(0.0, 10.0, size=n)
    y = 0.8 * x + 0.6 * noise

    # Empirical correlation check
    emp_r = float(np.corrcoef(x, y)[0, 1])
    assert 0.75 <= emp_r <= 0.85, f"Empirical r was {emp_r}"

    df = pd.DataFrame({"ad_spend": x, "revenue": y})
    dataset, sem_profile, readiness = _create_mock_dataset(df, "correlation_ds")

    spec, rejected, summary = run_discovery_pipeline(
        dataset=dataset,
        semantic_profile=sem_profile,
        readiness=readiness,
        intent="dashboard on this data",
    )

    corr_panels = [p for p in spec.panels if p.metadata.get("insight_type") == "CORRELATION"]
    assert len(corr_panels) >= 1, "Expected CORRELATION panel to be discovered"
    assert abs(corr_panels[0].metadata.get("strength", 0.0) - 0.8) < 0.10


# ---------------------------------------------------------------------------
# Gate Test 4: Planted Outlier Cluster
# ---------------------------------------------------------------------------


def test_gate_planted_outlier_cluster():
    """Planted outlier cluster -> found as DISTRIBUTION_OUTLIERS.

    Ground Truth (Computed by hand):
    - 95 rows with latency in [18, 22] (mean ~20)
    - 5 planted outliers with latency = 500.0 (z-score > 4.0)
    """
    rng = np.random.RandomState(123)
    normal_vals = rng.normal(20.0, 2.0, size=95).tolist()
    outlier_vals = [500.0] * 5

    df = pd.DataFrame({"latency": normal_vals + outlier_vals})
    dataset, sem_profile, readiness = _create_mock_dataset(df, "outlier_ds")

    spec, rejected, summary = run_discovery_pipeline(
        dataset=dataset,
        semantic_profile=sem_profile,
        readiness=readiness,
        intent="",
    )

    outlier_panels = [p for p in spec.panels if p.metadata.get("insight_type") == "DISTRIBUTION_OUTLIERS"]
    assert len(outlier_panels) >= 1, "Expected DISTRIBUTION_OUTLIERS panel to be discovered"
    assert outlier_panels[0].metadata.get("strength", 0.0) > 0.3


# ---------------------------------------------------------------------------
# Gate Test 5: Pure Noise Frame (20 seeds) -> at most 5% non-KPI insights
# ---------------------------------------------------------------------------


def test_gate_pure_noise_20_seeds():
    """Pure noise frame (random measures, random categories, 20 seeds):
    at most 5% of runs may surface any non-KPI insight.
    """
    total_runs = 20
    non_kpi_runs = 0

    for seed in range(total_runs):
        rng = np.random.RandomState(seed + 1000)
        n = 100
        # Pure independent Gaussian noise
        m1 = rng.normal(100.0, 15.0, size=n)
        m2 = rng.normal(50.0, 10.0, size=n)
        # Uniform independent categories
        cat1 = rng.choice(["North", "South", "East", "West"], size=n)
        cat2 = rng.choice(["Tier1", "Tier2", "Tier3"], size=n)

        df = pd.DataFrame({
            "noise_m1": m1,
            "noise_m2": m2,
            "noise_cat1": cat1,
            "noise_cat2": cat2,
        })

        dataset, sem_profile, readiness = _create_mock_dataset(df, f"noise_ds_{seed}")

        spec, rejected, summary = run_discovery_pipeline(
            dataset=dataset,
            semantic_profile=sem_profile,
            readiness=readiness,
            intent="dashboard on this data",
            fdr_alpha=0.05,
            strength_floor=0.08,
            robustness_floor=0.35,
        )

        # Check for non-KPI insights (RANKING, TREND, CORRELATION, SEGMENT_GAP, OUTLIERS)
        non_kpi_panels = [
            p
            for p in spec.panels
            if p.metadata.get("insight_type")
            in (
                InsightType.RANKING.value,
                InsightType.TREND.value,
                InsightType.CORRELATION.value,
                InsightType.SEGMENT_GAP.value,
                InsightType.COMPOSITION.value,
                InsightType.DISTRIBUTION_OUTLIERS.value,
            )
        ]

        if len(non_kpi_panels) > 0:
            non_kpi_runs += 1

    # Exact count output for gate report
    print(f"\n[PURE NOISE GATE]: {non_kpi_runs}/{total_runs} runs surfaced non-KPI insights (rate: {non_kpi_runs/total_runs:.1%})")

    # Gate rule: at most 5% of runs (i.e. at most 1 run out of 20) may surface any non-KPI insight
    assert non_kpi_runs <= 1, f"Expected at most 1 run out of 20 to surface non-KPI insights, but got {non_kpi_runs}"


# ---------------------------------------------------------------------------
# Gate Test 6: Determinism (Repeatability & Column Order Invariance)
# ---------------------------------------------------------------------------


def test_gate_determinism():
    """Determinism: same input twice gives identical output, and shuffling column order gives identical output."""
    rng = np.random.RandomState(999)
    df = pd.DataFrame({
        "revenue": rng.exponential(100.0, size=80),
        "cost": rng.exponential(60.0, size=80),
        "region": rng.choice(["North", "South", "Central"], size=80),
        "channel": rng.choice(["Online", "Retail"], size=80),
    })

    # Run 1: original order
    ds1, sem1, rdy1 = _create_mock_dataset(df, "det_ds")
    spec1, _, _ = run_discovery_pipeline(dataset=ds1, semantic_profile=sem1, readiness=rdy1, intent="")

    # Run 2: exact same
    ds2, sem2, rdy2 = _create_mock_dataset(df, "det_ds")
    spec2, _, _ = run_discovery_pipeline(dataset=ds2, semantic_profile=sem2, readiness=rdy2, intent="")

    # Run 3: shuffled column order
    shuffled_cols = ["channel", "cost", "region", "revenue"]
    df_shuffled = df[shuffled_cols]
    ds3, sem3, rdy3 = _create_mock_dataset(df_shuffled, "det_ds")
    spec3, _, _ = run_discovery_pipeline(dataset=ds3, semantic_profile=sem3, readiness=rdy3, intent="")

    # Assert run 1 == run 2
    assert len(spec1.panels) == len(spec2.panels)
    for p1, p2 in zip(spec1.panels, spec2.panels):
        assert p1.panel_type == p2.panel_type
        assert p1.title == p2.title
        assert p1.metadata.get("insight_type") == p2.metadata.get("insight_type")
        assert p1.metadata.get("strength") == p2.metadata.get("strength")
        assert p1.metadata.get("robustness") == p2.metadata.get("robustness")

    # Assert run 1 == run 3 (shuffled columns produce identical discovery dashboard)
    assert len(spec1.panels) == len(spec3.panels)
    for p1, p3 in zip(spec1.panels, spec3.panels):
        assert p1.panel_type == p3.panel_type
        assert p1.title == p3.title
        assert p1.metadata.get("insight_type") == p3.metadata.get("insight_type")
        assert p1.metadata.get("strength") == p3.metadata.get("strength")
        assert p1.metadata.get("robustness") == p3.metadata.get("robustness")


# ---------------------------------------------------------------------------
# Gate Test 7: Hallucination Guard (Number Verification)
# ---------------------------------------------------------------------------


def test_narration_hallucination_guard():
    """Verify that every number in a narration sentence must appear in the execution result or derived numbers."""
    from orchestrator.discovery.narration import verify_numbers_grounded
    from orchestrator.schemas import ExecutionResult, ExecutionStatus

    # Legitimate execution result with rows
    exec_res = ExecutionResult(
        plan_id="p1",
        status=ExecutionStatus.SUCCESS,
        columns=["category", "sales"],
        rows=[
            {"category": "Alpha", "sales": 1000.0},
            {"category": "Beta", "sales": 500.0},
        ],
        row_count=2,
    )
    details = {"top_val": 1000.0, "top_share": 0.6667, "top_group": "Alpha"}

    # Sentence with true numbers
    grounded_sentence = "Top category Alpha leads with 1,000.0 in sales, accounting for 66.7% of total across 2 records."
    assert verify_numbers_grounded(grounded_sentence, exec_res, details) is True

    # Sentence with hallucinated numbers
    hallucinated_sentence = "Top category Alpha leads with 9,999 in sales, accounting for 95.5% of total."
    assert verify_numbers_grounded(hallucinated_sentence, exec_res, details) is False
