"""Deterministic schema validation and analysis-readiness assessment engine.

This module provides a read-only layer that validates structural consistency
of a CanonicalDataset and produces an explicit AnalysisReadiness result
describing whether the dataset is suitable for downstream analytical execution.

Architecture position:
    CanonicalDataset
          +
    DataProfile          (optional — validated if provided)
          +
    DatasetSemanticProfile  (optional — validated if provided)
          ↓
    SchemaValidator
          ↓
    AnalysisReadiness  →  DuckDB Analytical Engine (future)

This layer is NOT data cleaning.
It detects inconsistencies and reports observations.
It never mutates the DataFrame, column dtypes, values, or row order.
"""

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
import datetime
import pandas as pd
from typing import Any, Dict, List, Optional

from ingestion.models import (
    CanonicalDataset,
    DataProfile,
    sanitize_json_value,
)
from intelligence.semantic_analyzer import DatasetSemanticProfile


# ---------------------------------------------------------------------------
# Status Enum
# ---------------------------------------------------------------------------


class ReadinessStatus(str, Enum):
    """Overall analysis-readiness classification for a CanonicalDataset.

    - READY: All structural checks passed. No observations that would limit
      downstream analytical execution.
    - READY_WITH_WARNINGS: Structurally valid. One or more data-quality
      observations (e.g., high missingness, constant columns) that should be
      reviewed before executing analysis. No structural blocking issues.
    - NOT_READY: One or more blocking structural issues prevent safe downstream
      analytical execution. Downstream systems must not proceed.
    """

    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    NOT_READY = "NOT_READY"


# ---------------------------------------------------------------------------
# ReadinessCheck — individual check result
# ---------------------------------------------------------------------------


@dataclass
class ReadinessCheck:
    """Result of a single deterministic readiness check.

    Attributes:
        check_name: Machine-readable identifier for this check.
        passed: True if the check passed (condition satisfied).
        message: Human-readable explanation of the result.
        is_blocking: True if a failing check produces a blocking issue
            (contributes to NOT_READY). False for informational or
            observation-level checks.
    """

    check_name: str
    passed: bool
    message: str
    is_blocking: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "message": self.message,
            "is_blocking": self.is_blocking,
        }


# ---------------------------------------------------------------------------
# AnalysisReadiness — unified result model
# ---------------------------------------------------------------------------


