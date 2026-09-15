"""Canonical Data Model definitions for the Business Intelligence & Dashboard Automation Platform.

This module provides format-agnostic dataclasses for representing datasets, column metadata,
semantic roles, data profiles, and canonical tabular datasets.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import datetime
import math
import numpy as np
import pandas as pd


def sanitize_json_value(val: Any) -> Any:
    """Recursively convert NumPy/Pandas scalars, dates, enums, and NaNs to standard JSON-safe Python primitives."""
    if val is None or val is pd.NA or val is pd.NaT:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        val_float = float(val)
        return None if math.isnan(val_float) or math.isinf(val_float) else val_float
    if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
        return val.isoformat()
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return {str(k): sanitize_json_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [sanitize_json_value(x) for x in val]
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    return str(val)


class ColumnRole(str, Enum):
    """Semantic role of a dataset column.

    - MEASURE: A field whose values represent quantities that can meaningfully participate
      in numerical aggregation or statistical analysis.
    - DIMENSION: A field used to categorize, group, filter, or segment records.
    - DATETIME: A field representing a date or timestamp that can support temporal analysis.
    - IDENTIFIER: A field primarily used to identify records or entities rather than represent
      an analytical quantity.
    - UNKNOWN: A field whose semantic role cannot yet be reliably determined.
    """

    MEASURE = "MEASURE"
    DIMENSION = "DIMENSION"
    DATETIME = "DATETIME"
    IDENTIFIER = "IDENTIFIER"
    UNKNOWN = "UNKNOWN"


@dataclass
class ColumnMetadata:
    """Metadata describing a single column in a dataset.

    Attributes:
        original_name: The original column header from the raw data source.
        normalized_name: Standardized, clean column name safe for downstream SQL/queries.
        detected_datatype: Data type detected during ingestion (e.g., 'int64', 'float64', 'string', 'datetime64[ns]').
        semantic_role: Inferred or assigned semantic role (default UNKNOWN).
        null_count: Number of missing/null values in this column.
        null_percentage: Percentage of null values (0.0 to 100.0).
        distinct_count: Number of unique non-null values.
        is_unique: Whether all non-null values in the column are unique.
        sample_values: Safe, representative sample of non-null values for inspection.
    """

    original_name: str
    normalized_name: str
    detected_datatype: str
    semantic_role: ColumnRole = ColumnRole.UNKNOWN
    null_count: int = 0
    null_percentage: float = 0.0
    distinct_count: int = 0
    is_unique: bool = False
    sample_values: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert column metadata to a JSON-serializable dictionary."""
        return {
            "original_name": self.original_name,
            "normalized_name": self.normalized_name,
            "detected_datatype": self.detected_datatype,
            "semantic_role": self.semantic_role.value if isinstance(self.semantic_role, Enum) else str(self.semantic_role),
            "null_count": int(self.null_count),
            "null_percentage": float(self.null_percentage),
            "distinct_count": int(self.distinct_count),
            "is_unique": bool(self.is_unique),
            "sample_values": [sanitize_json_value(v) for v in self.sample_values],
        }


@dataclass
class DatasetMetadata:
    """Metadata describing an entire dataset.

    Attributes:
        dataset_id: Unique identifier for the dataset.
        name: Human-readable dataset name.
        source_type: Input source format ('csv', 'xlsx', etc.).
        row_count: Total number of rows in the dataset.
        column_count: Total number of columns in the dataset.
        schema: List of column metadata objects describing dataset schema.
        created_at: Timestamp when dataset metadata was created.
        custom_metadata: Extensible key-value store for format-specific or extra metadata.
    """

    dataset_id: str
    name: str
    source_type: str
    row_count: int
    column_count: int
    schema: List[ColumnMetadata] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def get_column(self, name: str) -> Optional[ColumnMetadata]:
        """Look up column metadata by original or normalized column name."""
        for col in self.schema:
            if col.original_name == name or col.normalized_name == name:
                return col
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataset metadata to a JSON-serializable dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "source_type": self.source_type,
            "row_count": int(self.row_count),
            "column_count": int(self.column_count),
            "schema": [col.to_dict() for col in self.schema],
            "created_at": sanitize_json_value(self.created_at),
            "custom_metadata": sanitize_json_value(self.custom_metadata),
        }


@dataclass
class DataProfile:
    """Container for data profiling results describing statistical and physical properties.

    Attributes:
        profile_id: Unique identifier for this profile run.
        dataset_id: Identifier of the dataset profiled.
        generated_at: Timestamp when profile was generated.
        dataset_summary: Dataset-level statistics (row count, column count, missingness, duplicates).
        column_statistics: Detailed stats per column (min, max, mean, std, quantiles, top values).
        quality_issues: List of flagged data quality observations or anomalies.
        correlation_matrix: Numerical column correlation metrics if available.
    """

    profile_id: str
    dataset_id: str
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    dataset_summary: Dict[str, Any] = field(default_factory=dict)
    column_statistics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    quality_issues: List[Dict[str, Any]] = field(default_factory=list)
    correlation_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert data profile to a JSON-serializable dictionary."""
        return {
            "profile_id": self.profile_id,
            "dataset_id": self.dataset_id,
            "generated_at": sanitize_json_value(self.generated_at),
            "dataset_summary": sanitize_json_value(self.dataset_summary),
            "column_statistics": sanitize_json_value(self.column_statistics),
            "quality_issues": sanitize_json_value(self.quality_issues),
            "correlation_matrix": sanitize_json_value(self.correlation_matrix),
        }



@dataclass
class CanonicalDataset:
    """Canonical representation of a dataset combining metadata, tabular data, and profile.

    Attributes:
        metadata: Dataset-level and column-level metadata.
        data: Tabular representation held as a pandas DataFrame.
        profile: Profiling results container (optional).
        audit_logs: Log of operations/transformations performed on this dataset.
    """

    metadata: DatasetMetadata
    data: pd.DataFrame
    profile: Optional[DataProfile] = None
    audit_logs: List[Dict[str, Any]] = field(default_factory=list)

    def add_audit_entry(self, action: str, details: Dict[str, Any]) -> None:
        """Add an immutable audit record for operational tracking."""
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "action": action,
            "details": details,
        }
        self.audit_logs.append(entry)

    def validate_integrity(self) -> bool:
        """Check basic consistency between metadata and underlying tabular data."""
        df_rows, df_cols = self.data.shape
        return (
            df_rows == self.metadata.row_count
            and df_cols == self.metadata.column_count
            and len(self.metadata.schema) == df_cols
        )

    def to_dict(self) -> Dict[str, Any]:
        """Produce a JSON-safe SUMMARY representation of the canonical dataset.

        Does NOT serialize raw row-level DataFrame contents.
        """
        df_summary = {
            "row_count": int(self.data.shape[0]),
            "column_count": int(self.data.shape[1]),
            "columns": [str(col) for col in self.data.columns],
            "dtypes": {str(col): str(dtype) for col, dtype in self.data.dtypes.items()},
        }
        return {
            "metadata": self.metadata.to_dict(),
            "dataframe_summary": df_summary,
            "profile": self.profile.to_dict() if self.profile is not None else None,
            "audit_logs": sanitize_json_value(self.audit_logs),
            "is_integrity_valid": self.validate_integrity(),
        }

