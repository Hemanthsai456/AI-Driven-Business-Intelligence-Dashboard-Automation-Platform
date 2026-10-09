"""Deterministic Structural Cleaning & Semantic Role Management Engine (Data Studio Part 6.4).

Provides non-mutating preview and deterministic execution for:
1. User-controlled Column Dropping (single or multiple)
2. User-controlled Row Removal with structured condition filtering (equals, not equals, numeric <, >, <=, >=, missing, contains)
3. Multi-condition Row Filtering with AND/OR logic
4. Duplicate Row Removal with configurable keep strategy ('first', 'last')
5. Data-Quality-Based Structural Recommendations (high missingness, constant columns, likely identifiers, duplicate rows)
6. User-Controlled Semantic Role Overrides (IDENTIFIER, DIMENSION, MEASURE, DATETIME, UNKNOWN) with strict physical dtype separation
"""

from dataclasses import dataclass, field
import datetime
from enum import Enum
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DataProfile,
    DatasetMetadata,
    sanitize_json_value,
)
from intelligence.profiler import DataProfiler
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
    SemanticAnalyzer,
)


class StructuralExecutionError(Exception):
    """Raised when structural cleaning operation fails validation or invariants."""
    pass


# Supported row filter operators
SUPPORTED_FILTER_OPERATORS = {
    "equals",
    "eq",
    "==",
    "=",
    "not equals",
    "not_equals",
    "neq",
    "!=",
    "greater than",
    "greater_than",
    "gt",
    ">",
    "less than",
    "less_than",
    "lt",
    "<",
    "greater than or equal",
    "greater_than_or_equal",
    "gte",
    ">=",
    "less than or equal",
    "less_than_or_equal",
    "lte",
    "<=",
    "is missing",
    "is_missing",
    "is_null",
    "isna",
    "is not missing",
    "is_not_missing",
    "not_null",
    "notna",
    "contains",
}

VALID_SEMANTIC_ROLES = {"IDENTIFIER", "DIMENSION", "MEASURE", "DATETIME", "UNKNOWN"}


@dataclass
class FilterCondition:
    """Structured, non-code condition for row removal."""

    column: str
    operator: str
    value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "operator": self.operator,
            "value": self.value,
        }


@dataclass
class StructuralQualityRecommendation:
    """Deterministic structural recommendation based on profiling and data quality observations."""

    recommendation_id: str
    column_name: Optional[str]
    issue_type: str  # "HIGH_MISSINGNESS" | "CONSTANT_COLUMN" | "LIKELY_IDENTIFIER" | "DUPLICATE_ROWS"
    reason: str
    evidence: List[str]
    suggested_action: str  # "DROP_COLUMN" | "MARK_IDENTIFIER" | "REMOVE_DUPLICATES" | "KEEP"
    allowed_actions: List[str]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "column_name": self.column_name,
            "issue_type": self.issue_type,
            "reason": self.reason,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action,
            "allowed_actions": self.allowed_actions,
            "metrics": sanitize_json_value(self.metrics),
        }


@dataclass
class ColumnDropPreviewResult:
    """Non-mutating preview of dropping one or more columns."""

    dataset_id: str
    original_column_count: int
    resulting_column_count: int
    columns_to_drop: List[str]
    remaining_columns: List[str]
    original_row_count: int
    resulting_row_count: int
    sample_before_after: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "original_column_count": self.original_column_count,
            "resulting_column_count": self.resulting_column_count,
            "columns_to_drop": self.columns_to_drop,
            "remaining_columns": self.remaining_columns,
            "original_row_count": self.original_row_count,
            "resulting_row_count": self.resulting_row_count,
            "sample_before_after": sanitize_json_value(self.sample_before_after),
        }