@dataclass
class AnalysisReadiness:
    """Unified schema validation and analysis-readiness result.

    This is the single structured result produced by SchemaValidator.
    It combines structural validation findings, readiness status, and
    data-quality observations in one place for downstream consumption.

    Attributes:
        dataset_id: Identifier of the validated dataset.
        status: Overall readiness classification (READY / READY_WITH_WARNINGS /
            NOT_READY).
        checks: Ordered list of every check that was evaluated, with its
            individual result. Consumers can inspect this for full detail.
        blocking_issues: Human-readable list of issues that prevent analysis.
            Empty when status is READY or READY_WITH_WARNINGS.
        warnings: Human-readable list of data-quality observations. These
            are informational — they do NOT trigger cleaning. Empty when
            status is READY.
        summary: One-sentence overall summary of the result.
        checked_columns: Column names seen in the DataFrame at validation time.
        checked_row_count: Row count of the DataFrame at validation time.
        checked_column_count: Column count of the DataFrame at validation time.
        generated_at: UTC ISO-8601 timestamp of when validation ran.
    """

    dataset_id: str
    status: ReadinessStatus
    checks: List[ReadinessCheck] = field(default_factory=list)
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""
    checked_columns: List[str] = field(default_factory=list)
    checked_row_count: int = 0
    checked_column_count: int = 0
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dictionary using sanitize_json_value."""
        return {
            "dataset_id": self.dataset_id,
            "status": (
                self.status.value
                if isinstance(self.status, ReadinessStatus)
                else str(self.status)
            ),
            "generated_at": sanitize_json_value(self.generated_at),
            "summary": self.summary,
            "blocking_issues": self.blocking_issues,
            "warnings": self.warnings,
            "checked_columns": self.checked_columns,
            "checked_row_count": self.checked_row_count,
            "checked_column_count": self.checked_column_count,
            "checks": [c.to_dict() for c in self.checks],
        }


# ---------------------------------------------------------------------------
# SchemaValidator
# ---------------------------------------------------------------------------


class SchemaValidator:
    """Read-only, deterministic schema validator and analysis-readiness engine.

    Consumes a CanonicalDataset and optional intelligence artifacts (DataProfile,
    DatasetSemanticProfile) and produces an AnalysisReadiness result.

    This class never modifies the DataFrame, column dtypes, values, or row order.
    The only mutation performed is appending to canonical.audit_logs, which is
    consistent with the audit-trail pattern established in Steps 2, 3, and 4.
    """

    # Null percentage above which a high-missingness warning is issued.
    # Columns at exactly 100% trigger the all-null warning instead.
    HIGH_MISSINGNESS_THRESHOLD: float = 50.0

    def validate(
        self,
        canonical: CanonicalDataset,
        profile: Optional[DataProfile] = None,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
    ) -> AnalysisReadiness:
        """Validate structural consistency and assess analysis readiness.

        Args:
            canonical: The CanonicalDataset to validate.
            profile: Optional DataProfile produced by Step 3. If provided,
                its consistency against the current DataFrame is verified.
            semantic_profile: Optional DatasetSemanticProfile produced by
                Step 4. If provided, its column references are verified.

        Returns:
            AnalysisReadiness containing status, all check results,
            blocking issues, and observations.
        """
        checks: List[ReadinessCheck] = []
        blocking_issues: List[str] = []
        warnings: List[str] = []

        dataset_id = (
            canonical.metadata.dataset_id
            if canonical.metadata is not None
            else "UNKNOWN"
        )

        # ----------------------------------------------------------------
        # BLOCKING CHECK 1 — DataFrame must exist and be a valid DataFrame
        # ----------------------------------------------------------------
        df_valid = isinstance(canonical.data, pd.DataFrame)
        checks.append(
            ReadinessCheck(
                check_name="dataframe_exists",
                passed=df_valid,
                message=(
                    "DataFrame is present and valid."
                    if df_valid
                    else "canonical.data is not a valid pandas DataFrame."
                ),
                is_blocking=True,
            )
        )
        if not df_valid:
            blocking_issues.append("DataFrame is missing or invalid.")
            return self._finalise(
                dataset_id, checks, blocking_issues, warnings,
                checked_columns=[], checked_row_count=0, checked_column_count=0,
                canonical=canonical,
            )

        # From here df is guaranteed to be a valid DataFrame.
        df = canonical.data
        df_col_names: List[str] = list(df.columns)
        df_col_set: set = set(df_col_names)
        row_count: int = len(df)
        col_count: int = len(df_col_names)

        # ----------------------------------------------------------------
        # BLOCKING CHECK 2 — At least one column
        # ----------------------------------------------------------------
        has_columns = col_count >= 1
        checks.append(
            ReadinessCheck(
                check_name="column_count_nonzero",
                passed=has_columns,
                message=(
                    f"Dataset has {col_count} column(s)."
                    if has_columns
                    else "Dataset has no columns."
                ),
                is_blocking=True,
            )
        )
        if not has_columns:
            blocking_issues.append("Dataset contains no columns.")

        # ----------------------------------------------------------------
        # BLOCKING CHECK 3 — Metadata column count matches DataFrame
        # ----------------------------------------------------------------
        meta_col_count = len(canonical.metadata.schema)
        count_consistent = meta_col_count == col_count
        checks.append(
            ReadinessCheck(
                check_name="metadata_column_count_matches",
                passed=count_consistent,
                message=(
                    f"Metadata schema column count ({meta_col_count}) matches "
                    f"DataFrame column count ({col_count})."
                    if count_consistent
                    else (
                        f"Metadata schema column count ({meta_col_count}) does not "
                        f"match DataFrame column count ({col_count})."
                    )
                ),
                is_blocking=True,
            )
        )
        if not count_consistent:
            blocking_issues.append(
                f"Metadata column count ({meta_col_count}) does not match "
                f"DataFrame column count ({col_count})."
            )

        # ----------------------------------------------------------------
        # BLOCKING CHECK 4 — Metadata column names match DataFrame columns
        # ----------------------------------------------------------------
        meta_col_names: set = {col.original_name for col in canonical.metadata.schema}
        names_consistent = meta_col_names == df_col_set
        if not names_consistent:
            extra_in_meta = meta_col_names - df_col_set
            extra_in_df = df_col_set - meta_col_names
            name_msg = (
                f"Column name mismatch — "
                + (f"in metadata but not DataFrame: {sorted(extra_in_meta)!r}; " if extra_in_meta else "")
                + (f"in DataFrame but not metadata: {sorted(extra_in_df)!r}." if extra_in_df else "")
            )
        else:
            name_msg = "All metadata column names match DataFrame column names."
        checks.append(
            ReadinessCheck(
                check_name="metadata_column_names_match",
                passed=names_consistent,
                message=name_msg,
                is_blocking=True,
            )
        )
        if not names_consistent:
            blocking_issues.append(
                "Metadata column names do not match DataFrame column names."
            )

        # ----------------------------------------------------------------
        # BLOCKING CHECK 5 — DataFrame column references must be unique
        # (after ingestion disambiguates duplicates, e.g. name / name.1)
        # ----------------------------------------------------------------
        duplicate_names = [n for n, cnt in Counter(df_col_names).items() if cnt > 1]
        refs_unique = len(duplicate_names) == 0
        checks.append(
            ReadinessCheck(
                check_name="unique_column_references",
                passed=refs_unique,
                message=(
                    "All DataFrame column names are unique references."
                    if refs_unique
                    else f"Duplicate column references detected in DataFrame: {duplicate_names!r}."
                ),
                is_blocking=True,
            )
        )
        if not refs_unique:
            blocking_issues.append(
                f"DataFrame contains duplicate column references: {duplicate_names!r}."
            )

        # ----------------------------------------------------------------
        # PROFILE CONSISTENCY CHECKS (only when a profile is provided)
        # ----------------------------------------------------------------
        if profile is not None:
            checks.extend(
                self._check_profile_consistency(
                    profile, canonical.metadata.dataset_id, df_col_set,
                    row_count, blocking_issues,
                )
            )

        # Informational: profile availability
        checks.append(
            ReadinessCheck(
                check_name="profile_available",
                passed=profile is not None,
                message=(
                    "DataProfile is available."
                    if profile is not None
                    else (
                        "DataProfile is not provided. "
                        "Statistical analysis quality will be reduced for operations that require it."
                    )
                ),
                is_blocking=False,
            )
        )

        # ----------------------------------------------------------------
        # SEMANTIC PROFILE CONSISTENCY CHECKS
        # ----------------------------------------------------------------
        if semantic_profile is not None:
            checks.extend(
                self._check_semantic_profile_consistency(
                    semantic_profile, df_col_set, blocking_issues
                )
            )

        # Informational: semantic profile availability
        checks.append(
            ReadinessCheck(
                check_name="semantic_profile_available",
                passed=semantic_profile is not None,
                message=(
                    "DatasetSemanticProfile is available."
                    if semantic_profile is not None
                    else (
                        "DatasetSemanticProfile is not provided. "
                        "Semantic role evidence will be absent for operations that depend on it."
                    )
                ),
                is_blocking=False,
            )
        )

        # ----------------------------------------------------------------
        # WARNING CHECKS
        # ----------------------------------------------------------------

        # Zero rows
        if row_count == 0:
            checks.append(
                ReadinessCheck(
                    check_name="zero_row_warning",
                    passed=False,
                    message=(
                        "Dataset has zero rows. Structurally valid but contains "
                        "no data for analytical execution."
                    ),
                    is_blocking=False,
                )
            )
            warnings.append(
                "Dataset has zero rows. Structurally valid but not analytically useful."
            )
        else:
            checks.append(
                ReadinessCheck(
                    check_name="zero_row_warning",
                    passed=True,
                    message=f"Dataset has {row_count} row(s).",
                    is_blocking=False,
                )
            )

        # Per-column warnings (prefer profile stats; fall back to ColumnMetadata)
        for col_meta in canonical.metadata.schema:
            col_name = col_meta.original_name

            if profile is not None:
                col_stats = profile.column_statistics.get(col_name, {})
                is_all_null: bool = bool(col_stats.get("is_all_null", False))
                is_constant: bool = bool(col_stats.get("is_constant", False))
                null_pct: float = float(col_stats.get("null_percentage", 0.0))
            else:
                # Fallback: ColumnMetadata fields populated by ingestion loaders.
                # No DataFrame scan performed.
                is_all_null = (
                    canonical.metadata.row_count > 0
                    and col_meta.null_count >= canonical.metadata.row_count
                ) or col_meta.null_percentage >= 100.0
                is_constant = (col_meta.distinct_count == 1) and not is_all_null
                null_pct = float(col_meta.null_percentage)

            if is_all_null:
                checks.append(
                    ReadinessCheck(
                        check_name=f"all_null_column:{col_name}",
                        passed=False,
                        message=f"Column '{col_name}' contains 100% missing values.",
                        is_blocking=False,
                    )
                )
                warnings.append(
                    f"Column '{col_name}' is entirely null (100% missing values)."
                )
            elif null_pct >= self.HIGH_MISSINGNESS_THRESHOLD:
                checks.append(
                    ReadinessCheck(
                        check_name=f"high_missingness:{col_name}",
                        passed=False,
                        message=f"Column '{col_name}' has {null_pct:.1f}% missing values.",
                        is_blocking=False,
                    )
                )
                warnings.append(
                    f"Column '{col_name}' has high missingness ({null_pct:.1f}%). "
                    "This is an observation only — no data has been modified."
                )

            if is_constant:
                checks.append(
                    ReadinessCheck(
                        check_name=f"constant_column:{col_name}",
                        passed=False,
                        message=(
                            f"Column '{col_name}' has only one distinct non-null value (constant)."
                        ),
                        is_blocking=False,
                    )
                )
                warnings.append(
                    f"Column '{col_name}' is constant (only 1 distinct non-null value)."
                )

        return self._finalise(
            dataset_id, checks, blocking_issues, warnings,
            checked_columns=df_col_names,
            checked_row_count=row_count,
            checked_column_count=col_count,
            canonical=canonical,
        )

    # ----------------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------------

    def _check_profile_consistency(
        self,
        profile: DataProfile,
        expected_dataset_id: str,
        df_col_set: set,
        df_row_count: int,
        blocking_issues: List[str],
    ) -> List[ReadinessCheck]:
        """Validate that a DataProfile is consistent with the current DataFrame."""
        new_checks: List[ReadinessCheck] = []

        # dataset_id must match
        id_match = profile.dataset_id == expected_dataset_id
        new_checks.append(
            ReadinessCheck(
                check_name="profile_dataset_id_matches",
                passed=id_match,
                message=(
                    f"DataProfile dataset_id matches ('{expected_dataset_id}')."
                    if id_match
                    else (
                        f"DataProfile dataset_id ('{profile.dataset_id}') does not match "
                        f"canonical dataset_id ('{expected_dataset_id}'). "
                        "Profile may belong to a different dataset."
                    )
                ),
                is_blocking=True,
            )
        )
        if not id_match:
            blocking_issues.append(
                f"Profile dataset_id ('{profile.dataset_id}') does not match "
                f"canonical dataset_id ('{expected_dataset_id}')."
            )

        # Row count must match (if dataset_summary provides it)
        profile_row_count = profile.dataset_summary.get("row_count")
        if profile_row_count is not None:
            row_match = int(profile_row_count) == df_row_count
            new_checks.append(
                ReadinessCheck(
                    check_name="profile_row_count_matches",
                    passed=row_match,
                    message=(
                        f"DataProfile row count ({profile_row_count}) matches "
                        f"DataFrame row count ({df_row_count})."
                        if row_match
                        else (
                            f"DataProfile row count ({profile_row_count}) does not match "
                            f"DataFrame row count ({df_row_count}). "
                            "Profile may be stale."
                        )
                    ),
                    is_blocking=True,
                )
            )
            if not row_match:
                blocking_issues.append(
                    f"Profile row count ({profile_row_count}) does not match "
                    f"DataFrame row count ({df_row_count}). Profile may be stale."
                )

        # Profile column references must exist in DataFrame
        profile_cols = set(profile.column_statistics.keys())
        ghost_cols = profile_cols - df_col_set
        refs_valid = len(ghost_cols) == 0
        new_checks.append(
            ReadinessCheck(
                check_name="profile_column_references_valid",
                passed=refs_valid,
                message=(
                    "All DataProfile column references exist in the DataFrame."
                    if refs_valid
                    else (
                        f"DataProfile references columns not found in DataFrame: "
                        f"{sorted(ghost_cols)!r}."
                    )
                ),
                is_blocking=True,
            )
        )
        if not refs_valid:
            blocking_issues.append(
                f"Profile references non-existent columns: {sorted(ghost_cols)!r}."
            )

        return new_checks

    def _check_semantic_profile_consistency(
        self,
        semantic_profile: DatasetSemanticProfile,
        df_col_set: set,
        blocking_issues: List[str],
    ) -> List[ReadinessCheck]:
        """Validate that a DatasetSemanticProfile references only existing columns."""
        sem_cols = set(semantic_profile.column_evidences.keys())
        ghost_cols = sem_cols - df_col_set
        refs_valid = len(ghost_cols) == 0
        check = ReadinessCheck(
            check_name="semantic_profile_column_references_valid",
            passed=refs_valid,
            message=(
                "All DatasetSemanticProfile column references exist in the DataFrame."
                if refs_valid
                else (
                    f"DatasetSemanticProfile references columns not found in DataFrame: "
                    f"{sorted(ghost_cols)!r}."
                )
            ),
            is_blocking=True,
        )
        if not refs_valid:
            blocking_issues.append(
                f"Semantic profile references non-existent columns: {sorted(ghost_cols)!r}."
            )
        return [check]

    def _finalise(
        self,
        dataset_id: str,
        checks: List[ReadinessCheck],
        blocking_issues: List[str],
        warnings: List[str],
        checked_columns: List[str],
        checked_row_count: int,
        checked_column_count: int,
        canonical: CanonicalDataset,
    ) -> AnalysisReadiness:
        """Determine overall status, build summary, emit audit entry, return result."""

        if blocking_issues:
            status = ReadinessStatus.NOT_READY
        elif warnings:
            status = ReadinessStatus.READY_WITH_WARNINGS
        else:
            status = ReadinessStatus.READY

        issue_count = len(blocking_issues)
        warning_count = len(warnings)

        if status == ReadinessStatus.READY:
            summary = (
                f"Dataset '{dataset_id}' passed all schema checks and is "
                "ready for downstream analytical execution."
            )
        elif status == ReadinessStatus.READY_WITH_WARNINGS:
            summary = (
                f"Dataset '{dataset_id}' is structurally valid with "
                f"{warning_count} observation(s). "
                "Review warnings before analytical execution. "
                "No data has been modified."
            )
        else:
            summary = (
                f"Dataset '{dataset_id}' is NOT ready for analytical execution. "
                f"{issue_count} blocking issue(s) must be resolved."
            )

        readiness = AnalysisReadiness(
            dataset_id=dataset_id,
            status=status,
            checks=checks,
            blocking_issues=blocking_issues,
            warnings=warnings,
            summary=summary,
            checked_columns=checked_columns,
            checked_row_count=checked_row_count,
            checked_column_count=checked_column_count,
        )

        # Audit entry — appends to audit_logs only (never touches canonical.data)
        canonical.add_audit_entry(
            action="READINESS_CHECKED",
            details={
                "dataset_id": dataset_id,
                "status": status.value,
                "blocking_issue_count": issue_count,
                "warning_count": warning_count,
            },
        )

        return readiness


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def assess_readiness(
    canonical: CanonicalDataset,
    profile: Optional[DataProfile] = None,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> AnalysisReadiness:
    """Convenience wrapper: validate schema and assess analysis readiness.

    Args:
        canonical: The CanonicalDataset to validate.
        profile: Optional DataProfile from Step 3. Validated if provided.
        semantic_profile: Optional DatasetSemanticProfile from Step 4.
            Validated if provided.

    Returns:
        AnalysisReadiness with status READY / READY_WITH_WARNINGS / NOT_READY.
    """
    return SchemaValidator().validate(
        canonical=canonical,
        profile=profile,
        semantic_profile=semantic_profile,
    )
