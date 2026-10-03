"""Deterministic Candidate Insight Enumerator (Stage E1).

Generates typed insight candidates by systematically enumerating and pruning
combinations of (measure x aggregation x dimension) based on cleaned data and
semantic roles.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.profiler import DataProfile
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


def _infer_granularity(dt_series: pd.Series) -> Granularity:
    """Infer suitable temporal granularity from date span."""
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


def enumerate_candidate_insights(
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    data_profile: Optional[DataProfile] = None,
    cap_per_type: int = 8,
) -> List[InsightCandidate]:
    """Deterministically enumerate typed insight candidates.

    Pruning Rules:
    - Exclude IDENTIFIER columns as dimensions.
    - Exclude constant columns (nunique <= 1 or min == max).
    - Exclude near-empty columns (null rate > 0.5).
    - Exclude high-cardinality dimensions (nunique > 50 or nunique/N > 0.4 for N > 30).
    - Cap candidates per insight type.

    Returns:
        List of typed InsightCandidate objects.
    """
    df = dataset.data
    total_rows = len(df)
    if total_rows == 0:
        return []

    # 1. Classify columns by role & prune
    eligible_measures: List[str] = []
    eligible_dimensions: List[str] = []
    eligible_datetimes: List[str] = []

    # Collect column names deterministically (sorted)
    col_names = sorted(list(df.columns))

    for col in col_names:
        ev = semantic_profile.get_evidence(col)
        role = ev.candidate_role if ev else ColumnRole.UNKNOWN

        # Check null rate
        null_count = df[col].isna().sum()
        null_rate = null_count / total_rows if total_rows > 0 else 1.0
        if null_rate > 0.5:
            continue

        # Check distinct count
        distinct_count = df[col].nunique(dropna=True)
        if distinct_count <= 1:
            # Constant column
            continue

        # Identify Measures
        if role == ColumnRole.MEASURE or (
            role != ColumnRole.IDENTIFIER
            and role != ColumnRole.DATETIME
            and pd.api.types.is_numeric_dtype(df[col])
            and distinct_count > 1
        ):
            # Check not constant values
            try:
                valid_num = pd.to_numeric(df[col].dropna(), errors="coerce").dropna()
                if len(valid_num) > 1 and valid_num.std() > 0:
                    eligible_measures.append(col)
            except Exception:
                pass

        # Identify Dimensions (Only near-unique IDs are excluded as dimensions)
        is_near_unique_id = False
        if role == ColumnRole.IDENTIFIER:
            if ev and ev.sub_role == "FOREIGN_KEY":
                is_near_unique_id = False
            elif distinct_count == total_rows or (total_rows > 0 and (distinct_count / total_rows) >= 0.90):
                is_near_unique_id = True

        if role == ColumnRole.DIMENSION or (role == ColumnRole.IDENTIFIER and not is_near_unique_id):
            # Exclude high-cardinality
            is_high_card = distinct_count > 50 or (total_rows > 30 and (distinct_count / total_rows) > 0.4)
            if not is_high_card:
                eligible_dimensions.append(col)

        # Identify Datetimes
        if role == ColumnRole.DATETIME or (
            role != ColumnRole.IDENTIFIER
            and (pd.api.types.is_datetime64_any_dtype(df[col]) or "date" in col.lower() or "time" in col.lower())
        ):
            eligible_datetimes.append(col)

    # Sort all lists for 100% determinism
    eligible_measures = sorted(list(set(eligible_measures)))
    eligible_dimensions = sorted(list(set(eligible_dimensions)))
    eligible_datetimes = sorted(list(set(eligible_datetimes)))

    candidates_by_type: Dict[InsightType, List[InsightCandidate]] = {
        t: [] for t in InsightType
    }

    dataset_id = dataset.metadata.dataset_id or "dataset"

    # Helper to construct candidate
    def _create_candidate(
        insight_type: InsightType,
        measure: str,
        dim: Optional[str] = None,
        secondary_measure: Optional[str] = None,
        agg: AggregationType = AggregationType.SUM,
        granularity: Optional[Granularity] = None,
        vis: VisualizationType = VisualizationType.TABLE,
        params: Optional[Dict[str, Any]] = None,
    ) -> InsightCandidate:
        dims = []
        if dim:
            dims.append(DimensionSpec(column=dim, granularity=granularity))

        plan = CandidatePlan(
            dataset_id=dataset_id,
            intent=f"Discovery {insight_type.value}: {agg.value}({measure})" + (f" by {dim}" if dim else ""),
            metric=MetricSpec(column=measure, aggregation=agg),
            dimensions=dims,
            visualization=vis,
            generator="discovery_enumerator",
            reasoning=PlanReasoning(
                interpretation=f"Evaluate {insight_type.value} for {agg.value}({measure})" + (f" grouped by {dim}" if dim else ""),
                evidence=[f"Role {measure}: MEASURE", f"Role {dim}: DIMENSION"] if dim else [f"Role {measure}: MEASURE"],
            ),
        )

        return InsightCandidate(
            insight_type=insight_type,
            plan=plan,
            measure=measure,
            secondary_measure=secondary_measure,
            dimension=dim,
            aggregation=agg,
            proposed_by="enumerator",
            params=params or {},
        )

    # 1. TOTAL_KPI (chosen by measure semantics: AVG for rates/prices/ratios, SUM for amounts/totals)
    avg_tokens = {"price", "unitprice", "rate", "pct", "percentage", "ratio", "score", "margin", "discount", "rating", "age"}
    for m in eligible_measures:
        m_lower = m.lower().replace("_", "")
        preferred_agg = AggregationType.AVG if any(t in m_lower for t in avg_tokens) else AggregationType.SUM
        candidates_by_type[InsightType.TOTAL_KPI].append(
            _create_candidate(
                InsightType.TOTAL_KPI,
                measure=m,
                agg=preferred_agg,
                vis=VisualizationType.KPI,
            )
        )

    # 2. RANKING (Top and Bottom groups: k >= 3)
    for m in eligible_measures:
        for d in eligible_dimensions:
            d_card = df[d].nunique(dropna=True)
            if d_card >= 3:
                candidates_by_type[InsightType.RANKING].append(
                    _create_candidate(
                        InsightType.RANKING,
                        measure=m,
                        dim=d,
                        agg=AggregationType.SUM,
                        vis=VisualizationType.BAR,
                        params={"ranking_mode": "top_bottom"},
                    )
                )

    # 2b. COUNT(*) RANKING (When a dimension exists, enumerate COUNT(*) by dimension)
    for d in eligible_dimensions:
        d_card = df[d].nunique(dropna=True)
        if d_card >= 3:
            candidates_by_type[InsightType.RANKING].append(
                _create_candidate(
                    InsightType.RANKING,
                    measure="*",
                    dim=d,
                    agg=AggregationType.COUNT,
                    vis=VisualizationType.BAR,
                    params={"ranking_mode": "top_bottom", "is_count": True},
                )
            )

    # 3. COMPOSITION (Share of total: k >= 3)
    for m in eligible_measures:
        for d in eligible_dimensions:
            d_card = df[d].nunique(dropna=True)
            if d_card >= 3:
                candidates_by_type[InsightType.COMPOSITION].append(
                    _create_candidate(
                        InsightType.COMPOSITION,
                        measure=m,
                        dim=d,
                        agg=AggregationType.SUM,
                        vis=VisualizationType.BAR,
                        params={"composition_mode": "share_of_total"},
                    )
                )

    # 3b. COUNT(*) COMPOSITION (When a dimension exists, enumerate COUNT(*) by dimension)
    for d in eligible_dimensions:
        d_card = df[d].nunique(dropna=True)
        if 2 <= d_card <= 8:
            candidates_by_type[InsightType.COMPOSITION].append(
                _create_candidate(
                    InsightType.COMPOSITION,
                    measure="*",
                    dim=d,
                    agg=AggregationType.COUNT,
                    vis=VisualizationType.BAR,
                    params={"composition_mode": "share_of_total", "is_count": True},
                )
            )

    # 4. TREND (Needs datetime)
    if eligible_datetimes:
        for dt_col in eligible_datetimes:
            gran = _infer_granularity(df[dt_col])
            for m in eligible_measures:
                candidates_by_type[InsightType.TREND].append(
                    _create_candidate(
                        InsightType.TREND,
                        measure=m,
                        dim=dt_col,
                        agg=AggregationType.SUM,
                        granularity=gran,
                        vis=VisualizationType.LINE,
                        params={"time_column": dt_col, "granularity": gran.value},
                    )
                )

    # 5. PERIOD_CHANGE (Needs datetime)
    if eligible_datetimes:
        for dt_col in eligible_datetimes:
            gran = _infer_granularity(df[dt_col])
            for m in eligible_measures:
                candidates_by_type[InsightType.PERIOD_CHANGE].append(
                    _create_candidate(
                        InsightType.PERIOD_CHANGE,
                        measure=m,
                        dim=dt_col,
                        agg=AggregationType.SUM,
                        granularity=gran,
                        vis=VisualizationType.LINE,
                        params={"time_column": dt_col, "granularity": gran.value, "comparison": "period_over_period"},
                    )
                )

    # 6. DISTRIBUTION_OUTLIERS
    for m in eligible_measures:
        candidates_by_type[InsightType.DISTRIBUTION_OUTLIERS].append(
            _create_candidate(
                InsightType.DISTRIBUTION_OUTLIERS,
                measure=m,
                agg=AggregationType.AVG,
                vis=VisualizationType.BAR,
                params={"detection_method": "iqr_and_zscore"},
            )
        )

    # 7. CORRELATION (Measure pairs)
    for i in range(len(eligible_measures)):
        for j in range(i + 1, len(eligible_measures)):
            m1 = eligible_measures[i]
            m2 = eligible_measures[j]

            # Check derived measure arithmetic relationship
            ev1 = semantic_profile.get_evidence(m1) if semantic_profile else None
            ev2 = semantic_profile.get_evidence(m2) if semantic_profile else None
            is_arithmetic = False
            if ev1 and ev1.sub_role == "DERIVED" and ev1.derived_parts and m2 in ev1.derived_parts:
                is_arithmetic = True
            elif ev2 and ev2.sub_role == "DERIVED" and ev2.derived_parts and m1 in ev2.derived_parts:
                is_arithmetic = True

            candidates_by_type[InsightType.CORRELATION].append(
                _create_candidate(
                    InsightType.CORRELATION,
                    measure=m1,
                    secondary_measure=m2,
                    agg=AggregationType.AVG,
                    vis=VisualizationType.SCATTER if hasattr(VisualizationType, "SCATTER") else VisualizationType.TABLE,
                    params={"measure_x": m1, "measure_y": m2, "is_arithmetic": is_arithmetic},
                )
            )

    # 8. SEGMENT_GAP (Difference between groups: binary segments k == 2)
    for m in eligible_measures:
        for d in eligible_dimensions:
            d_card = df[d].nunique(dropna=True)
            if d_card == 2:
                candidates_by_type[InsightType.SEGMENT_GAP].append(
                    _create_candidate(
                        InsightType.SEGMENT_GAP,
                        measure=m,
                        dim=d,
                        agg=AggregationType.AVG,
                        vis=VisualizationType.BAR,
                        params={"effect_size_metric": "eta_squared", "group_count": d_card},
                    )
                )

    # Cap candidates per type deterministically
    all_pruned_candidates: List[InsightCandidate] = []
    for insight_type in InsightType:
        type_cands = candidates_by_type[insight_type]
        # Sort candidates for stability
        type_cands.sort(
            key=lambda c: (
                c.measure,
                c.dimension or "",
                c.secondary_measure or "",
                c.aggregation.value,
            )
        )
        capped = type_cands[:cap_per_type]
        all_pruned_candidates.extend(capped)

    return all_pruned_candidates
