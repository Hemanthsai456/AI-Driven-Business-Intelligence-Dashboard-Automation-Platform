"""Pydantic schemas for API requests and responses."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ColumnMetadataSchema(BaseModel):
    original_name: str
    normalized_name: str
    detected_datatype: str
    semantic_role: str
    null_count: int
    null_percentage: float
    distinct_count: int
    is_unique: bool
    sample_values: List[Any]


class DatasetMetadataResponse(BaseModel):
    dataset_id: str
    filename: str
    source_type: str
    row_count: int
    column_count: int
    columns: List[ColumnMetadataSchema]
    dtypes: Dict[str, str]
    ingestion_status: str
    ingestion_errors: List[str] = Field(default_factory=list)


class DataPreviewResponse(BaseModel):
    dataset_id: str
    filename: str
    total_rows: int
    preview_rows_count: int
    columns: List[str]
    rows: List[Dict[str, Any]]
    is_preview: bool = True


class DatasetSummaryResponse(BaseModel):
    dataset_id: str
    filename: str
    source_type: str
    row_count: int
    column_count: int
    missingness_percentage: float
    duplicate_rows: int
    dtypes_breakdown: Dict[str, int]


class DataProfileResponse(BaseModel):
    profile_id: str
    dataset_id: str
    generated_at: str
    dataset_summary: Dict[str, Any]
    column_statistics: Dict[str, Dict[str, Any]]
    quality_issues: List[Dict[str, Any]]
    correlation_matrix: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class SemanticColumnResponse(BaseModel):
    column_name: str
    candidate_role: str
    confidence: float
    confidence_level: str
    evidence: List[str]


class SemanticProfileResponse(BaseModel):
    dataset_id: str
    generated_at: str
    column_evidences: Dict[str, SemanticColumnResponse]


class AnalysisReadinessResponse(BaseModel):
    dataset_id: str
    status: str
    generated_at: str
    summary: str
    blocking_issues: List[str]
    warnings: List[str]
    checked_columns: List[str]
    checked_row_count: int
    checked_column_count: int
    checks: List[Dict[str, Any]]


class APIErrorResponse(BaseModel):
    error: str
    message: str
    status_code: int
    details: Optional[Dict[str, Any]] = None


class DatasetListItem(BaseModel):
    dataset_id: str
    filename: str
    source_type: str
    row_count: int
    column_count: int
    created_at: str
    readiness_status: str


class PlanRunResponse(BaseModel):
    plan_id: str
    pass1a: Dict[str, Any]
    execution: Optional[Dict[str, Any]] = None
    pass1b: Optional[Dict[str, Any]] = None


class GenerateCandidatesRequest(BaseModel):
    dataset_id: str
    intent: str
    k: int = 3
    mode: Optional[str] = None  # "llm_only" | "agent_only" | "both"


class GenerateCandidatesResponse(BaseModel):
    dataset_id: str
    intent: str
    ambiguity: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    logs: List[Dict[str, Any]]


class SelectWinnerRequest(BaseModel):
    """Request body for /api/orchestrator/select-winner.

    Accepts candidate plans and their execution results; the server re-ranks
    and selects the winner applying Pass 2 with cascade.
    """

    dataset_id: str
    intent: str
    # Candidates as CandidatePlan dicts (from /generate-candidates)
    candidates: List[Dict[str, Any]]
    # Execution results keyed by plan_id (from /run-plan per candidate)
    execution_results: Dict[str, Any]  # plan_id -> ExecutionResult dict
    # Optional generator logs for OrchestratorTrace
    generator_logs: Optional[List[Dict[str, Any]]] = None
    context_hash: Optional[str] = None


class SelectWinnerResponse(BaseModel):
    """Response from /api/orchestrator/select-winner."""

    spec_id: str
    dataset_id: str
    intent: str
    # Winner identification
    winner_plan_id: str
    winner_score: float
    winner_generator: str
    winner_visualization: str
    winner_rank_before_cascade: int
    # Pass 2 details
    pass2_passed: bool
    pass2_issues: List[Dict[str, Any]]
    cascade_depth: int
    cascade_triggered: bool
    # Tie handling
    is_tie: bool
    # Alternate interpretations (runner-ups)
    alternate_interpretations: List[Dict[str, Any]]
    # Full winner plan for display
    winner_plan: Dict[str, Any]
    # Full execution result of winner
    winner_execution: Dict[str, Any]
    # Score breakdown
    score_breakdown: Dict[str, Any]
    created_at: str


class OrchestratorPipelineRequest(BaseModel):
    """Request payload for the end-to-end Orchestrator pipeline."""

    dataset_id: str
    intent: str
    mode: Optional[str] = "both"  # "llm_only" | "agent_only" | "both"
    k: Optional[int] = 3
    chosen_plan_id: Optional[str] = None
    require_clarification: Optional[bool] = False
    rank_tie_epsilon: Optional[float] = None
    robustness_tie_floor: Optional[float] = None


class OrchestratorPipelineResponse(BaseModel):
    """Response payload from the end-to-end Orchestrator pipeline."""

    status: str  # "SUCCESS" | "REFUSED" | "UNANSWERABLE" | "NEEDS_CLARIFICATION"
    message: str
    spec_id: Optional[str] = None
    headline: Optional[str] = None
    panels: Optional[List[Dict[str, Any]]] = None
    dashboard_spec: Optional[Dict[str, Any]] = None
    ranked_candidates: List[Dict[str, Any]] = []
    winner: Optional[Dict[str, Any]] = None
    is_tie: bool = False
    cascade_depth: int = 0
    ambiguity_status: str = "CLEAR"
    ambiguity_message: Optional[str] = None
    clarification_needed: bool = False
    clarification_options: Optional[List[Dict[str, Any]]] = None
    options: Optional[List[Dict[str, Any]]] = None
    cached_candidates: Optional[List[Dict[str, Any]]] = None
    run_id: Optional[str] = None
    resolved_by: Optional[str] = None
    decision_log_entry: Optional[Dict[str, Any]] = None
    explainability_log_entry: Optional[Dict[str, Any]] = None
    mode: Optional[str] = "focused"
    rejected_insights: Optional[List[Dict[str, Any]]] = None


class ResolvePipelineRequest(BaseModel):
    """Request payload for resolving a tied pipeline run with a user-selected plan."""

    run_id: str
    selected_plan_id: str


class ResolveErrorResponse(BaseModel):
    """Typed error response when resolving a pipeline run fails."""

    error: str
    message: str
    error_type: str
    status_code: int


class TileFilter(BaseModel):
    """Filter applied to a tile query."""

    column: str
    operator: str = "="
    values: Optional[Any] = None
    value: Optional[Any] = None


class TileQueryRequest(BaseModel):
    """Request payload for querying a single dashboard tile with cross-filters/slicers."""

    filters: List[TileFilter] = Field(default_factory=list)


class TileQueryResponse(BaseModel):
    """Result data for a recompiled tile query."""

    tile_id: str
    status: str = "SUCCESS"  # "SUCCESS" | "INSUFFICIENT_DATA"
    row_count: int
    data: List[Dict[str, Any]]
    compiled_sql: Optional[str] = None
    cached: bool = False
    message: Optional[str] = None



