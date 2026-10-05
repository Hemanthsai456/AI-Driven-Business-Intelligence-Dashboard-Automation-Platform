"""Real-dataset validation test suite for Step 6 — Evidence-Grounded AI Insights Engine.

Verifies end-to-end evidence discovery, validation, and narration against the 5 real benchmark domain datasets:
1. Healthcare (diagnosis, severity, length_of_stay, hospital, admission_date)
2. HR (department, salary, performance_score, employee_id, joining_date)
3. Education (department, subject, marks, student_id, exam_date)
4. IoT (device, temperature, pressure, status, timestamp)
5. Logistics (destination, delivery_time, shipment_id, shipment_date, status)

For each domain:
- Profiles dataset dynamically via SemanticAnalyzer
- Executes deterministic evidence-grounded insight generation
- Validates all generated insights pass strict factual validation
- Confirms numerical accuracy and DuckDB SQL provenance
- Confirms absence of causal claims and fabricated statistics
"""

import os
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
    InsightType,
    generate_grounded_insights,
)


def _load_real_dataset(filename: str):
    path = os.path.join(os.path.dirname(__file__), "real_data", filename)
    df = pd.read_csv(path)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{filename.split('.')[0]}", filename, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


# ===========================================================================
# 1. Healthcare Dataset Insights
# ===========================================================================

def test_healthcare_grounded_insights():
    """Verify healthcare dataset generates valid, grounded insights with accurate metrics."""
    dataset, profile = _load_real_dataset("healthcare.csv")
    result = generate_grounded_insights(dataset, profile, use_llm=False)

    assert len(result.insights) >= 3
    types_found = {i.type for i in result.insights}
    assert InsightType.KPI in types_found or InsightType.RANKING in types_found

    # Check that each insight has valid SQL and grounded values
    for ins in result.insights:
        assert ins.evidence.compiled_sql is not None
        assert "SELECT" in ins.evidence.compiled_sql
        assert ins.evidence.source_dataset == dataset.metadata.dataset_id
        assert len(ins.title) > 0
        assert len(ins.statement) > 0

    # Specifically verify KPI insight matches pandas average
    kpis = [i for i in result.insights if i.type == InsightType.KPI]
    if kpis:
        kpi = kpis[0]
        col = kpi.evidence.metric_column
        expected_val = dataset.data[col].mean()
        actual_val = kpi.evidence.values["primary_value"]
        assert pytest.approx(actual_val, rel=1e-2) == expected_val


# ===========================================================================
# 2. HR Dataset Insights
# ===========================================================================

def test_hr_grounded_insights():
    """Verify HR dataset generates ranking and group comparison insights for salary/performance."""
    dataset, profile = _load_real_dataset("hr.csv")
    result = generate_grounded_insights(dataset, profile, use_llm=False)

    assert len(result.insights) >= 3
    types_found = {i.type for i in result.insights}
    assert InsightType.RANKING in types_found or InsightType.KPI in types_found

    # Check ranking accuracy if present
    rankings = [i for i in result.insights if i.type == InsightType.RANKING]
    if rankings:
        rank = rankings[0]
        dim = rank.evidence.dimension_column
        metric = rank.evidence.metric_column
        expected_top = dataset.data.groupby(dim)[metric].mean().idxmax()
        assert rank.evidence.values["top_group"] == expected_top


# ===========================================================================
# 3. Education Dataset Insights
# ===========================================================================

def test_education_grounded_insights():
    """Verify Education dataset produces diverse academic performance insights."""
    dataset, profile = _load_real_dataset("education.csv")
    result = generate_grounded_insights(dataset, profile, use_llm=False)

    assert len(result.insights) >= 3
    for ins in result.insights:
        assert ins.confidence > 0.0
        assert ins.importance > 0.0
        # No causal language anywhere
        assert "causes" not in ins.statement.lower()
        assert "drives" not in ins.statement.lower()


# ===========================================================================
# 4. IoT Dataset Insights
# ===========================================================================

def test_iot_grounded_insights():
    """Verify IoT dataset generates sensor telemetry and correlation insights."""
    dataset, profile = _load_real_dataset("iot.csv")
    result = generate_grounded_insights(dataset, profile, use_llm=False)

    assert len(result.insights) >= 3
    
    # Check correlations if present
    correlations = [i for i in result.insights if i.type == InsightType.CORRELATION]
    for corr in correlations:
        m1 = corr.evidence.metric_column
        m2 = corr.evidence.secondary_metric
        expected_r = dataset.data[[m1, m2]].corr().iloc[0, 1]
        actual_r = corr.evidence.values["correlation_r"]
        assert pytest.approx(actual_r, abs=0.05) == expected_r
        # Must explicitly be non-causal
        assert "cause" not in corr.statement.lower()
        assert "driven" not in corr.statement.lower()


# ===========================================================================
# 5. Logistics Dataset Insights
# ===========================================================================

def test_logistics_grounded_insights():
    """Verify Logistics dataset generates delivery time and distribution insights."""
    dataset, profile = _load_real_dataset("logistics.csv")
    result = generate_grounded_insights(dataset, profile, use_llm=False)

    assert len(result.insights) >= 3
    # Check temporal trend if date exists
    trends = [i for i in result.insights if i.type == InsightType.TEMPORAL_TREND]
    for tr in trends:
        assert tr.evidence.dimension_column in ("shipment_date", "date", "timestamp")
        assert tr.evidence.values["direction"] in ("increased", "decreased", "stable", "increasing", "decreasing")
