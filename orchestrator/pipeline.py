"""End-to-End Orchestrator Pipeline (Stage 7).

Coordinates:
1. Pre-dispatch Readiness Gate (C3 check): Refuses dispatch if NOT_READY.
2. Ambiguity Detection (rules + lightweight check).
3. Sanitized LLM Context Building (no raw rows, injection sanitized).
4. Candidate Generation (LLM Direct + External Agent).
5. Pass 1a Pre-Dispatch Validation.
6. Safe Query Compilation & DuckDB Execution (with C2 TRY_CAST).
7. Pass 1b Post-Execution Validation.
8. Deterministic Ranker V1 Scoring.
9. Pass 2 Winner-Only Validation with Runner-Up Cascade (capped at MAX_CASCADE_DEPTH).
10. Isolated per-candidate artifact emission.
11. Structured Decision & Explainability JSONL log emission.
12. Emission of final canonical DashboardSpec with alternate interpretations.

Architecture references:
- orchestrator_conformance.md §1, §Binding Resolutions
- ranker_v1_spec.md §1-§8
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from ingestion.models import CanonicalDataset
from intelligence.profiler import DataProfile
from intelligence.schema_validator import AnalysisReadiness, ReadinessStatus
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.ambiguity import AmbiguityResult, assess_ambiguity
from orchestrator.config import (
    AI_MAX_RETRIES,
    DEFAULT_GEMINI_MODEL,
    GEMINI_API_KEY_ENV,
    GEMINI_MODEL_ENV,
    GENERATOR_MODE,
    MAX_CASCADE_DEPTH,
    MAX_K,
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
)
from orchestrator.context_builder import build_llm_context
from orchestrator.executor import execute_plan
from orchestrator.generator import (
    ExternalAgentGenerator,
    LLMDirectGenerator,
    PlanGenerationCoordinator,
    PlanGenerator,
)
from orchestrator.llm import GeminiClient, LLMClient, MockLLMClient
from orchestrator.logger import (
    emit_decision_log,
    emit_explainability_log,
    save_candidate_artifact,
)
from orchestrator.schemas import (
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
)
from orchestrator.utils import check_candidate_output_consistency, rank_candidates
from orchestrator.validator import validate_pass1a, validate_pass1b, validate_pass2
from orchestrator.winner import WinnerSelectionError, select_winner


@dataclass
class OrchestrationPipelineResult:
    """Complete result from an end-to-end orchestration pipeline run."""
    status: str  # "SUCCESS", "REFUSED", "UNANSWERABLE"
    message: str
    dashboard_spec: Optional[DashboardSpec] = None
    ambiguity: Optional[AmbiguityResult] = None
    ranked_candidates: List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]] = None
    is_tie: bool = False
    cascade_depth: int = 0
    decision_log_entry: Optional[Dict[str, Any]] = None
    explainability_log_entry: Optional[Dict[str, Any]] = None


def get_default_llm_client() -> LLMClient:
    """Return configured GeminiClient if API key present, else MockLLMClient."""
    api_key = os.getenv(GEMINI_API_KEY_ENV)
    model = os.getenv(GEMINI_MODEL_ENV, DEFAULT_GEMINI_MODEL)
    if api_key:
        return GeminiClient(api_key=api_key, model_name=model)
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
    max_cascade_depth: int = MAX_CASCADE_DEPTH,
) -> OrchestrationPipelineResult:
    """Execute the full end-to-end analytical pipeline.

    Args:
        dataset: The canonical tabular dataset.
        semantic_profile: Inferred semantic profile (sole role authority).
        readiness: Schema readiness assessment.
        intent: User natural-language analytical question.
        data_profile: Optional data profile metrics.
        mode: Generator mode ("llm_only", "agent_only", "both").
        k: Number of candidate plans to generate (capped at MAX_K).
        generator: Optional generator override (for testing).
        max_cascade_depth: Cascade depth limit.

    Returns:
        OrchestrationPipelineResult with DashboardSpec or refusal reason.
    """
    request_id = str(uuid4())
    k_eff = min(max(1, k), MAX_K)

    # 1. Pre-dispatch Readiness Gate (C3 check)
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

    # 2. Ambiguity Detection
    ambiguity = assess_ambiguity(
        intent=intent,
        semantic_profile=semantic_profile,
    )

    # 3. Compact Sanitized LLM Context
    context = build_llm_context(
        dataset_id=dataset.metadata.dataset_id,
        intent=intent,
        semantic_profile=semantic_profile,
        data_profile=data_profile,
    )

    # 4. Candidate Generation
    if generator is not None:
        active_generator = generator
    else:
        llm_client = get_default_llm_client()
        direct_gen = LLMDirectGenerator(llm_client)
        agent_gen = ExternalAgentGenerator(llm_client=llm_client)
        active_generator = PlanGenerationCoordinator(
            direct_generator=direct_gen,
            agent_generator=agent_gen,
            mode=mode,
        )

    candidates, generator_logs = active_generator.generate_plans(context, k=k_eff)

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
        )

    # 5. Pass 1a Pre-Dispatch Validation + Execution + Pass 1b Post-Execution
    surviving_candidates: List[Tuple[CandidatePlan, ExecutionResult]] = []
    pass1a_counts = 0
    pass1b_counts = 0

    for cand in candidates:
        # Pass 1a
        pass1a_res = validate_pass1a(
            plan=cand,
            semantic_profile=semantic_profile,
            readiness=readiness,
        )
        if not pass1a_res.passed:
            save_candidate_artifact(plan=cand, pass1a=pass1a_res)
            continue
        pass1a_counts += 1

        # Execution
        exec_res = execute_plan(
            plan=cand,
            dataset=dataset,
            semantic_profile=semantic_profile,
        )

        # Pass 1b
        pass1b_res = validate_pass1b(
            plan=cand,
            exec_result=exec_res,
        )
        if not pass1b_res.passed:
            save_candidate_artifact(plan=cand, pass1a=pass1a_res, execution=exec_res, pass1b=pass1b_res)
            continue
        pass1b_counts += 1

        surviving_candidates.append((cand, exec_res))
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
        )

    # 6. Consistency Check
    consistency = check_candidate_output_consistency(surviving_candidates)

    # 7. Deterministic Ranker V1
    weights = RankerWeights(
        w1_evidence=RANK_W1_EVIDENCE,
        w2_coverage=RANK_W2_COVERAGE,
        w3_stability=RANK_W3_STABILITY,
        w4_assumptions=RANK_W4_ASSUMPTIONS,
    )
    intent_tokens = intent.lower().split()
    semantic_evidences = semantic_profile.column_evidences
    ranked, is_tie = rank_candidates(
        candidates=surviving_candidates,
        semantic_evidences=semantic_evidences,
        intent_tokens=intent_tokens,
        weights=weights,
    )

    # Update candidate artifacts with scores
    for plan, result, score, rank in ranked:
        save_candidate_artifact(
            plan=plan,
            execution=result,
            score=score,
        )

    # 8. Winner Selection with Pass 2 Cascade
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
            ranked_candidates=ranked,
            cascade_depth=e.cascade_depth,
        )

    # 9. Structured Logging
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
        ranked_candidates=ranked,
        is_tie=dashboard_spec.is_tie,
        cascade_depth=dashboard_spec.trace.cascade_depth,
        decision_log_entry=decision_entry,
        explainability_log_entry=explain_entry,
    )
