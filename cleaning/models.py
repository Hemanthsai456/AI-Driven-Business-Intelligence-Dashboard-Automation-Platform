"""Data structures and configuration models for the automated data cleaning layer."""

from dataclasses import dataclass, field
import datetime
from typing import Any, Dict, List, Optional

from ingestion.models import CanonicalDataset, sanitize_json_value


@dataclass
class CleaningChange:
    """Record of a single cleaning transformation rule applied to a dataset or column.

    Attributes:
        rule: Machine-readable identifier for the rule (e.g. 'deduplicate', 'coerce_currency').
        column: Column name transformed, or None for whole-dataset operations.
        count: Number of rows, values, or nulls modified.
        details: Additional contextual metadata regarding the transformation.
    """

    rule: str
    column: Optional[str]
    count: int
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert cleaning change record to a JSON-serializable dictionary."""
        return {
            "rule": self.rule,
            "column": self.column,
            "count": int(self.count),
            "details": sanitize_json_value(self.details),
        }


@dataclass
class CleaningConfig:
    """Configurable options governing the behavior of the DataCleaner.

    Attributes:
        deduplicate: Whether to drop exact duplicate rows.
        coerce_types: Whether to coerce numeric strings, currencies, percentages, and dates.
        normalize_categories: Whether to trim whitespace and normalize casing for dimension columns.
        handle_nulls: Whether to impute missing values per column role.
        null_drop_threshold: Column missingness fraction (0.0 - 1.0) above which a column is dropped.
        dimension_null_fill_value: Replacement text for missing categorical dimensions (default 'Unknown').
        measure_null_fill_strategy: Imputation strategy for measures ('median', 'mean', or 'zero').
    """

    deduplicate: bool = True
    coerce_types: bool = True
    normalize_categories: bool = True
    handle_nulls: bool = True
    impute_measures: bool = True  # Stage 4b: set False explicitly to report-only (opt-in to skip imputation)
    null_drop_threshold: float = 0.95
    dimension_null_fill_value: str = "Unknown"
    measure_null_fill_strategy: str = "median"

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "deduplicate": self.deduplicate,
            "coerce_types": self.coerce_types,
            "normalize_categories": self.normalize_categories,
            "handle_nulls": self.handle_nulls,
            "impute_measures": self.impute_measures,
            "null_drop_threshold": float(self.null_drop_threshold),
            "dimension_null_fill_value": self.dimension_null_fill_value,
            "measure_null_fill_strategy": self.measure_null_fill_strategy,
        }


@dataclass
class CleaningReport:
    """Comprehensive change log generated during a cleaning pass.

    Attributes:
        dataset_id: Identifier of the dataset being cleaned.
        initial_rows: Row count before cleaning.
        final_rows: Row count after cleaning.
        initial_columns: Column count before cleaning.
        final_columns: Column count after cleaning.
        changes: Ordered list of specific transformations applied.
        generated_at: ISO timestamp of report creation.
    """

    dataset_id: str
    initial_rows: int
    final_rows: int
    initial_columns: int
    final_columns: int
    changes: List[CleaningChange] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    @property
    def total_changes(self) -> int:
        """Total number of individual values, rows, or cells modified."""
        return sum(c.count for c in self.changes)

    @property
    def changes_by_rule(self) -> Dict[str, int]:
        """Summary of modification counts grouped by rule name."""
        summary: Dict[str, int] = {}
        for c in self.changes:
            summary[c.rule] = summary.get(c.rule, 0) + c.count
        return summary

    @property
    def changes_by_column(self) -> Dict[str, int]:
        """Summary of modification counts grouped by column name."""
        summary: Dict[str, int] = {}
        for c in self.changes:
            target = c.column or "_dataset_"
            summary[target] = summary.get(target, 0) + c.count
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert cleaning report to JSON-serializable dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "initial_rows": self.initial_rows,
            "final_rows": self.final_rows,
            "initial_columns": self.initial_columns,
            "final_columns": self.final_columns,
            "total_changes": self.total_changes,
            "changes_by_rule": self.changes_by_rule,
            "changes_by_column": self.changes_by_column,
            "changes": [c.to_dict() for c in self.changes],
            "generated_at": sanitize_json_value(self.generated_at),
        }


@dataclass
class CleaningResult:
    """Encapsulates the output of a data cleaning pass."""

    dataset: CanonicalDataset
    report: CleaningReport

    def to_dict(self) -> Dict[str, Any]:
        """Convert cleaning result to JSON-serializable dictionary."""
        return {
            "dataset": self.dataset.to_dict(),
            "report": self.report.to_dict(),
        }


# =========================================================================
# Part 4 — Data Studio: Cleaning Intelligence & Cleaning Plan Models
# =========================================================================


def get_default_supported_variants(operation: str) -> List[Dict[str, str]]:
    """Determine the deterministic set of allowed user-selectable operation variants."""
    if operation in ["IMPUTE_MEDIAN", "IMPUTE_MEAN"]:
        return [
            {"operation": "IMPUTE_MEDIAN", "label": "Median", "description": "Fill missing values with dynamically computed median"},
            {"operation": "IMPUTE_MEAN", "label": "Mean", "description": "Fill missing values with dynamically computed mean"},
            {"operation": "IMPUTE_SPECIFIC_VALUE", "label": "Specific Value", "description": "Fill missing values with a user-specified numeric constant"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Do not fill missing values"},
        ]
    elif operation == "FILL_MODE":
        return [
            {"operation": "FILL_MODE", "label": "Mode", "description": "Fill missing values with dominant mode"},
            {"operation": "FILL_UNKNOWN", "label": "Unknown", "description": "Fill missing values with 'Unknown' placeholder"},
            {"operation": "FILL_SPECIFIC_VALUE", "label": "Specific Value", "description": "Fill missing values with a user-specified text constant"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Do not fill missing values"},
        ]
    elif operation == "FILL_UNKNOWN":
        return [
            {"operation": "FILL_UNKNOWN", "label": "Unknown", "description": "Fill missing values with 'Unknown' placeholder"},
            {"operation": "FILL_MODE", "label": "Mode", "description": "Fill missing values with dominant mode"},
            {"operation": "FILL_SPECIFIC_VALUE", "label": "Specific Value", "description": "Fill missing values with a user-specified text constant"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Do not fill missing values"},
        ]
    elif operation == "REMOVE_DUPLICATES":
        return [
            {"operation": "REMOVE_DUPLICATES", "label": "Remove Duplicates", "description": "Drop exact duplicate rows"},
            {"operation": "LEAVE_UNCHANGED", "label": "Keep Duplicates", "description": "Keep all duplicate rows"},
        ]
    elif operation == "NORMALIZE_EMPTY_STRINGS":
        return [
            {"operation": "NORMALIZE_EMPTY_STRINGS", "label": "Normalize to Null", "description": "Convert empty/whitespace strings to null"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Keep whitespace strings as-is"},
        ]
    elif operation == "CONVERT_NUMERIC":
        return [
            {"operation": "CONVERT_NUMERIC", "label": "Convert to Numeric", "description": "Coerce values to numeric"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Preserve original text data type"},
        ]
    elif operation == "CONVERT_DATETIME":
        return [
            {"operation": "CONVERT_DATETIME", "label": "Convert to Datetime", "description": "Parse timestamps into datetime"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Preserve original text data type"},
        ]
    elif operation == "NORMALIZE_BOOLEAN":
        return [
            {"operation": "NORMALIZE_BOOLEAN", "label": "Normalize Boolean", "description": "Standardize yes/no/true/false to bool"},
            {"operation": "LEAVE_UNCHANGED", "label": "Leave Unchanged", "description": "Preserve original text representations"},
        ]
    return []


@dataclass
class CleaningRecommendation:
    """Structured deterministic cleaning proposal for a dataset column or whole dataset.

    Attributes:
        recommendation_id: Unique deterministic identifier for the recommendation.
        column_name: Name of the target column, or None for whole-dataset operations (e.g. deduplication).
        operation: Standardized recommended operation name (e.g. 'REMOVE_DUPLICATES', 'IMPUTE_MEDIAN', 'FILL_MODE').
        user_selected_operation: User-chosen operation variant (e.g. 'IMPUTE_MEAN', 'FILL_UNKNOWN', 'LEAVE_UNCHANGED').
        supported_variants: List of valid alternate operation choices available to the user.
        category: Broad category ('duplicates', 'missing_values', 'empty_values', 'type_conversion',
                  'datetime_conversion', 'boolean_normalization', 'invalid_values', 'outliers').
        evidence: Deterministic evidence statements backing the recommendation.
        affected_rows: Number of rows affected by this operation.
        affected_percentage: Percentage of total rows affected (0.0 to 100.0).
        confidence: Deterministic confidence score from 0.0 to 1.0.
        confidence_level: Categorical confidence ('HIGH', 'MEDIUM', 'LOW').
        risk_level: Risk classification ('LOW', 'MEDIUM', 'HIGH').
        default_selected: Whether this operation is preselected by default (safe + high confidence).
        user_selected: Current selection state for user approval/modification.
        rationale: Clear human-readable explanation of why this cleaning step is recommended.
        expected_effect: Clear human-readable description of what will happen if executed.
        requires_review: Whether this operation requires explicit user inspection before execution.
        status: Recommendation status ('RECOMMENDED', 'REVIEW_REQUIRED', 'NOT_RECOMMENDED').
        params: Contextual parameters (e.g., fill_value, strategy, target_dtype).
    """

    recommendation_id: str
    column_name: Optional[str]
    operation: str
    category: str
    evidence: List[str]
    affected_rows: int
    affected_percentage: float
    confidence: float
    confidence_level: str
    risk_level: str
    default_selected: bool
    user_selected: bool
    rationale: str
    expected_effect: str
    requires_review: bool
    status: str
    user_selected_operation: Optional[str] = None
    supported_variants: List[Dict[str, str]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.user_selected_operation is None:
            self.user_selected_operation = self.operation
        if not self.supported_variants:
            self.supported_variants = get_default_supported_variants(self.operation)

    def to_dict(self) -> Dict[str, Any]:
        """Convert cleaning recommendation to a JSON-serializable dictionary."""
        return {
            "recommendation_id": self.recommendation_id,
            "column_name": self.column_name,
            "operation": self.operation,
            "user_selected_operation": self.user_selected_operation or self.operation,
            "supported_variants": self.supported_variants,
            "category": self.category,
            "evidence": self.evidence,
            "affected_rows": int(self.affected_rows),
            "affected_percentage": round(float(self.affected_percentage), 2),
            "confidence": round(float(self.confidence), 2),
            "confidence_level": self.confidence_level,
            "risk_level": self.risk_level,
            "default_selected": bool(self.default_selected),
            "user_selected": bool(self.user_selected),
            "rationale": self.rationale,
            "expected_effect": self.expected_effect,
            "requires_review": bool(self.requires_review),
            "status": self.status,
            "params": sanitize_json_value(self.params),
        }


@dataclass
class CleaningPlan:
    """Ordered collection of deterministic cleaning recommendations for user review.

    Attributes:
        dataset_id: Identifier of the dataset.
        total_recommendations: Total count of proposed recommendations.
        recommended_count: Count of high-confidence recommended operations.
        review_required_count: Count of operations flagged for user review.
        safe_count: Count of low-risk safe operations.
        estimated_rows_affected: Estimated distinct rows affected across all recommendations.
        recommendations: Ordered list of cleaning recommendations.
        generated_at: ISO timestamp of plan creation.
    """

    dataset_id: str
    total_recommendations: int
    recommended_count: int
    review_required_count: int
    safe_count: int
    estimated_rows_affected: int
    recommendations: List[CleaningRecommendation] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert cleaning plan to a JSON-serializable dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "total_recommendations": int(self.total_recommendations),
            "recommended_count": int(self.recommended_count),
            "review_required_count": int(self.review_required_count),
            "safe_count": int(self.safe_count),
            "estimated_rows_affected": int(self.estimated_rows_affected),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "generated_at": sanitize_json_value(self.generated_at),
        }


# =========================================================================
# Part 5 — Data Studio: Cleaning Preview & Batch Execution Models
# =========================================================================


@dataclass
class SampleCellChange:
    """Sample record of a single cell value modified during cleaning preview/execution."""

    row_index: int
    column_name: str
    before_value: Any
    after_value: Any
    operation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_index": int(self.row_index),
            "column_name": self.column_name,
            "before_value": sanitize_json_value(self.before_value),
            "after_value": sanitize_json_value(self.after_value),
            "operation": self.operation,
        }


@dataclass
class OperationExecutionResult:
    """Detailed audit of a single executed or skipped cleaning recommendation."""

    recommendation_id: str
    operation: str
    column_name: Optional[str]
    status: str  # 'APPLIED', 'SKIPPED', 'WARNING', 'FAILED'
    rows_affected: int
    cells_affected: int
    method_used: str
    before_statistic: str
    after_statistic: str
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "operation": self.operation,
            "column_name": self.column_name,
            "status": self.status,
            "rows_affected": int(self.rows_affected),
            "cells_affected": int(self.cells_affected),
            "method_used": self.method_used,
            "before_statistic": self.before_statistic,
            "after_statistic": self.after_statistic,
            "details": sanitize_json_value(self.details),
            "warnings": self.warnings,
        }


@dataclass
class CleaningValidationCheck:
    """A deterministic invariant check performed on post-cleaning data."""

    check_name: str
    status: str  # 'PASSED', 'FAILED', 'WARNING'
    message: str
    column_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "message": self.message,
            "column_name": self.column_name,
            "details": sanitize_json_value(self.details),
        }


@dataclass
class CleaningValidationResult:
    """Comprehensive validation outcomes across all post-cleaning invariant checks."""

    overall_status: str  # 'PASSED', 'WARNING', 'FAILED'
    total_checks: int
    passed_checks: int
    failed_checks: int
    warning_checks: int
    checks: List[CleaningValidationCheck] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "total_checks": int(self.total_checks),
            "passed_checks": int(self.passed_checks),
            "failed_checks": int(self.failed_checks),
            "warning_checks": int(self.warning_checks),
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class CleaningPreviewResult:
    """Non-mutating preview of the selected cleaning operations."""

    dataset_id: str
    original_row_count: int
    preview_row_count: int
    row_count_change: int
    original_column_count: int
    preview_column_count: int
    operations_requested: int
    operations_applicable: int
    operations_skipped: int
    total_cells_affected: int
    operations: List[OperationExecutionResult] = field(default_factory=list)
    sample_changes: List[SampleCellChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "original_row_count": int(self.original_row_count),
            "preview_row_count": int(self.preview_row_count),
            "row_count_change": int(self.row_count_change),
            "original_column_count": int(self.original_column_count),
            "preview_column_count": int(self.preview_column_count),
            "operations_requested": int(self.operations_requested),
            "operations_applicable": int(self.operations_applicable),
            "operations_skipped": int(self.operations_skipped),
            "total_cells_affected": int(self.total_cells_affected),
            "operations": [op.to_dict() for op in self.operations],
            "sample_changes": [s.to_dict() for s in self.sample_changes],
            "warnings": self.warnings,
            "generated_at": sanitize_json_value(self.generated_at),
        }


@dataclass
class CleaningExecutionResult:
    """Audit-grade summary of applied batch cleaning transformations and validation."""

    dataset_id: str
    original_row_count: int
    cleaned_row_count: int
    row_count_change: int
    original_column_count: int
    cleaned_column_count: int
    operations_requested: int
    operations_applied: int
    operations_skipped: int
    operations_failed: int
    total_rows_affected: int
    total_cells_affected: int
    operations: List[OperationExecutionResult] = field(default_factory=list)
    validation: Optional[CleaningValidationResult] = None
    before_summary: Dict[str, Any] = field(default_factory=dict)
    after_summary: Dict[str, Any] = field(default_factory=dict)
    sample_changes: List[SampleCellChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    executed_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "original_row_count": int(self.original_row_count),
            "cleaned_row_count": int(self.cleaned_row_count),
            "row_count_change": int(self.row_count_change),
            "original_column_count": int(self.original_column_count),
            "cleaned_column_count": int(self.cleaned_column_count),
            "operations_requested": int(self.operations_requested),
            "operations_applied": int(self.operations_applied),
            "operations_skipped": int(self.operations_skipped),
            "operations_failed": int(self.operations_failed),
            "total_rows_affected": int(self.total_rows_affected),
            "total_cells_affected": int(self.total_cells_affected),
            "operations": [op.to_dict() for op in self.operations],
            "validation": self.validation.to_dict() if self.validation else None,
            "before_summary": sanitize_json_value(self.before_summary),
            "after_summary": sanitize_json_value(self.after_summary),
            "sample_changes": [s.to_dict() for s in self.sample_changes],
            "warnings": self.warnings,
            "executed_at": sanitize_json_value(self.executed_at),
        }


