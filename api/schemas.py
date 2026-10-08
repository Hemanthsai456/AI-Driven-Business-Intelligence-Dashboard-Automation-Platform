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
    system_role: Optional[str] = None
    user_override_role: Optional[str] = None
    is_user_overridden: bool = False
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


class EDAExploreRequest(BaseModel):
    """Request payload for interactive exploratory data analysis."""

    chart_type: str = "scatter"  # "scatter" | "line" | "bar" | "distribution"
    x_column: str
    y_column: Optional[str] = None
    group_by: Optional[str] = None
    aggregation: str = "mean"  # "mean" | "sum" | "median" | "count" | "min" | "max"
    time_granularity: Optional[str] = None  # "day" | "month" | "quarter" | "year"


class ColumnTransformPreviewRequest(BaseModel):
    """Request payload for deterministic preview of a single column transformation."""

    column_name: str
    operation: str
    target_type: Optional[str] = None
    custom_value: Optional[Any] = None
    allow_fractional_truncation: bool = False


class ColumnTransformPreviewResponse(BaseModel):
    """Response payload with preview metrics for a column transformation."""

    column_name: str
    operation: str
    target_type: str
    original_dtype: str
    target_dtype: str
    total_rows: int
    non_null_count: int
    converted_count: int
    unparseable_count: int
    unparseable_samples: List[Any] = Field(default_factory=list)
    fractional_loss_count: int = 0
    original_missing_count: int = 0
    new_missing_count: int = 0
    is_valid: bool = True
    error_message: Optional[str] = None
    sample_changes: List[Dict[str, Any]] = Field(default_factory=list)


class CleaningSelectionRequest(BaseModel):
    """Request payload for cleaning preview or apply."""

    selected_recommendation_ids: List[str] = Field(default_factory=list)
    operation_overrides: Optional[Dict[str, str]] = Field(default_factory=dict)
    operation_values: Optional[Dict[str, Any]] = Field(default_factory=dict)
    custom_transformations: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class MultiValueCandidateSchema(BaseModel):
    """Structured result of multi-valued cell detection on a column."""

    column_name: str
    detected_delimiter: str
    affected_rows: int
    affected_percentage: float
    average_values_per_affected_row: float
    max_values_per_row: int
    examples: List[str] = Field(default_factory=list)
    confidence: str
    recommendation: str
    reason: str
    evidence: List[str] = Field(default_factory=list)
    column_dtype: str = "object"
    semantic_role: str = "DIMENSION"


class MultiValueCandidatesResponse(BaseModel):
    """Response containing detected multi-valued cell candidates."""

    dataset_id: str
    candidates_count: int
    candidates: List[MultiValueCandidateSchema]


class MultiValuePreviewRequest(BaseModel):
    """Request payload for multi-valued cell transformation preview."""

    column_name: str
    action: str  # "SPLIT_COLUMNS" | "EXPAND_ROWS" | "KEEP"
    delimiter: Optional[str] = None


class MultiValuePreviewResponse(BaseModel):
    """Response payload for multi-valued cell transformation preview."""

    dataset_id: str
    column_name: str
    action: str
    delimiter_used: str
    original_row_count: int
    resulting_row_count: int
    rows_added: int
    original_column_count: int
    resulting_column_count: int
    affected_rows: int
    generated_columns: List[str] = Field(default_factory=list)
    warning_message: Optional[str] = None
    sample_before_after: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class MultiValueApplyRequest(BaseModel):
    """Request payload for applying multi-valued cell transformation."""

    column_name: str
    action: str  # "SPLIT_COLUMNS" | "EXPAND_ROWS" | "KEEP"
    delimiter: Optional[str] = None


class MultiValueApplyResponse(BaseModel):
    """Response payload after applying multi-valued cell transformation."""

    dataset_id: str
    action: str
    column_name: str
    audit_info: Dict[str, Any]
    cleaned_row_count: int
    cleaned_column_count: int
    status: str = "SUCCESS"


# =========================================================================
# Part 6.4 — Structural Cleaning & Semantic Role Overrides Schemas
# =========================================================================


class DropColumnsRequest(BaseModel):
    """Request payload for dropping one or more columns."""

    columns: List[str]


