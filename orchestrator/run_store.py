"""Run storage and resolution engine for interactive tie clarification.

Stores candidate evaluation state keyed by run_id, enabling users to resolve
ambiguities and ties without regenerating candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from ingestion.models import CanonicalDataset
from intelligence.schema_validator import AnalysisReadiness
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.config import MAX_CASCADE_DEPTH
from orchestrator.logger import emit_decision_log, emit_explainability_log
from orchestrator.schemas import (
    AmbiguityResult,
    CandidateConsistencyCheck,
    CandidatePlan,
    DashboardSpec,
    ExecutionResult,
    Pass1aResult,
    Pass1bResult,
    RankerWeights,
    ScoreBreakdown,
    SemanticInterpretation,
    StructuredIntent,
)
from orchestrator.winner import select_winner
from providers.types import GeneratorCallLog


# ---------------------------------------------------------------------------
# Typed Resolution Errors
# ---------------------------------------------------------------------------


class RunResolveError(Exception):
    """Base error for run resolution failures."""

    error_type: str
    status_code: int
    message: str

    def __init__(self, message: str, error_type: str = "RESOLVE_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code


class RunNotFoundError(RunResolveError):
    """Raised when run_id does not exist in the store."""

    def __init__(self, run_id: str):
        super().__init__(
            message=f"Run '{run_id}' not found.",
            error_type="RUN_NOT_FOUND",
            status_code=404,
        )


class RunExpiredError(RunResolveError):
    """Raised when run_id has expired based on TTL."""

    def __init__(self, run_id: str):
        super().__init__(
            message=f"Run '{run_id}' has expired.",
            error_type="RUN_EXPIRED",
            status_code=410,
        )


class PlanNotFoundError(RunResolveError):
    """Raised when selected_plan_id does not match any candidate in the stored run."""

    def __init__(self, plan_id: str, run_id: str):
        super().__init__(
            message=f"Candidate plan '{plan_id}' not found in run '{run_id}'.",
            error_type="PLAN_NOT_FOUND",
            status_code=422,
        )


# ---------------------------------------------------------------------------
# StoredRun
# ---------------------------------------------------------------------------


@dataclass
class StoredRun:
    """Snapshot of a pipeline run awaiting clarification resolution."""

    run_id: str
    created_at: float
    dataset: CanonicalDataset
    semantic_profile: DatasetSemanticProfile
    readiness: AnalysisReadiness
    intent: str
    context_hash: str
    ranked_candidates: List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]]
    candidate_records: List[Dict[str, Any]]
    generator_logs: List[GeneratorCallLog]
    weights: RankerWeights
    consistency: Optional[CandidateConsistencyCheck]
    structured_intent: Optional[StructuredIntent]
    ambiguity: Optional[AmbiguityResult]
    interpretations: Optional[List[SemanticInterpretation]]
    plans_generated: int
    pass1a_counts: int
    pass1b_counts: int
    candidate_validations: Dict[str, Tuple[Pass1aResult, Pass1bResult]]
    max_cascade_depth: int
    options: List[Dict[str, Any]]
    status: str = "NEEDS_CLARIFICATION"
    ttl_seconds: float = 3600.0  # 1 hour

    def is_expired(self, now: Optional[float] = None) -> bool:
        """Check whether the run exceeds its TTL."""
        current_time = time.time() if now is None else now
        return (current_time - self.created_at) > self.ttl_seconds


# ---------------------------------------------------------------------------
# RunStore
# ---------------------------------------------------------------------------


class RunStore:
    """Thread-safe in-memory store for pipeline runs awaiting resolution."""

    def __init__(self, default_ttl: float = 3600.0):
        self._runs: Dict[str, StoredRun] = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl

    def save_run(self, run: StoredRun) -> None:
        """Save or overwrite a stored run."""
        with self._lock:
            self._runs[run.run_id] = run

    def get_run(self, run_id: str) -> Optional[StoredRun]:
        """Retrieve stored run by run_id."""
        with self._lock:
            return self._runs.get(run_id)

    def delete_run(self, run_id: str) -> None:
        """Remove a run from storage."""
        with self._lock:
            self._runs.pop(run_id, None)

    def clear(self) -> None:
        """Clear all stored runs."""
        with self._lock:
            self._runs.clear()


# Default singleton instance
default_run_store = RunStore()


# ---------------------------------------------------------------------------
# Resolution Procedure
# ---------------------------------------------------------------------------


def resolve_pipeline_run(
    run_id: str,
    selected_plan_id: str,
    store: Optional[RunStore] = None,
) -> Any:
    """Resolve a tied pipeline run with a user-selected candidate plan.

    Reuses stored candidate plans, DuckDB execution results, and score breakdowns.
    Skips candidate regeneration. Runs Pass 2 on the chosen candidate, promotes it
    as rank 1 winner, generates the canonical DashboardSpec, and stamps resolved_by='user'
    in the trace.

    Args:
        run_id: Identifier of the stored pipeline run.
        selected_plan_id: Candidate plan ID selected by user.
        store: Optional RunStore instance (defaults to default_run_store).

    Returns:
        OrchestrationPipelineResult with status="SUCCESS" and resolved DashboardSpec.

    Raises:
        RunNotFoundError: If run_id is unknown.
        RunExpiredError: If run has expired past TTL.
        PlanNotFoundError: If selected_plan_id does not exist in the run.
    """
    from orchestrator.pipeline import OrchestrationPipelineResult

    active_store = store or default_run_store
    stored = active_store.get_run(run_id)

    if stored is None:
        raise RunNotFoundError(run_id)

    if stored.is_expired():
        raise RunExpiredError(run_id)

    # Find the chosen candidate among stored candidates
    chosen_match = next((t for t in stored.ranked_candidates if t[0].plan_id == selected_plan_id), None)
    if chosen_match is None:
        raise PlanNotFoundError(selected_plan_id, run_id)

    # Re-order candidates so the chosen plan is promoted to rank 1
    others = [t for t in stored.ranked_candidates if t[0].plan_id != selected_plan_id]
    re_ranked: List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]] = [
        (chosen_match[0], chosen_match[1], chosen_match[2], 1)
    ]
    for idx, item in enumerate(others, start=2):
        re_ranked.append((item[0], item[1], item[2], idx))

    # Run Pass 2 on chosen candidate, cascade if needed, and build DashboardSpec
    dashboard_spec: DashboardSpec = select_winner(
        ranked=re_ranked,
        dataset_id=stored.dataset.metadata.dataset_id,
        intent=stored.intent,
        context_hash=stored.context_hash,
        generator_logs=stored.generator_logs,
        ranker_weights=stored.weights,
        consistency_check=stored.consistency,
        max_cascade_depth=stored.max_cascade_depth,
        structured_intent=stored.structured_intent,
        ambiguity_result=stored.ambiguity,
        candidate_records=stored.candidate_records,
        plans_generated=stored.plans_generated,
        plans_passed_pass1a=stored.pass1a_counts,
        plans_passed_pass1b=stored.pass1b_counts,
        candidate_validations=stored.candidate_validations,
        resolved_by="user",
        run_id=run_id,
        semantic_profile=stored.semantic_profile,
    )

    # Log structured decision and explainability traces
    decision_entry = emit_decision_log(
        request_id=str(uuid4()),
        dataset_id=stored.dataset.metadata.dataset_id,
        intent=stored.intent,
        context_hash=stored.context_hash,
        mode="resolved",
        plans_generated=stored.plans_generated,
        plans_valid_pass1a=stored.pass1a_counts,
        plans_valid_pass1b=stored.pass1b_counts,
        winner_plan_id=dashboard_spec.winner.plan.plan_id,
        is_tie=False,
        cascade_depth=dashboard_spec.trace.cascade_depth,
        status="SUCCESS",
        generator_logs=stored.generator_logs,
    )

    explain_entry = emit_explainability_log(
        spec=dashboard_spec,
        ranked_candidates=re_ranked,
    )

    return OrchestrationPipelineResult(
        status="SUCCESS",
        message=f"Pipeline run '{run_id}' resolved successfully by user selection.",
        dashboard_spec=dashboard_spec,
        ambiguity=stored.ambiguity,
        structured_intent=stored.structured_intent,
        interpretations=stored.interpretations,
        ranked_candidates=re_ranked,
        is_tie=False,
        cascade_depth=dashboard_spec.trace.cascade_depth,
        decision_log_entry=decision_entry,
        explainability_log_entry=explain_entry,
        run_id=run_id,
    )