@dataclass
class RowFilterPreviewResult:
    """Non-mutating preview of row removal based on single or multi-conditions."""

    dataset_id: str
    conditions: List[Dict[str, Any]]
    logical_operator: str  # "AND" | "OR"
    original_row_count: int
    resulting_row_count: int
    rows_removed: int
    original_column_count: int
    resulting_column_count: int
    sample_matching_rows: List[Dict[str, Any]] = field(default_factory=list)
    sample_remaining_rows: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "conditions": self.conditions,
            "logical_operator": self.logical_operator,
            "original_row_count": self.original_row_count,
            "resulting_row_count": self.resulting_row_count,
            "rows_removed": self.rows_removed,
            "original_column_count": self.original_column_count,
            "resulting_column_count": self.resulting_column_count,
            "sample_matching_rows": sanitize_json_value(self.sample_matching_rows),
            "sample_remaining_rows": sanitize_json_value(self.sample_remaining_rows),
        }


@dataclass
class DuplicateRemovalPreviewResult:
    """Non-mutating preview of exact duplicate row removal."""

    dataset_id: str
    duplicate_rows_count: int
    keep_strategy: str  # "first" | "last"
    original_row_count: int
    resulting_row_count: int
    rows_removed: int
    sample_duplicate_rows: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "duplicate_rows_count": self.duplicate_rows_count,
            "keep_strategy": self.keep_strategy,
            "original_row_count": self.original_row_count,
            "resulting_row_count": self.resulting_row_count,
            "rows_removed": self.rows_removed,
            "sample_duplicate_rows": sanitize_json_value(self.sample_duplicate_rows),
        }


@dataclass
class SemanticRoleOverridePreviewResult:
    """Preview of a user-controlled semantic role override."""

    dataset_id: str
    column_name: str
    system_role: str
    selected_role: str
    physical_dtype: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "column_name": self.column_name,
            "system_role": self.system_role,
            "selected_role": self.selected_role,
            "physical_dtype": self.physical_dtype,
            "evidence": self.evidence,
        }