class DropColumnsPreviewResponse(BaseModel):
    """Response payload for column drop preview."""

    dataset_id: str
    original_column_count: int
    resulting_column_count: int
    columns_to_drop: List[str]
    remaining_columns: List[str]
    original_row_count: int
    resulting_row_count: int
    sample_before_after: List[Dict[str, Any]] = Field(default_factory=list)


class FilterConditionSchema(BaseModel):
    """Structured condition for row removal."""

    column: str
    operator: str
    value: Optional[Any] = None


class RowFilterRequest(BaseModel):
    """Request payload for single or multi-condition row removal."""

    conditions: List[FilterConditionSchema]
    logical_operator: str = "AND"  # "AND" | "OR"


class RowFilterPreviewResponse(BaseModel):
    """Response payload for row removal preview."""

    dataset_id: str
    conditions: List[Dict[str, Any]]
    logical_operator: str
    original_row_count: int
    resulting_row_count: int
    rows_removed: int
    original_column_count: int
    resulting_column_count: int
    sample_matching_rows: List[Dict[str, Any]] = Field(default_factory=list)
    sample_remaining_rows: List[Dict[str, Any]] = Field(default_factory=list)


class DuplicateRemovalRequest(BaseModel):
    """Request payload for duplicate row removal."""

    keep_strategy: str = "first"  # "first" | "last"


class DuplicateRemovalPreviewResponse(BaseModel):
    """Response payload for duplicate row removal preview."""

    dataset_id: str
    duplicate_rows_count: int
    keep_strategy: str
    original_row_count: int
    resulting_row_count: int
    rows_removed: int
    sample_duplicate_rows: List[Dict[str, Any]] = Field(default_factory=list)


class StructuralQualityRecommendationSchema(BaseModel):
    """Deterministic structural recommendation based on profiling observations."""

    recommendation_id: str
    column_name: Optional[str] = None
    issue_type: str
    reason: str
    evidence: List[str] = Field(default_factory=list)
    suggested_action: str
    allowed_actions: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class StructuralRecommendationsResponse(BaseModel):
    """Response containing structural recommendations."""

    dataset_id: str
    total_recommendations: int
    recommendations: List[StructuralQualityRecommendationSchema] = Field(default_factory=list)


class SemanticRoleOverrideRequest(BaseModel):
    """Request payload for overriding a column's semantic role."""

    column_name: str
    selected_role: str  # "IDENTIFIER" | "DIMENSION" | "MEASURE" | "DATETIME" | "UNKNOWN"


class SemanticRoleOverrideResponse(BaseModel):
    """Response payload after overriding a column's semantic role."""

    dataset_id: str
    column_name: str
    system_role: str
    selected_role: str
    physical_dtype: str
    evidence: List[str] = Field(default_factory=list)
    status: str = "SUCCESS"


class StructuralApplyResponse(BaseModel):
    """Response payload after applying a structural cleaning operation."""

    dataset_id: str
    action: str
    audit_info: Dict[str, Any]
    cleaned_row_count: int
    cleaned_column_count: int
    status: str = "SUCCESS"


# ---------------------------------------------------------------------------
# Part 1 — Cleaned Dataset Summary Schemas
# ---------------------------------------------------------------------------


class MetricBeforeAfter(BaseModel):
    """Before and after metric comparison for cleaned dataset summary."""

    before: int
    after: int
    change: int


class CleaningSummaryMetrics(BaseModel):
    """Comprehensive metric comparisons before and after cleaning."""

    rows: MetricBeforeAfter
    columns: MetricBeforeAfter
    missing_cells: MetricBeforeAfter
    duplicate_rows: MetricBeforeAfter


class CleanedDatasetSummaryResponse(BaseModel):
    """Summary of the current cleaned dataset state before registration."""

    dataset_id: str
    has_cleaned: bool
    status_message: str
    raw_data_protection: str = "Original dataset remains unchanged."
    metrics: CleaningSummaryMetrics
    changes_applied: List[str] = Field(default_factory=list)
    remaining_quality_issues: List[str] = Field(default_factory=list)
    registered_cleaned_dataset_id: Optional[str] = None




