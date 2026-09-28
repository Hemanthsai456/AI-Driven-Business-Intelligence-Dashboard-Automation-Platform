"""Winner selection and Pass 2 cascade logic.

Architecture references:
- ranker_v1_spec.md §6 (Pass 2 — Winner-Only Validation)
- orchestrator_conformance.md §1 (MAX_CASCADE_DEPTH project decision)

Algorithm:
  1. Take the descending-ranked list from rank_candidates().
  2. Attempt Pass 2 on rank-1 winner.
  3. If Pass 2 fails, promote rank-2 (runner-up) as new winner candidate.
  4. Repeat until Pass 2 passes or MAX_CASCADE_DEPTH exhausted.
  5. If exhaustion: raise WinnerSelectionError (caller converts to UNANSWERABLE).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import uuid4

from orchestrator.config import MAX_CASCADE_DEPTH, RANK_TIE_EPSILON
from orchestrator.schemas import (
    AlternateInterpretation,
    CandidatePlan,
    CandidateConsistencyCheck,
    DashboardSpec,
    ExecutionResult,
    GeneratorCallLog,
    OrchestratorTrace,
    Pass2Result,
    RankedCandidate,
    RankerWeights,
    ScoreBreakdown,
)
from orchestrator.utils import rank_candidates, check_candidate_output_consistency
from orchestrator.validator import validate_pass2


class WinnerSelectionError(Exception):
    """Raised when all candidates fail Pass 2 and cascade depth is exhausted."""

    def __init__(self, message: str, cascade_depth: int, failed_pass2_results: List[Pass2Result]):
        super().__init__(message)
        self.cascade_depth = cascade_depth
        self.failed_pass2_results = failed_pass2_results


def select_winner(
    ranked: List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]],
    *,
    dataset_id: str,
    intent: str,
    context_hash: str,
    generator_logs: Optional[List[GeneratorCallLog]] = None,
    ranker_weights: Optional[RankerWeights] = None,
    consistency_check: Optional[CandidateConsistencyCheck] = None,
    max_cascade_depth: int = MAX_CASCADE_DEPTH,
) -> DashboardSpec:
    """Select the winning candidate, apply Pass 2, and cascade if needed.

    Args:
        ranked: Sorted list of (plan, exec_result, score_breakdown, rank) — rank 1 first.
        dataset_id: Dataset identifier for OrchestratorTrace.
        intent: Original natural-language intent for OrchestratorTrace.
        context_hash: LLM context hash for OrchestratorTrace.
        generator_logs: Call logs from generator phase.
        ranker_weights: Weights used during ranking (for trace).
        consistency_check: Output of check_candidate_output_consistency (for trace).
        max_cascade_depth: Override cascade cap (default from config).

    Returns:
        DashboardSpec with the winning RankedCandidate, alternate interpretations, and trace.

    Raises:
        WinnerSelectionError: If all candidates fail Pass 2 after cascade depth exhaustion.
    """
    if not ranked:
        raise WinnerSelectionError(
            "No surviving candidates to select a winner from.",
            cascade_depth=0,
            failed_pass2_results=[],
        )

    cascade_depth = 0
    failed_pass2: List[Pass2Result] = []
    remaining = list(ranked)  # mutable copy, rank-1 first

    # Determine tie at the top
    is_tie = False
    if len(remaining) >= 2:
        top_score = remaining[0][2].total
        second_score = remaining[1][2].total
        if abs(top_score - second_score) < RANK_TIE_EPSILON:
            is_tie = True

    winning_ranked: Optional[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]] = None
    winning_pass2: Optional[Pass2Result] = None

    while remaining and cascade_depth <= max_cascade_depth:
        candidate_plan, candidate_result, candidate_score, candidate_rank = remaining[0]

        pass2 = validate_pass2(candidate_plan, candidate_result)

        if pass2.passed:
            winning_ranked = (candidate_plan, candidate_result, candidate_score, candidate_rank)
            winning_pass2 = pass2
            break
        else:
            failed_pass2.append(pass2)
            remaining.pop(0)
            cascade_depth += 1

    if winning_ranked is None or winning_pass2 is None:
        raise WinnerSelectionError(
            f"All candidates failed Pass 2 after {cascade_depth} cascade step(s). "
            "Returning UNANSWERABLE.",
            cascade_depth=cascade_depth,
            failed_pass2_results=failed_pass2,
        )

    winner_plan, winner_result, winner_score, winner_rank = winning_ranked

    # Build RankedCandidate for the winner
    # Pass1a/Pass1b results are not re-derived here; they were already validated.
    # We reconstruct minimal shells to satisfy schema — the full records live in
    # the generate-candidates trace. Pass2 is the new gate here.
    from orchestrator.schemas import Pass1aResult, Pass1bResult, ValidationStatus

    winner_ranked_candidate = RankedCandidate(
        plan=winner_plan,
        execution_result=winner_result,
        pass1a=Pass1aResult(plan_id=winner_plan.plan_id, passed=True, issues=[]),
        pass1b=Pass1bResult(plan_id=winner_plan.plan_id, passed=True, issues=[]),
        score_breakdown=winner_score,
        rank=1,
        is_winner=True,
    )

    # Build AlternateInterpretations from remaining losers
    alternate_interpretations: List[AlternateInterpretation] = []
    for plan, result, score, rank in remaining[1:]:  # skip the winner itself (already removed)
        reason = "Lower Ranker V1 score"
        alternate_interpretations.append(
            AlternateInterpretation(
                plan=plan,
                score=score.total,
                reason_not_winner=reason,
            )
        )
    # Also add those that failed Pass 2 as alternates with explanation
    for p2_fail in failed_pass2:
        # find matching plan from original ranked list
        for plan, result, score, rank in ranked:
            if plan.plan_id == p2_fail.plan_id:
                fail_reasons = "; ".join(
                    issue.message for issue in p2_fail.issues
                    if issue.status.value == "FAILED"
                )
                alternate_interpretations.append(
                    AlternateInterpretation(
                        plan=plan,
                        score=score.total,
                        reason_not_winner=f"Pass 2 failed: {fail_reasons}",
                    )
                )
                break

    # Build OrchestratorTrace
    trace = OrchestratorTrace(
        request_id=str(uuid4()),
        dataset_id=dataset_id,
        intent=intent,
        context_hash=context_hash,
        generated_at=datetime.now(timezone.utc).isoformat(),
        llm_call_count=sum(1 for log in (generator_logs or []) if log.generator == "llm_direct"),
        llm_token_usage=sum(
            (log.input_tokens + log.output_tokens)
            for log in (generator_logs or [])
        ),
        generator_logs=generator_logs or [],
        plans_generated=len(ranked),
        plans_passed_pass1a=len(ranked),   # all ranked candidates passed 1a
        plans_passed_pass1b=len(ranked),   # all ranked candidates passed 1b
        cascade_depth=cascade_depth,
        ranker_weights=ranker_weights,
        pass2_result=winning_pass2,
        consistency_check=consistency_check,
    )

    return DashboardSpec(
        spec_id=str(uuid4()),
        dataset_id=dataset_id,
        intent=intent,
        winner=winner_ranked_candidate,
        alternate_interpretations=alternate_interpretations,
        trace=trace,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_tie=is_tie,
    )