class StructuralCleaner:
    """Deterministic structural cleaning and semantic role engine."""

    # -------------------------------------------------------------------------
    # PART 1: Column Dropping
    # -------------------------------------------------------------------------

    def preview_drop_columns(
        self,
        canonical: CanonicalDataset,
        columns_to_drop: List[str],
    ) -> ColumnDropPreviewResult:
        """Preview column removal without mutating the underlying canonical dataset."""
        df = canonical.data
        if not columns_to_drop:
            raise StructuralExecutionError("At least one column must be specified for removal.")

        existing_cols = list(df.columns)
        for col in columns_to_drop:
            if col not in existing_cols:
                raise StructuralExecutionError(f"Target column '{col}' does not exist in dataset.")

        remaining = [c for c in existing_cols if c not in columns_to_drop]
        if len(remaining) == 0:
            raise StructuralExecutionError("Cannot drop all columns; at least one column must remain in the dataset.")

        total_rows = len(df)
        sample_changes: List[Dict[str, Any]] = []
        for idx in df.index[:5]:
            orig_row = df.loc[idx].to_dict()
            after_row = {k: orig_row[k] for k in remaining}
            sample_changes.append({
                "row_index": int(idx),
                "before": orig_row,
                "after": after_row,
            })

        return ColumnDropPreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            original_column_count=len(existing_cols),
            resulting_column_count=len(remaining),
            columns_to_drop=list(columns_to_drop),
            remaining_columns=remaining,
            original_row_count=total_rows,
            resulting_row_count=total_rows,
            sample_before_after=sample_changes,
        )

    def apply_drop_columns(
        self,
        canonical: CanonicalDataset,
        columns_to_drop: List[str],
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Drop selected columns on a deep copy of DataFrame, returning new CanonicalDataset."""
        raw_df = canonical.data
        if not columns_to_drop:
            raise StructuralExecutionError("At least one column must be specified for removal.")

        existing_cols = list(raw_df.columns)
        for col in columns_to_drop:
            if col not in existing_cols:
                raise StructuralExecutionError(f"Target column '{col}' does not exist in dataset.")

        remaining = [c for c in existing_cols if c not in columns_to_drop]
        if len(remaining) == 0:
            raise StructuralExecutionError("Cannot drop all columns; at least one column must remain in the dataset.")

        working_df = raw_df.copy(deep=True).drop(columns=columns_to_drop)

        from ingestion.loaders import CSVLoader
        loader = CSVLoader()
        new_schema = loader.extract_column_metadata(working_df)

        cleaned_meta = DatasetMetadata(
            dataset_id=canonical.metadata.dataset_id,
            name=f"{canonical.metadata.name} (Dropped {len(columns_to_drop)} cols)",
            source_type=canonical.metadata.source_type,
            row_count=len(working_df),
            column_count=len(working_df.columns),
            schema=new_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )
        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=working_df)

        audit_info = {
            "action": "DROP_COLUMNS",
            "columns_dropped": list(columns_to_drop),
            "columns_dropped_count": len(columns_to_drop),
            "original_column_count": len(existing_cols),
            "resulting_column_count": len(working_df.columns),
            "original_row_count": len(working_df),
            "resulting_row_count": len(working_df),
        }
        cleaned_canonical.add_audit_entry("DROP_COLUMNS", audit_info)
        return cleaned_canonical, audit_info

    # -------------------------------------------------------------------------
    # PART 2 & 3: Row Removal with Single & Multi-Condition Filtering
    # -------------------------------------------------------------------------

    @staticmethod
    def _evaluate_single_condition(df: pd.DataFrame, cond: FilterCondition) -> pd.Series:
        """Evaluate a single condition against DataFrame, returning a boolean mask of MATCHING rows (to remove)."""
        col = cond.column
        if col not in df.columns:
            raise StructuralExecutionError(f"Target column '{col}' does not exist in dataset.")

        op = cond.operator.lower().strip()
        if op not in SUPPORTED_FILTER_OPERATORS:
            raise StructuralExecutionError(f"Unsupported filter operator '{cond.operator}'.")

        series = df[col]
        val = cond.value

        # Missingness checks
        if op in ["is missing", "is_missing", "is_null", "isna"]:
            return series.isna() | (series.astype(str).str.strip() == "")
        elif op in ["is not missing", "is_not_missing", "not_null", "notna"]:
            return series.notna() & (series.astype(str).str.strip() != "")

        # Value-based comparisons require a comparison value
        if val is None:
            raise StructuralExecutionError(f"Operator '{cond.operator}' requires a comparison value.")

        # String contains check
        if op in ["contains", "contains_substring"]:
            val_str = str(val)
            return series.astype(str).str.contains(val_str, case=False, na=False)

        # Equality checks
        if op in ["equals", "eq", "==", "="]:
            # Numeric equality check if numeric
            if pd.api.types.is_numeric_dtype(series):
                try:
                    num_val = float(val)
                    return pd.to_numeric(series, errors="coerce") == num_val
                except (ValueError, TypeError):
                    return series.astype(str).str.strip() == str(val).strip()
            else:
                return series.astype(str).str.strip() == str(val).strip()

        elif op in ["not equals", "not_equals", "neq", "!="]:
            if pd.api.types.is_numeric_dtype(series):
                try:
                    num_val = float(val)
                    return (pd.to_numeric(series, errors="coerce") != num_val) | series.isna()
                except (ValueError, TypeError):
                    return series.astype(str).str.strip() != str(val).strip()
            else:
                return series.astype(str).str.strip() != str(val).strip()

        # Numeric range checks (<, >, <=, >=)
        try:
            num_val = float(val)
        except (ValueError, TypeError):
            raise StructuralExecutionError(
                f"Operator '{cond.operator}' requires a numeric comparison value, got '{val}'."
            )

        num_series = pd.to_numeric(series, errors="coerce")

        if op in ["greater than", "greater_than", "gt", ">"]:
            return num_series > num_val
        elif op in ["less than", "less_than", "lt", "<"]:
            return num_series < num_val
        elif op in ["greater than or equal", "greater_than_or_equal", "gte", ">="]:
            return num_series >= num_val
        elif op in ["less than or equal", "less_than_or_equal", "lte", "<="]:
            return num_series <= num_val

        raise StructuralExecutionError(f"Unhandled filter operator '{cond.operator}'.")

    def _evaluate_combined_conditions(
        self,
        df: pd.DataFrame,
        conditions: List[FilterCondition],
        logical_operator: str = "AND",
    ) -> pd.Series:
        """Combine multiple condition masks with AND / OR logic, returning mask of rows to REMOVE."""
        if not conditions:
            raise StructuralExecutionError("At least one filter condition must be provided.")

        norm_logic = logical_operator.upper().strip()
        if norm_logic not in ["AND", "OR"]:
            raise StructuralExecutionError(f"Logical operator must be 'AND' or 'OR', got '{logical_operator}'.")

        masks = [self._evaluate_single_condition(df, cond) for cond in conditions]

        if norm_logic == "AND":
            combined = masks[0]
            for m in masks[1:]:
                combined = combined & m
            return combined
        else:  # "OR"
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m
            return combined

    def preview_filter_rows(
        self,
        canonical: CanonicalDataset,
        conditions: List[FilterCondition],
        logical_operator: str = "AND",
    ) -> RowFilterPreviewResult:
        """Preview row removal without mutating the underlying canonical dataset."""
        df = canonical.data
        total_rows = len(df)

        remove_mask = self._evaluate_combined_conditions(df, conditions, logical_operator)
        rows_to_remove = int(remove_mask.sum())
        resulting_rows = total_rows - rows_to_remove

        sample_matching = df[remove_mask].head(5).to_dict(orient="records")
        sample_remaining = df[~remove_mask].head(5).to_dict(orient="records")

        return RowFilterPreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            conditions=[c.to_dict() for c in conditions],
            logical_operator=logical_operator.upper().strip(),
            original_row_count=total_rows,
            resulting_row_count=resulting_rows,
            rows_removed=rows_to_remove,
            original_column_count=len(df.columns),
            resulting_column_count=len(df.columns),
            sample_matching_rows=sample_matching,
            sample_remaining_rows=sample_remaining,
        )

    def apply_filter_rows(
        self,
        canonical: CanonicalDataset,
        conditions: List[FilterCondition],
        logical_operator: str = "AND",
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Remove matching rows on a deep copy of DataFrame, returning new CanonicalDataset."""
        raw_df = canonical.data
        total_rows = len(raw_df)

        remove_mask = self._evaluate_combined_conditions(raw_df, conditions, logical_operator)
        rows_to_remove = int(remove_mask.sum())

        working_df = raw_df.copy(deep=True)[~remove_mask].reset_index(drop=True)

        from ingestion.loaders import CSVLoader
        loader = CSVLoader()
        new_schema = loader.extract_column_metadata(working_df)

        cleaned_meta = DatasetMetadata(
            dataset_id=canonical.metadata.dataset_id,
            name=f"{canonical.metadata.name} (Filtered {rows_to_remove} rows)",
            source_type=canonical.metadata.source_type,
            row_count=len(working_df),
            column_count=len(working_df.columns),
            schema=new_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )
        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=working_df)

        audit_info = {
            "action": "FILTER_ROWS",
            "conditions": [c.to_dict() for c in conditions],
            "logical_operator": logical_operator.upper().strip(),
            "original_row_count": total_rows,
            "resulting_row_count": len(working_df),
            "rows_removed": rows_to_remove,
        }
        cleaned_canonical.add_audit_entry("FILTER_ROWS", audit_info)
        return cleaned_canonical, audit_info

    # -------------------------------------------------------------------------
    # PART 4: Duplicate Row Removal
    # -------------------------------------------------------------------------

    def preview_remove_duplicates(
        self,
        canonical: CanonicalDataset,
        keep_strategy: str = "first",
    ) -> DuplicateRemovalPreviewResult:
        """Preview duplicate row removal without mutating the underlying canonical dataset."""
        df = canonical.data
        strategy = keep_strategy.lower().strip()
        if strategy not in ["first", "last", "none", False]:
            raise StructuralExecutionError(f"Duplicate keep strategy must be 'first' or 'last', got '{keep_strategy}'.")

        keep_val = False if strategy == "none" else strategy
        dup_mask = df.duplicated(keep=keep_val)
        dup_count = int(dup_mask.sum())
        total_rows = len(df)
        resulting_rows = total_rows - dup_count

        sample_dups = df[dup_mask].head(5).to_dict(orient="records")

        return DuplicateRemovalPreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            duplicate_rows_count=dup_count,
            keep_strategy=strategy,
            original_row_count=total_rows,
            resulting_row_count=resulting_rows,
            rows_removed=dup_count,
            sample_duplicate_rows=sample_dups,
        )

    def apply_remove_duplicates(
        self,
        canonical: CanonicalDataset,
        keep_strategy: str = "first",
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Remove duplicate rows on a deep copy of DataFrame, returning new CanonicalDataset."""
        raw_df = canonical.data
        strategy = keep_strategy.lower().strip()
        if strategy not in ["first", "last", "none", False]:
            raise StructuralExecutionError(f"Duplicate keep strategy must be 'first' or 'last', got '{keep_strategy}'.")

        keep_val = False if strategy == "none" else strategy
        total_rows = len(raw_df)
        working_df = raw_df.copy(deep=True).drop_duplicates(keep=keep_val).reset_index(drop=True)
        rows_removed = total_rows - len(working_df)

        from ingestion.loaders import CSVLoader
        loader = CSVLoader()
        new_schema = loader.extract_column_metadata(working_df)

        cleaned_meta = DatasetMetadata(
            dataset_id=canonical.metadata.dataset_id,
            name=f"{canonical.metadata.name} (Deduplicated)",
            source_type=canonical.metadata.source_type,
            row_count=len(working_df),
            column_count=len(working_df.columns),
            schema=new_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )
        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=working_df)

        audit_info = {
            "action": "REMOVE_DUPLICATES",
            "keep_strategy": strategy,
            "original_row_count": total_rows,
            "resulting_row_count": len(working_df),
            "rows_removed": rows_removed,
        }
        cleaned_canonical.add_audit_entry("REMOVE_DUPLICATES", audit_info)
        return cleaned_canonical, audit_info

    # -------------------------------------------------------------------------
    # PART 5: Data Quality Structural Recommendations
    # -------------------------------------------------------------------------

    def get_structural_recommendations(
        self,
        canonical: CanonicalDataset,
        profile: Optional[DataProfile] = None,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
    ) -> List[StructuralQualityRecommendation]:
        """Generate deterministic structural recommendations from quality & profiling signals."""
        if profile is None:
            profiler = DataProfiler()
            profile = profiler.profile(canonical, attach=False)
        if semantic_profile is None:
            analyzer = SemanticAnalyzer()
            semantic_profile = analyzer.analyze(canonical)

        df = canonical.data
        total_rows = len(df)
        recs: List[StructuralQualityRecommendation] = []

        # 1. Dataset-level Duplicate Rows Recommendation
        dup_count = int(df.duplicated().sum()) if total_rows > 0 else 0
        if dup_count > 0:
            dup_pct = round((dup_count / max(total_rows, 1)) * 100, 2)
            recs.append(
                StructuralQualityRecommendation(
                    recommendation_id=f"rec-struct-dup-{canonical.metadata.dataset_id[:8]}",
                    column_name=None,
                    issue_type="DUPLICATE_ROWS",
                    reason=f"{dup_count} exact duplicate rows ({dup_pct}%) detected.",
                    evidence=[
                        f"{dup_count} identical records out of {total_rows} total rows ({dup_pct}%)",
                        "Exact duplicate rows skew aggregation totals and statistical distributions.",
                    ],
                    suggested_action="REMOVE_DUPLICATES",
                    allowed_actions=["KEEP", "REMOVE_DUPLICATES"],
                    metrics={"duplicate_count": dup_count, "duplicate_percentage": dup_pct},
                )
            )

        # 2. Column-level Structural Recommendations
        for col in df.columns:
            col_name = str(col)
            series = df[col]
            stats = profile.column_statistics.get(col_name, {})
            null_cnt = stats.get("null_count", int(series.isna().sum()))
            null_pct = stats.get("null_percentage", round((null_cnt / max(total_rows, 1)) * 100, 2))
            distinct_cnt = stats.get("distinct_count", int(series.dropna().nunique()))
            non_null_cnt = total_rows - null_cnt

            ev = semantic_profile.get_evidence(col_name) if semantic_profile else None
            role = ev.candidate_role.value if ev and hasattr(ev.candidate_role, "value") else (str(ev.candidate_role) if ev else "UNKNOWN")

            # 2A. Very High Missingness (>= 90%)
            if null_pct >= 90.0 and total_rows >= 5:
                recs.append(
                    StructuralQualityRecommendation(
                        recommendation_id=f"rec-struct-miss-{col_name}",
                        column_name=col_name,
                        issue_type="HIGH_MISSINGNESS",
                        reason=f"Column '{col_name}' has {null_pct}% missing values ({null_cnt} of {total_rows} rows).",
                        evidence=[
                            f"Missing rate is {null_pct}% (threshold >= 90%).",
                            f"Only {non_null_cnt} valid entries remaining.",
                            "Columns with near-total missingness contribute minimal analytical signal and can introduce noise.",
                        ],
                        suggested_action="DROP_COLUMN",
                        allowed_actions=["KEEP", "DROP_COLUMN"],
                        metrics={"null_count": null_cnt, "null_percentage": null_pct},
                    )
                )

            # 2B. Constant Column (distinct non-null <= 1)
            elif non_null_cnt > 0 and distinct_cnt <= 1 and total_rows >= 5:
                sample_val = str(series.dropna().iloc[0]) if non_null_cnt > 0 else "None"
                recs.append(
                    StructuralQualityRecommendation(
                        recommendation_id=f"rec-struct-const-{col_name}",
                        column_name=col_name,
                        issue_type="CONSTANT_COLUMN",
                        reason=f"Column '{col_name}' is constant (0 variance, single distinct value: '{sample_val}').",
                        evidence=[
                            f"Distinct non-null count: {distinct_cnt}",
                            f"Single value: '{sample_val}' across all populated records.",
                            "Zero variance columns provide no predictive or analytical utility.",
                        ],
                        suggested_action="DROP_COLUMN",
                        allowed_actions=["KEEP", "DROP_COLUMN"],
                        metrics={"distinct_count": distinct_cnt, "constant_value": sample_val},
                    )
                )

            # 2C. Likely Identifier Column
            is_id_name = any(tok in col_name.lower() for tok in ["id", "uuid", "guid", "key", "pk", "fk"])
            is_high_unique = non_null_cnt > 10 and (distinct_cnt / max(non_null_cnt, 1)) >= 0.95
            is_overridden = getattr(ev, "is_user_overridden", False) if ev else False
            if (is_high_unique or is_id_name) and not is_overridden:
                recs.append(
                    StructuralQualityRecommendation(
                        recommendation_id=f"rec-struct-id-{col_name}",
                        column_name=col_name,
                        issue_type="LIKELY_IDENTIFIER",
                        reason=f"Column '{col_name}' appears to be a record or entity identifier ({distinct_cnt} unique values).",
                        evidence=[
                            f"Distinct non-null ratio: {round((distinct_cnt / max(non_null_cnt, 1)) * 100, 1)}%",
                            f"Current semantic role: {role}",
                            "Identifiers identify individual entities and should not be used as quantitative measures.",
                        ],
                        suggested_action="MARK_IDENTIFIER",
                        allowed_actions=["KEEP", "MARK_IDENTIFIER", "DROP_COLUMN"],
                        metrics={"distinct_count": distinct_cnt, "uniqueness_ratio": round((distinct_cnt / max(non_null_cnt, 1)), 4)},
                    )
                )

        return recs

    # -------------------------------------------------------------------------
    # PART 6 & 7: Semantic Role Overrides
    # -------------------------------------------------------------------------

    def preview_semantic_role_override(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        selected_role: str,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
    ) -> SemanticRoleOverridePreviewResult:
        """Preview a user-controlled semantic role override without mutating state."""
        df = canonical.data
        if column_name not in df.columns:
            raise StructuralExecutionError(f"Target column '{column_name}' does not exist in dataset.")

        norm_role = selected_role.upper().strip()
        if norm_role not in VALID_SEMANTIC_ROLES:
            raise StructuralExecutionError(f"Invalid semantic role '{selected_role}'. Valid roles: {list(VALID_SEMANTIC_ROLES)}")

        if semantic_profile is None:
            analyzer = SemanticAnalyzer()
            semantic_profile = analyzer.analyze(canonical)

        ev = semantic_profile.get_evidence(column_name)
        if ev:
            if hasattr(ev, "system_role") and ev.system_role is not None:
                system_role = ev.system_role.value if hasattr(ev.system_role, "value") else str(ev.system_role)
            else:
                system_role = ev.candidate_role.value if hasattr(ev.candidate_role, "value") else str(ev.candidate_role)
        else:
            system_role = "UNKNOWN"
        dtype_str = str(df[column_name].dtype)

        evidence = [
            f"Physical data type: '{dtype_str}' (strictly preserved)",
            f"Inferred system role: '{system_role}'",
            f"User-selected authoritative role: '{norm_role}'",
        ]

        return SemanticRoleOverridePreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            column_name=column_name,
            system_role=system_role,
            selected_role=norm_role,
            physical_dtype=dtype_str,
            evidence=evidence,
        )

    def apply_semantic_role_override(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        selected_role: str,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
        user_role_overrides_dict: Optional[Dict[str, str]] = None,
    ) -> Tuple[DatasetSemanticProfile, Dict[str, Any]]:
        """Apply user-controlled semantic role override, storing it separately and returning updated profile."""
        df = canonical.data
        if column_name not in df.columns:
            raise StructuralExecutionError(f"Target column '{column_name}' does not exist in dataset.")

        norm_role = selected_role.upper().strip()
        if norm_role not in VALID_SEMANTIC_ROLES:
            raise StructuralExecutionError(f"Invalid semantic role '{selected_role}'. Valid roles: {list(VALID_SEMANTIC_ROLES)}")

        if semantic_profile is None:
            analyzer = SemanticAnalyzer()
            semantic_profile = analyzer.analyze(canonical)

        if user_role_overrides_dict is not None:
            user_role_overrides_dict[column_name] = norm_role

        # Apply override on evidence object
        ev = semantic_profile.get_evidence(column_name)
        if ev is not None:
            if not hasattr(ev, "system_role") or getattr(ev, "system_role") is None:
                ev.system_role = ev.candidate_role
            ev.user_override_role = ColumnRole(norm_role)
            ev.candidate_role = ColumnRole(norm_role)
            ev.is_user_overridden = True
            ev.evidence = list(ev.evidence) + [f"User explicitly designated column as {norm_role}."]

        system_role_val = "UNKNOWN"
        if ev:
            if hasattr(ev, "system_role") and ev.system_role is not None:
                system_role_val = ev.system_role.value if hasattr(ev.system_role, "value") else str(ev.system_role)
            else:
                system_role_val = ev.candidate_role.value if hasattr(ev.candidate_role, "value") else str(ev.candidate_role)

        audit_info = {
            "action": "SEMANTIC_ROLE_OVERRIDE",
            "column_name": column_name,
            "selected_role": norm_role,
            "system_role": system_role_val,
            "physical_dtype": str(df[column_name].dtype),
        }
        canonical.add_audit_entry("SEMANTIC_ROLE_OVERRIDE", audit_info)
        return semantic_profile, audit_info
