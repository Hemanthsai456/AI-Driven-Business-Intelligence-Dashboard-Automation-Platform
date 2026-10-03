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
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orchestrator.config import (
    LOW_COVERAGE_CONFIDENCE_CAP,
    MAX_CASCADE_DEPTH,
    RANK_TIE_EPSILON,
)
from orchestrator.schemas import (
    AlternateInterpretation,
    AmbiguityResult,
    CandidatePlan,
    CandidateConsistencyCheck,
    DashboardSpec,
    ExecutionResult,
    GeneratorCallLog,
    OrchestratorTrace,
    Pass1aResult,
    Pass1bResult,
    Pass2Result,
    PassResult,
    RankedCandidate,
    RankerWeights,
    ScoreBreakdown,
    StructuredIntent,
)
from orchestrator.utils import rank_candidates, check_candidate_output_consistency
from orchestrator.validator import validate_pass2
from orchestrator.panels import build_dashboard_panels


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
    structured_intent: Optional[StructuredIntent] = None,
    ambiguity_result: Optional[AmbiguityResult] = None,
    candidate_records: Optional[List[Dict[str, Any]]] = None,
    plans_generated: Optional[int] = None,
    plans_passed_pass1a: Optional[int] = None,
    plans_passed_pass1b: Optional[int] = None,
    candidate_validations: Optional[Dict[str, Tuple[Pass1aResult, Pass1bResult]]] = None,
    resolved_by: Optional[str] = None,
    run_id: Optional[str] = None,
    semantic_profile: Optional[Any] = None,
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
        structured_intent: Structured intent stage result for full trace.
        ambiguity_result: Ambiguity stage result for full trace.
        candidate_records: Detailed candidate records across all stages for trace.
        plans_generated: Total count of plans generated.
        plans_passed_pass1a: Count of plans that passed Pass 1a.
        plans_passed_pass1b: Count of plans that passed Pass 1b.
        candidate_validations: Map of plan_id to real (pass1a, pass1b) results.
        resolved_by: Identifier of resolver ('user' when resolved via user action).
        run_id: Associated pipeline run ID for auditability.

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

    # Determine tie at the top or low-coverage clarification
    is_tie = False
    if resolved_by != "user":
        if len(remaining) >= 2:
            top_score = remaining[0][2].total
            second_score = remaining[1][2].total
            if (
                abs(top_score - second_score) < RANK_TIE_EPSILON
                or remaining[0][2].coverage < LOW_COVERAGE_CONFIDENCE_CAP
            ):
                is_tie = True
        elif len(remaining) == 1 and remaining[0][2].coverage < LOW_COVERAGE_CONFIDENCE_CAP:
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

    # Retrieve real Pass1a and Pass1b results if provided
    real_pass1a = None
    real_pass1b = None
    if candidate_validations and winner_plan.plan_id in candidate_validations:
        real_pass1a, real_pass1b = candidate_validations[winner_plan.plan_id]
    if real_pass1a is None:
        real_pass1a = Pass1aResult(plan_id=winner_plan.plan_id, passed=True, issues=[])
    if real_pass1b is None:
        real_pass1b = Pass1bResult(plan_id=winner_plan.plan_id, passed=True, issues=[])

    winner_ranked_candidate = RankedCandidate(
        plan=winner_plan,
        execution_result=winner_result,
        pass1a=real_pass1a,
        pass1b=real_pass1b,
        score_breakdown=winner_score,
        rank=1,
        is_winner=True,
    )

    # Build AlternateInterpretations from remaining losers
    alternate_interpretations: List[AlternateInterpretation] = []
    for plan, result, score, rank in remaining[1:]:  # skip the winner itself (already removed)
        reason = f"Rank {rank} (score: {score.total:.3f})"
        alternate_interpretations.append(
            AlternateInterpretation(
                plan=plan,
                score=score.total,
                reason_not_winner=reason,
            )
        )
    # Also add those that failed Pass 2 as alternates with explanation
    for p2_fail in failed_pass2:
        for plan, result, score, rank in ranked:
            if plan.plan_id == p2_fail.plan_id:
                fail_reasons = "; ".join(p2_fail.reasons) or "; ".join(
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

    # Build full OrchestratorTrace
    trace = OrchestratorTrace(
        request_id=str(uuid4()),
        dataset_id=dataset_id,
        intent=intent,
        context_hash=context_hash,
        generated_at=datetime.now(timezone.utc).isoformat(),
        structured_intent=structured_intent,
        ambiguity_result=ambiguity_result,
        llm_call_count=sum(1 for log in (generator_logs or []) if log.generator == "llm_direct"),
        llm_token_usage=sum(
            (log.input_tokens + log.output_tokens)
            for log in (generator_logs or [])
        ),
        generator_logs=generator_logs or [],
        plans_generated=plans_generated if plans_generated is not None else len(ranked),
        plans_passed_pass1a=plans_passed_pass1a if plans_passed_pass1a is not None else len(ranked),
        plans_passed_pass1b=plans_passed_pass1b if plans_passed_pass1b is not None else len(ranked),
        cascade_depth=cascade_depth,
        ranker_weights=ranker_weights,
        pass2_result=winning_pass2,
        consistency_check=consistency_check,
        candidate_records=candidate_records or [],
        resolved_by=resolved_by,
        run_id=run_id,
    )

    # Build generic dashboard panels and headline insight
    headline, panels = build_dashboard_panels(
        winner_plan=winner_ranked_candidate.plan,
        winner_result=winner_ranked_candidate.execution_result,
        winner_score=winner_ranked_candidate.score_breakdown,
        alternates=alternate_interpretations,
        semantic_profile=semantic_profile,
    )

    # Build focused tiles
    from orchestrator.schemas import DashboardTile, TileSize, TileEvidence, PanelType
    from orchestrator.discovery.tiles import _format_provenance, build_slicer_definitions

    focused_tiles: List[DashboardTile] = []
    main_chart_panel = next((p for p in panels if p.panel_type in (PanelType.BAR, PanelType.LINE, PanelType.KPI)), None)
    if main_chart_panel:
        c_type = "kpi" if main_chart_panel.panel_type == PanelType.KPI else ("line" if main_chart_panel.panel_type == PanelType.LINE else "bar")
        focused_tiles.append(
            DashboardTile(
                id=f"tile_{main_chart_panel.panel_id[:8]}",
                title=main_chart_panel.title,
                chart_type=c_type,
                size=TileSize(w=8, h=4) if c_type != "kpi" else TileSize(w=3, h=2),
                priority=1,
                generator=_format_provenance("rule_baseline"),
                evidence=TileEvidence(
                    strength=1.0,
                    robustness=winner_ranked_candidate.score_breakdown.stability,
                    score=winner_ranked_candidate.score_breakdown.total,
                    n=winner_ranked_candidate.execution_result.row_count,
                ),
                why_chosen=f"Winner candidate plan: {winner_ranked_candidate.plan.reasoning.interpretation}",
                plan=winner_ranked_candidate.plan,
                compiled_sql=winner_ranked_candidate.execution_result.compiled_sql,
                data=main_chart_panel.data,
                x_key=main_chart_panel.x_key,
                y_keys=main_chart_panel.y_keys,
                dimensions=[d.column for d in winner_ranked_candidate.plan.dimensions],
                metrics=[winner_ranked_candidate.plan.metric.column],
            )
        )

    # Slicers from dataset if available
    slicers = []
    try:
        from api.store import session_store
        rec = session_store.get(dataset_id)
        if rec and rec.dataset:
            slicers = build_slicer_definitions(rec.dataset, semantic_profile)
    except Exception:
        pass

    return DashboardSpec(
        spec_id=str(uuid4()),
        dataset_id=dataset_id,
        intent=intent,
        headline=headline,
        winner=winner_ranked_candidate,
        panels=panels,
        tiles=focused_tiles,
        slicers=slicers,
        alternate_interpretations=alternate_interpretations,
        trace=trace,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_tie=is_tie,
    )
