"""Ambiguity pre-check engine evaluating natural-language requests against semantic profiles.

Architecture references:
- orchestrator_conformance.md §1 ('Ambiguity Handling')
- orchestrator_contracts.md §AmbiguityResult
"""

from __future__ import annotations

import re
from typing import List, Set
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.schemas import (
    AmbiguityDetail,
    AmbiguityResult,
    AmbiguityStatus,
    AmbiguityType,
)


def _tokenize(text: str) -> Set[str]:
    """Tokenize lowercased text into alphanumeric words."""
    return set(re.findall(r"\b[a-z0-9]+\b", text.lower()))


def assess_ambiguity(
    intent: str,
    semantic_profile: DatasetSemanticProfile,
) -> AmbiguityResult:
    """Assess whether an analytical request is CLEAR, AMBIGUOUS, or UNANSWERABLE.

    Checks:
    1. Empty / unanswerable request.
    2. Multiple matching measures when user request is non-specific (e.g. 'show sales').
    3. Multiple date columns when temporal analysis ('trend', 'over time') is requested.
    4. Explicit requests referencing non-existent concepts.
    """
    if not intent or not intent.strip():
        return AmbiguityResult(
            status=AmbiguityStatus.UNANSWERABLE,
            ambiguities=[],
            message="Analytical request is empty.",
        )

    tokens = _tokenize(intent)
    ambiguities: List[AmbiguityDetail] = []

    # Partition columns by role
    measures: List[str] = []
    dates: List[str] = []
    for col, ev in semantic_profile.column_evidences.items():
        if ev.candidate_role == ColumnRole.MEASURE:
            measures.append(col)
        elif ev.candidate_role == ColumnRole.DATETIME:
            dates.append(col)

    # Check 1: Temporal trend requested with multiple date columns
    temporal_keywords = {"trend", "monthly", "daily", "yearly", "over", "time", "timeline", "history", "recent"}
    if tokens & temporal_keywords and len(dates) > 1:
        # Check if the user specifically named one of the date columns
        named_dates = [d for d in dates if d.lower() in intent.lower()]
        if not named_dates:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.MULTIPLE_DATE_COLUMNS,
                    field="date_dimension",
                    alternatives=dates,
                )
            )

    # Check 2: Measure ambiguity when user gives generic request
    generic_measure_keywords = {"metric", "performance", "kpi", "numbers", "stats", "data", "summary"}
    if (tokens & generic_measure_keywords) and len(measures) > 1:
        named_measures = [m for m in measures if m.lower() in intent.lower()]
        if not named_measures:
            ambiguities.append(
                AmbiguityDetail(
                    type=AmbiguityType.MULTIPLE_MEASURES,
                    field="metric_column",
                    alternatives=measures,
                )
            )

    if ambiguities:
        messages = [
            f"Ambiguity detected in {a.field} ({a.type.value}): choose from {a.alternatives}"
            for a in ambiguities
        ]
        return AmbiguityResult(
            status=AmbiguityStatus.AMBIGUOUS,
            ambiguities=ambiguities,
            message="; ".join(messages),
        )

    return AmbiguityResult(
        status=AmbiguityStatus.CLEAR,
        ambiguities=[],
        message=None,
    )
