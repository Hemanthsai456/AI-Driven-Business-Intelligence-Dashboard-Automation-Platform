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
from typing import Any, List, Optional, Sequence, Tuple

from orchestrator.config import (
    LOW_COVERAGE_CONFIDENCE_CAP,
    MIN_CONSENSUS_RESPONDENTS,
    RANK_TIE_EPSILON,
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RANK_W5_AGREEMENT,
    RESULT_ROW_CAP,
    TOTAL_ACTIVE_PROVIDERS,
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
        ]
        + [d.column.lower() for d in plan.dimensions]
        + [f.column.lower() for f in plan.filters]
    )

    matched = sum(1 for token in intent_tokens if token in plan_text)
    return min(1.0, matched / len(intent_tokens))


from orchestrator.robustness import (
    RobustnessEvaluation,
    compute_spearman_rank_correlation,
    evaluate_robustness,
    generate_perturbations,
)


def _compute_stability(
    execution_result: ExecutionResult,
    robustness_result: Optional[RobustnessEvaluation] = None,
) -> Optional[float]:
    """Robustness across interpretations (replaces V1 stability proxy).

    If robustness_result is provided, returns its robustness score.
    If execution_result failed, returns 0.0.
    Otherwise returns None (UNTESTED).
    """
    if execution_result.status != ExecutionStatus.SUCCESS:
        return 0.0
    if robustness_result is not None:
        return robustness_result.robustness
    return None


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
    coverage_override: Optional[float] = None,
    robustness_result: Optional[RobustnessEvaluation] = None,
    dataset: Optional[Any] = None,
    semantic_profile: Optional[Any] = None,
    ambiguity_result: Optional[Any] = None,
    stability_override: Optional[float] = None,
) -> ScoreBreakdown:
    """Compute Ranker V1 score for a candidate plan with robustness across interpretations.

    Args:
        plan: The candidate plan.
        execution_result: DuckDB worker output.
        semantic_evidences: Dict[str, ColumnSemanticEvidence].
        intent_tokens: Lower-cased word tokens from the request.
        weights: Ranker weights (defaults to config values if None).
        coverage_override: Optional coverage override.
        robustness_result: Pre-computed RobustnessEvaluation if available.
        dataset: CanonicalDataset for runtime variant execution.
        semantic_profile: DatasetSemanticProfile for role-based perturbations.
        ambiguity_result: AmbiguityResult for ambiguity-based perturbations.
        stability_override: Direct override for robustness/stability (for testing).

    Returns:
        ScoreBreakdown with individual components and weighted total.
    """
    if weights is None:
        weights = RankerWeights(
            w1_evidence=RANK_W1_EVIDENCE,
            w2_coverage=RANK_W2_COVERAGE,
            w3_stability=RANK_W3_STABILITY,
            w4_assumptions=RANK_W4_ASSUMPTIONS,
            w5_agreement=0.10, # default if not configured
        )

    evidence = _compute_evidence(plan, semantic_evidences)
    coverage = coverage_override if coverage_override is not None else _compute_coverage(plan, intent_tokens)

    # 1. Robustness across interpretations
    rob_eval: Optional[RobustnessEvaluation] = robustness_result
    if rob_eval is None and dataset is not None and semantic_profile is not None:
        rob_eval = evaluate_robustness(
            plan=plan,
            candidate_result=execution_result,
            dataset=dataset,
            semantic_profile=semantic_profile,
            ambiguity_result=ambiguity_result,
        )

    if stability_override is not None:
        stability = stability_override
        stability_status = "TESTED"
    elif execution_result.status != ExecutionStatus.SUCCESS:
        stability = 0.0
        stability_status = "FAILED"
    elif rob_eval is not None:
        stability = rob_eval.robustness
        stability_status = rob_eval.status
    else:
        # If fewer than 2 valid variants exist, robustness = None with status="UNTESTED"
        # It must never default to 1.0, because untested is not robust.
        stability = None
        stability_status = "UNTESTED"

    # In total score calculation, untested/None stability contributes 0.0
    stability_term = stability if stability is not None else 0.0

    assumptions = _compute_assumptions(plan)

    # Agreement calculation incorporating provider response completeness:
    total_expected = getattr(weights, "total_active_providers", TOTAL_ACTIVE_PROVIDERS)
    if total_expected <= 0:
        total_expected = 3

    if plan.providers_responded > 0:
        raw_consensus = plan.supporting_count / plan.providers_responded
        participation_factor = min(1.0, plan.providers_responded / total_expected)
        agreement = raw_consensus * participation_factor
    else:
        agreement = 0.0

    w5 = getattr(weights, "w5_agreement", RANK_W5_AGREEMENT)
    agreement_contribution = w5 * agreement * coverage

    # Keep failed_cast_rate as a separate quality penalty
    cast_penalty = execution_result.failed_cast_rate

    total = (
        weights.w1_evidence * evidence
        + weights.w2_coverage * coverage
        + weights.w3_stability * stability_term
        + agreement_contribution
        - weights.w4_assumptions * assumptions
        - cast_penalty
    )
    total = max(0.0, min(1.0, total))  # clamp to [0, 1]

    # Gate agreement by coverage: if coverage falls below LOW_COVERAGE_CONFIDENCE_CAP,
    # cap candidate's final score to force ties/clarification rather than an automatic win
    if coverage < LOW_COVERAGE_CONFIDENCE_CAP:
        total = min(total, LOW_COVERAGE_CONFIDENCE_CAP)

    return ScoreBreakdown(
        evidence=evidence,
        coverage=coverage,
        stability=stability,
        assumptions=assumptions,
        agreement=agreement,
        failed_cast_penalty=cast_penalty,
        total=total,
        stability_status=stability_status,
        variants_attempted=rob_eval.variants_attempted if rob_eval else 0,
        variants_valid=rob_eval.variants_valid if rob_eval else 0,
        variants_failed=rob_eval.variants_failed if rob_eval else [],
        variant_details=rob_eval.variant_details if rob_eval else [],
        coverage_of_test=rob_eval.coverage_of_test if rob_eval else 0.0,
    )


