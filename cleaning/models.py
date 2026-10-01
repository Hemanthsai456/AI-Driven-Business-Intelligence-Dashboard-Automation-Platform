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
