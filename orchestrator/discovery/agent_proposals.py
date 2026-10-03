"""Agent Proposals Engine (Stage E2).

Provides bounded statistical summaries (describe, top values, correlations,
time span - never raw rows) to agent generators and receives extra typed insight
candidates in the same schema. Agents never produce numbers, only plans.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.discovery.schemas import InsightCandidate, InsightType
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    Granularity,
    MetricSpec,
    PlanReasoning,
    VisualizationType,
)
from providers.base import LLMClient


def build_bounded_stats_summary(
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
) -> Dict[str, Any]:
    """Generate a compact, bounded statistical summary without raw rows.

    Includes:
    - Per-column describe (min, max, mean, std, quantiles, nulls, distinct)
    - Top 5 values with counts for categorical columns
    - Correlation matrix for measure pairs with |r| >= 0.25
    - Date range and span for datetime columns
    """
    df = dataset.data
    summary: Dict[str, Any] = {
        "dataset_id": dataset.metadata.dataset_id or "dataset",
        "row_count": len(df),
        "columns": {},
        "correlations": [],
        "time_spans": {},
    }

    numeric_cols: List[str] = []

    for col in sorted(list(df.columns)):
        ev = semantic_profile.get_evidence(col)
        role = ev.candidate_role.value if ev else "UNKNOWN"
        col_type = str(df[col].dtype)
        null_count = int(df[col].isna().sum())
        null_pct = round(null_count / len(df) * 100, 2) if len(df) > 0 else 0.0
        distinct_count = int(df[col].nunique(dropna=True))

        col_stat: Dict[str, Any] = {
            "role": role,
            "dtype": col_type,
            "null_pct": null_pct,
            "distinct_count": distinct_count,
        }

        # Numeric stats (exclude boolean)
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
            numeric_cols.append(col)
            valid = df[col].dropna()
            if len(valid) > 0:
                col_stat["describe"] = {
                    "min": round(float(valid.min()), 2),
                    "max": round(float(valid.max()), 2),
                    "mean": round(float(valid.mean()), 2),
                    "std": round(float(valid.std()), 2) if len(valid) > 1 else 0.0,
                    "q25": round(float(valid.quantile(0.25)), 2),
                    "median": round(float(valid.median()), 2),
                    "q75": round(float(valid.quantile(0.75)), 2),
                }

        # Categorical top values (top 5 only, no raw row dumps)
        elif role == ColumnRole.DIMENSION.value or pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
            val_counts = df[col].value_counts().head(5)
            col_stat["top_values"] = [
                {"value": str(val), "count": int(cnt)}
                for val, cnt in val_counts.items()
            ]

        # Datetime span
        if role == ColumnRole.DATETIME.value or "date" in col.lower() or "time" in col.lower():
            try:
                dt_clean = pd.to_datetime(df[col].dropna(), errors="coerce").dropna()
                if len(dt_clean) > 0:
                    summary["time_spans"][col] = {
                        "min_date": dt_clean.min().isoformat(),
                        "max_date": dt_clean.max().isoformat(),
                        "span_days": int((dt_clean.max() - dt_clean.min()).days),
                    }
            except Exception:
                pass

        summary["columns"][col] = col_stat

    # Compute pairwise correlations for numeric columns
    if len(numeric_cols) >= 2:
        for i in range(len(numeric_cols)):
            for j in range(i + 1, len(numeric_cols)):
                c1 = numeric_cols[i]
                c2 = numeric_cols[j]
                try:
                    valid_pairs = df[[c1, c2]].dropna()
                    if len(valid_pairs) > 3:
                        r = float(valid_pairs[c1].corr(valid_pairs[c2]))
                        if not np.isnan(r) and abs(r) >= 0.25:
                            summary["correlations"].append({
                                "col_1": c1,
                                "col_2": c2,
                                "pearson_r": round(r, 3),
                            })
                except Exception:
                    pass

    return summary


def generate_agent_proposals(
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    llm_client: Optional[LLMClient] = None,
    brief: Optional[str] = None,
) -> List[InsightCandidate]:
    """Generate supplementary candidate insight proposals via LLM/agent.

    The agent is provided with ONLY the bounded statistical summary and intent,
    and returns structured plans conforming to the InsightCandidate schema.
    """
    stats_summary = build_bounded_stats_summary(dataset, semantic_profile)
    dataset_id = dataset.metadata.dataset_id or "dataset"

    # If no LLM available or mock environment, generate high-value heuristic proposals
    # that supplement base enumeration (e.g. median aggregates or top-correlated pairs)
    if llm_client is None:
        proposals: List[InsightCandidate] = []
        # Propose MEDIAN KPI for skewed measures
        for col, meta in stats_summary["columns"].items():
            if meta.get("role") == ColumnRole.MEASURE.value and "describe" in meta:
                desc = meta["describe"]
                mean_val = desc["mean"]
                median_val = desc["median"]
                std_val = desc["std"]
                if std_val > 0 and abs(mean_val - median_val) / std_val > 0.5:
                    plan = CandidatePlan(
                        dataset_id=dataset_id,
                        intent=f"Agent Proposal: MEDIAN({col}) to mitigate skew",
                        metric=MetricSpec(column=col, aggregation=AggregationType.MEDIAN),
                        dimensions=[],
                        visualization=VisualizationType.KPI,
                        generator="external_agent",
                        reasoning=PlanReasoning(
                            interpretation=f"Evaluate median of {col} due to high skew (|mean-median|/std > 0.5)",
                            evidence=[f"mean={mean_val}, median={median_val}, std={std_val}"],
                        ),
                    )
                    proposals.append(
                        InsightCandidate(
                            insight_type=InsightType.TOTAL_KPI,
                            plan=plan,
                            measure=col,
                            aggregation=AggregationType.MEDIAN,
                            proposed_by="agent",
                            params={"rationale": "skew_mitigation"},
                        )
                    )
        return proposals

    # When LLM client is available, prompt with bounded summary
    prompt = (
        f"You are a Senior BI Analyst. Analyze this bounded dataset summary (no raw rows):\n"
        f"{json.dumps(stats_summary, indent=2)}\n\n"
        f"User Brief: '{brief or 'Discover key insights on this data'}'\n\n"
        f"Propose up to 3 candidate analytical plans. Rules:\n"
        f"1. You must ONLY output plan specifications in JSON format.\n"
        f"2. NEVER output calculated numbers or facts—only plan targets.\n"
        f"3. Return a JSON list of objects with fields:\n"
        f"   - insight_type: one of [TOTAL_KPI, RANKING, COMPOSITION, TREND, PERIOD_CHANGE, DISTRIBUTION_OUTLIERS, CORRELATION, SEGMENT_GAP]\n"
        f"   - measure: column name\n"
        f"   - dimension: column name or null\n"
        f"   - aggregation: SUM, AVG, MEDIAN, or COUNT\n"
        f"   - reason: short justification\n"
    )

    try:
        response = llm_client.generate(prompt=prompt)
        # Parse JSON from response
        text = response.text if hasattr(response, "text") else str(response)
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            raw_list = json.loads(text[start : end + 1])
            agent_candidates = []
            for item in raw_list:
                m = item.get("measure")
                d = item.get("dimension")
                itype_str = item.get("insight_type", "TOTAL_KPI")
                try:
                    itype = InsightType(itype_str)
                except Exception:
                    continue
                agg_str = item.get("aggregation", "SUM")
                try:
                    agg = AggregationType(agg_str)
                except Exception:
                    agg = AggregationType.SUM

                if not m or m not in stats_summary["columns"]:
                    continue

                dims = [DimensionSpec(column=d)] if d and d in stats_summary["columns"] else []
                plan = CandidatePlan(
                    dataset_id=dataset_id,
                    intent=f"Agent Proposed {itype.value}: {agg.value}({m})" + (f" by {d}" if d else ""),
                    metric=MetricSpec(column=m, aggregation=agg),
                    dimensions=dims,
                    visualization=VisualizationType.BAR if dims else VisualizationType.KPI,
                    generator="external_agent",
                    reasoning=PlanReasoning(
                        interpretation=item.get("reason", f"Agent suggested {itype.value} on {m}"),
                        evidence=[f"Bounded stats analyzed for {m}"],
                    ),
                )
                agent_candidates.append(
                    InsightCandidate(
                        insight_type=itype,
                        plan=plan,
                        measure=m,
                        dimension=d if dims else None,
                        aggregation=agg,
                        proposed_by="agent",
                        params={"agent_reason": item.get("reason")},
                    )
                )
            return agent_candidates
    except Exception:
        pass

    return []