def rank_candidates(
    candidates: List[Tuple[CandidatePlan, ExecutionResult]],
    semantic_evidences: dict,
    intent_tokens: Sequence[str],
    weights: Optional[RankerWeights] = None,
    start_rank: int = 1,
    dataset: Optional[Any] = None,
    semantic_profile: Optional[Any] = None,
    ambiguity_result: Optional[Any] = None,
) -> Tuple[List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]], bool]:
    """Rank surviving candidates by Ranker V1 score.

    Args:
        candidates: (plan, execution_result) pairs — all must have PASSED Pass 1.
        semantic_evidences: Dict[str, ColumnSemanticEvidence].
        intent_tokens: Lower-cased word tokens from the original request.
        weights: Optional custom weights.
        start_rank: Starting rank number (1-based).
        dataset: CanonicalDataset for runtime variant execution.
        semantic_profile: DatasetSemanticProfile for role-based perturbations.
        ambiguity_result: AmbiguityResult for ambiguity-based perturbations.

    Returns:
        Tuple of:
            - List of (plan, result, score_breakdown, rank) sorted descending by total score.
            - is_tie: True when top-2 candidates differ by < RANK_TIE_EPSILON or top candidate has low coverage.
    """
    if not candidates:
        return [], False

    scored = []
    for plan, result in candidates:
        sb = compute_score(
            plan=plan,
            execution_result=result,
            semantic_evidences=semantic_evidences,
            intent_tokens=intent_tokens,
            weights=weights,
            dataset=dataset,
            semantic_profile=semantic_profile,
            ambiguity_result=ambiguity_result,
        )
        scored.append((plan, result, sb))

    scored.sort(key=lambda x: x[2].total, reverse=True)

    ranked = [(plan, result, sb, start_rank + i) for i, (plan, result, sb) in enumerate(scored)]

    is_tie = False
    if len(ranked) >= 2:
        top_score = ranked[0][2].total
        second_score = ranked[1][2].total
        if (
            abs(top_score - second_score) < RANK_TIE_EPSILON
            or ranked[0][2].coverage < LOW_COVERAGE_CONFIDENCE_CAP
        ):
            is_tie = True
    elif len(ranked) == 1 and ranked[0][2].coverage < LOW_COVERAGE_CONFIDENCE_CAP:
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
