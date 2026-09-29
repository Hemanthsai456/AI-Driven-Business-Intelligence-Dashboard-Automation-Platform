"""Discrete Interpretation Generation stage in the 6-step cognitive loop.

Transforms StructuredIntent and Ambiguity assessment into 1..K discrete,
coherent SemanticInterpretation instances.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.schemas import (
    AggregationType,
    AmbiguityResult,
    AmbiguityType,
    Granularity,
    SemanticInterpretation,
    StructuredIntent,
    VisualizationType,
)


def _granularity_from_string(gran_str: Optional[str]) -> Optional[Granularity]:
    if not gran_str:
        return None
    val = gran_str.strip().upper()
    try:
        return Granularity[val]
    except KeyError:
        return None


def _col_confidence(semantic_profile: DatasetSemanticProfile, col: str) -> float:
    ev = semantic_profile.get_evidence(col)
    return float(ev.confidence) if ev else 0.5


def generate_interpretations(
    structured_intent: StructuredIntent,
    semantic_profile: DatasetSemanticProfile,
    ambiguity: Optional[AmbiguityResult] = None,
    k: int = 3,
) -> List[SemanticInterpretation]:
    """Generate 1 to K distinct, coherent SemanticInterpretation instances.

    Behavior:
    1. If item-level ambiguity exists (e.g., multiple date columns for trend),
       forks separate interpretations for each alternative date column.
    2. If multiple candidate metrics or dimensions were requested, forks distinct
       interpretations exploring primary analytical choices.
    3. If unambiguous, produces the canonical interpretation with explicit
       evidence and minimal assumptions.
    """
    interpretations: List[SemanticInterpretation] = []

    # Partition columns by role
    measures: List[str] = []
    dimensions: List[str] = []
    datetimes: List[str] = []

    for col, ev in semantic_profile.column_evidences.items():
        if ev.candidate_role == ColumnRole.MEASURE:
            measures.append(col)
        elif ev.candidate_role == ColumnRole.DIMENSION:
            dimensions.append(col)
        elif ev.candidate_role == ColumnRole.DATETIME:
            datetimes.append(col)

    # Resolve primary metric
    candidate_metrics = structured_intent.requested_metrics or measures
    primary_metric = candidate_metrics[0] if candidate_metrics else (measures[0] if measures else "count")
    metric_agg = AggregationType.SUM if primary_metric in measures else AggregationType.COUNT

    # Resolve primary dimension
    primary_dims = structured_intent.requested_dimensions
    granularity = _granularity_from_string(structured_intent.grouping_granularity)

    # Check for item-level date ambiguity
    date_alts: List[str] = []
    if ambiguity and ambiguity.ambiguities:
        for amb in ambiguity.ambiguities:
            if amb.type == AmbiguityType.MULTIPLE_DATE_COLUMNS and amb.alternatives:
                date_alts = amb.alternatives

    # Scenario 1: Multiple date column alternatives -> fork interpretations
    if date_alts and len(date_alts) > 1:
        for idx, date_col in enumerate(date_alts[:k]):
            vis = VisualizationType.LINE if structured_intent.analytical_goal == "trend" else VisualizationType.BAR
            dim_cols = [date_col]
            if primary_dims:
                dim_cols = [date_col] + [d for d in primary_dims if d != date_col]

            interp = SemanticInterpretation(
                interpretation_id=str(uuid4()),
                intent_summary=f"Analyze {primary_metric} trend over time bucketed by {date_col}",
                metric_column=primary_metric,
                aggregation=metric_agg,
                dimension_columns=dim_cols,
                granularity=granularity or Granularity.MONTH,
                visualization=vis,
                resolved_intent_elements={
                    "metric": primary_metric,
                    "date_column": date_col,
                    "granularity": (granularity or Granularity.MONTH).value,
                },
                referenced_columns=[primary_metric] + dim_cols,
                assumptions=[f"Assumed date dimension '{date_col}' among available alternatives: {date_alts}"],
                unresolved_elements=[],
                evidence=[
                    f"Metric '{primary_metric}' confidence: {_col_confidence(semantic_profile, primary_metric):.2f}",
                    f"Date '{date_col}' confidence: {_col_confidence(semantic_profile, date_col):.2f}",
                ],
                confidence=round(structured_intent.confidence * 0.9, 2),
            )
            interpretations.append(interp)

    # Scenario 2: Multiple candidate metrics requested -> fork interpretations
    elif len(structured_intent.requested_metrics) > 1:
        for m_col in structured_intent.requested_metrics[:k]:
            vis = VisualizationType.BAR if primary_dims else VisualizationType.KPI
            interp = SemanticInterpretation(
                interpretation_id=str(uuid4()),
                intent_summary=f"Aggregate {m_col} across {primary_dims or 'entire dataset'}",
                metric_column=m_col,
                aggregation=AggregationType.SUM,
                dimension_columns=primary_dims,
                granularity=granularity,
                visualization=vis,
                resolved_intent_elements={
                    "metric": m_col,
                    "dimensions": primary_dims,
                },
                referenced_columns=[m_col] + primary_dims,
                assumptions=[],
                unresolved_elements=structured_intent.unresolved_terms,
                evidence=[
                    f"Metric '{m_col}' confidence: {_col_confidence(semantic_profile, m_col):.2f}",
                ],
                confidence=structured_intent.confidence,
            )
            interpretations.append(interp)

    # Scenario 3: Canonical single interpretation
    if not interpretations:
        dim_cols = list(primary_dims)
        temporal_col = structured_intent.temporal_scope or (datetimes[0] if structured_intent.analytical_goal == "trend" and datetimes else None)

        if temporal_col and temporal_col not in dim_cols:
            dim_cols.append(temporal_col)

        # Visualization selection
        if structured_intent.requested_visual_preferences:
            vis_map = {
                "bar": VisualizationType.BAR,
                "line": VisualizationType.LINE,
                "pie": VisualizationType.PIE,
                "table": VisualizationType.TABLE,
                "kpi": VisualizationType.KPI,
                "scatter": VisualizationType.SCATTER,
                "area": VisualizationType.AREA,
            }
            vis = vis_map.get(structured_intent.requested_visual_preferences.lower(), VisualizationType.BAR)
        elif structured_intent.analytical_goal == "trend":
            vis = VisualizationType.LINE
        elif not dim_cols:
            vis = VisualizationType.KPI
        elif len(dim_cols) == 1:
            vis = VisualizationType.BAR
        else:
            vis = VisualizationType.TABLE

        evidence_list = []
        if primary_metric in semantic_profile.column_evidences:
            evidence_list.append(
                f"Metric '{primary_metric}' confidence: {_col_confidence(semantic_profile, primary_metric):.2f}"
            )
        for d in dim_cols:
            if d in semantic_profile.column_evidences:
                evidence_list.append(
                    f"Dimension '{d}' confidence: {_col_confidence(semantic_profile, d):.2f}"
                )

        interp = SemanticInterpretation(
            interpretation_id=str(uuid4()),
            intent_summary=f"Compute {metric_agg.value} of {primary_metric}" + (f" by {', '.join(dim_cols)}" if dim_cols else ""),
            metric_column=primary_metric,
            aggregation=metric_agg,
            dimension_columns=dim_cols,
            granularity=granularity if temporal_col else None,
            visualization=vis,
            resolved_intent_elements={
                "metric": primary_metric,
                "dimensions": dim_cols,
                "granularity": granularity.value if (temporal_col and granularity) else None,
            },
            referenced_columns=[primary_metric] + dim_cols,
            assumptions=[] if primary_dims or temporal_col else ["Defaulted to aggregated summary view."],
            unresolved_elements=structured_intent.unresolved_terms,
            evidence=evidence_list,
            confidence=structured_intent.confidence,
        )
        interpretations.append(interp)

    return interpretations[:k]
