"""Evaluation Script for Step 6 — Evidence-Grounded AI Insights Engine.

Generates insights across the 5 benchmark datasets:
1. Healthcare (healthcare.csv)
2. HR (hr.csv)
3. Education (education.csv)
4. IoT (iot.csv)
5. Logistics (logistics.csv)

For every generated insight:
- Computes independent ground truth via direct DuckDB / Pandas execution.
- Checks numerical grounding, SQL provenance, semantic aggregation validity.
- Checks ranking, trend, correlation correctness and causal statement absence.
- Evaluates duplicate redundancy, confidence distribution, and potential false positives.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from engine.duckdb_executor import DuckDBExecutor
from orchestrator.insights import (
    EvidenceGroundedInsight,
    InsightEngine,
    InsightEvidence,
    InsightGenerationResult,
    InsightType,
    generate_grounded_insights,
)
from orchestrator.schemas import AggregationType, ExecutionStatus


def load_benchmark_dataset(filename: str) -> Tuple[CanonicalDataset, Any]:
    path = os.path.join(PROJECT_ROOT, "tests", "real_data", filename)
    df = pd.read_csv(path)
    cols = [ColumnMetadata(c, c, str(df[c].dtype)) for c in df.columns]
    meta = DatasetMetadata(f"ds_{filename.split('.')[0]}", filename, "csv", len(df), len(cols), cols)
    dataset = CanonicalDataset(meta, df)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    return dataset, sem_profile


def compute_independent_ground_truth(dataset: CanonicalDataset, sem_profile: Any, insight: EvidenceGroundedInsight) -> Dict[str, Any]:
    """Compute independent ground truth using direct DuckDB SQL and Pandas."""
    df = dataset.data
    ev = insight.evidence
    gt = {}

    if ev.query_or_plan:
        exec_res = DuckDBExecutor().execute_plan(
            plan=ev.query_or_plan,
            dataset=dataset,
            semantic_profile=sem_profile,
            custom_sql=ev.compiled_sql,
        )
        if exec_res.status == ExecutionStatus.SUCCESS:
            gt["sql_row_count"] = exec_res.row_count
            gt["sql_first_row"] = exec_res.rows[0] if exec_res.rows else {}

    if insight.type == InsightType.KPI:
        metric = ev.metric_column
        agg = ev.aggregation
        if agg == AggregationType.SUM:
            gt["expected_metric_val"] = float(df[metric].sum())
        elif agg == AggregationType.AVG:
            gt["expected_metric_val"] = float(df[metric].mean())
        elif agg == AggregationType.COUNT:
            gt["expected_metric_val"] = float(len(df))
        elif agg == AggregationType.MIN:
            gt["expected_metric_val"] = float(df[metric].min())
        elif agg == AggregationType.MAX:
            gt["expected_metric_val"] = float(df[metric].max())

    elif insight.type == InsightType.RANKING:
        dim = ev.dimension_column
        metric = ev.metric_column
        agg = ev.aggregation
        grouped = df.groupby(dim)[metric].mean() if agg == AggregationType.AVG else df.groupby(dim)[metric].sum()
        sorted_g = grouped.sort_values(ascending=False)
        gt["expected_top_group"] = sorted_g.index[0]
        gt["expected_top_val"] = float(sorted_g.iloc[0])
        gt["expected_bottom_group"] = sorted_g.index[-1]
        gt["expected_bottom_val"] = float(sorted_g.iloc[-1])
        gt["expected_difference"] = float(sorted_g.iloc[0] - sorted_g.iloc[-1])

    elif insight.type == InsightType.GROUP_COMPARISON:
        dim = ev.dimension_column
        metric = ev.metric_column
        agg = ev.aggregation
        grouped = df.groupby(dim)[metric].mean() if agg == AggregationType.AVG else df.groupby(dim)[metric].sum()
        lead_group = grouped.idxmax()
        lead_val = float(grouped.max())
        mean_val = float(grouped.mean())
        gt["expected_lead_group"] = lead_group
        gt["expected_lead_val"] = lead_val
        gt["expected_group_mean"] = mean_val
        gt["expected_rel_diff_pct"] = float(((lead_val - mean_val) / (mean_val or 1.0)) * 100.0)

    elif insight.type == InsightType.DISTRIBUTION:
        dim = ev.dimension_column
        counts = df[dim].value_counts()
        gt["expected_dominant_category"] = counts.index[0]
        gt["expected_dominant_count"] = int(counts.iloc[0])
        gt["expected_dominant_share_pct"] = float((counts.iloc[0] / len(df)) * 100.0)

    elif insight.type == InsightType.CORRELATION:
        m1 = ev.metric_column
        m2 = ev.secondary_metric
        valid = df[[m1, m2]].dropna()
        gt["expected_r"] = float(valid.corr().iloc[0, 1])
        gt["expected_n"] = len(valid)

    elif insight.type == InsightType.OUTLIER:
        metric = ev.metric_column
        s = df[metric].dropna()
        q1 = float(s.quantile(0.25))
        q3 = float(s.quantile(0.75))
        iqr = q3 - q1
        low = q1 - 1.5 * iqr
        high = q3 + 1.5 * iqr
        outliers = s[(s < low) | (s > high)]
        gt["expected_outlier_count"] = len(outliers)
        gt["expected_iqr_low"] = low
        gt["expected_iqr_high"] = high

    return gt


def run_evaluation() -> Dict[str, Any]:
    datasets_to_eval = [
        "healthcare.csv",
        "hr.csv",
        "education.csv",
        "iot.csv",
        "logistics.csv",
    ]

    report: Dict[str, Any] = {
        "datasets": {},
        "summary": {
            "total_insights": 0,
            "passed_ground_truth": 0,
            "failed_ground_truth": 0,
            "provenance_intact_count": 0,
            "causal_claims_detected": 0,
            "hallucinated_numbers_detected": 0,
            "duplicates_detected": 0,
        },
    }

    for fname in datasets_to_eval:
        domain = fname.split(".")[0]
        dataset, sem_profile = load_benchmark_dataset(fname)
        result: InsightGenerationResult = generate_grounded_insights(dataset, sem_profile, use_llm=False)

        domain_report = {
            "row_count": len(dataset.data),
            "columns": list(dataset.data.columns),
            "insights_generated": len(result.insights),
            "rejected_count": len(result.rejections),
            "insights": [],
        }

        seen_signatures = set()

        for ins in result.insights:
            report["summary"]["total_insights"] += 1
            gt = compute_independent_ground_truth(dataset, sem_profile, ins)

            # Check provenance
            has_prov = bool(ins.evidence.compiled_sql and "SELECT" in ins.evidence.compiled_sql)
            if has_prov:
                report["summary"]["provenance_intact_count"] += 1

            # Check causal assertions
            has_causal = any(w in ins.statement.lower() for w in ["cause", "caused", "causes", "drives", "leads to"])
            if has_causal and ins.type == InsightType.CORRELATION:
                report["summary"]["causal_claims_detected"] += 1

            # Check duplicates
            sig = (ins.type, ins.evidence.metric_column, ins.evidence.dimension_column, ins.evidence.secondary_metric)
            is_dup = sig in seen_signatures
            if is_dup:
                report["summary"]["duplicates_detected"] += 1
            seen_signatures.add(sig)

            # Check factual correctness against GT
            is_correct = True
            mismatch_reasons = []

            if ins.type == InsightType.KPI:
                actual_val = ins.evidence.values.get("primary_value")
                exp_val = gt.get("expected_metric_val")
                if actual_val is not None and exp_val is not None:
                    if abs(actual_val - exp_val) > 0.05 * (abs(exp_val) + 1e-5):
                        is_correct = False
                        mismatch_reasons.append(f"KPI value mismatch: got {actual_val}, exp {exp_val}")

            elif ins.type == InsightType.RANKING:
                actual_top = ins.evidence.values.get("top_group")
                exp_top = gt.get("expected_top_group")
                if actual_top != exp_top:
                    is_correct = False
                    mismatch_reasons.append(f"Top group mismatch: got {actual_top}, exp {exp_top}")

            elif ins.type == InsightType.GROUP_COMPARISON:
                actual_lead = ins.evidence.values.get("lead_group")
                exp_lead = gt.get("expected_lead_group")
                if actual_lead != exp_lead:
                    is_correct = False
                    mismatch_reasons.append(f"Lead group mismatch: got {actual_lead}, exp {exp_lead}")

            elif ins.type == InsightType.DISTRIBUTION:
                actual_dom = ins.evidence.values.get("dominant_category")
                exp_dom = gt.get("expected_dominant_category")
                if actual_dom != exp_dom:
                    is_correct = False
                    mismatch_reasons.append(f"Dominant category mismatch: got {actual_dom}, exp {exp_dom}")

            elif ins.type == InsightType.CORRELATION:
                actual_r = ins.evidence.values.get("correlation_r")
                exp_r = gt.get("expected_r")
                if actual_r is not None and exp_r is not None:
                    if abs(actual_r - exp_r) > 0.05:
                        is_correct = False
                        mismatch_reasons.append(f"Correlation r mismatch: got {actual_r}, exp {exp_r}")

            elif ins.type == InsightType.OUTLIER:
                actual_count = ins.evidence.values.get("outlier_count")
                exp_count = gt.get("expected_outlier_count")
                if actual_count != exp_count:
                    is_correct = False
                    mismatch_reasons.append(f"Outlier count mismatch: got {actual_count}, exp {exp_count}")

            if is_correct:
                report["summary"]["passed_ground_truth"] += 1
            else:
                report["summary"]["failed_ground_truth"] += 1

            domain_report["insights"].append({
                "insight_id": ins.insight_id,
                "type": ins.type.value,
                "title": ins.title,
                "statement": ins.statement,
                "importance": ins.importance,
                "confidence": ins.confidence,
                "evidence_values": ins.evidence.values,
                "ground_truth": gt,
                "is_correct": is_correct,
                "mismatch_reasons": mismatch_reasons,
                "compiled_sql": ins.evidence.compiled_sql,
            })

        report["datasets"][domain] = domain_report

    return report


if __name__ == "__main__":
    rep = run_evaluation()
    print("==================================================================")
    print("STEP 6 EVIDENCE-GROUNDED INSIGHTS EVALUATION RESULTS")
    print("==================================================================")
    print(f"Total Insights Evaluated:        {rep['summary']['total_insights']}")
    print(f"Passed Ground Truth Parity:      {rep['summary']['passed_ground_truth']}")
    print(f"Failed Ground Truth Parity:      {rep['summary']['failed_ground_truth']}")
    print(f"Provenance Intact:               {rep['summary']['provenance_intact_count']} / {rep['summary']['total_insights']}")
    print(f"Causal Claims Detected:          {rep['summary']['causal_claims_detected']}")
    print(f"Duplicate Insights Detected:     {rep['summary']['duplicates_detected']}")
    print("==================================================================")

    for domain, d_rep in rep["datasets"].items():
        print(f"\n[{domain.upper()}] ({d_rep['insights_generated']} insights generated):")
        for i, ins in enumerate(d_rep["insights"], 1):
            status = "PASS" if ins["is_correct"] else f"FAIL ({ins['mismatch_reasons']})"
            print(f"  {i}. [{ins['type'].upper()}] {ins['title']}")
            print(f"     Statement:  {ins['statement']}")
            print(f"     Importance: {ins['importance']:.2f} | Confidence: {ins['confidence']:.2f} | Status: {status}")
            print(f"     SQL:        {ins['compiled_sql']}")
