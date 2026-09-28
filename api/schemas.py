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

