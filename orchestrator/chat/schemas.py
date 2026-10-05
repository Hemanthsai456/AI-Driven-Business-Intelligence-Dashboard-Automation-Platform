"""Schemas for Evidence-Grounded Dataset Interaction / Chat (Step 8 / Roadmap #7).

Defines structured contracts for:
1. User chat requests and assistant responses
2. Structured conversation context and state tracking
3. Chat intent classifications and clarification specifications
4. Evidence and provenance bindings
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    FilterSpec,
    MetricSpec,
    VisualizationType,
)


class ChatIntentType(str, Enum):
    """Categorized intent for conversational interaction."""

    ANALYTICAL_QUERY = "ANALYTICAL_QUERY"
    FOLLOW_UP = "FOLLOW_UP"
    COMPARISON = "COMPARISON"
    DATASET_METADATA = "DATASET_METADATA"
    INSIGHT_EXPLANATION = "INSIGHT_EXPLANATION"
    DASHBOARD_EXPLANATION = "DASHBOARD_EXPLANATION"
    PROVENANCE_OR_SQL = "PROVENANCE_OR_SQL"
    UNSUPPORTED_OR_CAUSAL = "UNSUPPORTED_OR_CAUSAL"
    AMBIGUOUS_CLARIFICATION = "AMBIGUOUS_CLARIFICATION"
    GENERAL_HELP = "GENERAL_HELP"


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """Individual message in a conversation thread."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    role: ChatRole
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    intent_type: Optional[ChatIntentType] = None
    query_plan: Optional[Dict[str, Any]] = None
    compiled_sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: int = 0
    evidence: Optional[Any] = None
    confidence: float = 1.0
    warnings: List[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_options: Optional[List[str]] = None
    provenance: Optional[Any] = None


class ConversationContext(BaseModel):
    """Lightweight structured state for conversational multi-turn context."""

    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    history: List[ChatMessage] = Field(default_factory=list)
    last_question: Optional[str] = None
    last_intent_type: Optional[ChatIntentType] = None
    last_plan: Optional[Dict[str, Any]] = None
    last_result_rows: Optional[List[Dict[str, Any]]] = None
    last_columns: Optional[List[str]] = None
    last_metric: Optional[str] = None
    last_aggregation: Optional[AggregationType] = None
    last_dimensions: Optional[List[str]] = None
    last_filters: Optional[List[Dict[str, Any]]] = None
    last_compiled_sql: Optional[str] = None
    last_insight_ids: Optional[List[str]] = None
    last_dashboard_spec_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_message(self, message: ChatMessage) -> None:
        """Append message and update timestamp."""
        self.history.append(message)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def update_analytical_state(
        self,
        question: str,
        plan: Optional[CandidatePlan],
        rows: Optional[List[Dict[str, Any]]],
        columns: Optional[List[str]],
        compiled_sql: Optional[str],
        intent_type: ChatIntentType = ChatIntentType.ANALYTICAL_QUERY,
    ) -> None:
        """Update last analytical query context."""
        self.last_question = question
        self.last_intent_type = intent_type
        if plan:
            self.last_plan = plan.model_dump()
            self.last_metric = plan.metric.column if plan.metric else None
            self.last_aggregation = plan.metric.aggregation if plan.metric else None
            self.last_dimensions = [d.column for d in plan.dimensions] if plan.dimensions else []
            self.last_filters = [f.model_dump() for f in plan.filters] if plan.filters else []
        self.last_result_rows = rows
        self.last_columns = columns
        self.last_compiled_sql = compiled_sql
        self.updated_at = datetime.now(timezone.utc).isoformat()


class ChatRequest(BaseModel):
    """Payload for conversational dataset interaction."""

    dataset_id: str
    message: str
    conversation_id: Optional[str] = None
    use_llm: Optional[bool] = True


class ChatResponse(BaseModel):
    """Structured response for conversational dataset interaction."""

    conversation_id: str
    message_id: str
    dataset_id: str
    question: str
    answer: str
    intent_type: ChatIntentType
    query_plan: Optional[Dict[str, Any]] = None
    compiled_sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: int = 0
    evidence: Optional[Any] = None
    confidence: float = 1.0
    warnings: List[str] = Field(default_factory=list)
    ambiguity_status: str = "CLEAR"
    clarification_needed: bool = False
    clarification_options: Optional[List[str]] = None
    provenance: Optional[Any] = None
    runtime_seconds: float = 0.0
    error: Optional[str] = None
