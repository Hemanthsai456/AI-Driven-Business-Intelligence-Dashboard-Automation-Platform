"""End-to-End Orchestrator Pipeline (Stage 7).

Coordinates the 6-step cognitive loop:
1. Intent Interpretation: User Request -> StructuredIntent
2. Ambiguity Detection & Active Gating: StructuredIntent -> Ambiguity Gate (blocking vs item-level)
3. Discrete Interpretation Generation: StructuredIntent -> SemanticInterpretation[]
4. Planning x K: SemanticInterpretation[] -> CandidatePlan[] (MultiProvider/Agent)
5. Validation / Execution Coordination: Pass 1a -> Deterministic Engine Execution -> Pass 1b
6. Ranking & Winner Selection: Deterministic Ranker V1 -> Pass 2 Cascade -> DashboardSpec

Architecture references:
- orchestrator_conformance.md §1, §Binding Resolutions
- ranker_v1_spec.md §1-§8
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from engine.executor import AnalyticsEngine, get_default_engine
from ingestion.models import CanonicalDataset
from intelligence.profiler import DataProfile
from intelligence.schema_validator import AnalysisReadiness, ReadinessStatus
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.ambiguity import AmbiguityResult, assess_ambiguity, is_blocking_ambiguity
import time
from orchestrator.config import (
    AI_MAX_RETRIES,
    GENERATOR_MODE,
    LOW_COVERAGE_CONFIDENCE_CAP,
    MAX_CASCADE_DEPTH,
    MAX_K,
    RANK_TIE_EPSILON,
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RANK_W5_AGREEMENT,
    ROBUSTNESS_TIE_FLOOR,
)
from orchestrator.run_store import StoredRun, default_run_store
from orchestrator.context_builder import build_llm_context
from orchestrator.generator import (
    ExternalAgentGenerator,
    MultiProviderGenerator,
    PlanGenerationCoordinator,
    PlanGenerator,
)
from orchestrator.intent import interpret_user_request
from orchestrator.interpretation import generate_interpretations
from orchestrator.logger import (
    emit_decision_log,
    emit_explainability_log,
    save_candidate_artifact,
)
from orchestrator.schemas import (
    AmbiguityStatus,
    CandidatePlan,
    DashboardSpec,
    ExecutionResult,
    GeneratorCallLog,
    LLMContext,
    Pass1aResult,
    Pass1bResult,
    Pass2Result,
    RankerWeights,
    ScoreBreakdown,
    SemanticInterpretation,
    StructuredIntent,
)
from orchestrator.utils import check_candidate_output_consistency, rank_candidates
from orchestrator.validator import validate_pass1a, validate_pass1b, validate_pass2
from orchestrator.winner import WinnerSelectionError, select_winner
from providers import LLMClient, MockLLMClient, ProviderInitializationError, get_llm_client


@dataclass
class OrchestrationPipelineResult:
    """Complete result from an end-to-end orchestration pipeline run."""
    status: str  # "SUCCESS", "REFUSED", "UNANSWERABLE", "AMBIGUOUS", "NEEDS_CLARIFICATION"
    message: str
    dashboard_spec: Optional[DashboardSpec] = None
    ambiguity: Optional[AmbiguityResult] = None
    structured_intent: Optional[StructuredIntent] = None
    interpretations: Optional[List[SemanticInterpretation]] = None
    ranked_candidates: List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]] = None
    is_tie: bool = False
    cascade_depth: int = 0
    decision_log_entry: Optional[Dict[str, Any]] = None
    explainability_log_entry: Optional[Dict[str, Any]] = None
    clarification_options: Optional[List[Dict[str, Any]]] = None
    cached_candidates: Optional[List[CandidatePlan]] = None
    options: Optional[List[Dict[str, Any]]] = None
    run_id: Optional[str] = None


def get_default_llm_client() -> LLMClient:
    """Return configured LLMClient via provider factory or raise ProviderInitializationError outside tests."""
    provider = os.getenv("PROVIDER", "gemini")
    is_testing = bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"))
    try:
        return get_llm_client(provider=provider)
    except Exception as e:
        if is_testing:
            return MockLLMClient()
        if isinstance(e, ProviderInitializationError):
            raise
        raise ProviderInitializationError(provider, str(e)) from e


def run_orchestration_pipeline(
    *,
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    readiness: AnalysisReadiness,
    intent: str,
    data_profile: Optional[DataProfile] = None,
    mode: str = "both",
    k: int = 3,
    generator: Optional[PlanGenerator] = None,
    engine: Optional[AnalyticsEngine] = None,
    max_cascade_depth: int = MAX_CASCADE_DEPTH,
    require_clarification: bool = False,
    chosen_plan_id: Optional[str] = None,
    existing_candidates: Optional[List[CandidatePlan]] = None,
    robustness_tie_floor: float = ROBUSTNESS_TIE_FLOOR,
    rank_tie_epsilon: float = RANK_TIE_EPSILON,
) -> OrchestrationPipelineResult:
    """Execute the full 6-step cognitive analytical orchestration pipeline.

    Args:
        dataset: The canonical tabular dataset.
        semantic_profile: Inferred semantic profile (sole role authority).
        readiness: Schema readiness assessment.
        intent: User natural-language analytical question.
        data_profile: Optional data profile metrics.
        mode: Generator mode ("llm_only", "agent_only", "both").
        k: Number of candidate plans to generate (capped at MAX_K).
        generator: Optional generator override (for testing).
        engine: Optional deterministic AnalyticsEngine override.
        max_cascade_depth: Cascade depth limit.
        require_clarification: Return NEEDS_CLARIFICATION on tie or low coverage.
        chosen_plan_id: Chosen plan id when resolving clarification.
        existing_candidates: Pre-generated candidates to re-run from for clarification.

    Returns:
        OrchestrationPipelineResult with DashboardSpec or refusal reason.
    """
    request_id = str(uuid4())
    k_eff = min(max(1, k), MAX_K)
    exec_engine = engine or get_default_engine()

    # Pre-dispatch Readiness Gate (C3 check)
    if readiness.status == ReadinessStatus.NOT_READY:
        reasons = [
            chk.message
            for chk in readiness.checks
            if (not chk.passed and chk.is_blocking)
        ]
        refusal_msg = (
            f"Dispatch refused: Dataset '{dataset.metadata.dataset_id}' readiness status is NOT_READY. "
            f"Blocking check failures: {'; '.join(reasons)}"
        )
        emit_decision_log(
            request_id=request_id,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent,
            context_hash="N/A",
            mode=mode,
            plans_generated=0,
            plans_valid_pass1a=0,
            plans_valid_pass1b=0,
            winner_plan_id=None,
            is_tie=False,
            cascade_depth=0,
            status="REFUSED",
            generator_logs=[],
        )
        return OrchestrationPipelineResult(
            status="REFUSED",
            message=refusal_msg,
        )

    # Stage E: Insight Discovery Mode Trigger Check
    # If the brief is empty or generic, run DISCOVERY mode.
    # A specific brief keeps the existing focused mode.
    # A brief that names a topic only biases scoring in discovery mode.
    # Never ask for clarification in discovery mode; default to rendering.
    from orchestrator.discovery import classify_intent_mode, run_discovery_pipeline

    intent_mode, topic = classify_intent_mode(intent, semantic_profile)
    if intent_mode == "discovery" and not chosen_plan_id and not existing_candidates:
        discovery_spec, discovery_rejected, discovery_summary = run_discovery_pipeline(
            dataset=dataset,
            semantic_profile=semantic_profile,
            readiness=readiness,
            intent=intent,
            data_profile=data_profile,
            engine=exec_engine,
            topic=topic,
        )

        ranked_tuples = [
            (
                discovery_spec.winner.plan,
                discovery_spec.winner.execution_result,
                discovery_spec.winner.score_breakdown,
                1,
            )
        ]

        emit_decision_log(
            request_id=request_id,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent or "Discovery Mode",
            context_hash="discovery",
            mode=mode,
            plans_generated=discovery_summary.candidates_generated,
            plans_valid_pass1a=discovery_summary.candidates_executed,
            plans_valid_pass1b=discovery_summary.candidates_executed,
            winner_plan_id=discovery_spec.winner.plan.plan_id,
            is_tie=False,
            cascade_depth=0,
            status="SUCCESS",
            generator_logs=[],
        )

        emit_explainability_log(
            spec=discovery_spec,
            ranked_candidates=ranked_tuples,
        )

        return OrchestrationPipelineResult(
            status="SUCCESS",
            message="Discovery mode completed successfully.",
            dashboard_spec=discovery_spec,
            ranked_candidates=ranked_tuples,
            is_tie=False,
            cascade_depth=0,
        )

    # 1. Step 1: Intent Interpretation
    structured_intent = interpret_user_request(
        request_text=intent,
        semantic_profile=semantic_profile,
    )

    # 2. Step 2: Ambiguity Detection & Active Gate
    ambiguity = assess_ambiguity(
        intent=structured_intent,
        semantic_profile=semantic_profile,
    )

    if is_blocking_ambiguity(ambiguity, structured_intent):
        refusal_msg = f"Clarification required: {ambiguity.message}"
        emit_decision_log(
            request_id=request_id,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent,
            context_hash="N/A",
            mode=mode,
            plans_generated=0,
            plans_valid_pass1a=0,
            plans_valid_pass1b=0,
            winner_plan_id=None,
            is_tie=False,
            cascade_depth=0,
            status="UNANSWERABLE" if ambiguity.status == AmbiguityStatus.UNANSWERABLE else "AMBIGUOUS",
            generator_logs=[],
        )
        return OrchestrationPipelineResult(
            status="UNANSWERABLE" if ambiguity.status == AmbiguityStatus.UNANSWERABLE else "AMBIGUOUS",
            message=refusal_msg,
            ambiguity=ambiguity,
            structured_intent=structured_intent,
        )

    # 3. Compact Sanitized LLM Context
    context = build_llm_context(
        dataset_id=dataset.metadata.dataset_id,
        intent=intent,
        semantic_profile=semantic_profile,
        data_profile=data_profile,
    )

    # 4. Step 3: Discrete Interpretation Generation
    interpretations = generate_interpretations(
        structured_intent=structured_intent,
        semantic_profile=semantic_profile,
        ambiguity=ambiguity,
        k=k_eff,
    )

    # 5. Step 4: Planning x K (consuming interpretations)
    if existing_candidates:
        candidates = existing_candidates
        generator_logs = []
    elif generator is not None:
        active_generator = generator
        candidates, generator_logs = active_generator.generate_plans(
            context,
            k=k_eff,
            interpretations=interpretations,
        )
    else:
        llm_client = get_default_llm_client()
        direct_gen = MultiProviderGenerator()
        agent_gen = ExternalAgentGenerator(llm_client=llm_client)
        active_generator = PlanGenerationCoordinator(
            direct_generator=direct_gen,
            agent_generator=agent_gen,
            mode=mode,
        )
        candidates, generator_logs = active_generator.generate_plans(
            context,
            k=k_eff,
            interpretations=interpretations,
        )

    if not candidates:
        emit_decision_log(
            request_id=request_id,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent,
            context_hash=context.context_hash,
            mode=mode,
            plans_generated=0,
            plans_valid_pass1a=0,
            plans_valid_pass1b=0,
            winner_plan_id=None,
            is_tie=False,
            cascade_depth=0,
            status="UNANSWERABLE",
            generator_logs=generator_logs,
        )
        return OrchestrationPipelineResult(
            status="UNANSWERABLE",
            message="No candidate plans could be generated for the given analytical intent.",
            ambiguity=ambiguity,
            structured_intent=structured_intent,
            interpretations=interpretations,
        )

    # 6. Step 5: Validation / Execution Coordination
    surviving_candidates: List[Tuple[CandidatePlan, ExecutionResult]] = []
    candidate_validations: Dict[str, Tuple[Pass1aResult, Pass1bResult]] = {}
    candidate_records: List[Dict[str, Any]] = []
    pass1a_counts = 0
    pass1b_counts = 0

    for cand in candidates:
        cand_record: Dict[str, Any] = {
            "plan_id": cand.plan_id,
            "metric": f"{cand.metric.aggregation.value}({cand.metric.column})",
            "dimensions": [d.column for d in cand.dimensions],
            "visualization": cand.visualization.value,
        }
        # Pass 1a: Pre-dispatch validation
        pass1a_res = validate_pass1a(
            plan=cand,
            semantic_profile=semantic_profile,
            readiness=readiness,
        )
        cand_record["pass1a"] = {
            "passed": pass1a_res.passed,
            "issues": [issue.message for issue in pass1a_res.issues],
        }
        if not pass1a_res.passed:
            save_candidate_artifact(plan=cand, pass1a=pass1a_res)
            candidate_records.append(cand_record)
            continue
        pass1a_counts += 1

        # Deterministic engine execution
        exec_res = exec_engine.execute(
            plan=cand,
            dataset=dataset,
            semantic_profile=semantic_profile,
        )

        # Pass 1b: Post-execution validation
        pass1b_res = validate_pass1b(
            plan=cand,
            exec_result=exec_res,
        )
        cand_record["pass1b"] = {
            "passed": pass1b_res.passed,
            "row_count": exec_res.row_count,
            "failed_cast_rate": exec_res.failed_cast_rate,
            "issues": [issue.message for issue in pass1b_res.issues],
        }
        if not pass1b_res.passed:
            save_candidate_artifact(plan=cand, pass1a=pass1a_res, execution=exec_res, pass1b=pass1b_res)
            candidate_records.append(cand_record)
            continue
        pass1b_counts += 1

        surviving_candidates.append((cand, exec_res))
        candidate_validations[cand.plan_id] = (pass1a_res, pass1b_res)
        candidate_records.append(cand_record)
        save_candidate_artifact(plan=cand, pass1a=pass1a_res, execution=exec_res, pass1b=pass1b_res)

    if not surviving_candidates:
        emit_decision_log(
            request_id=request_id,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent,
            context_hash=context.context_hash,
            mode=mode,
            plans_generated=len(candidates),
            plans_valid_pass1a=pass1a_counts,
            plans_valid_pass1b=0,
            winner_plan_id=None,
            is_tie=False,
            cascade_depth=0,
            status="UNANSWERABLE",
            generator_logs=generator_logs,
        )
        return OrchestrationPipelineResult(
            status="UNANSWERABLE",
            message="All generated candidate plans failed validation (Pass 1a or Pass 1b).",
            ambiguity=ambiguity,
            structured_intent=structured_intent,
            interpretations=interpretations,
        )

    # 7. Step 6: Consistency Check, Ranking, and Winner Selection
    consistency = check_candidate_output_consistency(surviving_candidates)

    weights = RankerWeights(
        w1_evidence=RANK_W1_EVIDENCE,
        w2_coverage=RANK_W2_COVERAGE,
        w3_stability=RANK_W3_STABILITY,
        w4_assumptions=RANK_W4_ASSUMPTIONS,
        w5_agreement=RANK_W5_AGREEMENT,
    )
    intent_tokens = intent.lower().split()
    semantic_evidences = semantic_profile.column_evidences
    ranked, is_tie = rank_candidates(
        candidates=surviving_candidates,
        semantic_evidences=semantic_evidences,
        intent_tokens=intent_tokens,
        weights=weights,
        dataset=dataset,
        semantic_profile=semantic_profile,
        ambiguity_result=ambiguity,
    )

    # Helper for formatting candidate options in clarification responses
    def _format_clarification_option(p: CandidatePlan, r: ExecutionResult, s: ScoreBreakdown) -> Dict[str, Any]:
        dims = [d.column for d in p.dimensions]
        dim_str = dims[0] if len(dims) == 1 else (", ".join(dims) if dims else "None")
        interpretation = (
            p.reasoning.interpretation
            if p.reasoning and p.reasoning.interpretation
            else f"{p.metric.aggregation.value} of {p.metric.column}{' by ' + ', '.join(dims) if dims else ''}"
        )
        return {
            "plan_id": p.plan_id,
            "interpretation": interpretation,
            "metric": p.metric.column,
            "dimension": dim_str,
            "dimensions": dims,
            "aggregation": p.metric.aggregation.value,
            "score": round(s.total, 4),
            "robustness": round(s.stability, 4) if s.stability is not None else None,
            "label": f"{p.metric.aggregation.value} of {p.metric.column}{' by ' + ', '.join(dims) if dims else ''}",
            "description": interpretation,
            "coverage": round(s.coverage, 4),
            "evidence": round(s.evidence, 4),
            "visualization": p.visualization.value,
        }

    # If chosen_plan_id was provided in a follow-up call, prioritize it as rank-1 winner
    is_user_resolved = False
    if chosen_plan_id:
        chosen_match = next((t for t in ranked if t[0].plan_id == chosen_plan_id), None)
        if chosen_match:
            others = [t for t in ranked if t[0].plan_id != chosen_plan_id]
            re_ranked = [(chosen_match[0], chosen_match[1], chosen_match[2], 1)]
            for idx, item in enumerate(others, start=2):
                re_ranked.append((item[0], item[1], item[2], idx))
            ranked = re_ranked
            is_tie = False
            is_user_resolved = True

    # Tie check:
    # A tie is any of:
    # 1. top-two score gap < RANK_TIE_EPSILON
    # 2. winner robustness below configurable floor (ROBUSTNESS_TIE_FLOOR)
    # 3. coverage below LOW_COVERAGE_CONFIDENCE_CAP
    if not is_user_resolved and len(ranked) >= 2:
        top_score = ranked[0][2].total
        second_score = ranked[1][2].total
        score_gap_tie = abs(top_score - second_score) < rank_tie_epsilon
        winner_robustness = ranked[0][2].stability
        robustness_tie = (
            winner_robustness is not None
            and winner_robustness < robustness_tie_floor
        )
        winner_coverage = ranked[0][2].coverage
        coverage_tie = (
            winner_coverage < LOW_COVERAGE_CONFIDENCE_CAP
        )

        is_tie = score_gap_tie or robustness_tie or coverage_tie

        if is_tie and require_clarification:
            # Determine tied candidates to present as clarification options
            if score_gap_tie:
                tied_tuples = [t for t in ranked if abs(top_score - t[2].total) < rank_tie_epsilon]
            else:
                tied_tuples = list(ranked)

            if len(tied_tuples) < 2 and len(ranked) >= 2:
                tied_tuples = list(ranked)

            options = [
                _format_clarification_option(plan, res, score)
                for plan, res, score, _ in tied_tuples
            ]

            # Save candidate artifacts and records before returning
            for plan, result, score, rank in ranked:
                save_candidate_artifact(
                    plan=plan,
                    execution=result,
                    score=score,
                )
                for rec in candidate_records:
                    if rec["plan_id"] == plan.plan_id:
                        rec["rank"] = rank
                        rec["score_breakdown"] = score.model_dump()
                        rec["robustness"] = {
                            "variants_attempted": score.variants_attempted,
                            "variants_valid": score.variants_valid,
                            "variants_failed": score.variants_failed,
                            "variant_details": score.variant_details,
                            "coverage_of_test": score.coverage_of_test,
                            "robustness": score.stability,
                            "status": score.stability_status,
                        }
                        break

            run_id = str(uuid4())
            stored_run = StoredRun(
                run_id=run_id,
                created_at=time.time(),
                dataset=dataset,
                semantic_profile=semantic_profile,
                readiness=readiness,
                intent=intent,
                context_hash=context.context_hash,
                ranked_candidates=ranked,
                candidate_records=candidate_records,
                generator_logs=generator_logs,
                weights=weights,
                consistency=consistency,
                structured_intent=structured_intent,
                ambiguity=ambiguity,
                interpretations=interpretations,
                plans_generated=len(candidates),
                pass1a_counts=pass1a_counts,
                pass1b_counts=pass1b_counts,
                candidate_validations=candidate_validations,
                max_cascade_depth=max_cascade_depth,
                options=options,
                status="NEEDS_CLARIFICATION",
            )
            default_run_store.save_run(stored_run)

            return OrchestrationPipelineResult(
                status="NEEDS_CLARIFICATION",
                message="Multiple candidate interpretations tied or confidence is low; user clarification required.",
                dashboard_spec=None,
                options=options,
                clarification_options=options,
                cached_candidates=[p for p, _, _, _ in ranked],
                ranked_candidates=ranked,
                is_tie=True,
                ambiguity=ambiguity,
                structured_intent=structured_intent,
                interpretations=interpretations,
                run_id=run_id,
            )

    # Update candidate artifacts and records with scores
    for plan, result, score, rank in ranked:
        save_candidate_artifact(
            plan=plan,
            execution=result,
            score=score,
        )
        for rec in candidate_records:
            if rec["plan_id"] == plan.plan_id:
                rec["rank"] = rank
                rec["score_breakdown"] = score.model_dump()
                rec["robustness"] = {
                    "variants_attempted": score.variants_attempted,
                    "variants_valid": score.variants_valid,
                    "variants_failed": score.variants_failed,
                    "variant_details": score.variant_details,
                    "coverage_of_test": score.coverage_of_test,
                    "robustness": score.stability,
                    "status": score.stability_status,
                }
                break

    # Winner Selection with Pass 2 Cascade
    try:
        dashboard_spec = select_winner(
            ranked=ranked,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent,
            context_hash=context.context_hash,
            generator_logs=generator_logs,
            ranker_weights=weights,
            consistency_check=consistency,
            max_cascade_depth=max_cascade_depth,
            structured_intent=structured_intent,
            ambiguity_result=ambiguity,
            candidate_records=candidate_records,
            plans_generated=len(candidates),
            plans_passed_pass1a=pass1a_counts,
            plans_passed_pass1b=pass1b_counts,
            candidate_validations=candidate_validations,
            resolved_by="user" if is_user_resolved else None,
            semantic_profile=semantic_profile,
            dataset=dataset,
        )
    except WinnerSelectionError as e:
        emit_decision_log(
            request_id=request_id,
            dataset_id=dataset.metadata.dataset_id,
            intent=intent,
            context_hash=context.context_hash,
            mode=mode,
            plans_generated=len(candidates),
            plans_valid_pass1a=pass1a_counts,
            plans_valid_pass1b=pass1b_counts,
            winner_plan_id=None,
            is_tie=False,
            cascade_depth=e.cascade_depth,
            status="UNANSWERABLE",
            generator_logs=generator_logs,
        )
        return OrchestrationPipelineResult(
            status="UNANSWERABLE",
            message=(
                f"All candidates failed Pass 2 validation after {e.cascade_depth} cascade step(s). "
                "No viable winner could be selected."
            ),
            ambiguity=ambiguity,
            structured_intent=structured_intent,
            interpretations=interpretations,
            ranked_candidates=ranked,
            cascade_depth=e.cascade_depth,
        )

    # Structured Logging
    decision_entry = emit_decision_log(
        request_id=request_id,
        dataset_id=dataset.metadata.dataset_id,
        intent=intent,
        context_hash=context.context_hash,
        mode=mode,
        plans_generated=len(candidates),
        plans_valid_pass1a=pass1a_counts,
        plans_valid_pass1b=pass1b_counts,
        winner_plan_id=dashboard_spec.winner.plan.plan_id,
        is_tie=dashboard_spec.is_tie,
        cascade_depth=dashboard_spec.trace.cascade_depth,
        status="SUCCESS",
        generator_logs=generator_logs,
    )

    explain_entry = emit_explainability_log(
        spec=dashboard_spec,
        ranked_candidates=ranked,
    )

    return OrchestrationPipelineResult(
        status="SUCCESS",
        message="Orchestration pipeline completed successfully.",
        dashboard_spec=dashboard_spec,
        ambiguity=ambiguity,
        structured_intent=structured_intent,
        interpretations=interpretations,
        ranked_candidates=ranked,
        is_tie=dashboard_spec.is_tie,
        cascade_depth=dashboard_spec.trace.cascade_depth,
        decision_log_entry=decision_entry,
        explainability_log_entry=explain_entry,
    )
