"""Pydantic schemas and contracts for Evidence-Grounded AI Insights (Step 6).

Implements:
- Structured InsightType vocabulary for the 7 required insight types
- Structured InsightEvidence model maintaining complete analytical provenance
- EvidenceGroundedInsight model containing verified claims and metadata
- Validation and rejection reporting models
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4
from pydantic import BaseModel, Field

from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    FilterSpec,
    Granularity,
)


class InsightType(str, Enum):
    """Authoritative insight type categories for evidence-grounded insights."""

    KPI = "KPI"
    RANKING = "RANKING"
    GROUP_COMPARISON = "GROUP_COMPARISON"
    DISTRIBUTION = "DISTRIBUTION"
    TEMPORAL_TREND = "TEMPORAL_TREND"
    OUTLIER = "OUTLIER"
    CORRELATION = "CORRELATION"


class InsightEvidence(BaseModel):
    """Structured analytical evidence backing an insight claim.

    Every numerical and factual claim in an insight must be traceable to this object.
    """

    source_dataset: str = Field(description="Dataset ID or name")
    metric_column: str = Field(description="Primary metric or column analyzed")
    aggregation: AggregationType = Field(description="Aggregation applied")
    dimension_column: Optional[str] = Field(default=None, description="Primary grouping dimension if grouped")
    secondary_dimension: Optional[str] = Field(default=None, description="Secondary grouping dimension if multi-dimensional")
    secondary_metric: Optional[str] = Field(default=None, description="Second metric analyzed (e.g. in correlation)")
    filters: List[FilterSpec] = Field(default_factory=list, description="Filter constraints applied during analysis")
    time_grain: Optional[Granularity] = Field(default=None, description="Temporal bucketing granularity if time-series")
    
    # Ground-truth computed values
    values: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value metrics (e.g. {'primary_value': 84.5, 'top_group': 'Eng', 'top_val': 95.0, 'bottom_group': 'Sales', 'bottom_val': 45.0, 'difference': 50.0, 'difference_pct': 111.1})"
    )
    
    # Provenance and execution metadata
    query_or_plan: Optional[CandidatePlan] = Field(default=None, description="Candidate plan used to compute the evidence")
    compiled_sql: Optional[str] = Field(default=None, description="Authoritative compiled SQL executed in DuckDB")
    row_count: int = Field(default=0, description="Total rows in the executed query result")
    supporting_rows_or_groups: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top / supporting sample rows returned by DuckDB"
    )
    statistical_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Statistical test results, effect sizes, sample size, p-values, correlations, or dispersion metrics"
    )

    model_config = {"frozen": True}


class EvidenceGroundedInsight(BaseModel):
    """A fully verified, evidence-backed analytical insight."""

    insight_id: str = Field(default_factory=lambda: str(uuid4()))
    type: InsightType = Field(description="Type of insight")
    title: str = Field(description="Concise, informative headline")
    statement: str = Field(description="Factual, evidence-grounded natural language sentence")
    interpretation: Optional[str] = Field(default=None, description="Analytical significance or context")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Heuristic importance / magnitude score")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Validation & evidence confidence")
    evidence: InsightEvidence = Field(description="Structured deterministic evidence backing all claims")
    warnings: List[str] = Field(default_factory=list, description="Data quality or scope caveats")
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution trace (plan_id, compiled_sql, engine, execution_time)"
    )

    model_config = {"frozen": True}


class InsightRejectionInfo(BaseModel):
    """Audit record for candidate insights rejected during deterministic validation."""

    candidate_id: str
    insight_type: InsightType
    metric: str
    dimension: Optional[str] = None
    reason: str
    stage: str = "VALIDATION"  # "SEMANTIC_PRUNING", "EXECUTION", "VALIDATION", "DEDUPLICATION"

    model_config = {"frozen": True}


class InsightGenerationResult(BaseModel):
    """Aggregate result from the Evidence-Grounded Insight Engine."""

    dataset_id: str
    insights: List[EvidenceGroundedInsight] = Field(default_factory=list)
    rejections: List[InsightRejectionInfo] = Field(default_factory=list)
    total_candidates_generated: int = 0
    total_candidates_executed: int = 0
    total_insights_validated: int = 0
    total_insights_selected: int = 0
    runtime_seconds: float = 0.0
    summary_notice: Optional[str] = None

    model_config = {"frozen": True}
