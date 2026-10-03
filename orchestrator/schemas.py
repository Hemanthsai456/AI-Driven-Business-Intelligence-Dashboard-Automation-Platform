"""Orchestrator Pydantic v2 schema definitions.

All schemas are immutable data containers (frozen=True where practical).
Enums are the authoritative type vocabulary for the orchestrator layer.

Architecture references:
- orchestrator_conformance.md §1 (Requirement Matrix)
- orchestrator_contracts.md (this module is the implementation)
- ranker_v1_spec.md (RankedCandidate, DashboardSpec)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AggregationType(str, Enum):
    """Whitelisted aggregation functions.  Never accept raw SQL beyond this list."""

    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    STDDEV = "STDDEV"
    MEDIAN = "MEDIAN"


class Granularity(str, Enum):
    """Temporal bucketing granularities, all of which require a DATETIME column."""

    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"


class VisualizationType(str, Enum):
    """Supported chart/visualization types for dashboard output."""

    BAR = "BAR"
    LINE = "LINE"
    AREA = "AREA"
    PIE = "PIE"
    SCATTER = "SCATTER"
    TABLE = "TABLE"
    KPI = "KPI"
    HEATMAP = "HEATMAP"


class AmbiguityStatus(str, Enum):
    """Ambiguity classification produced by the ambiguity pre-check engine."""

    CLEAR = "CLEAR"
    AMBIGUOUS = "AMBIGUOUS"
    UNANSWERABLE = "UNANSWERABLE"


class AmbiguityType(str, Enum):
    """Types of detected ambiguity."""

    MULTIPLE_MEASURES = "MULTIPLE_MEASURES"
    MULTIPLE_DATE_COLUMNS = "MULTIPLE_DATE_COLUMNS"
    MULTIPLE_GROUP_BYS = "MULTIPLE_GROUP_BYS"
    MISSING_AGGREGATION = "MISSING_AGGREGATION"
    MISSING_COLUMN = "MISSING_COLUMN"
    UNKNOWN_KPI = "UNKNOWN_KPI"
    UNKNOWN_ROLE = "UNKNOWN_ROLE"

    # Stage 3 typed ambiguity categories
    LEXICAL = "lexical"
    GRANULARITY = "granularity"
    AGGREGATION = "aggregation"
    SCOPE = "scope"


class ValidationStatus(str, Enum):
    """Per-candidate validation outcome."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"


