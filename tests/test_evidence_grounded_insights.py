"""Unit tests for Step 6 — Evidence-Grounded AI Insights Engine.

Covers:
1. Overall Aggregate / KPI Insight
2. Ranking / Top-Bottom Insight
3. Group Comparison Insight
4. Distribution Insight
5. Temporal Trend Insight
6. Outlier Observation Insight
7. Correlation Insight
8. Numerical Claim Grounding Verification
9. Causal Language Prohibition in Correlation
10. Provider Failure Fallback
11. Provenance Preservation (Compiled SQL, DuckDB Execution)
"""

import math
from typing import Any
import pandas as pd
import pytest

from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
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
from orchestrator.schemas import AggregationType, Granularity
from providers.base import LLMClient


@pytest.fixture
def sample_dataset():
    data = {
        "employee_id": [f"EMP_{i:03d}" for i in range(1, 21)],
        "department": ["Engineering", "Engineering", "Engineering", "Engineering", "Engineering",
                       "Product", "Product", "Product", "Product", "Product",
                       "Sales", "Sales", "Sales", "Sales", "Sales",
                       "Support", "Support", "Support", "Support", "Support"],
        "salary": [120000.0, 115000.0, 125000.0, 110000.0, 130000.0,
                   95000.0, 98000.0, 92000.0, 96000.0, 94000.0,
                   85000.0, 82000.0, 88000.0, 86000.0, 84000.0,
                   65000.0, 62000.0, 67000.0, 64000.0, 300000.0],  # 300000 is an outlier
        "tenure_months": [36, 24, 48, 12, 60,
                          20, 24, 18, 22, 19,
                          15, 12, 18, 16, 14,
                          10, 8, 12, 9, 72],
        "hire_date": pd.date_range("2021-01-01", periods=20, freq="60D"),
    }
    df = pd.DataFrame(data)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata("ds_sample", "sample_hr", "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


def test_kpi_aggregate_insight(sample_dataset):
    """Verify overall KPI aggregate insight contains exact DuckDB calculations."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    kpi_insights = [i for i in res.insights if i.type == InsightType.KPI]
    assert len(kpi_insights) > 0

    kpi = kpi_insights[0]
    assert kpi.evidence.metric_column in ("salary", "tenure_months")
    assert kpi.evidence.compiled_sql is not None
    assert "SELECT" in kpi.evidence.compiled_sql
    assert kpi.evidence.values["primary_value"] is not None

    # Parity check
    col = kpi.evidence.metric_column
    expected_avg = round(float(dataset.data[col].mean()), 2)
    assert pytest.approx(kpi.evidence.values["primary_value"], rel=1e-2) == expected_avg
    assert str(kpi.evidence.values["primary_value"]) in kpi.statement or f"{kpi.evidence.values['primary_value']:.2f}" in kpi.statement


def test_ranking_top_bottom_insight(sample_dataset):
    """Verify ranking insight identifies highest and lowest groups with exact spread."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    rank_insights = [i for i in res.insights if i.type == InsightType.RANKING]
    assert len(rank_insights) > 0

    rank_ins = rank_insights[0]
    assert rank_ins.evidence.dimension_column == "department"
    assert "top_group" in rank_ins.evidence.values
    assert "bottom_group" in rank_ins.evidence.values
    assert "difference" in rank_ins.evidence.values

    # Top group should be Engineering or Support (depending on outlier)
    assert rank_ins.evidence.values["top_group"] in ("Engineering", "Support")
    assert rank_ins.evidence.values["top_value"] >= rank_ins.evidence.values["bottom_value"]


def test_group_comparison_insight(sample_dataset):
    """Verify group comparison measures segment divergence from group baseline."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    comp_insights = [i for i in res.insights if i.type == InsightType.GROUP_COMPARISON]
    assert len(comp_insights) > 0

    comp = comp_insights[0]
    assert "lead_group" in comp.evidence.values
    assert "lead_value" in comp.evidence.values
    assert "group_mean" in comp.evidence.values
    assert comp.evidence.values["lead_value"] >= comp.evidence.values["group_mean"]


def test_distribution_insight(sample_dataset):
    """Verify categorical share distribution captures top group proportion."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    dist_insights = [i for i in res.insights if i.type == InsightType.DISTRIBUTION]
    assert len(dist_insights) > 0

    dist = dist_insights[0]
    assert dist.evidence.dimension_column == "department"
    assert "dominant_category" in dist.evidence.values
    assert "dominant_share_pct" in dist.evidence.values
    # 4 departments each with 5 records = 25% share
    assert dist.evidence.values["dominant_share_pct"] == 25.0


def test_temporal_trend_insight(sample_dataset):
    """Verify temporal trend calculates directional trajectory across datetime."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    trend_insights = [i for i in res.insights if i.type == InsightType.TEMPORAL_TREND]
    assert len(trend_insights) > 0

    trend = trend_insights[0]
    assert trend.evidence.dimension_column == "hire_date"
    assert "start_value" in trend.evidence.values
    assert "end_value" in trend.evidence.values
    assert "direction" in trend.evidence.values
    assert trend.evidence.values["periods_analyzed"] >= 2


def test_outlier_insight(sample_dataset):
    """Verify outlier detection identifies high-leverage data point ($300,000)."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    outlier_insights = [i for i in res.insights if i.type == InsightType.OUTLIER]
    assert len(outlier_insights) > 0

    outlier = outlier_insights[0]
    assert outlier.evidence.values["outlier_count"] >= 1
    assert outlier.evidence.values["max_outlier_value"] >= 300000.0


def test_correlation_insight(sample_dataset):
    """Verify correlation between salary and tenure."""
    dataset, profile = sample_dataset
    res = generate_grounded_insights(dataset, profile, use_llm=False)

    corr_insights = [i for i in res.insights if i.type == InsightType.CORRELATION]
    assert len(corr_insights) > 0

    corr = corr_insights[0]
    assert corr.evidence.values["correlation_r"] is not None
    assert -1.0 <= corr.evidence.values["correlation_r"] <= 1.0
    assert "causes" not in corr.statement.lower()
    assert "caused" not in corr.statement.lower()


def test_hallucinated_number_rejected():
    """Verify validator rejects an insight whose text contains an ungrounded fabricated number."""
    validator = InsightValidator()
    
    # Construct synthetic evidence with true value = 42.0
    evidence = InsightEvidence(
        source_dataset="ds_test",
        metric_column="score",
        aggregation=AggregationType.AVG,
        values={"primary_value": 42.0},
        compiled_sql='SELECT AVG("score") FROM "source_data";',
        row_count=1,
    )
    
    # Valid grounded insight
    valid_ins = EvidenceGroundedInsight(
        type=InsightType.KPI,
        title="Average Score",
        statement="The average score is 42.0 across the dataset.",
        evidence=evidence,
    )
    df = pd.DataFrame({"score": [40.0, 44.0]})
    meta = DatasetMetadata("ds_test", "ds_test", "csv", 2, 1, [ColumnMetadata("score", "score", "float64")])
    ds = CanonicalDataset(meta, df)
    profile = analyze_semantics(ds)
    
    ok, reason = validator.validate_final_insight(valid_ins, ds, profile)
    assert ok is True
    
    # Hallucinated insight with fabricated number 999.99
    fake_ins = EvidenceGroundedInsight(
        type=InsightType.KPI,
        title="Average Score",
        statement="The average score increased by 999.99 points unexpectedly.",
        evidence=evidence,
    )
    ok_fake, reason_fake = validator.validate_final_insight(fake_ins, ds, profile)
    assert ok_fake is False
    assert "not grounded in evidence values" in reason_fake


def test_causal_correlation_rejected():
    """Verify validator rejects correlation insight attempting to make causal claims."""
    validator = InsightValidator()
    evidence = InsightEvidence(
        source_dataset="ds_test",
        metric_column="temperature",
        secondary_metric="pressure",
        aggregation=AggregationType.AVG,
        values={"correlation_r": 0.85, "sample_size": 20, "direction": "positive", "strength": "strong"},
        compiled_sql='SELECT CORR("temperature", "pressure") FROM "source_data";',
        row_count=20,
    )
    df = pd.DataFrame({"temperature": [20.0, 25.0, 30.0], "pressure": [1.0, 1.2, 1.5]})
    meta = DatasetMetadata("ds_test", "ds_test", "csv", 3, 2, [
        ColumnMetadata("temperature", "temperature", "float64"),
        ColumnMetadata("pressure", "pressure", "float64")
    ])
    ds = CanonicalDataset(meta, df)
    profile = analyze_semantics(ds)

    causal_ins = EvidenceGroundedInsight(
        type=InsightType.CORRELATION,
        title="Temperature Drives Pressure",
        statement="Temperature causes a direct rise in pressure levels (r = 0.85, N = 20).",
        evidence=evidence,
    )
    ok, reason = validator.validate_final_insight(causal_ins, ds, profile)
    assert ok is False
    assert "forbidden causal language" in reason


def test_llm_failure_fallback():
    """Verify that if LLM fails or raises an error, narrator falls back to deterministic template."""
    class FailingLLMClient(LLMClient):
        def __init__(self):
            super().__init__(provider="mock", model_name="mock")
        def generate(self, prompt: str) -> str:
            raise RuntimeError("API quota exceeded")
        def generate_plan(self, prompt: str, schema: dict) -> dict:
            raise RuntimeError("API quota exceeded")
        def generate_structured(self, prompt: str, response_model: type) -> Any:
            raise RuntimeError("API quota exceeded")

    from orchestrator.insights.narrator import InsightNarrator
    narrator = InsightNarrator(llm_client=FailingLLMClient())
    evidence = InsightEvidence(
        source_dataset="ds_test",
        metric_column="sales",
        aggregation=AggregationType.SUM,
        values={"primary_value": 50000.0},
        row_count=1,
    )

    title, statement, _ = narrator.narrate_insight(InsightType.KPI, evidence, use_llm=True)
    assert "Overall SUM Sales" in title
    assert "50000.0" in statement
