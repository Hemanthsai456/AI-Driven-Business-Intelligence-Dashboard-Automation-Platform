"""Orchestrator utility functions.

Contains plan_signature deduplication, Ranker V1 scoring, and
Candidate Output Consistency Check logic.

Ranker V1 is deterministic, zero-LLM:
    score = w1*evidence + w2*coverage + w3*stability - w4*assumptions

All weights and thresholds are project decisions (hypotheses), logged alongside
every ranking decision for auditability.
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional, Sequence, Tuple

from orchestrator.config import (
    RANK_TIE_EPSILON,
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RESULT_ROW_CAP,
)
from orchestrator.schemas import (
    AggregationType,
    CandidateConsistencyCheck,
    CandidatePlan,
    ExecutionResult,
    ExecutionStatus,
    RankedCandidate,
    RankerWeights,
    ScoreBreakdown,
)


# ---------------------------------------------------------------------------
# Ranker V1 — deterministic, zero LLM
# ---------------------------------------------------------------------------


def _compute_evidence(plan: CandidatePlan, semantic_evidences: dict) -> float:
    """Mean role confidence of columns used in the plan.

    Args:
        plan: The candidate plan.
        semantic_evidences: Dict[column_name, ColumnSemanticEvidence] from
            DatasetSemanticProfile.column_evidences.

    Returns:
        Mean confidence in [0.0, 1.0].  Returns 0.0 if no columns found.
    """
    used_columns = {plan.metric.column}
    for dim in plan.dimensions:
        used_columns.add(dim.column)
    for f in plan.filters:
        used_columns.add(f.column)

    confidences = []
    for col in used_columns:
        ev = semantic_evidences.get(col)
        if ev is not None:
            confidences.append(float(ev.confidence))

    if not confidences:
        return 0.0
    return sum(confidences) / len(confidences)


def _compute_coverage(plan: CandidatePlan, intent_tokens: Sequence[str]) -> float:
    """Fraction of intent tokens that appear in plan field values.

    Args:
        plan: The candidate plan.
        intent_tokens: Lower-cased word tokens from the original request.

    Returns:
        Coverage in [0.0, 1.0].
    """
    if not intent_tokens:
        return 0.0

    plan_text = " ".join(
        [
            plan.metric.column.lower(),
            plan.metric.aggregation.lower(),
            plan.intent.lower(),
        ]
        + [d.column.lower() for d in plan.dimensions]
        + [f.column.lower() for f in plan.filters]
    )

    matched = sum(1 for token in intent_tokens if token in plan_text)
    return min(1.0, matched / len(intent_tokens))


def _compute_stability(
    execution_result: ExecutionResult,
) -> float:
    """Stability proxy: penalise high failed-cast rates and near-empty results.

    True perturbation stability (running adjacent granularity variants) is
    deferred to Stage 7.  This is a V1 proxy based on execution quality.

    Returns:
        Stability score in [0.0, 1.0].
    """
    if execution_result.status != ExecutionStatus.SUCCESS:
        return 0.0

    # Penalise failed-cast rate proportionally
    cast_penalty = execution_result.failed_cast_rate

    # Penalise near-empty results (< 2 rows has low stability signal)
    empty_penalty = 0.2 if execution_result.row_count < 2 else 0.0

    return max(0.0, 1.0 - cast_penalty - empty_penalty)


def _compute_assumptions(plan: CandidatePlan) -> float:
    """Normalised assumption count.

    An assumption is a field that has a non-trivial default value
    (e.g. visualization defaulted to TABLE, no comparison requested, no filters).
    Higher assumption count = lower score.

    Returns:
        Normalised assumption penalty in [0.0, 1.0].
    """
    assumptions = 0

    # Visualization defaulted to TABLE is a weak assumption
    from orchestrator.schemas import VisualizationType
    if plan.visualization == VisualizationType.TABLE:
        assumptions += 1

    # No dimensions specified
    if not plan.dimensions:
        assumptions += 1

    # No filters specified
    if not plan.filters:
        assumptions += 1

    # No comparison specified
    if plan.comparison is None:
        assumptions += 1

    # Normalise over max possible (currently 4)
    return assumptions / 4.0


def compute_score(
    plan: CandidatePlan,
    execution_result: ExecutionResult,
    semantic_evidences: dict,
    intent_tokens: Sequence[str],
    weights: Optional[RankerWeights] = None,
) -> ScoreBreakdown:
    """Compute Ranker V1 score for a candidate plan.

    Args:
        plan: The candidate plan.
        execution_result: DuckDB worker output.
        semantic_evidences: Dict[str, ColumnSemanticEvidence].
        intent_tokens: Lower-cased word tokens from the request.
        weights: Ranker weights (defaults to config values if None).

    Returns:
        ScoreBreakdown with individual components and weighted total.
    """
    if weights is None:
        weights = RankerWeights(
            w1_evidence=RANK_W1_EVIDENCE,
            w2_coverage=RANK_W2_COVERAGE,
            w3_stability=RANK_W3_STABILITY,
            w4_assumptions=RANK_W4_ASSUMPTIONS,
        )

    evidence = _compute_evidence(plan, semantic_evidences)
    coverage = _compute_coverage(plan, intent_tokens)
    stability = _compute_stability(execution_result)
    assumptions = _compute_assumptions(plan)

    total = (
        weights.w1_evidence * evidence
        + weights.w2_coverage * coverage
        + weights.w3_stability * stability
        - weights.w4_assumptions * assumptions
    )
    total = max(0.0, min(1.0, total))  # clamp to [0, 1]

    return ScoreBreakdown(
        evidence=evidence,
        coverage=coverage,
        stability=stability,
        assumptions=assumptions,
        total=total,
    )


def rank_candidates(
    candidates: List[Tuple[CandidatePlan, ExecutionResult]],
    semantic_evidences: dict,
    intent_tokens: Sequence[str],
    weights: Optional[RankerWeights] = None,
    start_rank: int = 1,
) -> Tuple[List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]], bool]:
    """Rank surviving candidates by Ranker V1 score.

    Args:
        candidates: (plan, execution_result) pairs — all must have PASSED Pass 1.
        semantic_evidences: Dict[str, ColumnSemanticEvidence].
        intent_tokens: Lower-cased word tokens from the original request.
        weights: Optional custom weights.
        start_rank: Starting rank number (1-based).

    Returns:
        Tuple of:
            - List of (plan, result, score_breakdown, rank) sorted descending by total score.
            - is_tie: True when top-2 candidates differ by < RANK_TIE_EPSILON.
    """
    if not candidates:
        return [], False

    scored = []
    for plan, result in candidates:
        sb = compute_score(plan, result, semantic_evidences, intent_tokens, weights)
        scored.append((plan, result, sb))

    scored.sort(key=lambda x: x[2].total, reverse=True)

    ranked = [(plan, result, sb, start_rank + i) for i, (plan, result, sb) in enumerate(scored)]

    is_tie = False
    if len(ranked) >= 2:
        top_score = ranked[0][2].total
        second_score = ranked[1][2].total
        if abs(top_score - second_score) < RANK_TIE_EPSILON:
            is_tie = True

    return ranked, is_tie


# ---------------------------------------------------------------------------
# Candidate Output Consistency Check
# ---------------------------------------------------------------------------


def check_candidate_output_consistency(
    candidates: List[Tuple[CandidatePlan, ExecutionResult]],
) -> CandidateConsistencyCheck:
    """Verify that surviving candidates share identical output semantics.

    Checks:
    - Same metric column semantics (same column name).
    - Same time basis (granularity of first DATETIME dimension).
    - Same output column schema (set of result columns).

    Args:
        candidates: Surviving (plan, result) pairs after Pass 1b.

    Returns:
        CandidateConsistencyCheck with passed flag and mismatches.
    """
    if len(candidates) <= 1:
        return CandidateConsistencyCheck(passed=True, mismatches=[])

    mismatches: List[str] = []
    reference_plan, reference_result = candidates[0]

    ref_metric_col = reference_plan.metric.column
    ref_granularity = next(
        (d.granularity for d in reference_plan.dimensions if d.granularity is not None),
        None,
    )
    ref_schema = frozenset(reference_result.columns)

    for i, (plan, result) in enumerate(candidates[1:], start=2):
        # Metric column consistency
        if plan.metric.column != ref_metric_col:
            mismatches.append(
                f"Candidate {i}: metric column '{plan.metric.column}' "
                f"differs from reference '{ref_metric_col}'."
            )

        # Time basis (granularity) consistency
        granularity = next(
            (d.granularity for d in plan.dimensions if d.granularity is not None),
            None,
        )
        if granularity != ref_granularity:
            mismatches.append(
                f"Candidate {i}: granularity '{granularity}' "
                f"differs from reference '{ref_granularity}'."
            )

        # Output schema consistency
        schema = frozenset(result.columns)
        if schema != ref_schema:
            mismatches.append(
                f"Candidate {i}: output columns {sorted(schema)} "
                f"differ from reference {sorted(ref_schema)}."
            )

    return CandidateConsistencyCheck(
        passed=len(mismatches) == 0,
        mismatches=mismatches,
    )
