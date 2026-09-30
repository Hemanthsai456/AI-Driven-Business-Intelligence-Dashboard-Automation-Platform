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

    # General Rule: Unresolvable Request / Missing Target Schema
    # If requested_metrics AND requested_dimensions are both empty AND unresolved_terms is non-empty,
    # the request cannot be answered from the dataset schema -> blocking ambiguity / UNANSWERABLE.
    from orchestrator.intent import interpret_user_request
    structured = intent if isinstance(intent, StructuredIntent) else interpret_user_request(raw_intent, semantic_profile)

    if not structured.requested_metrics and not structured.requested_dimensions and structured.unresolved_terms:
        return AmbiguityResult(
            status=AmbiguityStatus.UNANSWERABLE,
            ambiguities=[
                AmbiguityDetail(
                    type=AmbiguityType.MULTIPLE_MEASURES,
                    field="intent_terms",
                    alternatives=list(structured.unresolved_terms),
                    is_blocking=True,
                )
            ],
            message=f"Request contains unmapped terms {structured.unresolved_terms} with no identifiable metrics or dimensions in dataset schema.",
            is_blocking=True,
        )

    tokens = _tokenize(raw_intent)
    ambiguities: List[AmbiguityDetail] = []

    # Partition columns by role
    measures: List[str] = []
    dates: List[str] = []
    dimensions: List[str] = []

    for col, ev in semantic_profile.column_evidences.items():
        if ev.candidate_role == ColumnRole.MEASURE:
            measures.append(col)
        elif ev.candidate_role == ColumnRole.DATETIME:
            dates.append(col)
        elif ev.candidate_role == ColumnRole.DIMENSION:
            dimensions.append(col)

    # Check 1: Temporal trend requested with multiple date columns (Item-level ambiguity)
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
                )
            )

    # Check 2: Measure ambiguity when user gives generic request (Request-level blocking ambiguity)
    generic_measure_keywords = {"metric", "performance", "kpi", "numbers", "stats", "data", "summary"}
    if (tokens & generic_measure_keywords) and len(measures) > 1:
        named_measures = [m for m in measures if m.lower() in raw_intent.lower()]
        if not named_measures:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.MULTIPLE_MEASURES,
                    field="metric_column",
                    alternatives=measures,
                    is_blocking=True,  # Request-level blocking: user must clarify what to measure
                )
            )

    if ambiguities:
        messages = [
            f"Ambiguity detected in {a.field} ({a.type.value}): choose from {a.alternatives}"
            for a in ambiguities
        ]
        has_blocking = any(a.is_blocking for a in ambiguities)
        return AmbiguityResult(
            status=AmbiguityStatus.AMBIGUOUS,
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
