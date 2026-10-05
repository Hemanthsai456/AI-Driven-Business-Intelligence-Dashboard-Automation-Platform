"""Deterministic Insight Discovery Engine (Step 6).

Generates evidence-backed analytical candidates across the 7 required insight types:
1. KPI / Overall Aggregate
2. Ranking / Top-Bottom Groups
3. Group Comparison / Segment Gap
4. Distribution / Categorical Spread
5. Temporal Trend
6. Outlier / Unusual Observations
7. Correlation (Numeric Pairs)

Every candidate runs its analytical plan through the authoritative SQL compiler
and executes in DuckDB to produce exact, verifiable numbers and provenance.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import uuid4
import numpy as np
import pandas as pd

from engine.compiler import compile_plan_to_sql
from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
)
from orchestrator.insights.schemas import (
    InsightEvidence,
    InsightType,
)
from orchestrator.interpretation import _resolve_aggregation
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionStatus,
    Granularity,
    MetricSpec,
    PlanReasoning,
    VisualizationType,
)


def _infer_time_grain(dt_series: pd.Series) -> Granularity:
    """Infer suitable temporal granularity from datetime span."""
    try:
        dt_clean = pd.to_datetime(dt_series.dropna(), errors="coerce").dropna()
        if len(dt_clean) < 2:
            return Granularity.MONTH
        span_days = (dt_clean.max() - dt_clean.min()).days
        if span_days <= 14:
            return Granularity.DAY
        elif span_days <= 90:
            return Granularity.WEEK
        elif span_days <= 730:
            return Granularity.MONTH
        else:
            return Granularity.YEAR
    except Exception:
        return Granularity.MONTH


class AnalyticalInsightDiscoverer:
    """Generates deterministic analytical candidates and executes their DuckDB evidence."""

    def __init__(self, executor: Optional[DuckDBExecutor] = None) -> None:
        self.executor = executor or DuckDBExecutor()

    def discover_candidates(
        self,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
    ) -> List[Tuple[InsightType, InsightEvidence]]:
        """Discover analytical insight candidates across all 7 supported types.

        Returns:
            List of (InsightType, InsightEvidence) pairs.
        """
        df = dataset.data
        if df is None or len(df) == 0:
            return []

        dataset_id = dataset.metadata.dataset_id if dataset.metadata else "source_data"
        total_rows = len(df)

        # Classify columns using runtime semantic profile
        measures: List[str] = []
        dimensions: List[str] = []
        datetimes: List[str] = []
        identifiers: List[str] = []

        for col, ev in semantic_profile.column_evidences.items():
            if col not in df.columns:
                continue
            # Check null rate
            null_rate = df[col].isna().sum() / total_rows if total_rows > 0 else 1.0
            if null_rate > 0.8:
                continue
            # Check distinct count
            nunique = df[col].nunique(dropna=True)
            if nunique <= 1:
                continue

            if ev.candidate_role == ColumnRole.MEASURE or (
                ev.candidate_role != ColumnRole.IDENTIFIER
                and ev.candidate_role != ColumnRole.DATETIME
                and pd.api.types.is_numeric_dtype(df[col])
            ):
                measures.append(col)
            elif ev.candidate_role == ColumnRole.DIMENSION or (
                ev.candidate_role != ColumnRole.IDENTIFIER
                and ev.candidate_role != ColumnRole.DATETIME
                and nunique < 50
                and not pd.api.types.is_numeric_dtype(df[col])
            ):
                if nunique <= 50 and (nunique / total_rows <= 0.5 or total_rows <= 20):
                    dimensions.append(col)
            elif ev.candidate_role == ColumnRole.DATETIME or pd.api.types.is_datetime64_any_dtype(df[col]):
                datetimes.append(col)
            elif ev.candidate_role == ColumnRole.IDENTIFIER:
                identifiers.append(col)

        # Sort deterministically
        measures.sort()
        dimensions.sort()
        datetimes.sort()

        discovered: List[Tuple[InsightType, InsightEvidence]] = []

        # -------------------------------------------------------------------
        # 1. KPI / Overall Aggregates
        # -------------------------------------------------------------------
        for m in measures:
            ev_m = semantic_profile.get_evidence(m)
            agg = _resolve_aggregation(m, "", semantic_profile)
            plan = CandidatePlan(
                plan_id=str(uuid4()),
                dataset_id=dataset_id,
                intent=f"Overall {agg.value} of {m}",
                metric=MetricSpec(column=m, aggregation=agg),
                dimensions=[],
                filters=[],
                visualization=VisualizationType.KPI,
                generator="insight_engine",
                provider="deterministic_engine",
                reasoning=PlanReasoning(interpretation=f"Compute overall {agg.value} of {m}"),
            )
            compiled_sql = compile_plan_to_sql(plan, "source_data")
            exec_res = self.executor.execute_plan(plan=plan, dataset=dataset, semantic_profile=semantic_profile, custom_sql=compiled_sql)
            if exec_res.status == ExecutionStatus.SUCCESS and exec_res.rows:
                primary_val = list(exec_res.rows[0].values())[0]
                if primary_val is not None and not (isinstance(primary_val, float) and math.isnan(primary_val)):
                    evidence = InsightEvidence(
                        source_dataset=dataset_id,
                        metric_column=m,
                        aggregation=agg,
                        dimension_column=None,
                        filters=[],
                        time_grain=None,
                        values={
                            "primary_value": round(float(primary_val), 2),
                            "raw_value": float(primary_val),
                            "aggregation": agg.value,
                        },
                        query_or_plan=plan,
                        compiled_sql=compiled_sql,
                        row_count=exec_res.row_count,
                        supporting_rows_or_groups=exec_res.rows,
                        statistical_metadata={
                            "total_dataset_rows": total_rows,
                            "null_count": int(df[m].isna().sum()),
                        },
                    )
                    discovered.append((InsightType.KPI, evidence))

        # -------------------------------------------------------------------
        # 2. Ranking & 3. Group Comparison
        # -------------------------------------------------------------------
        for m in measures:
            agg = _resolve_aggregation(m, "", semantic_profile)
            for d in dimensions:
                plan_rank = CandidatePlan(
                    plan_id=str(uuid4()),
                    dataset_id=dataset_id,
                    intent=f"Rank {d} by {agg.value} of {m}",
                    metric=MetricSpec(column=m, aggregation=agg),
                    dimensions=[DimensionSpec(column=d, granularity=None)],
                    filters=[],
                    order_by=f"{agg.value.lower()}_{m}",
                    order_direction="DESC",
                    visualization=VisualizationType.BAR,
                    generator="insight_engine",
                    provider="deterministic_engine",
                    reasoning=PlanReasoning(interpretation=f"Rank {d} by {agg.value} of {m}"),
                )
                compiled_sql = compile_plan_to_sql(plan_rank, "source_data")
                exec_res = self.executor.execute_plan(plan=plan_rank, dataset=dataset, semantic_profile=semantic_profile, custom_sql=compiled_sql)
                if exec_res.status == ExecutionStatus.SUCCESS and len(exec_res.rows) >= 2:
                    rows = [
                        r for r in exec_res.rows
                        if r.get(d) is not None and str(r.get(d)).strip() not in ("", "None", "nan", "NaN", "NULL", "null")
                    ]
                    if len(rows) < 2:
                        continue
                    val_col = f"{agg.value.lower()}_{m}" if f"{agg.value.lower()}_{m}" in rows[0] else list(rows[0].keys())[1]
                    
                    top_row = rows[0]
                    bottom_row = rows[-1]

                    top_group = str(top_row.get(d, ""))
                    top_val = float(top_row.get(val_col, 0.0) or 0.0)
                    bottom_group = str(bottom_row.get(d, ""))
                    bottom_val = float(bottom_row.get(val_col, 0.0) or 0.0)

                    diff = top_val - bottom_val
                    pct_diff = (diff / abs(bottom_val) * 100.0) if abs(bottom_val) > 1e-6 else 0.0

                    # 2. Ranking Candidate
                    rank_evidence = InsightEvidence(
                        source_dataset=dataset_id,
                        metric_column=m,
                        aggregation=agg,
                        dimension_column=d,
                        filters=[],
                        time_grain=None,
                        values={
                            "top_group": top_group,
                            "top_value": round(top_val, 2),
                            "bottom_group": bottom_group,
                            "bottom_value": round(bottom_val, 2),
                            "difference": round(diff, 2),
                            "difference_pct": round(pct_diff, 1),
                            "total_groups": len(rows),
                        },
                        query_or_plan=plan_rank,
                        compiled_sql=compiled_sql,
                        row_count=exec_res.row_count,
                        supporting_rows_or_groups=rows[:5],
                        statistical_metadata={
                            "group_count": len(rows),
                            "spread": round(diff, 2),
                        },
                    )
                    discovered.append((InsightType.RANKING, rank_evidence))

                    # 3. Group Comparison Candidate (if meaningful spread)
                    all_vals = [float(r.get(val_col, 0.0) or 0.0) for r in rows]
                    mean_val = float(np.mean(all_vals))
                    std_val = float(np.std(all_vals)) if len(all_vals) > 1 else 0.0
                    top_vs_mean_diff = top_val - mean_val
                    top_vs_mean_pct = (top_vs_mean_diff / abs(mean_val) * 100.0) if abs(mean_val) > 1e-6 else 0.0

                    comp_evidence = InsightEvidence(
                        source_dataset=dataset_id,
                        metric_column=m,
                        aggregation=agg,
                        dimension_column=d,
                        filters=[],
                        time_grain=None,
                        values={
                            "lead_group": top_group,
                            "lead_value": round(top_val, 2),
                            "group_mean": round(mean_val, 2),
                            "relative_premium_pct": round(top_vs_mean_pct, 1),
                            "bottom_group": bottom_group,
                            "bottom_value": round(bottom_val, 2),
                        },
                        query_or_plan=plan_rank,
                        compiled_sql=compiled_sql,
                        row_count=exec_res.row_count,
                        supporting_rows_or_groups=rows[:5],
                        statistical_metadata={
                            "variance_across_groups": round(std_val, 2),
                            "group_count": len(rows),
                        },
                    )
                    discovered.append((InsightType.GROUP_COMPARISON, comp_evidence))

        # -------------------------------------------------------------------
        # 4. Distribution / Categorical Share
        # -------------------------------------------------------------------
        for d in dimensions:
            plan_dist = CandidatePlan(
                plan_id=str(uuid4()),
                dataset_id=dataset_id,
                intent=f"Distribution of {d}",
                metric=MetricSpec(column="*", aggregation=AggregationType.COUNT),
                dimensions=[DimensionSpec(column=d, granularity=None)],
                filters=[],
                order_by="count",
                order_direction="DESC",
                visualization=VisualizationType.PIE,
                generator="insight_engine",
                provider="deterministic_engine",
                reasoning=PlanReasoning(interpretation=f"Distribution of records by {d}"),
            )
            compiled_sql = compile_plan_to_sql(plan_dist, "source_data")
            exec_res = self.executor.execute_plan(plan=plan_dist, dataset=dataset, semantic_profile=semantic_profile, custom_sql=compiled_sql)
            if exec_res.status == ExecutionStatus.SUCCESS and len(exec_res.rows) >= 2:
                rows = [
                    r for r in exec_res.rows
                    if r.get(d) is not None and str(r.get(d)).strip() not in ("", "None", "nan", "NaN", "NULL", "null")
                ]
                if len(rows) < 2:
                    continue
                cnt_col = "count" if "count" in rows[0] else list(rows[0].keys())[1]
                counts = [float(r.get(cnt_col, 0) or 0) for r in rows]
                total_cnt = sum(counts)
                if total_cnt > 0:
                    top_row = rows[0]
                    top_cat = str(top_row.get(d, ""))
                    top_cnt = float(top_row.get(cnt_col, 0) or 0)
                    top_share = (top_cnt / total_cnt) * 100.0

                    dist_evidence = InsightEvidence(
                        source_dataset=dataset_id,
                        metric_column="*",
                        aggregation=AggregationType.COUNT,
                        dimension_column=d,
                        filters=[],
                        time_grain=None,
                        values={
                            "dominant_category": top_cat,
                            "dominant_count": int(top_cnt),
                            "dominant_share_pct": round(top_share, 1),
                            "total_categories": len(rows),
                            "total_records": int(total_cnt),
                        },
                        query_or_plan=plan_dist,
                        compiled_sql=compiled_sql,
                        row_count=exec_res.row_count,
                        supporting_rows_or_groups=rows[:5],
                        statistical_metadata={
                            "top_share_fraction": round(top_share / 100.0, 3),
                            "category_count": len(rows),
                        },
                    )
                    discovered.append((InsightType.DISTRIBUTION, dist_evidence))

        # -------------------------------------------------------------------
        # 5. Temporal Trends
        # -------------------------------------------------------------------
        if datetimes:
            date_col = datetimes[0]
            grain = _infer_time_grain(df[date_col])
            for m in measures:
                agg = _resolve_aggregation(m, "", semantic_profile)
                plan_trend = CandidatePlan(
                    plan_id=str(uuid4()),
                    dataset_id=dataset_id,
                    intent=f"Trend of {m} over {date_col}",
                    metric=MetricSpec(column=m, aggregation=agg),
                    dimensions=[DimensionSpec(column=date_col, granularity=grain)],
                    filters=[],
                    order_by=date_col,
                    order_direction="ASC",
                    visualization=VisualizationType.LINE,
                    generator="insight_engine",
                    provider="deterministic_engine",
                    reasoning=PlanReasoning(interpretation=f"Analyze trend of {m} bucketed by {date_col}"),
                )
                compiled_sql = compile_plan_to_sql(plan_trend, "source_data")
                exec_res = self.executor.execute_plan(plan=plan_trend, dataset=dataset, semantic_profile=semantic_profile, custom_sql=compiled_sql)
                if exec_res.status == ExecutionStatus.SUCCESS and len(exec_res.rows) >= 2:
                    rows = exec_res.rows
                    val_col = f"{agg.value.lower()}_{m}" if f"{agg.value.lower()}_{m}" in rows[0] else list(rows[0].keys())[1]
                    vals = [float(r.get(val_col, 0.0) or 0.0) for r in rows if r.get(val_col) is not None]
                    if len(vals) >= 2:
                        first_val = vals[0]
                        last_val = vals[-1]
                        change = last_val - first_val
                        pct_change = (change / abs(first_val) * 100.0) if abs(first_val) > 1e-6 else 0.0
                        
                        # Direction
                        x = np.arange(len(vals))
                        slope = float(np.polyfit(x, vals, 1)[0]) if len(vals) > 1 else 0.0
                        direction = "increased" if slope > 0.001 else ("decreased" if slope < -0.001 else "remained stable")

                        trend_evidence = InsightEvidence(
                            source_dataset=dataset_id,
                            metric_column=m,
                            aggregation=agg,
                            dimension_column=date_col,
                            filters=[],
                            time_grain=grain,
                            values={
                                "start_value": round(first_val, 2),
                                "end_value": round(last_val, 2),
                                "net_change": round(change, 2),
                                "percent_change": round(pct_change, 1),
                                "direction": direction,
                                "periods_analyzed": len(vals),
                            },
                            query_or_plan=plan_trend,
                            compiled_sql=compiled_sql,
                            row_count=exec_res.row_count,
                            supporting_rows_or_groups=rows[:6],
                            statistical_metadata={
                                "slope": round(slope, 4),
                                "period_count": len(vals),
                            },
                        )
                        discovered.append((InsightType.TEMPORAL_TREND, trend_evidence))

        # -------------------------------------------------------------------
        # 6. Outliers / Unusual Observations
        # -------------------------------------------------------------------
        for m in measures:
            clean_s = df[m].dropna().astype(float)
            if len(clean_s) >= 8:
                q1 = float(clean_s.quantile(0.25))
                q3 = float(clean_s.quantile(0.75))
                iqr = q3 - q1
                if iqr > 1e-6:
                    lower_bound = q1 - 1.5 * iqr
                    upper_bound = q3 + 1.5 * iqr
                    outliers = clean_s[(clean_s < lower_bound) | (clean_s > upper_bound)]
                    outlier_count = len(outliers)
                    if 0 < outlier_count <= max(1, int(0.15 * len(clean_s))):
                        max_outlier = float(outliers.max()) if len(outliers) > 0 else float(clean_s.max())
                        min_outlier = float(outliers.min()) if len(outliers) > 0 else float(clean_s.min())
                        median_val = float(clean_s.median())

                        outlier_evidence = InsightEvidence(
                            source_dataset=dataset_id,
                            metric_column=m,
                            aggregation=AggregationType.AVG,
                            dimension_column=None,
                            filters=[],
                            time_grain=None,
                            values={
                                "outlier_count": outlier_count,
                                "outlier_fraction_pct": round((outlier_count / len(clean_s)) * 100.0, 1),
                                "max_outlier_value": round(max_outlier, 2),
                                "min_outlier_value": round(min_outlier, 2),
                                "dataset_median": round(median_val, 2),
                                "iqr_threshold_upper": round(upper_bound, 2),
                                "iqr_threshold_lower": round(lower_bound, 2),
                            },
                            query_or_plan=None,
                            compiled_sql=f'SELECT "{m}" FROM "{dataset_id}" WHERE "{m}" < {lower_bound} OR "{m}" > {upper_bound};',
                            row_count=outlier_count,
                            supporting_rows_or_groups=[{"outlier_value": round(v, 2)} for v in outliers.iloc[:5]],
                            statistical_metadata={
                                "q1": round(q1, 2),
                                "q3": round(q3, 2),
                                "iqr": round(iqr, 2),
                                "sample_size": len(clean_s),
                            },
                        )
                        discovered.append((InsightType.OUTLIER, outlier_evidence))

        # -------------------------------------------------------------------
        # 7. Correlation (Numeric Pairs)
        # -------------------------------------------------------------------
        if len(measures) >= 2:
            for i in range(len(measures)):
                for j in range(i + 1, len(measures)):
                    m1, m2 = measures[i], measures[j]
                    pair_df = df[[m1, m2]].dropna().astype(float)
                    if len(pair_df) >= 8:
                        std1 = float(pair_df[m1].std())
                        std2 = float(pair_df[m2].std())
                        if std1 > 1e-6 and std2 > 1e-6:
                            r_val = float(pair_df[m1].corr(pair_df[m2]))
                            if not math.isnan(r_val) and abs(r_val) >= 0.35:
                                # t-statistic and approximate p-value
                                n = len(pair_df)
                                r2 = r_val ** 2
                                strength = "strong" if abs(r_val) >= 0.70 else ("moderate" if abs(r_val) >= 0.50 else "moderate-weak")
                                direction = "positive" if r_val > 0 else "negative"

                                corr_evidence = InsightEvidence(
                                    source_dataset=dataset_id,
                                    metric_column=m1,
                                    aggregation=AggregationType.AVG,
                                    dimension_column=None,
                                    secondary_metric=m2,
                                    filters=[],
                                    time_grain=None,
                                    values={
                                        "metric_1": m1,
                                        "metric_2": m2,
                                        "correlation_r": round(r_val, 3),
                                        "r_squared": round(r2, 3),
                                        "sample_size": n,
                                        "direction": direction,
                                        "strength": strength,
                                    },
                                    query_or_plan=None,
                                    compiled_sql=f'SELECT CORR("{m1}", "{m2}") AS corr FROM "{dataset_id}";',
                                    row_count=n,
                                    supporting_rows_or_groups=[],
                                    statistical_metadata={
                                        "sample_size": n,
                                        "method": "pearson",
                                        "r": round(r_val, 4),
                                    },
                                )
                                discovered.append((InsightType.CORRELATION, corr_evidence))

        return discovered
