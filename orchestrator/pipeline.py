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
from orchestrator.config import (
    AI_MAX_RETRIES,
    GENERATOR_MODE,
    MAX_CASCADE_DEPTH,
    MAX_K,
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RANK_W5_AGREEMENT,
)
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
from providers import LLMClient, MockLLMClient, get_llm_client


@dataclass
class OrchestrationPipelineResult:
    """Complete result from an end-to-end orchestration pipeline run."""
    status: str  # "SUCCESS", "REFUSED", "UNANSWERABLE", "AMBIGUOUS"
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


def get_default_llm_client() -> LLMClient:
    """Return configured LLMClient via provider factory or MockLLMClient."""
    try:
        return get_llm_client()
    except Exception:
        return MockLLMClient()


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
    if generator is not None:
        active_generator = generator
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
<<<<<<< HEAD
        cand_record: Dict[str, Any] = {
            "plan_id": cand.plan_id,
            "metric": f"{cand.metric.aggregation.value}({cand.metric.column})",
            "dimensions": [d.column for d in cand.dimensions],
            "visualization": cand.visualization.value,
        }
=======
>>>>>>> main
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
