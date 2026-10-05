"""Deterministic, rule-based dataset quality assessment engine.

Provides read-only, explainable quality assessment for CanonicalDatasets
based on DataProfile, DatasetSemanticProfile, and AnalysisReadiness.

Guarantees:
1. Non-mutating: CanonicalDataset and its underlying DataFrame are never modified.
2. Deterministic: Output is fully reproducible without random or LLM dependencies.
3. Transparent: Quality status is derived from clear, documented rules without arbitrary scores.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd

from ingestion.models import CanonicalDataset, DataProfile, sanitize_json_value
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from intelligence.schema_validator import AnalysisReadiness, ReadinessStatus


class QualityStatus(str, Enum):
    """Overall dataset quality status classification.

    - GOOD: All checks pass, zero duplicates, zero missing values, no data quality warnings.
    - NEEDS_ATTENTION: Dataset is usable but contains missing values, duplicates, or constant columns.
    - CRITICAL: Blocking issues prevent reliable analysis (e.g. all-null columns, infinite values, 0 rows).
    """

    GOOD = "Good"
    NEEDS_ATTENTION = "Needs Attention"
    CRITICAL = "Critical"


@dataclass
class MissingColumnInfo:
    """Missing value statistics for a single affected column."""

    column_name: str
    detected_datatype: str
    semantic_role: str
    null_count: int
    null_percentage: float
    completeness_percentage: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "detected_datatype": self.detected_datatype,
            "semantic_role": self.semantic_role,
            "null_count": int(self.null_count),
            "null_percentage": round(float(self.null_percentage), 2),
            "completeness_percentage": round(float(self.completeness_percentage), 2),
        }


@dataclass
class NumericQualityInfo:
    """Quality observations for a numeric column."""

    column_name: str
    detected_datatype: str
    non_null_count: int
    zero_count: int
    zero_percentage: float
    negative_count: int
    negative_percentage: float
    infinite_count: int
    min: Optional[float]
    max: Optional[float]
    mean: Optional[float]
    median: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "detected_datatype": self.detected_datatype,
            "non_null_count": int(self.non_null_count),
            "zero_count": int(self.zero_count),
            "zero_percentage": round(float(self.zero_percentage), 2),
            "negative_count": int(self.negative_count),
            "negative_percentage": round(float(self.negative_percentage), 2),
            "infinite_count": int(self.infinite_count),
            "min": sanitize_json_value(self.min),
            "max": sanitize_json_value(self.max),
            "mean": sanitize_json_value(self.mean),
            "median": sanitize_json_value(self.median),
        }


@dataclass
class DatetimeQualityInfo:
    """Quality observations for a datetime column."""

    column_name: str
    detected_datatype: str
    non_null_count: int
    null_count: int
    null_percentage: float
    min_datetime: Optional[str]
    max_datetime: Optional[str]
    distinct_dates_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "detected_datatype": self.detected_datatype,
            "non_null_count": int(self.non_null_count),
            "null_count": int(self.null_count),
            "null_percentage": round(float(self.null_percentage), 2),
            "min_datetime": sanitize_json_value(self.min_datetime),
            "max_datetime": sanitize_json_value(self.max_datetime),
            "distinct_dates_count": int(self.distinct_dates_count),
        }


@dataclass
class CardinalityInfo:
    """Cardinality characteristics for candidate identifiers and constants."""

    column_name: str
    detected_datatype: str
    semantic_role: str
    distinct_count: int
    is_unique: bool
    is_constant: bool
    cardinality_ratio: float  # distinct / total_rows

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_name": self.column_name,
            "detected_datatype": self.detected_datatype,
            "semantic_role": self.semantic_role,
            "distinct_count": int(self.distinct_count),
            "is_unique": bool(self.is_unique),
            "is_constant": bool(self.is_constant),
            "cardinality_ratio": round(float(self.cardinality_ratio), 4),
        }


@dataclass
class QualityAssessment:
    """Comprehensive, deterministic quality assessment for a dataset."""

    dataset_id: str
    status: QualityStatus
    status_reason: str
    total_rows: int
    total_columns: int
    duplicate_row_count: int
    duplicate_row_percentage: float
    overall_missing_count: int
    overall_missing_percentage: float
    completeness_percentage: float
    uniqueness_percentage: float
    affected_missing_columns_count: int
    missing_columns: List[MissingColumnInfo] = field(default_factory=list)
    numeric_observations: List[NumericQualityInfo] = field(default_factory=list)
    datetime_observations: List[DatetimeQualityInfo] = field(default_factory=list)
    cardinality_observations: List[CardinalityInfo] = field(default_factory=list)
    quality_issues: List[Dict[str, Any]] = field(default_factory=list)
    readiness_warnings: List[str] = field(default_factory=list)
    readiness_blocking_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "duplicate_row_count": self.duplicate_row_count,
            "duplicate_row_percentage": self.duplicate_row_percentage,
            "overall_missing_count": self.overall_missing_count,
            "overall_missing_percentage": self.overall_missing_percentage,
            "completeness_percentage": self.completeness_percentage,
            "uniqueness_percentage": self.uniqueness_percentage,
            "affected_missing_columns_count": self.affected_missing_columns_count,
            "missing_columns": [c.to_dict() for c in self.missing_columns],
            "numeric_observations": [n.to_dict() for n in self.numeric_observations],
            "datetime_observations": [d.to_dict() for d in self.datetime_observations],
            "cardinality_observations": [c.to_dict() for c in self.cardinality_observations],
            "quality_issues": sanitize_json_value(self.quality_issues),
            "readiness_warnings": self.readiness_warnings,
            "readiness_blocking_issues": self.readiness_blocking_issues,
        }


class QualityAssessor:
    """Read-only deterministic quality evaluation engine."""

    def assess(
        self,
        canonical: CanonicalDataset,
        profile: DataProfile,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
        readiness: Optional[AnalysisReadiness] = None,
    ) -> QualityAssessment:
        """Perform deterministic quality assessment of a dataset."""
        df = canonical.data
        row_cnt = int(len(df))
        col_cnt = int(len(df.columns))

        # 1. Summaries from Profile
        dataset_summary = profile.dataset_summary or {}
        dup_row_cnt = int(dataset_summary.get("duplicate_row_count", 0))
        dup_pct = float(dataset_summary.get("duplicate_row_percentage", 0.0))
        overall_missing_cnt = int(dataset_summary.get("overall_missing_count", 0))
        overall_missing_pct = float(dataset_summary.get("overall_missing_percentage", 0.0))

        completeness_pct = round(100.0 - overall_missing_pct, 2) if overall_missing_pct <= 100 else 0.0
        uniqueness_pct = round(100.0 - dup_pct, 2) if dup_pct <= 100 else 0.0

        # 2. Column-Level Breakdowns
        missing_cols: List[MissingColumnInfo] = []
        numeric_obs: List[NumericQualityInfo] = []
        datetime_obs: List[DatetimeQualityInfo] = []
        cardinality_obs: List[CardinalityInfo] = []

        all_null_cols_count = 0
        infinite_cols_count = 0
        constant_cols_count = 0
        high_missing_cols_count = 0

        for col_name, stats in profile.column_statistics.items():
            dtype = str(stats.get("detected_datatype", ""))
            null_cnt = int(stats.get("null_count", 0))
            null_p = float(stats.get("null_percentage", 0.0))
            non_null_cnt = int(stats.get("non_null_count", row_cnt - null_cnt))
            distinct_cnt = int(stats.get("distinct_count", 0))
            is_uniq = bool(stats.get("is_unique", False))
            is_const = bool(stats.get("is_constant", False))
            is_all_null = bool(stats.get("is_all_null", False)) or (null_cnt == row_cnt and row_cnt > 0)

            # Inferred Role from Semantic Profile
            sem_evidence = semantic_profile.get_evidence(col_name) if semantic_profile else None
            role_val = (
                sem_evidence.candidate_role.value
                if sem_evidence and hasattr(sem_evidence.candidate_role, "value")
                else (str(sem_evidence.candidate_role) if sem_evidence else "UNKNOWN")
            )

            # Missingness
            if null_cnt > 0:
                missing_cols.append(
                    MissingColumnInfo(
                        column_name=col_name,
                        detected_datatype=dtype,
                        semantic_role=role_val,
                        null_count=null_cnt,
                        null_percentage=null_p,
                        completeness_percentage=round(100.0 - null_p, 2),
                    )
                )
                if null_p >= 50.0:
                    high_missing_cols_count += 1

            if is_all_null:
                all_null_cols_count += 1
            if is_const:
                constant_cols_count += 1

            # Cardinality
            card_ratio = float(distinct_cnt / row_cnt) if row_cnt > 0 else 0.0
            cardinality_obs.append(
                CardinalityInfo(
                    column_name=col_name,
                    detected_datatype=dtype,
                    semantic_role=role_val,
                    distinct_count=distinct_cnt,
                    is_unique=is_uniq,
                    is_constant=is_const,
                    cardinality_ratio=card_ratio,
                )
            )

            # Numeric observations
            if "mean" in stats and stats["mean"] is not None:
                z_cnt = int(stats.get("zero_count", 0))
                neg_cnt = int(stats.get("negative_count", 0))
                inf_cnt = int(stats.get("infinite_count", 0))
                if inf_cnt > 0:
                    infinite_cols_count += 1

                numeric_obs.append(
                    NumericQualityInfo(
                        column_name=col_name,
                        detected_datatype=dtype,
                        non_null_count=non_null_cnt,
                        zero_count=z_cnt,
                        zero_percentage=(round((z_cnt / non_null_cnt) * 100.0, 2) if non_null_cnt > 0 else 0.0),
                        negative_count=neg_cnt,
                        negative_percentage=(round((neg_cnt / non_null_cnt) * 100.0, 2) if non_null_cnt > 0 else 0.0),
                        infinite_count=inf_cnt,
                        min=stats.get("min"),
                        max=stats.get("max"),
                        mean=stats.get("mean"),
                        median=stats.get("median"),
                    )
                )

            # Datetime observations
            if "min_datetime" in stats and stats["min_datetime"] is not None:
                datetime_obs.append(
                    DatetimeQualityInfo(
                        column_name=col_name,
                        detected_datatype=dtype,
                        non_null_count=non_null_cnt,
                        null_count=null_cnt,
                        null_percentage=null_p,
                        min_datetime=str(stats.get("min_datetime")),
                        max_datetime=str(stats.get("max_datetime")),
                        distinct_dates_count=int(stats.get("distinct_dates_count", 0)),
                    )
                )

        # Sort missing columns by null_count desc
        missing_cols.sort(key=lambda c: c.null_count, reverse=True)

        # 3. Readiness checks & issues
        readiness_warnings: List[str] = readiness.warnings if readiness else []
        readiness_blocking: List[str] = readiness.blocking_issues if readiness else []
        quality_issues: List[Dict[str, Any]] = profile.quality_issues or []

        # 4. Deterministic Overall Quality Status Decision
        reasons: List[str] = []

        is_critical = (
            (readiness and readiness.status == ReadinessStatus.NOT_READY)
            or row_cnt == 0
            or col_cnt == 0
            or all_null_cols_count > 0
            or infinite_cols_count > 0
            or len(readiness_blocking) > 0
        )

        if is_critical:
            status = QualityStatus.CRITICAL
            if row_cnt == 0:
                reasons.append("Dataset contains 0 rows.")
            if all_null_cols_count > 0:
                reasons.append(f"{all_null_cols_count} column(s) contain 100% missing values.")
            if infinite_cols_count > 0:
                reasons.append(f"Infinite numeric values detected in {infinite_cols_count} column(s).")
            if readiness_blocking:
                reasons.extend(readiness_blocking)
        else:
            has_attention_items = (
                dup_row_cnt > 0
                or overall_missing_cnt > 0
                or high_missing_cols_count > 0
                or constant_cols_count > 0
                or len(readiness_warnings) > 0
                or (readiness and readiness.status == ReadinessStatus.READY_WITH_WARNINGS)
            )

            if has_attention_items:
                status = QualityStatus.NEEDS_ATTENTION
                if dup_row_cnt > 0:
                    reasons.append(f"{dup_row_cnt} duplicate row(s) detected ({dup_pct:.1f}% of dataset).")
                if overall_missing_cnt > 0:
                    reasons.append(
                        f"{overall_missing_cnt} missing value(s) across {len(missing_cols)} column(s) ({overall_missing_pct:.1f}% overall missingness)."
                    )
                if high_missing_cols_count > 0:
                    reasons.append(f"{high_missing_cols_count} column(s) have >= 50% missing values.")
                if constant_cols_count > 0:
                    reasons.append(f"{constant_cols_count} column(s) have only 1 constant non-null value.")
            else:
                status = QualityStatus.GOOD
                reasons.append("All quality checks passed. Zero duplicate rows, zero missing values, and high schema integrity.")

        status_reason = " ".join(reasons)

        return QualityAssessment(
            dataset_id=canonical.metadata.dataset_id,
            status=status,
            status_reason=status_reason,
            total_rows=row_cnt,
            total_columns=col_cnt,
            duplicate_row_count=dup_row_cnt,
            duplicate_row_percentage=dup_pct,
            overall_missing_count=overall_missing_cnt,
            overall_missing_percentage=overall_missing_pct,
            completeness_percentage=completeness_pct,
            uniqueness_percentage=uniqueness_pct,
            affected_missing_columns_count=len(missing_cols),
            missing_columns=missing_cols,
            numeric_observations=numeric_obs,
            datetime_observations=datetime_obs,
            cardinality_observations=cardinality_obs,
            quality_issues=quality_issues,
            readiness_warnings=readiness_warnings,
            readiness_blocking_issues=readiness_blocking,
        )


def assess_quality(
    canonical: CanonicalDataset,
    profile: DataProfile,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
    readiness: Optional[AnalysisReadiness] = None,
) -> QualityAssessment:
    """Convenience function to assess dataset quality deterministically."""
    return QualityAssessor().assess(
        canonical=canonical,
        profile=profile,
        semantic_profile=semantic_profile,
        readiness=readiness,
    )