class ExecutionStatus(str, Enum):
    """DuckDB execution outcome."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    MEMORY_EXCEEDED = "MEMORY_EXCEEDED"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class MetricSpec(BaseModel):
    """A single metric: one column + one aggregation function."""

    column: str = Field(description="Column name (must exist in DatasetSemanticProfile).")
    aggregation: AggregationType = Field(description="Whitelisted aggregation function.")

    model_config = {"frozen": True}


class DimensionSpec(BaseModel):
    """A grouping dimension, optionally with temporal granularity."""

    column: str = Field(description="Column name to group by.")
    granularity: Optional[Granularity] = Field(
        default=None,
        description="Temporal granularity — only valid when column has DATETIME role.",
    )

    model_config = {"frozen": True}


class FilterSpec(BaseModel):
    """A single column filter predicate (equality or range)."""

    column: str
    operator: str = Field(description="One of: =, !=, <, <=, >, >=, IN, NOT IN, IS NULL, IS NOT NULL")
    value: Optional[Any] = Field(default=None, description="Filter value; None for IS NULL / IS NOT NULL.")

    model_config = {"frozen": True}


class ComparisonSpec(BaseModel):
    """Period-over-period or segment comparison specification."""

    compare_to: str = Field(description="Human-readable description of comparison baseline (e.g. 'previous year').")
    column: str = Field(description="Column used for the comparison anchor.")
    value: Any = Field(description="Comparison baseline value.")

    model_config = {"frozen": True}


class PlanReasoning(BaseModel):
    """LLM-generated reasoning and evidence strings attached to a CandidatePlan."""

    interpretation: str = Field(description="Human-readable interpretation of the analytical intent.")
    evidence: List[str] = Field(
        default_factory=list,
        description="Evidence snippets from semantic profile supporting this interpretation.",
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# CandidatePlan — core orchestrator data contract
# ---------------------------------------------------------------------------


class CandidatePlan(BaseModel):
    """A structured analytical plan generated by the LLM and validated by Pass 1.

    Field set matches the frozen semantic_profile_v1 schema: candidate_role,
    confidence scores, and evidence strings are read-only inputs to plan generation.
    The LLM never modifies semantic roles.
    """

    plan_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique plan identifier (UUID).",
    )
    dataset_id: str = Field(description="ID of the CanonicalDataset this plan operates on.")
    intent: str = Field(description="Natural-language request or analytical intent.")
    metric: MetricSpec = Field(description="Primary metric (column + aggregation).")
    dimensions: List[DimensionSpec] = Field(
        default_factory=list,
        description="Zero or more grouping dimensions.",
    )
    filters: List[FilterSpec] = Field(
        default_factory=list,
        description="Zero or more column filter predicates.",
    )
    comparison: Optional[ComparisonSpec] = Field(
        default=None,
        description="Optional period-over-period or segment comparison.",
    )
    visualization: VisualizationType = Field(
        default=VisualizationType.TABLE,
        description="Proposed chart type for this plan.",
    )
    generator: str = Field(
        default="llm_direct",
        description="Generator identifier (e.g. 'llm_direct', 'external_agent').",
    )
    provider: str = Field(
        default="unknown",
        description="LLM provider (e.g. 'gemini', 'groq', 'ollama').",
    )
    supporting_providers: List[str] = Field(
        default_factory=list,
        description="List of providers that generated identical plans.",
    )
    supporting_count: int = Field(default=1)
    providers_responded: int = Field(default=1)
    reasoning: PlanReasoning = Field(description="LLM interpretation and evidence.")

    model_config = {"frozen": True}


    def plan_signature(self) -> str:
        """Compute a structural signature for deduplication.

        'Materially different' = differs in metric, aggregation, grouping,
        time column/range/granularity, filter/scope, comparison basis, or
        KPI definition.  Visualization and reasoning do NOT affect the signature.

        Returns:
            SHA-256 hex digest of the canonical JSON representation.
        """
        sig_dict = {
            "dataset_id": self.dataset_id,
            "metric": {"column": self.metric.column, "aggregation": self.metric.aggregation},
            "dimensions": sorted(
                [{"column": d.column, "granularity": d.granularity} for d in self.dimensions],
                key=lambda x: x["column"],
            ),
            "filters": sorted(
                [{"column": f.column, "operator": f.operator, "value": str(f.value)} for f in self.filters],
                key=lambda x: x["column"],
            ),
            "comparison": {
                "column": self.comparison.column,
                "value": str(self.comparison.value),
            }
            if self.comparison
            else None,
        }
        canonical_json = json.dumps(sig_dict, sort_keys=True)
        return hashlib.sha256(canonical_json.encode()).hexdigest()


# ---------------------------------------------------------------------------
# AmbiguityResult
# ---------------------------------------------------------------------------


class AmbiguityDetail(BaseModel):
    """Specific ambiguity detected in a request."""

    type: AmbiguityType
    field: str = Field(description="Column name or field where ambiguity was detected.")
    alternatives: List[str] = Field(
        default_factory=list,
        description="Candidate alternatives the user can choose from.",
    )
    is_blocking: bool = Field(
        default=False,
        description="Whether this ambiguity blocks candidate generation (request-level) or can be resolved/branched (item-level).",
    )
    category: Optional[str] = Field(
        default=None,
        description="One of: lexical, granularity, aggregation, scope.",
    )

    model_config = {"frozen": True}


class AmbiguityResult(BaseModel):
    """Ambiguity pre-check result for a natural-language request."""

    status: AmbiguityStatus
    ambiguities: List[AmbiguityDetail] = Field(
        default_factory=list,
        description="Non-empty only when status is AMBIGUOUS or UNANSWERABLE.",
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable summary of why the request is ambiguous or unanswerable.",
    )
    is_blocking: bool = Field(
        default=False,
        description="True if this ambiguity requires clarification and cannot proceed to planning.",
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# StructuredIntent & SemanticInterpretation — 6-step cognitive loop contracts
# ---------------------------------------------------------------------------


class StructuredIntent(BaseModel):
    """Structured representation of interpreted user analytical intent.

    Captures only information justified by the request and available schema/semantic evidence.
    """

    original_request: str
    analytical_goal: Optional[str] = Field(
        default=None,
        description="High-level analytical goal (e.g. 'aggregation', 'trend', 'distribution', 'comparison').",
    )
    requested_metrics: List[str] = Field(
        default_factory=list,
        description="Candidate measure/metric columns identified from request.",
    )
    requested_dimensions: List[str] = Field(
        default_factory=list,
        description="Grouping or categorical dimension columns identified.",
    )
    temporal_scope: Optional[str] = Field(
        default=None,
        description="Identified date/time column if temporal analysis was requested.",
    )
    grouping_granularity: Optional[str] = Field(
        default=None,
        description="Temporal granularity (e.g. 'month', 'year', 'day') if specified.",
    )
    comparison_requirements: Optional[str] = Field(
        default=None,
        description="Comparison or period-over-period requirement if specified.",
    )
    requested_visual_preferences: Optional[str] = Field(
        default=None,
        description="Explicit visual preference (e.g. 'bar', 'line', 'table') if mentioned.",
    )
    filters: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Filter constraints identified from intent.",
    )
    unresolved_terms: List[str] = Field(
        default_factory=list,
        description="Terms from request that could not be mapped to semantic columns.",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score for the interpreted intent.",
    )

    model_config = {"frozen": True}


class SemanticInterpretation(BaseModel):
    """A coherent, concrete semantic interpretation of the user request.

    Bridges between the structured intent and candidate planning.
    """

    interpretation_id: str = Field(default_factory=lambda: str(uuid4()))
    intent_summary: str = Field(description="Summary of this interpretation.")
    metric_column: str = Field(description="Selected metric measure column.")
    aggregation: AggregationType = Field(description="Aggregation function.")
    dimension_columns: List[str] = Field(default_factory=list)
    granularity: Optional[Granularity] = Field(default=None)
    filter_specs: List[FilterSpec] = Field(default_factory=list)
    visualization: VisualizationType = Field(default=VisualizationType.TABLE)
    resolved_intent_elements: Dict[str, Any] = Field(default_factory=dict)
    referenced_columns: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    unresolved_elements: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0)

    model_config = {"frozen": True}



# ---------------------------------------------------------------------------
# LLMContext — compact structured context sent to the LLM
# ---------------------------------------------------------------------------


class ColumnContextEntry(BaseModel):
    """Compact per-column semantic evidence for LLM context.  Raw rows never included."""

    column_name: str
    candidate_role: str
    confidence: float
    confidence_level: str
    evidence: List[str] = Field(default_factory=list)
    # Key statistics (safe, non-PII summary only)
    distinct_count: Optional[int] = None
    null_percentage: Optional[float] = None
    dtype: Optional[str] = None

    model_config = {"frozen": True}


class LLMContext(BaseModel):
    """Compact structured context passed to the LLM for plan generation.

    Raw data rows are NEVER included — only role, confidence, evidence,
    and key statistics (docs/orchestrator_conformance.md §1, 'Compact LLM Context').
    """

    dataset_id: str
    intent: str
    columns: List[ColumnContextEntry] = Field(
        description="Request-relevant columns only, derived from DatasetSemanticProfile.",
    )
    context_hash: str = Field(
        description="SHA-256 hash of dataset_id + intent + column names for decision logging.",
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    model_config = {"frozen": True}

    @classmethod
    def compute_hash(cls, dataset_id: str, intent: str, column_names: Sequence[str]) -> str:
        raw = json.dumps(
            {"dataset_id": dataset_id, "intent": intent, "columns": sorted(column_names)},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ExecutionResult — DuckDB worker output
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    """Output from a single DuckDB worker execution.

    Includes structured warnings for failed TRY_CAST operations on DATETIME
    string columns (C2 binding resolution from orchestrator_conformance.md §4.2).
    """

    plan_id: str
    status: ExecutionStatus
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    row_count: int = Field(default=0)
    compiled_sql: Optional[str] = Field(default=None, description="Compiled DuckDB SQL (for audit).")
    failed_cast_count: int = Field(
        default=0,
        description="Number of TRY_CAST(col AS TIMESTAMP) NULLs produced for DATETIME string columns.",
    )
    failed_cast_rate: float = Field(
        default=0.0,
        description="failed_cast_count / total rows examined. Pass 1b rejects if above threshold.",
    )
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings including failed-cast summaries.")
    error_message: Optional[str] = Field(default=None)
    runtime_seconds: float = Field(default=0.0)

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """A single validation check outcome."""

    check: str = Field(description="Check name (e.g. 'column_exists', 'role_aggregation_compat').")
    status: ValidationStatus
    message: str = Field(description="Human-readable description of the check result.")
    column: Optional[str] = Field(default=None, description="Column name involved, if applicable.")

    model_config = {"frozen": True}


class Pass1aResult(BaseModel):
    """Pass 1a pre-dispatch validation result (before DuckDB worker invocation)."""

    plan_id: str
    passed: bool
    issues: List[ValidationIssue] = Field(default_factory=list)

    model_config = {"frozen": True}


class Pass1bResult(BaseModel):
    """Pass 1b post-execution validation result (after DuckDB worker, before ranking)."""

    plan_id: str
    passed: bool
    issues: List[ValidationIssue] = Field(default_factory=list)

    model_config = {"frozen": True}


class Pass2Result(BaseModel):
    """Pass 2 winner-only validation result.

    Validates plan-vs-result consistency and visualization suitability.
    Failure triggers runner-up cascade (capped by MAX_CASCADE_DEPTH).
    """

    plan_id: str = ""
    passed: bool
    reasons: List[str] = Field(default_factory=list)
    issues: List[ValidationIssue] = Field(default_factory=list)
    cascade_triggered: bool = False

    model_config = {"frozen": True}


# PassResult alias for Pass 2 output contract
PassResult = Pass2Result


class CandidateConsistencyCheck(BaseModel):
    """Verifies that surviving candidates share identical metric semantics.

    Checks: same metric column semantics, time basis (granularity), scope,
    units interpretation, and output column schema.
    """

    passed: bool
    mismatches: List[str] = Field(
        default_factory=list,
        description="Descriptions of semantic mismatches between surviving candidates.",
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Ranker V1 — scored candidate
# ---------------------------------------------------------------------------


class RankerWeights(BaseModel):
    """Ranker V1 weight configuration.  All weights are project hypotheses, logged with ranking."""

    w1_evidence: float = Field(description="Weight for evidence score (mean role confidence of columns used).")
    w2_coverage: float = Field(description="Weight for coverage score (fraction of request terms mapped to plan).")
    w3_stability: float = Field(description="Weight for stability score (result agreement under perturbations).")
    w4_assumptions: float = Field(description="Penalty weight for assumptions (defaults filled without request support).")
    w5_agreement: float = Field(default=0.0, description="Weight for agreement score (supporting_count / providers_responded).")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def weights_positive(self) -> "RankerWeights":
        for attr in ("w1_evidence", "w2_coverage", "w3_stability", "w4_assumptions", "w5_agreement"):
            if getattr(self, attr) < 0.0:
                raise ValueError(f"Ranker weight {attr} must be non-negative.")
        return self


class ScoreBreakdown(BaseModel):
    """Per-candidate score component breakdown for explainability logging."""

    evidence: float = Field(description="Mean role confidence of columns used (0.0-1.0).")
    coverage: float = Field(description="Fraction of request terms mapped to plan fields (0.0-1.0).")
    stability: Optional[float] = Field(default=None, description="Robustness across interpretations (or None if UNTESTED).")
    assumptions: float = Field(description="Normalised count of defaults filled without request support (0.0-1.0).")
    agreement: float = Field(default=0.0, description="Agreement score from multiple providers (0.0-1.0).")
    failed_cast_penalty: float = Field(default=0.0, description="Separate quality penalty for failed datetime TRY_CAST operations.")
    total: float = Field(description="Weighted total score: w1*evidence + w2*coverage + w3*stability - w4*assumptions + w5*agreement - failed_cast_penalty.")
    stability_status: str = Field(default="UNTESTED", description="'TESTED', 'UNTESTED', or 'FAILED'.")
    variants_attempted: int = Field(default=0, description="Count of attempted perturbation variants.")
    variants_valid: int = Field(default=0, description="Count of successfully executed and validated perturbation variants.")
    variants_failed: List[Dict[str, Any]] = Field(default_factory=list, description="List of failed variants with reasons.")
    variant_details: List[Dict[str, Any]] = Field(default_factory=list, description="Per-variant top-1 match and Spearman metrics.")
    coverage_of_test: float = Field(default=0.0, description="Coverage ratio: valid_variants / attempted_variants.")

    model_config = {"frozen": True}


class RankedCandidate(BaseModel):
    """A candidate plan with its execution result, validation outcomes, and ranking score."""

    plan: CandidatePlan
    execution_result: ExecutionResult
    pass1a: Pass1aResult
    pass1b: Pass1bResult
    score_breakdown: ScoreBreakdown
    rank: int = Field(description="1-based rank (1 = winner).")
    is_winner: bool = Field(default=False)

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# DashboardSpec — final orchestrator output
# ---------------------------------------------------------------------------


class AlternateInterpretation(BaseModel):
    """A runner-up or alternative plan preserved for transparency."""

    plan: CandidatePlan
    score: float
    reason_not_winner: str

    model_config = {"frozen": True}


from providers.types import GeneratorCallLog


class OrchestratorTrace(BaseModel):
    """Full execution trace for auditability and explainability logging."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    intent: str
    context_hash: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ambiguity_result: Optional[AmbiguityResult] = None
    structured_intent: Optional[StructuredIntent] = None
    llm_call_count: int = Field(default=0)
    llm_token_usage: int = Field(default=0)
    llm_latency_seconds: float = Field(default=0.0)
    generator_logs: List[GeneratorCallLog] = Field(default_factory=list)
    plans_generated: int = Field(default=0)
    plans_passed_pass1a: int = Field(default=0)
    plans_passed_pass1b: int = Field(default=0)
    reprompt_count: int = Field(default=0)
    cascade_depth: int = Field(default=0)
    ranker_weights: Optional[RankerWeights] = None
    pass2_result: Optional[Pass2Result] = None
    consistency_check: Optional[CandidateConsistencyCheck] = None
    total_runtime_seconds: float = Field(default=0.0)
    candidate_records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Trace records for all candidates: plan, pass1a, pass1b, score breakdown.",
    )
    resolved_by: Optional[str] = Field(
        default=None,
        description="Resolution source: 'user' when resolved via user interaction or None for automatic.",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Stored pipeline run ID associated with this trace.",
    )

    model_config = {"frozen": True}


