"""Deterministic Cleaning Execution and Preview Engine (Data Studio Part 5 & 5.1).

Executes selected cleaning operations on an explicit deep copy of the raw dataset,
guaranteeing that the original CanonicalDataset remains strictly immutable.
Provides non-mutating previews, batch execution, deterministic post-validation,
and user-controlled operation variant selection/overrides.
"""

from copy import deepcopy
import datetime
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from cleaning.models import (
    CleaningExecutionResult,
    CleaningPlan,
    CleaningPreviewResult,
    CleaningRecommendation,
    CleaningValidationCheck,
    CleaningValidationResult,
    OperationExecutionResult,
    SampleCellChange,
    get_default_supported_variants,
)
from cleaning.planner import CleaningPlanner
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DatasetMetadata,
    sanitize_json_value,
)
from intelligence.profiler import DataProfiler


class CleaningExecutionError(Exception):
    """Raised when cleaning execution fails critical invariants."""
    pass


class CleaningExecutor:
    """Executes selected cleaning operations in a deterministic pipeline on copies only."""

    SUPPORTED_TRANSFORM_OPERATIONS: Set[str] = {
        "REMOVE_DUPLICATES",
        "NORMALIZE_EMPTY_STRINGS",
        "IMPUTE_MEDIAN",
        "IMPUTE_MEAN",
        "FILL_MODE",
        "FILL_UNKNOWN",
        "CONVERT_NUMERIC",
        "CONVERT_DATETIME",
        "NORMALIZE_BOOLEAN",
        "LEAVE_UNCHANGED",
    }

    REVIEW_ONLY_OPERATIONS: Set[str] = {
        "REVIEW_OUTLIERS",
        "REVIEW_DATETIME_MISSING",
        "REVIEW_IDENTIFIER_MISSING",
        "REVIEW_CONSTANT_COLUMN",
        "REVIEW_HIGH_MISSINGNESS",
    }

    def __init__(self, planner: Optional[CleaningPlanner] = None) -> None:
        self.planner = planner or CleaningPlanner()
        self.profiler = DataProfiler()

    def _resolve_and_validate_recommendations(
        self,
        canonical: CanonicalDataset,
        selected_ids: List[str],
        plan: Optional[CleaningPlan] = None,
        operation_overrides: Optional[Dict[str, str]] = None,
    ) -> List[CleaningRecommendation]:
        """Resolve recommendation IDs against the canonical dataset's deterministic plan,
        applying and validating any user-selected operation overrides.
        """
        if plan is None:
            plan = self.planner.generate_plan(canonical=canonical)

        plan_map = {r.recommendation_id: r for r in plan.recommendations}
        resolved: List[CleaningRecommendation] = []
        unknown_ids: List[str] = []
        overrides = operation_overrides or {}

        for rec_id in selected_ids:
            if rec_id in plan_map:
                base_rec = plan_map[rec_id]
                if rec_id in overrides and overrides[rec_id]:
                    user_chosen_op = overrides[rec_id]
                    # Validate against supported variants
                    variants = base_rec.supported_variants or get_default_supported_variants(base_rec.operation)
                    valid_ops = {v["operation"] for v in variants}

                    if user_chosen_op not in valid_ops and user_chosen_op != "LEAVE_UNCHANGED":
                        raise CleaningExecutionError(
                            f"Operation variant '{user_chosen_op}' is not supported for recommendation '{rec_id}' ({base_rec.operation}). "
                            f"Allowed variants: {list(valid_ops)}"
                        )

                    # Security check: Review-only items cannot be turned into destructive transforms
                    if base_rec.operation in self.REVIEW_ONLY_OPERATIONS and user_chosen_op not in ["LEAVE_UNCHANGED", base_rec.operation]:
                        raise CleaningExecutionError(
                            f"Review-only recommendation '{rec_id}' cannot be converted to automated transformation '{user_chosen_op}'."
                        )

                    # Clone recommendation with user selected operation
                    customized_rec = CleaningRecommendation(
                        recommendation_id=base_rec.recommendation_id,
                        column_name=base_rec.column_name,
                        operation=user_chosen_op,
                        category=base_rec.category,
                        evidence=list(base_rec.evidence),
                        affected_rows=base_rec.affected_rows,
                        affected_percentage=base_rec.affected_percentage,
                        confidence=base_rec.confidence,
                        confidence_level=base_rec.confidence_level,
                        risk_level=base_rec.risk_level,
                        default_selected=base_rec.default_selected,
                        user_selected=base_rec.user_selected,
                        rationale=base_rec.rationale,
                        expected_effect=base_rec.expected_effect,
                        requires_review=base_rec.requires_review,
                        status=base_rec.status,
                        user_selected_operation=user_chosen_op,
                        supported_variants=list(variants),
                        params=dict(base_rec.params),
                    )
                    resolved.append(customized_rec)
                else:
                    resolved.append(base_rec)
            else:
                unknown_ids.append(rec_id)

        if unknown_ids:
            raise CleaningExecutionError(
                f"Invalid recommendation IDs not found in dataset plan: {unknown_ids}"
            )

        return resolved

    def _order_operations(
        self, recommendations: List[CleaningRecommendation]
    ) -> List[CleaningRecommendation]:
        """Order recommendations deterministically:
        1. Empty string normalization
        2. Type conversions (Numeric, Datetime, Boolean)
        3. Missing value handling (Median, Mean, Mode, Unknown)
        4. Duplicate removal
        5. Review / Diagnostic items / Leave Unchanged (last / skipped)
        """
        phase_map = {
            "NORMALIZE_EMPTY_STRINGS": 1,
            "CONVERT_NUMERIC": 2,
            "CONVERT_DATETIME": 2,
            "NORMALIZE_BOOLEAN": 2,
            "IMPUTE_MEDIAN": 3,
            "IMPUTE_MEAN": 3,
            "FILL_MODE": 3,
            "FILL_UNKNOWN": 3,
            "REMOVE_DUPLICATES": 4,
            "LEAVE_UNCHANGED": 90,
        }

        def sort_key(rec: CleaningRecommendation) -> Tuple[int, str, str]:
            phase = phase_map.get(rec.operation, 99)
            col = rec.column_name or ""
            return (phase, rec.operation, col)

        return sorted(recommendations, key=sort_key)

    def _execute_pipeline(
        self,
        raw_df: pd.DataFrame,
        ordered_recs: List[CleaningRecommendation],
        max_sample_changes: int = 10,
    ) -> Tuple[
        pd.DataFrame,
        List[OperationExecutionResult],
        List[SampleCellChange],
        List[str],
        int,
        int,
    ]:
        """Core execution logic applied on a working copy of DataFrame.
        Returns: (working_df, operation_results, sample_changes, warnings, total_rows_affected, total_cells_affected)
        """
        working_df = raw_df.copy(deep=True)
        operation_results: List[OperationExecutionResult] = []
        sample_changes: List[SampleCellChange] = []
        warnings: List[str] = []
        total_cells_affected = 0
        total_rows_affected_set: Set[int] = set()

        for rec in ordered_recs:
            op = rec.operation
            col = rec.column_name

            # -------------------------------------------------------------
            # Leave Unchanged (User Override)
            # -------------------------------------------------------------
            if op == "LEAVE_UNCHANGED":
                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="SKIPPED",
                        rows_affected=0,
                        cells_affected=0,
                        method_used="Leave unchanged",
                        before_statistic="Unchanged",
                        after_statistic="Unchanged",
                        details={"note": "User explicitly chose to leave unchanged."},
                        warnings=[],
                    )
                )
                continue

            # -------------------------------------------------------------
            # Review-Only / Diagnostic operations
            # -------------------------------------------------------------
            if op in self.REVIEW_ONLY_OPERATIONS:
                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="SKIPPED",
                        rows_affected=0,
                        cells_affected=0,
                        method_used="Diagnostic review only",
                        before_statistic="Review required",
                        after_statistic="Unchanged",
                        details={"note": "Review-only diagnostic item; automated transformation disabled."},
                        warnings=["Operation flagged as review-only; no automated data changes applied."],
                    )
                )
                continue

            # -------------------------------------------------------------
            # Unsupported Operations
            # -------------------------------------------------------------
            if op not in self.SUPPORTED_TRANSFORM_OPERATIONS:
                msg = f"Unsupported cleaning operation '{op}'."
                warnings.append(msg)
                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="FAILED",
                        rows_affected=0,
                        cells_affected=0,
                        method_used="None",
                        before_statistic="N/A",
                        after_statistic="N/A",
                        details={"error": msg},
                        warnings=[msg],
                    )
                )
                continue

            # -------------------------------------------------------------
            # Column Existence Check for column-level ops
            # -------------------------------------------------------------
            if col is not None and col not in working_df.columns:
                msg = f"Target column '{col}' does not exist in working dataset."
                warnings.append(msg)
                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="FAILED",
                        rows_affected=0,
                        cells_affected=0,
                        method_used="None",
                        before_statistic="N/A",
                        after_statistic="N/A",
                        details={"error": msg},
                        warnings=[msg],
                    )
                )
                continue

            # -------------------------------------------------------------
            # 1. REMOVE_DUPLICATES
            # -------------------------------------------------------------
            if op == "REMOVE_DUPLICATES":
                dup_mask = working_df.duplicated()
                dup_count_before = int(dup_mask.sum())
                rows_before = len(working_df)

                if dup_count_before > 0:
                    dup_indices = working_df.index[dup_mask].tolist()
                    working_df = working_df.drop_duplicates().reset_index(drop=True)
                    rows_after = len(working_df)
                    rows_removed = rows_before - rows_after

                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=None,
                            status="APPLIED",
                            rows_affected=rows_removed,
                            cells_affected=rows_removed * len(working_df.columns),
                            method_used="Exact row deduplication",
                            before_statistic=f"Duplicates: {dup_count_before} ({rows_before} total rows)",
                            after_statistic=f"Duplicates: 0 ({rows_after} total rows)",
                            details={"rows_before": rows_before, "rows_after": rows_after, "rows_removed": rows_removed},
                        )
                    )
                    total_cells_affected += rows_removed * len(working_df.columns)
                    total_rows_affected_set.update(dup_indices)
                    # For duplicate removal, we record row indices
                    for idx in dup_indices[:max_sample_changes]:
                        if len(sample_changes) < max_sample_changes:
                            sample_changes.append(
                                SampleCellChange(
                                    row_index=idx,
                                    column_name="_all_columns_",
                                    before_value=f"Duplicate Row (Index {idx})",
                                    after_value="[ROW DROPPED]",
                                    operation=op,
                                )
                            )
                else:
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=None,
                            status="APPLIED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Exact row deduplication",
                            before_statistic="Duplicates: 0",
                            after_statistic="Duplicates: 0",
                            details={"note": "No duplicate rows found at execution time."},
                        )
                    )
                continue

            # -------------------------------------------------------------
            # 2. NORMALIZE_EMPTY_STRINGS
            # -------------------------------------------------------------
            if op == "NORMALIZE_EMPTY_STRINGS" and col is not None:
                series = working_df[col]
                if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                    empty_mask = series.notna() & (series.astype(str).str.strip() == "")
                    empty_count = int(empty_mask.sum())

                    if empty_count > 0:
                        changed_indices = working_df.index[empty_mask].tolist()
                        for idx in changed_indices[:max_sample_changes]:
                            if len(sample_changes) < max_sample_changes:
                                sample_changes.append(
                                    SampleCellChange(
                                        row_index=idx,
                                        column_name=col,
                                        before_value=working_df.loc[idx, col],
                                        after_value=None,
                                        operation=op,
                                    )
                                )

                        working_df.loc[empty_mask, col] = np.nan
                        total_cells_affected += empty_count
                        for idx in changed_indices:
                            total_rows_affected_set.add(idx)

                        operation_results.append(
                            OperationExecutionResult(
                                recommendation_id=rec.recommendation_id,
                                operation=op,
                                column_name=col,
                                status="APPLIED",
                                rows_affected=empty_count,
                                cells_affected=empty_count,
                                method_used="Convert whitespace-only strings to null",
                                before_statistic=f"Empty strings: {empty_count}",
                                after_statistic="Empty strings: 0",
                                details={"empty_string_count": empty_count},
                            )
                        )
                    else:
                        operation_results.append(
                            OperationExecutionResult(
                                recommendation_id=rec.recommendation_id,
                                operation=op,
                                column_name=col,
                                status="APPLIED",
                                rows_affected=0,
                                cells_affected=0,
                                method_used="Convert whitespace-only strings to null",
                                before_statistic="Empty strings: 0",
                                after_statistic="Empty strings: 0",
                                details={"note": "No empty strings detected at execution time."},
                            )
                        )
                else:
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="SKIPPED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Convert whitespace-only strings to null",
                            before_statistic=f"Dtype: {working_df[col].dtype}",
                            after_statistic=f"Dtype: {working_df[col].dtype}",
                            details={"note": "Column is not string/object dtype."},
                        )
                    )
                continue

            # -------------------------------------------------------------
            # 3. CONVERT_NUMERIC
            # -------------------------------------------------------------
            if op == "CONVERT_NUMERIC" and col is not None:
                series = working_df[col]
                non_null_cnt = int(series.dropna().shape[0])
                converted = pd.to_numeric(series, errors="coerce")
                parsed_cnt = int(converted.dropna().shape[0])
                unparseable_cnt = non_null_cnt - parsed_cnt

                # Safety check: if review required and unparseable data exists, do not silently destroy
                if rec.requires_review and unparseable_cnt > 0:
                    warn_msg = (
                        f"Skipped CONVERT_NUMERIC on '{col}': column has {unparseable_cnt} unparseable values "
                        f"and requires review. Coercion was rejected to prevent data loss."
                    )
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="SKIPPED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Safe numeric coercion (pd.to_numeric)",
                            before_statistic=f"Dtype: {series.dtype} ({unparseable_cnt} unparseable)",
                            after_statistic=f"Dtype: {series.dtype}",
                            details={"unparseable_count": unparseable_cnt},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                # Record samples
                changed_mask = series.notna() & (series != converted)
                changed_indices = working_df.index[changed_mask].tolist()
                for idx in changed_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=working_df.loc[idx, col],
                                after_value=converted.loc[idx],
                                operation=op,
                            )
                        )

                working_df[col] = converted
                cells_mod = len(changed_indices)
                total_cells_affected += cells_mod
                for idx in changed_indices:
                    total_rows_affected_set.add(idx)

                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="APPLIED",
                        rows_affected=cells_mod,
                        cells_affected=cells_mod,
                        method_used="Safe numeric coercion (pd.to_numeric)",
                        before_statistic=f"Dtype: {series.dtype}",
                        after_statistic=f"Dtype: {working_df[col].dtype}",
                        details={"target_dtype": str(working_df[col].dtype), "converted_count": parsed_cnt},
                    )
                )
                continue

            # -------------------------------------------------------------
            # 4. CONVERT_DATETIME
            # -------------------------------------------------------------
            if op == "CONVERT_DATETIME" and col is not None:
                series = working_df[col]
                non_null_cnt = int(series.dropna().shape[0])
                try:
                    converted_dt = pd.to_datetime(series, errors="coerce", format="mixed")
                    parsed_cnt = int(converted_dt.dropna().shape[0])
                    unparseable_cnt = non_null_cnt - parsed_cnt

                    if rec.requires_review and unparseable_cnt > 0:
                        warn_msg = (
                            f"Skipped CONVERT_DATETIME on '{col}': column has {unparseable_cnt} unparseable date entries "
                            f"and requires review. Coercion was rejected to prevent data loss."
                        )
                        warnings.append(warn_msg)
                        operation_results.append(
                            OperationExecutionResult(
                                recommendation_id=rec.recommendation_id,
                                operation=op,
                                column_name=col,
                                status="SKIPPED",
                                rows_affected=0,
                                cells_affected=0,
                                method_used="Deterministic datetime coercion",
                                before_statistic=f"Dtype: {series.dtype} ({unparseable_cnt} unparseable)",
                                after_statistic=f"Dtype: {series.dtype}",
                                details={"unparseable_count": unparseable_cnt},
                                warnings=[warn_msg],
                            )
                        )
                        continue

                    # Record samples
                    changed_mask = series.notna()
                    changed_indices = working_df.index[changed_mask].tolist()
                    for idx in changed_indices[:max_sample_changes]:
                        if len(sample_changes) < max_sample_changes:
                            sample_changes.append(
                                SampleCellChange(
                                    row_index=idx,
                                    column_name=col,
                                    before_value=working_df.loc[idx, col],
                                    after_value=converted_dt.loc[idx].isoformat() if pd.notna(converted_dt.loc[idx]) else None,
                                    operation=op,
                                )
                            )

                    working_df[col] = converted_dt
                    cells_mod = len(changed_indices)
                    total_cells_affected += cells_mod
                    for idx in changed_indices:
                        total_rows_affected_set.add(idx)

                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="APPLIED",
                            rows_affected=cells_mod,
                            cells_affected=cells_mod,
                            method_used="Deterministic datetime coercion (pd.to_datetime)",
                            before_statistic=f"Dtype: {series.dtype}",
                            after_statistic=f"Dtype: {working_df[col].dtype}",
                            details={"target_dtype": str(working_df[col].dtype), "parsed_count": parsed_cnt},
                        )
                    )
                except Exception as ex:
                    msg = f"Datetime conversion failed on column '{col}': {str(ex)}"
                    warnings.append(msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="pd.to_datetime",
                            before_statistic=f"Dtype: {series.dtype}",
                            after_statistic=f"Dtype: {series.dtype}",
                            details={"error": str(ex)},
                            warnings=[msg],
                        )
                    )
                continue

            # -------------------------------------------------------------
            # 5. NORMALIZE_BOOLEAN
            # -------------------------------------------------------------
            if op == "NORMALIZE_BOOLEAN" and col is not None:
                series = working_df[col]
                true_set = {"true", "yes", "1", "t", "y"}
                false_set = {"false", "no", "0", "f", "n"}

                def _map_val(val: Any) -> Any:
                    if pd.isna(val):
                        return np.nan
                    s = str(val).strip().lower()
                    if s in true_set:
                        return True
                    if s in false_set:
                        return False
                    return val

                converted_bool = series.apply(_map_val)
                changed_mask = series.notna() & (series != converted_bool)
                changed_indices = working_df.index[changed_mask].tolist()

                for idx in changed_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=working_df.loc[idx, col],
                                after_value=converted_bool.loc[idx],
                                operation=op,
                            )
                        )

                working_df[col] = converted_bool
                cells_mod = len(changed_indices)
                total_cells_affected += cells_mod
                for idx in changed_indices:
                    total_rows_affected_set.add(idx)

                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="APPLIED",
                        rows_affected=cells_mod,
                        cells_affected=cells_mod,
                        method_used="Normalize boolean representations (True/False)",
                        before_statistic=f"Dtype: {series.dtype}",
                        after_statistic=f"Dtype: {working_df[col].dtype}",
                        details={"target_dtype": str(working_df[col].dtype)},
                    )
                )
                continue

            # -------------------------------------------------------------
            # 6. IMPUTE_MEDIAN
            # -------------------------------------------------------------
            if op == "IMPUTE_MEDIAN" and col is not None:
                series = working_df[col]
                null_mask = series.isna()
                null_cnt = int(null_mask.sum())

                if null_cnt == 0:
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="APPLIED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Median imputation",
                            before_statistic="Missing: 0",
                            after_statistic="Missing: 0",
                            details={"note": "No missing values present at execution time."},
                        )
                    )
                    continue

                numeric_non_null = pd.to_numeric(series.dropna(), errors="coerce").dropna()
                if len(numeric_non_null) == 0:
                    warn_msg = f"No valid numeric entries found in '{col}' to compute median."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Median imputation",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                median_val = float(numeric_non_null.median())
                if math.isnan(median_val):
                    warn_msg = f"Computed median for '{col}' is NaN."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Median imputation",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                fill_val = round(median_val, 2) if isinstance(median_val, float) else median_val
                null_indices = working_df.index[null_mask].tolist()

                for idx in null_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=None,
                                after_value=fill_val,
                                operation=op,
                            )
                        )

                working_df[col] = working_df[col].fillna(fill_val)
                total_cells_affected += null_cnt
                for idx in null_indices:
                    total_rows_affected_set.add(idx)

                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="APPLIED",
                        rows_affected=null_cnt,
                        cells_affected=null_cnt,
                        method_used=f"Median imputation ({fill_val})",
                        before_statistic=f"Missing: {null_cnt} ({round((null_cnt/max(len(working_df),1))*100, 1)}%)",
                        after_statistic="Missing: 0 (0.0%)",
                        details={"imputed_value": fill_val, "strategy": "median"},
                    )
                )
                continue

            # -------------------------------------------------------------
            # 6B. IMPUTE_MEAN (User-Selected Variant)
            # -------------------------------------------------------------
            if op == "IMPUTE_MEAN" and col is not None:
                series = working_df[col]
                null_mask = series.isna()
                null_cnt = int(null_mask.sum())

                if null_cnt == 0:
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="APPLIED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Mean imputation",
                            before_statistic="Missing: 0",
                            after_statistic="Missing: 0",
                            details={"note": "No missing values present at execution time."},
                        )
                    )
                    continue

                numeric_non_null = pd.to_numeric(series.dropna(), errors="coerce").dropna()
                if len(numeric_non_null) == 0:
                    warn_msg = f"No valid numeric entries found in '{col}' to compute mean."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Mean imputation",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                mean_val = float(numeric_non_null.mean())
                if math.isnan(mean_val):
                    warn_msg = f"Computed mean for '{col}' is NaN."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Mean imputation",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                fill_val = round(mean_val, 2)
                null_indices = working_df.index[null_mask].tolist()

                for idx in null_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=None,
                                after_value=fill_val,
                                operation=op,
                            )
                        )

                working_df[col] = working_df[col].fillna(fill_val)
                total_cells_affected += null_cnt
                for idx in null_indices:
                    total_rows_affected_set.add(idx)

                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="APPLIED",
                        rows_affected=null_cnt,
                        cells_affected=null_cnt,
                        method_used=f"Mean imputation ({fill_val})",
                        before_statistic=f"Missing: {null_cnt} ({round((null_cnt/max(len(working_df),1))*100, 1)}%)",
                        after_statistic="Missing: 0 (0.0%)",
                        details={"imputed_value": fill_val, "strategy": "mean"},
                    )
                )
                continue

            # -------------------------------------------------------------
            # 7. FILL_MODE
            # -------------------------------------------------------------
            if op == "FILL_MODE" and col is not None:
                series = working_df[col]
                null_mask = series.isna()
                null_cnt = int(null_mask.sum())

                if null_cnt == 0:
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="APPLIED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Mode imputation",
                            before_statistic="Missing: 0",
                            after_statistic="Missing: 0",
                            details={"note": "No missing values present at execution time."},
                        )
                    )
                    continue

                non_nulls = series.dropna()
                if len(non_nulls) == 0:
                    warn_msg = f"Cannot compute mode on '{col}'; column is entirely missing."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Mode imputation",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                mode_series = non_nulls.mode()
                if len(mode_series) == 0:
                    warn_msg = f"Could not determine dominant mode for '{col}'."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Mode imputation",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                mode_val = mode_series.iloc[0]
                null_indices = working_df.index[null_mask].tolist()

                for idx in null_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=None,
                                after_value=mode_val,
                                operation=op,
                            )
                        )

                working_df[col] = working_df[col].fillna(mode_val)
                total_cells_affected += null_cnt
                for idx in null_indices:
                    total_rows_affected_set.add(idx)

                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="APPLIED",
                        rows_affected=null_cnt,
                        cells_affected=null_cnt,
                        method_used=f"Mode fill ('{mode_val}')",
                        before_statistic=f"Missing: {null_cnt} ({round((null_cnt/max(len(working_df),1))*100, 1)}%)",
                        after_statistic="Missing: 0 (0.0%)",
                        details={"imputed_value": str(mode_val), "strategy": "mode"},
                    )
                )
                continue

            # -------------------------------------------------------------
            # 8. FILL_UNKNOWN
            # -------------------------------------------------------------
            if op == "FILL_UNKNOWN" and col is not None:
                series = working_df[col]
                null_mask = series.isna()
                null_cnt = int(null_mask.sum())

                if null_cnt == 0:
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="APPLIED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Constant fill ('Unknown')",
                            before_statistic="Missing: 0",
                            after_statistic="Missing: 0",
                            details={"note": "No missing values present at execution time."},
                        )
                    )
                    continue

                null_indices = working_df.index[null_mask].tolist()
                for idx in null_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=None,
                                after_value="Unknown",
                                operation=op,
                            )
                        )

                working_df[col] = working_df[col].fillna("Unknown")
                total_cells_affected += null_cnt
                for idx in null_indices:
                    total_rows_affected_set.add(idx)

                operation_results.append(
                    OperationExecutionResult(
                        recommendation_id=rec.recommendation_id,
                        operation=op,
                        column_name=col,
                        status="APPLIED",
                        rows_affected=null_cnt,
                        cells_affected=null_cnt,
                        method_used="Constant fill ('Unknown')",
                        before_statistic=f"Missing: {null_cnt} ({round((null_cnt/max(len(working_df),1))*100, 1)}%)",
                        after_statistic="Missing: 0 (0.0%)",
                        details={"imputed_value": "Unknown", "strategy": "constant"},
                    )
                )
                continue

        return (
            working_df,
            operation_results,
            sample_changes,
            warnings,
            len(total_rows_affected_set),
            total_cells_affected,
        )

    def _validate_execution(
        self,
        raw_df: pd.DataFrame,
        cleaned_df: pd.DataFrame,
        ordered_recs: List[CleaningRecommendation],
        operation_results: List[OperationExecutionResult],
    ) -> CleaningValidationResult:
        """Deterministic post-cleaning invariant validations."""
        checks: List[CleaningValidationCheck] = []

        # 1. Row count invariant
        if len(cleaned_df) <= len(raw_df):
            checks.append(
                CleaningValidationCheck(
                    check_name="ROW_COUNT_INVARIANT",
                    status="PASSED",
                    message=f"Cleaned dataset row count ({len(cleaned_df)}) is valid (<= {len(raw_df)} initial rows).",
                    details={"initial_rows": len(raw_df), "cleaned_rows": len(cleaned_df)},
                )
            )
        else:
            checks.append(
                CleaningValidationCheck(
                    check_name="ROW_COUNT_INVARIANT",
                    status="FAILED",
                    message=f"Cleaned dataset row count ({len(cleaned_df)}) unexpectedly increased beyond initial rows ({len(raw_df)}).",
                    details={"initial_rows": len(raw_df), "cleaned_rows": len(cleaned_df)},
                )
            )

        # 2. Column count invariant
        if len(cleaned_df.columns) == len(raw_df.columns):
            checks.append(
                CleaningValidationCheck(
                    check_name="COLUMN_COUNT_INVARIANT",
                    status="PASSED",
                    message=f"Column schema integrity preserved ({len(cleaned_df.columns)} columns).",
                    details={"initial_columns": len(raw_df.columns), "cleaned_columns": len(cleaned_df.columns)},
                )
            )
        else:
            checks.append(
                CleaningValidationCheck(
                    check_name="COLUMN_COUNT_INVARIANT",
                    status="FAILED",
                    message=f"Column count changed from {len(raw_df.columns)} to {len(cleaned_df.columns)}.",
                    details={"initial_columns": len(raw_df.columns), "cleaned_columns": len(cleaned_df.columns)},
                )
            )

        # 3. Duplicate Invariant
        dup_op = next((r for r in ordered_recs if r.operation == "REMOVE_DUPLICATES"), None)
        cleaned_dups = int(cleaned_df.duplicated().sum())
        if dup_op is not None:
            if cleaned_dups == 0:
                checks.append(
                    CleaningValidationCheck(
                        check_name="DUPLICATE_REDUCTION",
                        status="PASSED",
                        message="Exact duplicate rows completely eliminated (0 remaining duplicates).",
                        details={"remaining_duplicates": 0},
                    )
                )
            else:
                checks.append(
                    CleaningValidationCheck(
                        check_name="DUPLICATE_REDUCTION",
                        status="FAILED",
                        message=f"Duplicates still remain after deduplication ({cleaned_dups} duplicate rows).",
                        details={"remaining_duplicates": cleaned_dups},
                    )
                )
        else:
            raw_dups = int(raw_df.duplicated().sum())
            if cleaned_dups <= raw_dups:
                checks.append(
                    CleaningValidationCheck(
                        check_name="DUPLICATE_STABILITY",
                        status="PASSED",
                        message="Duplicate count remained stable without unexpected row generation.",
                        details={"duplicates": cleaned_dups},
                    )
                )

        # 4. Per-operation Invariants
        for rec in ordered_recs:
            op = rec.operation
            col = rec.column_name

            if op in ["IMPUTE_MEDIAN", "IMPUTE_MEAN", "FILL_MODE", "FILL_UNKNOWN"] and col in cleaned_df.columns:
                cleaned_nulls = int(cleaned_df[col].isna().sum())
                raw_nulls = int(raw_df[col].isna().sum())
                if cleaned_nulls == 0:
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"MISSINGNESS_RESOLVED_{col}",
                            status="PASSED",
                            message=f"Missing values in column '{col}' successfully resolved (from {raw_nulls} to 0 via {op}).",
                            column_name=col,
                            details={"initial_missing": raw_nulls, "cleaned_missing": 0, "operation": op},
                        )
                    )
                elif cleaned_nulls < raw_nulls:
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"MISSINGNESS_REDUCED_{col}",
                            status="WARNING",
                            message=f"Missing values in column '{col}' reduced from {raw_nulls} to {cleaned_nulls}.",
                            column_name=col,
                            details={"initial_missing": raw_nulls, "cleaned_missing": cleaned_nulls, "operation": op},
                        )
                    )
                else:
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"MISSINGNESS_CHECK_{col}",
                            status="FAILED",
                            message=f"Missing values in column '{col}' did not decrease ({cleaned_nulls} missing).",
                            column_name=col,
                            details={"initial_missing": raw_nulls, "cleaned_missing": cleaned_nulls, "operation": op},
                        )
                    )

            elif op == "NORMALIZE_EMPTY_STRINGS" and col in cleaned_df.columns:
                series = cleaned_df[col]
                if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                    empty_cnt = int((series.notna() & (series.astype(str).str.strip() == "")).sum())
                    if empty_cnt == 0:
                        checks.append(
                            CleaningValidationCheck(
                                check_name=f"EMPTY_STRING_NORMALIZED_{col}",
                                status="PASSED",
                                message=f"Column '{col}' verified free of empty/whitespace-only strings.",
                                column_name=col,
                                details={"remaining_empty_strings": 0},
                            )
                        )
                    else:
                        checks.append(
                            CleaningValidationCheck(
                                check_name=f"EMPTY_STRING_NORMALIZED_{col}",
                                status="FAILED",
                                message=f"Column '{col}' still contains {empty_cnt} empty strings.",
                                column_name=col,
                                details={"remaining_empty_strings": empty_cnt},
                            )
                        )

            elif op == "CONVERT_NUMERIC" and col in cleaned_df.columns:
                if pd.api.types.is_numeric_dtype(cleaned_df[col]):
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"NUMERIC_DTYPE_VALID_{col}",
                            status="PASSED",
                            message=f"Column '{col}' data type successfully converted to numeric ({cleaned_df[col].dtype}).",
                            column_name=col,
                            details={"dtype": str(cleaned_df[col].dtype)},
                        )
                    )
                elif rec.requires_review:
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"NUMERIC_DTYPE_REVIEW_{col}",
                            status="WARNING",
                            message=f"Column '{col}' retained original data type ({cleaned_df[col].dtype}) as review was required.",
                            column_name=col,
                            details={"dtype": str(cleaned_df[col].dtype)},
                        )
                    )
                else:
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"NUMERIC_DTYPE_VALID_{col}",
                            status="FAILED",
                            message=f"Column '{col}' failed numeric type conversion ({cleaned_df[col].dtype}).",
                            column_name=col,
                            details={"dtype": str(cleaned_df[col].dtype)},
                        )
                    )

            elif op == "CONVERT_DATETIME" and col in cleaned_df.columns:
                if pd.api.types.is_datetime64_any_dtype(cleaned_df[col]):
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"DATETIME_DTYPE_VALID_{col}",
                            status="PASSED",
                            message=f"Column '{col}' successfully converted to datetime64.",
                            column_name=col,
                            details={"dtype": str(cleaned_df[col].dtype)},
                        )
                    )

        # Aggregate status
        total_checks = len(checks)
        passed_cnt = sum(1 for c in checks if c.status == "PASSED")
        failed_cnt = sum(1 for c in checks if c.status == "FAILED")
        warning_cnt = sum(1 for c in checks if c.status == "WARNING")

        if failed_cnt > 0:
            overall = "FAILED"
        elif warning_cnt > 0:
            overall = "WARNING"
        else:
            overall = "PASSED"

        return CleaningValidationResult(
            overall_status=overall,
            total_checks=total_checks,
            passed_checks=passed_cnt,
            failed_checks=failed_cnt,
            warning_checks=warning_cnt,
            checks=checks,
        )

    def preview(
        self,
        canonical: CanonicalDataset,
        selected_recommendation_ids: List[str],
        plan: Optional[CleaningPlan] = None,
        operation_overrides: Optional[Dict[str, str]] = None,
    ) -> CleaningPreviewResult:
        """Pure non-mutating preview of selected cleaning operations with optional user overrides.
        Never mutates canonical.data or session store.
        """
        raw_rows, raw_cols = len(canonical.data), len(canonical.data.columns)

        resolved_recs = self._resolve_and_validate_recommendations(
            canonical=canonical,
            selected_ids=selected_recommendation_ids,
            plan=plan,
            operation_overrides=operation_overrides,
        )
        ordered_recs = self._order_operations(resolved_recs)

        working_df, op_results, samples, warnings, rows_aff, cells_aff = self._execute_pipeline(
            raw_df=canonical.data,
            ordered_recs=ordered_recs,
            max_sample_changes=10,
        )

        # Confirm raw immutability
        assert len(canonical.data) == raw_rows and len(canonical.data.columns) == raw_cols, (
            "Raw CanonicalDataset was mutated during preview!"
        )

        app_cnt = sum(1 for r in op_results if r.status == "APPLIED")
        skip_cnt = sum(1 for r in op_results if r.status in ["SKIPPED", "WARNING"])

        return CleaningPreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            original_row_count=raw_rows,
            preview_row_count=len(working_df),
            row_count_change=len(working_df) - raw_rows,
            original_column_count=raw_cols,
            preview_column_count=len(working_df.columns),
            operations_requested=len(selected_recommendation_ids),
            operations_applicable=app_cnt,
            operations_skipped=skip_cnt,
            total_cells_affected=cells_aff,
            operations=op_results,
            sample_changes=samples,
            warnings=warnings,
        )

    def execute(
        self,
        canonical: CanonicalDataset,
        selected_recommendation_ids: List[str],
        plan: Optional[CleaningPlan] = None,
        operation_overrides: Optional[Dict[str, str]] = None,
    ) -> Tuple[CleaningExecutionResult, CanonicalDataset]:
        """Execute selected cleaning operations on an explicit copy of raw data,
        applying any user-selected operation overrides.
        Returns the structured CleaningExecutionResult and the new cleaned CanonicalDataset.
        The input CanonicalDataset is guaranteed untouched.
        """
        raw_df = canonical.data
        raw_rows, raw_cols = len(raw_df), len(raw_df.columns)
        raw_dups = int(raw_df.duplicated().sum())

        # Build initial summary
        before_summary = {
            "row_count": raw_rows,
            "column_count": raw_cols,
            "duplicate_rows": raw_dups,
            "total_nulls": int(raw_df.isna().sum().sum()),
            "column_nulls": {col: int(raw_df[col].isna().sum()) for col in raw_df.columns},
            "column_dtypes": {col: str(raw_df[col].dtype) for col in raw_df.columns},
        }

        resolved_recs = self._resolve_and_validate_recommendations(
            canonical=canonical,
            selected_ids=selected_recommendation_ids,
            plan=plan,
            operation_overrides=operation_overrides,
        )
        ordered_recs = self._order_operations(resolved_recs)

        cleaned_df, op_results, samples, warnings, rows_aff, cells_aff = self._execute_pipeline(
            raw_df=raw_df,
            ordered_recs=ordered_recs,
            max_sample_changes=10,
        )

        # Confirm raw immutability
        assert len(canonical.data) == raw_rows and len(canonical.data.columns) == raw_cols, (
            "Raw CanonicalDataset was mutated during execution!"
        )

        # Deterministic Post-Validation
        validation = self._validate_execution(
            raw_df=raw_df,
            cleaned_df=cleaned_df,
            ordered_recs=ordered_recs,
            operation_results=op_results,
        )

        # Build after summary
        after_summary = {
            "row_count": len(cleaned_df),
            "column_count": len(cleaned_df.columns),
            "duplicate_rows": int(cleaned_df.duplicated().sum()),
            "total_nulls": int(cleaned_df.isna().sum().sum()),
            "column_nulls": {col: int(cleaned_df[col].isna().sum()) for col in cleaned_df.columns},
            "column_dtypes": {col: str(cleaned_df[col].dtype) for col in cleaned_df.columns},
        }

        # Build new in-memory Cleaned CanonicalDataset
        cleaned_schema: List[ColumnMetadata] = []
        for col in cleaned_df.columns:
            orig_meta = canonical.metadata.get_column(col)
            col_null_cnt = int(cleaned_df[col].isna().sum())
            col_len = len(cleaned_df)
            col_null_pct = round(float((col_null_cnt / col_len) * 100.0), 4) if col_len > 0 else 0.0
            col_distinct = int(cleaned_df[col].nunique(dropna=True))
            sample_vals = [
                sanitize_json_value(v)
                for v in cleaned_df[col].dropna().head(5).tolist()
            ]

            cleaned_schema.append(
                ColumnMetadata(
                    original_name=col,
                    normalized_name=orig_meta.normalized_name if orig_meta else col.lower(),
                    detected_datatype=str(cleaned_df[col].dtype),
                    semantic_role=orig_meta.semantic_role if orig_meta else ColumnRole.UNKNOWN,
                    null_count=col_null_cnt,
                    null_percentage=col_null_pct,
                    distinct_count=col_distinct,
                    is_unique=bool(cleaned_df[col].is_unique) if col_len > 0 else False,
                    sample_values=sample_vals,
                )
            )

        cleaned_metadata = DatasetMetadata(
            dataset_id=f"{canonical.metadata.dataset_id}_cleaned",
            name=f"{canonical.metadata.name} (Cleaned)",
            source_type=canonical.metadata.source_type,
            row_count=len(cleaned_df),
            column_count=len(cleaned_df.columns),
            schema=cleaned_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )

        cleaned_canonical = CanonicalDataset(metadata=cleaned_metadata, data=cleaned_df)
        # Profile cleaned dataset
        cleaned_canonical.profile = self.profiler.profile(cleaned_canonical, attach=True)

        app_cnt = sum(1 for r in op_results if r.status == "APPLIED")
        skip_cnt = sum(1 for r in op_results if r.status in ["SKIPPED", "WARNING"])
        fail_cnt = sum(1 for r in op_results if r.status == "FAILED")

        execution_result = CleaningExecutionResult(
            dataset_id=canonical.metadata.dataset_id,
            original_row_count=raw_rows,
            cleaned_row_count=len(cleaned_df),
            row_count_change=len(cleaned_df) - raw_rows,
            original_column_count=raw_cols,
            cleaned_column_count=len(cleaned_df.columns),
            operations_requested=len(selected_recommendation_ids),
            operations_applied=app_cnt,
            operations_skipped=skip_cnt,
            operations_failed=fail_cnt,
            total_rows_affected=rows_aff,
            total_cells_affected=cells_aff,
            operations=op_results,
            validation=validation,
            before_summary=before_summary,
            after_summary=after_summary,
            sample_changes=samples,
            warnings=warnings,
        )

        return execution_result, cleaned_canonical


def preview_cleaning_plan(
    canonical: CanonicalDataset,
    selected_recommendation_ids: List[str],
    plan: Optional[CleaningPlan] = None,
    operation_overrides: Optional[Dict[str, str]] = None,
) -> CleaningPreviewResult:
    """Convenience helper for non-mutating preview of cleaning operations."""
    executor = CleaningExecutor()
    return executor.preview(
        canonical=canonical,
        selected_recommendation_ids=selected_recommendation_ids,
        plan=plan,
        operation_overrides=operation_overrides,
    )


def execute_cleaning_plan(
    canonical: CanonicalDataset,
    selected_recommendation_ids: List[str],
    plan: Optional[CleaningPlan] = None,
    operation_overrides: Optional[Dict[str, str]] = None,
) -> Tuple[CleaningExecutionResult, CanonicalDataset]:
    """Convenience helper for batch cleaning execution on CanonicalDataset copy."""
    executor = CleaningExecutor()
    return executor.execute(
        canonical=canonical,
        selected_recommendation_ids=selected_recommendation_ids,
        plan=plan,
        operation_overrides=operation_overrides,
    )
