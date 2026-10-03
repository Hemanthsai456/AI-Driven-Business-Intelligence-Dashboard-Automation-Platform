"""Schemas and data models for Stage E: Insight Discovery Mode."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4
from pydantic import BaseModel, Field

from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DashboardPanel,
    DashboardSpec,
    ExecutionResult,
)


class InsightType(str, Enum):
    """Supported typed insight categories for discovery mode."""

    TOTAL_KPI = "TOTAL_KPI"
    RANKING = "RANKING"
    COMPOSITION = "COMPOSITION"
    TREND = "TREND"
    PERIOD_CHANGE = "PERIOD_CHANGE"
    DISTRIBUTION_OUTLIERS = "DISTRIBUTION_OUTLIERS"
    DISTRIBUTION = "DISTRIBUTION"
    CORRELATION = "CORRELATION"
    SEGMENT_GAP = "SEGMENT_GAP"


class InsightCandidate(BaseModel):
    """A typed insight candidate proposed by enumeration or agents."""

    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    insight_type: InsightType
    plan: CandidatePlan
    measure: str
    secondary_measure: Optional[str] = None
    dimension: Optional[str] = None
    aggregation: AggregationType = AggregationType.SUM
    proposed_by: str = "enumerator"  # "enumerator" or "agent"
    params: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class InsightScore(BaseModel):
    """Score breakdown for a discovered insight."""

    strength: float = Field(description="Effect size per type (eta², top share, R², outlier frac, |r|)")
    robustness: float = Field(description="Fraction of perturbations preserving the claim")
    p_value: float = Field(description="Significance test p-value")
    fdr_passed: bool = Field(description="Whether insight passed Benjamini-Hochberg FDR control")
    fdr_critical_value: float = Field(default=0.05, description="FDR critical p-value threshold")
    quality: float = Field(description="Data quality score: group size, null rate, cast rate")
    total_score: float = Field(description="strength * robustness * quality")
    rejected: bool = False
    rejection_reason: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class DiscoveredInsight(BaseModel):
    """A fully executed, scored, and validated insight with narration."""

    candidate: InsightCandidate
    execution_result: ExecutionResult
    score: InsightScore
    narration: Optional[str] = None
    why_chosen: Optional[str] = None
    rank: int = 0

    model_config = {"frozen": True}


class RejectedInsightInfo(BaseModel):
    """Summary of a candidate insight rejected during validation, testing, or selection."""

    candidate_id: str
    insight_type: InsightType
    description: str
    measure: str
    dimension: Optional[str] = None
    rejection_stage: str  # "PASS1A", "EXECUTION", "PASS1B", "FDR", "FLOOR", "DIVERSITY"
    reason: str
    p_value: Optional[float] = None
    score: Optional[float] = None

    model_config = {"frozen": True}


class DiscoverySummary(BaseModel):
    """Summary metrics of the insight discovery process."""

    dataset_id: str
    candidates_generated: int
    candidates_executed: int
    candidates_rejected: int
    candidates_selected: int
    enumerator_proposed: int = 0
    agent_proposed: int = 0
    candidates_fdr_passed: int = 0
    enumerator_fdr_passed: int = 0
    agent_fdr_passed: int = 0
    enumerator_selected: int = 0
    agent_selected: int = 0
    fdr_alpha: float = 0.05
    strength_floor: float = 0.08
    robustness_floor: float = 0.35
    quality_floor: float = 0.40
    data_supports_insights: bool = True
    notice: Optional[str] = None

    model_config = {"frozen": True}