class PanelType(str, Enum):
    """Supported visual dashboard panel types."""

    KPI = "KPI"
    BAR = "BAR"
    LINE = "LINE"
    TABLE = "TABLE"
    HEATMAP = "HEATMAP"
    INSIGHT = "INSIGHT"
    ALTERNATES = "ALTERNATES"


class DashboardPanel(BaseModel):
    """A renderable dashboard panel derived generically from plan semantics and execution results."""

    panel_id: str = Field(default_factory=lambda: str(uuid4()))
    panel_type: PanelType = Field(description="Visual component type: KPI, BAR, LINE, TABLE, HEATMAP, INSIGHT, ALTERNATES.")
    title: str = Field(description="Generic descriptive panel title derived at runtime.")
    description: Optional[str] = Field(default=None, description="Subtitle or explanatory commentary.")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Row/matrix data structured for visual rendering.")
    x_key: Optional[str] = Field(default=None, description="Dimension or category column key.")
    y_keys: List[str] = Field(default_factory=list, description="Metric column keys.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata such as cardinality, aggregation, and robustness details.")

    model_config = {"frozen": True}


class TileSize(BaseModel):
    """Tile dimensions on a 12-column grid."""

    w: int = Field(default=4, description="Width on 12-column grid (e.g. 3, 4, 6, 8, 12)")
    h: int = Field(default=3, description="Height or row span (e.g. 2, 3, 4)")

    model_config = {"frozen": True}


