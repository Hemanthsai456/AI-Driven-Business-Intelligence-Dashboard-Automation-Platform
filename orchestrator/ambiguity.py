"""Ambiguity pre-check engine and active ambiguity gate for analytical requests.

Architecture references:
- orchestrator_conformance.md §1 ('Ambiguity Handling')
- 6-step cognitive loop: Active Ambiguity Gate
"""

from __future__ import annotations

import re
from typing import List, Optional, Set, Union
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.schemas import (
    AmbiguityDetail,
    AmbiguityResult,
    AmbiguityStatus,
    AmbiguityType,
    StructuredIntent,
)


def _tokenize(text: str) -> Set[str]:
    """Tokenize lowercased text into alphanumeric words."""
    return set(re.findall(r"\b[a-z0-9_]+\b", text.lower()))


def assess_ambiguity(
    intent: Union[str, StructuredIntent],
    semantic_profile: DatasetSemanticProfile,
) -> AmbiguityResult:
    """Assess whether an analytical request is CLEAR, AMBIGUOUS, or UNANSWERABLE.

    Distinguishes:
    A. Request-level blocking ambiguity:
       - Empty request (UNANSWERABLE)
       - Generic request with multiple measures where analytical target cannot be determined (AMBIGUOUS, is_blocking=True)
       - Request referencing non-existent KPIs (UNANSWERABLE or AMBIGUOUS, is_blocking=True)
    B. Item-level ambiguity:
       - Multiple date columns when temporal trend requested (AMBIGUOUS, is_blocking=False; branched via interpretations)
       - Specific ambiguity that can be isolated without blocking the entire pipeline
    """
    raw_intent = intent.original_request if isinstance(intent, StructuredIntent) else intent
    if not raw_intent or not raw_intent.strip():
        return AmbiguityResult(
            status=AmbiguityStatus.UNANSWERABLE,
            ambiguities=[],
            message="Analytical request is empty.",
            is_blocking=True,
        )

    from orchestrator.intent import interpret_user_request
    structured = intent if isinstance(intent, StructuredIntent) else interpret_user_request(raw_intent, semantic_profile)

    tokens = _tokenize(raw_intent)
    ambiguities: List[AmbiguityDetail] = []
    is_unanswerable = (
        not structured.requested_metrics
        and not structured.requested_dimensions
        and bool(structured.unresolved_terms)
    )

    # Partition columns by role
    measures: List[str] = []
    dates: List[str] = []
    dimensions: List[str] = []

    for col, ev in semantic_profile.column_evidences.items():
        if ev.candidate_role == ColumnRole.MEASURE:
            measures.append(col)
        elif ev.candidate_role == ColumnRole.DATETIME:
            dates.append(col)
        elif ev.candidate_role in (ColumnRole.DIMENSION, ColumnRole.IDENTIFIER):
            dimensions.append(col)

    # Check 1: Temporal trend requested with multiple date columns (Granularity/Date ambiguity)
    temporal_keywords = {"trend", "monthly", "daily", "yearly", "over", "time", "timeline", "history", "recent"}
    if tokens & temporal_keywords and len(dates) > 1:
        named_dates = [d for d in dates if d.lower() in raw_intent.lower()]
        if not named_dates:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.MULTIPLE_DATE_COLUMNS,
                    field="date_dimension",
                    alternatives=dates,
                    is_blocking=False,  # Item-level: can generate parallel interpretations
                    category="granularity",
                )
            )

    # Check 2: Measure ambiguity when user gives generic request (Lexical ambiguity)
    generic_measure_keywords = {"metric", "performance", "kpi", "numbers", "stats", "data", "summary"}
    if (tokens & generic_measure_keywords) and len(measures) > 1:
        named_measures = [m for m in measures if m.lower() in raw_intent.lower()]
        if not named_measures:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.LEXICAL,
                    field="metric_column",
                    alternatives=measures,
                    is_blocking=True,  # Request-level blocking: user must clarify what to measure
                    category="lexical",
                )
            )

    # Check 3: Scope Ambiguity (vague ranking or filtering scope: top, best, recent, outliers)
    scope_keywords = {"top", "best", "worst", "highest", "lowest", "outliers", "anomalies", "recent"}
    if tokens & scope_keywords:
        if "recent" in tokens and len(dates) == 0:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.SCOPE,
                    field="temporal_scope",
                    alternatives=[f"No datetime columns found in dataset; candidate dimensions: {dimensions}"],
                    is_blocking=True,
                    category="scope",
                )
            )
        elif (tokens & {"top", "best", "worst", "highest", "lowest"}) and not any(re.search(r"\b\d+\b", raw_intent) for _ in [0]):
            if not structured.requested_metrics and not structured.requested_dimensions:
                ambiguities.append(
                    AmbiguityDetail(
                        type=AmbiguityType.SCOPE,
                        field="ranking_scope",
                        alternatives=measures if measures else dimensions,
                        is_blocking=True,
                        category="scope",
                    )
                )

    # Check 4: Granularity Ambiguity (trend or time-series requested without explicit frequency)
    if (tokens & {"trend", "timeline", "history"}) or ("over" in tokens and "time" in tokens):
        if structured.grouping_granularity is None and (dates or structured.temporal_scope):
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.GRANULARITY,
                    field="temporal_granularity",
                    alternatives=["month", "quarter", "year", "day"],
                    is_blocking=False,
                    category="granularity",
                )
            )

    # Check 5: Aggregation Ambiguity (metric specified without aggregation operator)
    agg_keywords = {"total", "sum", "average", "avg", "mean", "count", "min", "max", "percentage", "rate"}
    if structured.requested_metrics and not (tokens & agg_keywords):
        ambiguities.append(
            AmbiguityDetail(
                type=AmbiguityType.AGGREGATION,
                field=structured.requested_metrics[0],
                alternatives=["sum", "avg", "count", "max", "min"],
                is_blocking=False,
                category="aggregation",
            )
        )

    # Check 6: Lexical Ambiguity for unmapped concepts/terms
    if structured.unresolved_terms and not (tokens & generic_measure_keywords):
        candidate_cols = dimensions + measures
        for term in structured.unresolved_terms:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.LEXICAL,
                    field=term,
                    alternatives=[c for c in candidate_cols if term in c.lower()] or candidate_cols[:3],
                    is_blocking=True,
                    category="lexical",
                )
            )

    if is_unanswerable and not ambiguities:
        candidate_cols = list(semantic_profile.column_evidences.keys())
        ambiguities.append(
            AmbiguityDetail(
                type=AmbiguityType.LEXICAL,
                field="intent_terms",
                alternatives=candidate_cols,
                is_blocking=True,
                category="lexical",
            )
        )

    if ambiguities:
        messages = [
            f"Ambiguity detected in {a.field} [{a.category or a.type.value}]: candidate columns/options {a.alternatives}"
            for a in ambiguities
        ]
        has_blocking = True if is_unanswerable else any(a.is_blocking for a in ambiguities)
        return AmbiguityResult(
            status=AmbiguityStatus.UNANSWERABLE if is_unanswerable else AmbiguityStatus.AMBIGUOUS,
            ambiguities=ambiguities,
            message="; ".join(messages),
            is_blocking=has_blocking,
        )

    return AmbiguityResult(
        status=AmbiguityStatus.CLEAR,
        ambiguities=[],
        message=None,
        is_blocking=False,
    )


def is_blocking_ambiguity(
    ambiguity: AmbiguityResult,
    structured_intent: Optional[StructuredIntent] = None,
) -> bool:
    """Return True if ambiguity represents a request-level block requiring clarification."""
    if ambiguity.status == AmbiguityStatus.UNANSWERABLE:
        return True
    if ambiguity.status == AmbiguityStatus.AMBIGUOUS and ambiguity.is_blocking:
        return True
    return False