class SlicerOption(BaseModel):
    """A distinct option in a categorical/dimension slicer."""

    value: Any
    label: str
    count: Optional[int] = None

    model_config = {"frozen": True}


class SlicerDef(BaseModel):
    """Runtime slicer filter definition generated dynamically from the dataset."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    column: str
    role: str = Field(description="DATETIME or DIMENSION")
    control_type: str = Field(description="'date_range' or 'multi_select'")
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    options: List[SlicerOption] = Field(default_factory=list)

    model_config = {"frozen": True}


class TileEvidence(BaseModel):
    """Statistical and provenance evidence attached to a tile."""

    strength: Optional[float] = None
    robustness: Optional[float] = None
    fdr_passed: Optional[bool] = None
    fdr_q_value: Optional[float] = None
    n: Optional[int] = None
    score: Optional[float] = None

    model_config = {"frozen": True}


class DashboardTile(BaseModel):
    """A Power BI-style dashboard tile positioned on a 12-column grid."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(description="Insight title sentence")
    chart_type: str = Field(description="kpi, bar, horizontal_bar, line, area, donut, stacked_bar, scatter, histogram, table")
    size: TileSize = Field(default_factory=TileSize)
    priority: int = Field(default=0, description="Sorting priority (1=highest)")
    candidate_id: Optional[str] = None
    generator: str = Field(default="rule_baseline", description="Generator provenance: Gemini, Groq, agent, rule-based baseline")
    evidence: Optional[TileEvidence] = None
    why_chosen: Optional[str] = None
    plan: Optional[CandidatePlan] = None
    compiled_sql: Optional[str] = None
    data: List[Dict[str, Any]] = Field(default_factory=list)
    x_key: Optional[str] = None
    y_keys: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)
    delta: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class DashboardSpec(BaseModel):
    """Final orchestrator output: canonical dashboard specification.

    Contains the winning candidate specification, alternate interpretations,
    generic dashboard panels, Power BI-style dashboard tiles, runtime slicers,
    and the full execution trace for auditing and explainability.
    """

    spec_id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    intent: str
    headline: Optional[str] = Field(
        default=None,
        description="Headline insight sentence generated from spec (metric, dimension, top group, robustness).",
    )
    winner: RankedCandidate
    panels: List[DashboardPanel] = Field(
        default_factory=list,
        description="Generic renderable dashboard panels built from execution results.",
    )
    tiles: List[DashboardTile] = Field(
        default_factory=list,
        description="Power BI-style dashboard tiles positioned on a 12-column grid.",
    )
    slicers: List[SlicerDef] = Field(
        default_factory=list,
        description="Runtime slicer filter definitions generated dynamically from the dataset.",
    )
    alternate_interpretations: List[AlternateInterpretation] = Field(
        default_factory=list,
        description="Runner-up candidates preserved for transparency.",
    )
    trace: OrchestratorTrace
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_tie: bool = Field(
        default=False,
        description="True when top-2 candidates scored within RANK_TIE_EPSILON; clarification was triggered.",
    )
    mode: str = Field(
        default="focused",
        description="Execution mode: 'focused' (goal-directed) or 'discovery' (insight discovery mode).",
    )
    rejected_insights: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of candidate insights considered and rejected during discovery mode.",
    )
    discovery_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Summary statistics of discovery candidate evaluation.",
    )

    model_config = {"frozen": True}
