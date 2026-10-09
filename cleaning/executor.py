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
        "TRIM_WHITESPACE",
        "IMPUTE_MEDIAN",
        "IMPUTE_MEAN",
        "IMPUTE_MODE",
        "IMPUTE_UNKNOWN",
        "IMPUTE_SPECIFIC_VALUE",
        "FILL_MODE",
        "FILL_UNKNOWN",
        "FILL_SPECIFIC_VALUE",
        "CONVERT_NUMERIC",
        "CONVERT_FLOAT",
        "CONVERT_INTEGER",
        "CONVERT_DATETIME",
        "NORMALIZE_BOOLEAN",
        "CONVERT_BOOLEAN",
        "CONVERT_STRING",
        "CONVERT_TEXT",
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
        operation_values: Optional[Dict[str, Any]] = None,
        custom_transformations: Optional[List[Dict[str, Any]]] = None,
    ) -> List[CleaningRecommendation]:
        """Resolve recommendation IDs against the canonical dataset's deterministic plan,
        applying and validating any user-selected operation overrides, custom values,
        and explicit user-defined column transformations.
        """
        if plan is None:
            plan = self.planner.generate_plan(canonical=canonical)

        plan_map = {r.recommendation_id: r for r in plan.recommendations}
        resolved: List[CleaningRecommendation] = []
        unknown_ids: List[str] = []
        overrides = operation_overrides or {}
        custom_values = operation_values or {}

        for rec_id in selected_ids:
            if rec_id in plan_map:
                base_rec = plan_map[rec_id]
                user_chosen_op = overrides.get(rec_id, base_rec.operation)

                # Validate against supported variants
                variants = base_rec.supported_variants or get_default_supported_variants(base_rec.operation)
                valid_ops = {v["operation"] for v in variants}

                if user_chosen_op != base_rec.operation and user_chosen_op not in valid_ops and user_chosen_op != "LEAVE_UNCHANGED":
                    raise CleaningExecutionError(
                        f"Operation variant '{user_chosen_op}' is not supported for recommendation '{rec_id}' ({base_rec.operation}). "
                        f"Allowed variants: {list(valid_ops)}"
                    )

                # Security check: Review-only items cannot be turned into destructive transforms
                if base_rec.operation in self.REVIEW_ONLY_OPERATIONS and user_chosen_op not in ["LEAVE_UNCHANGED", base_rec.operation]:
                    raise CleaningExecutionError(
                        f"Review-only recommendation '{rec_id}' cannot be converted to automated transformation '{user_chosen_op}'."
                    )

                # Clone recommendation params
                rec_params = dict(base_rec.params)

                # If converting to integer, guard against silent fractional truncation
                if user_chosen_op == "CONVERT_INTEGER" and base_rec.column_name in canonical.data.columns:
                    col_series = canonical.data[base_rec.column_name]
                    num_series = pd.to_numeric(col_series.dropna(), errors="coerce").dropna()
                    if len(num_series) > 0 and ((num_series % 1) != 0).any():
                        if not rec_params.get("allow_fractional_truncation", False):
                            raise CleaningExecutionError(
                                f"Integer conversion on '{base_rec.column_name}' rejected: "
                                f"column contains fractional numbers. Integer conversion would truncate fractional values."
                            )

                # Validate specific custom values if chosen
                if user_chosen_op == "IMPUTE_SPECIFIC_VALUE":
                    val = custom_values.get(rec_id, rec_params.get("custom_value"))
                    if val is None or str(val).strip() == "":
                        raise CleaningExecutionError(
                            f"A specific numeric value must be provided for recommendation '{rec_id}' on column '{base_rec.column_name}'."
                        )
                    try:
                        numeric_val = float(val)
                        if math.isnan(numeric_val) or math.isinf(numeric_val):
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise CleaningExecutionError(
                            f"Specific value for numeric column '{base_rec.column_name}' must be a valid number, got: '{val}'"
                        )
                    rec_params["custom_value"] = numeric_val

                elif user_chosen_op == "FILL_SPECIFIC_VALUE":
                    val = custom_values.get(rec_id, rec_params.get("custom_value"))
                    if val is None or str(val).strip() == "":
                        raise CleaningExecutionError(
                            f"A specific text value must be provided for recommendation '{rec_id}' on column '{base_rec.column_name}'."
                        )
                    rec_params["custom_value"] = str(val).strip()

                elif rec_id in custom_values:
                    rec_params["custom_value"] = custom_values[rec_id]

                # Clone recommendation with user selected operation and params
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
                    source=base_rec.source or "RECOMMENDATION",
                    user_selected_operation=user_chosen_op,
                    supported_variants=list(variants),
                    params=rec_params,
                )
                resolved.append(customized_rec)
            else:
                unknown_ids.append(rec_id)

        if unknown_ids:
            raise CleaningExecutionError(
                f"Invalid recommendation IDs not found in dataset plan: {unknown_ids}"
            )

        # Process explicit user-defined column transformations (source="USER")
        if custom_transformations:
            for item in custom_transformations:
                col = item.get("column_name")
                op = item.get("operation")
                if not col or col not in canonical.data.columns:
                    raise CleaningExecutionError(f"Target column '{col}' does not exist in dataset.")
                if not op or op not in self.SUPPORTED_TRANSFORM_OPERATIONS:
                    raise CleaningExecutionError(f"Unsupported cleaning operation '{op}' for column '{col}'.")

                # Normalize aliases
                if op == "IMPUTE_MODE":
                    op = "FILL_MODE"
                elif op == "IMPUTE_UNKNOWN":
                    op = "FILL_UNKNOWN"
                elif op == "CONVERT_TEXT":
                    op = "CONVERT_STRING"

                params = dict(item)
                # Fractional check for user-defined integer conversion
                if op == "CONVERT_INTEGER":
                    col_series = canonical.data[col]
                    num_series = pd.to_numeric(col_series.dropna(), errors="coerce").dropna()
                    if len(num_series) > 0 and ((num_series % 1) != 0).any():
                        if not item.get("allow_fractional_truncation", False):
                            raise CleaningExecutionError(
                                f"Integer conversion on '{col}' rejected: "
                                f"column contains fractional numbers. Integer conversion would truncate fractional values."
                            )

                # Validate specific value
                if op in ["IMPUTE_SPECIFIC_VALUE", "FILL_SPECIFIC_VALUE"]:
                    val = item.get("custom_value")
                    if val is None or str(val).strip() == "":
                        raise CleaningExecutionError(f"A specific constant value must be provided for column '{col}'.")
                    col_series = canonical.data[col]
                    if pd.api.types.is_numeric_dtype(col_series):
                        try:
                            numeric_val = float(val)
                            if math.isnan(numeric_val) or math.isinf(numeric_val):
                                raise ValueError()
                            params["custom_value"] = numeric_val
                            op = "IMPUTE_SPECIFIC_VALUE"
                        except (ValueError, TypeError):
                            raise CleaningExecutionError(
                                f"Specific value for numeric column '{col}' must be a valid number, got: '{val}'"
                            )
                    else:
                        val_str = str(val).strip()
                        forbidden = ["DROP ", "DELETE ", "SELECT ", ";", "<script>"]
                        if any(tok.lower() in val_str.lower() for tok in forbidden):
                            raise CleaningExecutionError(f"Specific value for column '{col}' contains invalid code patterns: '{val}'")
                        params["custom_value"] = val_str
                        op = "FILL_SPECIFIC_VALUE"

                user_rec = CleaningRecommendation(
                    recommendation_id=f"user_custom_{col}_{op.lower()}",
                    column_name=col,
                    operation=op,
                    user_selected_operation=op,
                    category="USER_TRANSFORMATION",
                    evidence=[f"Direct user-configured transformation on column '{col}'"],
                    affected_rows=int(canonical.data[col].notna().sum()) if col in canonical.data.columns else len(canonical.data),
                    affected_percentage=100.0,
                    confidence=1.0,
                    confidence_level="HIGH",
                    risk_level="LOW",
                    default_selected=True,
                    user_selected=True,
                    rationale=f"User-requested {op.replace('_', ' ').lower()} on '{col}'",
                    expected_effect=f"Transform column '{col}' using {op}",
                    requires_review=False,
                    status="RECOMMENDED",
                    source="USER",
                    params=params,
                )
                resolved.append(user_rec)

        return resolved

    def _order_operations(
        self, recommendations: List[CleaningRecommendation]
    ) -> List[CleaningRecommendation]:
        """Order recommendations deterministically:
        1. Empty string normalization & string whitespace trimming
        2. Type conversions (Numeric, Integer, Float, Datetime, Boolean, Text/String)
        3. Missing value handling (Median, Mean, Specific Value, Mode, Unknown)
        4. Duplicate removal
        5. Review / Diagnostic items / Leave Unchanged (last / skipped)
        """
        phase_map = {
            "NORMALIZE_EMPTY_STRINGS": 1,
            "TRIM_WHITESPACE": 1,
            "CONVERT_NUMERIC": 2,
            "CONVERT_FLOAT": 2,
            "CONVERT_INTEGER": 2,
            "CONVERT_DATETIME": 2,
            "NORMALIZE_BOOLEAN": 2,
            "CONVERT_BOOLEAN": 2,
            "CONVERT_STRING": 2,
            "CONVERT_TEXT": 2,
            "IMPUTE_MEDIAN": 3,
            "IMPUTE_MEAN": 3,
            "IMPUTE_MODE": 3,
            "IMPUTE_UNKNOWN": 3,
            "IMPUTE_SPECIFIC_VALUE": 3,
            "FILL_MODE": 3,
            "FILL_UNKNOWN": 3,
            "FILL_SPECIFIC_VALUE": 3,
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
                        status="REVIEW_ONLY",
                        rows_affected=0,
                        cells_affected=0,
                        method_used="Selected for review — no automatic transformation applied",
                        before_statistic="Review requested",
                        after_statistic="Data unchanged",
                        details={"note": "Review-only diagnostic item; data remains unchanged."},
                        warnings=[],
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
            # 2B. TRIM_WHITESPACE
            # -------------------------------------------------------------
            if op == "TRIM_WHITESPACE" and col is not None:
                series = working_df[col]
                if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                    trimmed = series.map(lambda x: x.strip() if isinstance(x, str) else x)
                    changed_mask = series.notna() & (series != trimmed)
                    changed_indices = working_df.index[changed_mask].tolist()
                    cells_mod = len(changed_indices)

                    for idx in changed_indices[:max_sample_changes]:
                        if len(sample_changes) < max_sample_changes:
                            sample_changes.append(
                                SampleCellChange(
                                    row_index=idx,
                                    column_name=col,
                                    before_value=working_df.loc[idx, col],
                                    after_value=trimmed.loc[idx],
                                    operation=op,
                                )
                            )

                    working_df[col] = trimmed
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
                            method_used="Trim leading and trailing whitespace",
                            before_statistic=f"Modified: {cells_mod} cells",
                            after_statistic="Whitespace trimmed",
                            details={"trimmed_count": cells_mod},
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
                            method_used="Trim leading and trailing whitespace",
                            before_statistic=f"Dtype: {working_df[col].dtype}",
                            after_statistic=f"Dtype: {working_df[col].dtype}",
                            details={"note": "Column is not string/object dtype."},
                        )
                    )
                continue

            # -------------------------------------------------------------
            # 3. CONVERT_NUMERIC / CONVERT_FLOAT
            # -------------------------------------------------------------
            if op in ["CONVERT_NUMERIC", "CONVERT_FLOAT"] and col is not None:
                series = working_df[col]
                non_null_cnt = int(series.dropna().shape[0])
                converted = pd.to_numeric(series, errors="coerce").astype("float64")
                parsed_cnt = int(converted.dropna().shape[0])
                unparseable_cnt = non_null_cnt - parsed_cnt

                # Safety check: if review required and unparseable data exists, do not silently destroy
                if rec.requires_review and unparseable_cnt > 0:
                    warn_msg = (
                        f"Skipped {op} on '{col}': column has {unparseable_cnt} unparseable values "
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
            # 3B. CONVERT_INTEGER
            # -------------------------------------------------------------
            if op == "CONVERT_INTEGER" and col is not None:
                series = working_df[col]
                num_series = pd.to_numeric(series, errors="coerce")
                fractional_mask = num_series.notna() & ((num_series % 1) != 0)
                fractional_cnt = int(fractional_mask.sum())

                if fractional_cnt > 0 and not rec.params.get("allow_fractional_truncation", False):
                    warn_msg = (
                        f"Skipped CONVERT_INTEGER on '{col}': column contains {fractional_cnt} fractional values "
                        f"(e.g. {num_series[fractional_mask].iloc[0]}). Integer conversion would truncate fractional values."
                    )
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Integer conversion (rejected due to fractional numbers)",
                            before_statistic=f"Dtype: {series.dtype} ({fractional_cnt} fractional values)",
                            after_statistic=f"Dtype: {series.dtype}",
                            details={"fractional_loss_count": fractional_cnt, "error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                valid_nums = num_series.dropna()
                truncated_map = valid_nums.apply(lambda x: int(math.trunc(x)))
                converted_int = pd.Series(pd.NA, index=series.index, dtype="Int64")
                if len(truncated_map) > 0:
                    converted_int.loc[truncated_map.index] = truncated_map.values
                parsed_cnt = int(converted_int.dropna().shape[0])

                changed_mask = series.notna()
                changed_indices = working_df.index[changed_mask].tolist()
                for idx in changed_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=working_df.loc[idx, col],
                                after_value=int(converted_int.loc[idx]) if pd.notna(converted_int.loc[idx]) else None,
                                operation=op,
                            )
                        )

                working_df[col] = converted_int
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
                        method_used="Deterministic integer conversion (Int64)",
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
            # 5. NORMALIZE_BOOLEAN / CONVERT_BOOLEAN
            # -------------------------------------------------------------
            if op in ["NORMALIZE_BOOLEAN", "CONVERT_BOOLEAN"] and col is not None:
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
            # 5B. CONVERT_STRING / CONVERT_TEXT
            # -------------------------------------------------------------
            if op in ["CONVERT_STRING", "CONVERT_TEXT"] and col is not None:
                series = working_df[col]
                converted_str = series.map(lambda x: None if pd.isna(x) else str(x))
                changed_mask = series.notna() & (series != converted_str)
                changed_indices = working_df.index[changed_mask].tolist()
                cells_mod = len(changed_indices)

                for idx in changed_indices[:max_sample_changes]:
                    if len(sample_changes) < max_sample_changes:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=col,
                                before_value=working_df.loc[idx, col],
                                after_value=converted_str.loc[idx],
                                operation=op,
                            )
                        )

                working_df[col] = converted_str
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
                        method_used="Convert column to text/string",
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
            # 6C. IMPUTE_SPECIFIC_VALUE (User-Selected Custom Numeric Value)
            # -------------------------------------------------------------
            if op == "IMPUTE_SPECIFIC_VALUE" and col is not None:
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
                            method_used="Specific numeric value",
                            before_statistic="Missing: 0",
                            after_statistic="Missing: 0",
                            details={"note": "No missing values present at execution time."},
                        )
                    )
                    continue

                custom_val = rec.params.get("custom_value")
                if custom_val is None:
                    custom_val = rec.params.get("fill_value")
                try:
                    fill_val = float(custom_val)
                    if math.isnan(fill_val) or math.isinf(fill_val):
                        raise ValueError()
                except (TypeError, ValueError):
                    warn_msg = f"Invalid specific numeric value '{custom_val}' for column '{col}'."
                    warnings.append(warn_msg)
                    operation_results.append(
                        OperationExecutionResult(
                            recommendation_id=rec.recommendation_id,
                            operation=op,
                            column_name=col,
                            status="FAILED",
                            rows_affected=0,
                            cells_affected=0,
                            method_used="Specific numeric value",
                            before_statistic=f"Missing: {null_cnt}",
                            after_statistic=f"Missing: {null_cnt}",
                            details={"error": warn_msg},
                            warnings=[warn_msg],
                        )
                    )
                    continue

                # Preserve int if exact whole number
                if fill_val.is_integer():
                    fill_val = int(fill_val)

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
                        method_used=f"Specific value ({fill_val})",
                        before_statistic=f"Missing: {null_cnt} ({round((null_cnt/max(len(working_df),1))*100, 1)}%)",
                        after_statistic="Missing: 0 (0.0%)",
                        details={"imputed_value": fill_val, "strategy": "specific_value"},
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

            # -------------------------------------------------------------
            # 8B. FILL_SPECIFIC_VALUE (User-Selected Custom Text Value)
            # -------------------------------------------------------------
            if op == "FILL_SPECIFIC_VALUE" and col is not None:
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
                            method_used="Specific text value",
                            before_statistic="Missing: 0",
                            after_statistic="Missing: 0",
                            details={"note": "No missing values present at execution time."},
                        )
                    )
                    continue

                custom_val = rec.params.get("custom_value")
                if custom_val is None:
                    custom_val = rec.params.get("fill_value", "Unknown")
                fill_val = str(custom_val).strip()

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
                        method_used=f"Specific value ({fill_val!r})",
                        before_statistic=f"Missing: {null_cnt} ({round((null_cnt/max(len(working_df),1))*100, 1)}%)",
                        after_statistic="Missing: 0 (0.0%)",
                        details={"imputed_value": fill_val, "strategy": "specific_value"},
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

            elif op in ["CONVERT_NUMERIC", "CONVERT_FLOAT"] and col in cleaned_df.columns:
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

            elif op == "CONVERT_INTEGER" and col in cleaned_df.columns:
                if pd.api.types.is_integer_dtype(cleaned_df[col]) or pd.api.types.is_numeric_dtype(cleaned_df[col]):
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"INTEGER_DTYPE_VALID_{col}",
                            status="PASSED",
                            message=f"Column '{col}' successfully converted to integer ({cleaned_df[col].dtype}).",
                            column_name=col,
                            details={"dtype": str(cleaned_df[col].dtype)},
                        )
                    )
                else:
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"INTEGER_DTYPE_VALID_{col}",
                            status="FAILED",
                            message=f"Column '{col}' failed integer conversion ({cleaned_df[col].dtype}).",
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

            elif op in ["CONVERT_STRING", "CONVERT_TEXT"] and col in cleaned_df.columns:
                if pd.api.types.is_string_dtype(cleaned_df[col]) or pd.api.types.is_object_dtype(cleaned_df[col]):
                    checks.append(
                        CleaningValidationCheck(
                            check_name=f"STRING_DTYPE_VALID_{col}",
                            status="PASSED",
                            message=f"Column '{col}' successfully converted to string/text.",
                            column_name=col,
                            details={"dtype": str(cleaned_df[col].dtype)},
                        )
                    )

            elif op == "TRIM_WHITESPACE" and col in cleaned_df.columns:
                series = cleaned_df[col]
                if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                    has_untrimmed = (series.dropna().astype(str) != series.dropna().astype(str).str.strip()).any()
                    if not has_untrimmed:
                        checks.append(
                            CleaningValidationCheck(
                                check_name=f"WHITESPACE_TRIMMED_{col}",
                                status="PASSED",
                                message=f"Column '{col}' verified free of untrimmed leading/trailing whitespace.",
                                column_name=col,
                                details={"untrimmed": False},
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

    def preview_column_transformation(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        operation: str,
        target_type: Optional[str] = None,
        custom_value: Optional[Any] = None,
        allow_fractional_truncation: bool = False,
    ) -> Any:
        """Deterministic non-mutating conversion preview for a single user-controlled column transformation."""
        from cleaning.models import ColumnTransformPreviewResult
        df = canonical.data
        if column_name not in df.columns:
            return ColumnTransformPreviewResult(
                column_name=column_name,
                operation=operation,
                target_type=target_type or "Unknown",
                original_dtype="unknown",
                target_dtype="unknown",
                total_rows=len(df),
                non_null_count=0,
                converted_count=0,
                unparseable_count=0,
                is_valid=False,
                error_message=f"Column '{column_name}' does not exist in dataset.",
            )

        if operation not in self.SUPPORTED_TRANSFORM_OPERATIONS:
            return ColumnTransformPreviewResult(
                column_name=column_name,
                operation=operation,
                target_type=target_type or "Unknown",
                original_dtype=str(df[column_name].dtype),
                target_dtype="unknown",
                total_rows=len(df),
                non_null_count=int(df[column_name].notna().sum()),
                converted_count=0,
                unparseable_count=0,
                is_valid=False,
                error_message=f"Unsupported cleaning operation '{operation}'.",
            )

        series = df[column_name]
        total_rows = len(df)
        orig_dtype = str(series.dtype)
        non_null_cnt = int(series.notna().sum())
        orig_missing_cnt = int(series.isna().sum())
        target_dtype = orig_dtype
        converted_cnt = 0
        unparseable_cnt = 0
        unparseable_samples: List[Any] = []
        fractional_loss_cnt = 0
        new_missing_cnt = orig_missing_cnt
        is_valid = True
        error_msg: Optional[str] = None
        sample_changes: List[SampleCellChange] = []

        # Datatype conversions
        if operation in ["CONVERT_NUMERIC", "CONVERT_FLOAT"]:
            target_dtype = "float64"
            converted = pd.to_numeric(series, errors="coerce")
            parsed_cnt = int(converted.notna().sum())
            converted_cnt = parsed_cnt
            unparseable_mask = series.notna() & converted.isna()
            unparseable_cnt = int(unparseable_mask.sum())
            if unparseable_cnt > 0:
                unparseable_samples = [
                    sanitize_json_value(x)
                    for x in series[unparseable_mask].unique()[:5].tolist()
                ]
            new_missing_cnt = orig_missing_cnt + unparseable_cnt
            changed_mask = series.notna() & (series != converted)
            for idx in df.index[changed_mask][:10]:
                sample_changes.append(
                    SampleCellChange(
                        row_index=idx,
                        column_name=column_name,
                        before_value=series.loc[idx],
                        after_value=converted.loc[idx],
                        operation=operation,
                    )
                )

        elif operation == "CONVERT_INTEGER":
            target_dtype = "Int64"
            num_series = pd.to_numeric(series, errors="coerce")
            parsed_cnt = int(num_series.notna().sum())
            converted_cnt = parsed_cnt
            unparseable_mask = series.notna() & num_series.isna()
            unparseable_cnt = int(unparseable_mask.sum())
            if unparseable_cnt > 0:
                unparseable_samples = [
                    sanitize_json_value(x)
                    for x in series[unparseable_mask].unique()[:5].tolist()
                ]
            new_missing_cnt = orig_missing_cnt + unparseable_cnt
            fractional_mask = num_series.notna() & ((num_series % 1) != 0)
            fractional_loss_cnt = int(fractional_mask.sum())
            if fractional_loss_cnt > 0 and not allow_fractional_truncation:
                is_valid = False
                error_msg = f"Integer conversion would truncate {fractional_loss_cnt} fractional values."

            valid_nums = num_series.dropna()
            truncated_map = valid_nums.apply(lambda x: int(math.trunc(x)))
            converted_int = pd.Series(pd.NA, index=series.index, dtype="Int64")
            if len(truncated_map) > 0:
                converted_int.loc[truncated_map.index] = truncated_map.values

            changed_mask = series.notna()
            for idx in df.index[changed_mask][:10]:
                sample_changes.append(
                    SampleCellChange(
                        row_index=idx,
                        column_name=column_name,
                        before_value=series.loc[idx],
                        after_value=int(converted_int.loc[idx]) if pd.notna(converted_int.loc[idx]) else None,
                        operation=operation,
                    )
                )

        elif operation == "CONVERT_DATETIME":
            target_dtype = "datetime64[ns]"
            try:
                converted_dt = pd.to_datetime(series, errors="coerce", format="mixed")
                parsed_cnt = int(converted_dt.notna().sum())
                converted_cnt = parsed_cnt
                unparseable_mask = series.notna() & converted_dt.isna()
                unparseable_cnt = int(unparseable_mask.sum())
                if unparseable_cnt > 0:
                    unparseable_samples = [
                        sanitize_json_value(x)
                        for x in series[unparseable_mask].unique()[:5].tolist()
                    ]
                new_missing_cnt = orig_missing_cnt + unparseable_cnt
                changed_mask = series.notna()
                for idx in df.index[changed_mask][:10]:
                    sample_changes.append(
                        SampleCellChange(
                            row_index=idx,
                            column_name=column_name,
                            before_value=series.loc[idx],
                            after_value=converted_dt.loc[idx].isoformat() if pd.notna(converted_dt.loc[idx]) else None,
                            operation=operation,
                        )
                    )
            except Exception as ex:
                is_valid = False
                error_msg = f"Datetime conversion failed: {str(ex)}"

        elif operation in ["NORMALIZE_BOOLEAN", "CONVERT_BOOLEAN"]:
            target_dtype = "bool"
            true_set = {"true", "yes", "1", "t", "y"}
            false_set = {"false", "no", "0", "f", "n"}

            def _map_b(val: Any) -> Any:
                if pd.isna(val):
                    return np.nan
                s = str(val).strip().lower()
                if s in true_set:
                    return True
                if s in false_set:
                    return False
                return np.nan

            converted_b = series.apply(_map_b)
            converted_cnt = int(converted_b.notna().sum())
            unparseable_mask = series.notna() & converted_b.isna()
            unparseable_cnt = int(unparseable_mask.sum())
            if unparseable_cnt > 0:
                unparseable_samples = [
                    sanitize_json_value(x)
                    for x in series[unparseable_mask].unique()[:5].tolist()
                ]
            new_missing_cnt = orig_missing_cnt + unparseable_cnt
            changed_mask = series.notna() & (series != converted_b)
            for idx in df.index[changed_mask][:10]:
                sample_changes.append(
                    SampleCellChange(
                        row_index=idx,
                        column_name=column_name,
                        before_value=series.loc[idx],
                        after_value=converted_b.loc[idx],
                        operation=operation,
                    )
                )

        elif operation in ["CONVERT_STRING", "CONVERT_TEXT"]:
            target_dtype = "string"
            converted_s = series.map(lambda x: None if pd.isna(x) else str(x))
            converted_cnt = int(converted_s.notna().sum())
            changed_mask = series.notna() & (series != converted_s)
            for idx in df.index[changed_mask][:10]:
                sample_changes.append(
                    SampleCellChange(
                        row_index=idx,
                        column_name=column_name,
                        before_value=series.loc[idx],
                        after_value=converted_s.loc[idx],
                        operation=operation,
                    )
                )

        elif operation == "TRIM_WHITESPACE":
            if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                trimmed = series.map(lambda x: x.strip() if isinstance(x, str) else x)
                changed_mask = series.notna() & (series != trimmed)
                converted_cnt = int(changed_mask.sum())
                for idx in df.index[changed_mask][:10]:
                    sample_changes.append(
                        SampleCellChange(
                            row_index=idx,
                            column_name=column_name,
                            before_value=series.loc[idx],
                            after_value=trimmed.loc[idx],
                            operation=operation,
                        )
                    )
            else:
                is_valid = False
                error_msg = f"Column '{column_name}' is not text/string; whitespace trim not applicable."

        elif operation == "NORMALIZE_EMPTY_STRINGS":
            if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                empty_mask = series.notna() & (series.astype(str).str.strip() == "")
                converted_cnt = int(empty_mask.sum())
                new_missing_cnt = orig_missing_cnt + converted_cnt
                for idx in df.index[empty_mask][:10]:
                    sample_changes.append(
                        SampleCellChange(
                            row_index=idx,
                            column_name=column_name,
                            before_value=series.loc[idx],
                            after_value=None,
                            operation=operation,
                        )
                    )
            else:
                is_valid = False
                error_msg = f"Column '{column_name}' is not text/string; empty string normalization not applicable."

        elif operation in ["IMPUTE_MEDIAN", "IMPUTE_MEAN", "IMPUTE_SPECIFIC_VALUE"]:
            if orig_missing_cnt == 0:
                converted_cnt = 0
                new_missing_cnt = 0
            else:
                num_s = pd.to_numeric(series.dropna(), errors="coerce").dropna()
                if len(num_s) == 0 and operation in ["IMPUTE_MEDIAN", "IMPUTE_MEAN"]:
                    is_valid = False
                    error_msg = f"No valid numeric data in '{column_name}' to compute {operation}."
                else:
                    if operation == "IMPUTE_MEDIAN":
                        fill_val = round(float(num_s.median()), 2)
                    elif operation == "IMPUTE_MEAN":
                        fill_val = round(float(num_s.mean()), 2)
                    else:
                        if custom_value is None or str(custom_value).strip() == "":
                            is_valid = False
                            error_msg = "Specific numeric value is required."
                            fill_val = 0.0
                        else:
                            try:
                                fill_val = float(custom_value)
                                if math.isnan(fill_val) or math.isinf(fill_val):
                                    raise ValueError()
                                if fill_val.is_integer():
                                    fill_val = int(fill_val)
                            except (ValueError, TypeError):
                                is_valid = False
                                error_msg = f"Invalid specific numeric value: {custom_value}"
                                fill_val = 0.0

                    if is_valid:
                        converted_cnt = orig_missing_cnt
                        new_missing_cnt = 0
                        null_indices = df.index[series.isna()][:10]
                        for idx in null_indices:
                            sample_changes.append(
                                SampleCellChange(
                                    row_index=idx,
                                    column_name=column_name,
                                    before_value=None,
                                    after_value=fill_val,
                                    operation=operation,
                                )
                            )

        elif operation in ["FILL_MODE", "IMPUTE_MODE", "FILL_UNKNOWN", "IMPUTE_UNKNOWN", "FILL_SPECIFIC_VALUE"]:
            if orig_missing_cnt == 0:
                converted_cnt = 0
                new_missing_cnt = 0
            else:
                if operation in ["FILL_MODE", "IMPUTE_MODE"]:
                    non_nulls = series.dropna()
                    modes = non_nulls.mode() if len(non_nulls) > 0 else []
                    if len(modes) == 0:
                        is_valid = False
                        error_msg = f"No valid non-null entries to compute mode on '{column_name}'."
                        fill_val = "Unknown"
                    else:
                        fill_val = modes.iloc[0]
                elif operation in ["FILL_UNKNOWN", "IMPUTE_UNKNOWN"]:
                    fill_val = "Unknown"
                else:
                    if custom_value is None or str(custom_value).strip() == "":
                        is_valid = False
                        error_msg = "Specific text value is required."
                        fill_val = "Unknown"
                    else:
                        fill_val = str(custom_value).strip()

                if is_valid:
                    converted_cnt = orig_missing_cnt
                    new_missing_cnt = 0
                    null_indices = df.index[series.isna()][:10]
                    for idx in null_indices:
                        sample_changes.append(
                            SampleCellChange(
                                row_index=idx,
                                column_name=column_name,
                                before_value=None,
                                after_value=fill_val,
                                operation=operation,
                            )
                        )

        elif operation == "LEAVE_UNCHANGED":
            converted_cnt = 0
            new_missing_cnt = orig_missing_cnt

        return ColumnTransformPreviewResult(
            column_name=column_name,
            operation=operation,
            target_type=target_type or target_dtype,
            original_dtype=orig_dtype,
            target_dtype=target_dtype,
            total_rows=total_rows,
            non_null_count=non_null_cnt,
            converted_count=converted_cnt,
            unparseable_count=unparseable_cnt,
            unparseable_samples=unparseable_samples,
            fractional_loss_count=fractional_loss_cnt,
            original_missing_count=orig_missing_cnt,
            new_missing_count=new_missing_cnt,
            is_valid=is_valid,
            error_message=error_msg,
            sample_changes=sample_changes,
        )

    def preview(
        self,
        canonical: CanonicalDataset,
        selected_recommendation_ids: List[str],
        plan: Optional[CleaningPlan] = None,
        operation_overrides: Optional[Dict[str, str]] = None,
        operation_values: Optional[Dict[str, Any]] = None,
        custom_transformations: Optional[List[Dict[str, Any]]] = None,
    ) -> CleaningPreviewResult:
        """Pure non-mutating preview of selected cleaning operations with optional user overrides,
        custom values, and explicit user-defined column transformations.
        Never mutates canonical.data or session store.
        """
        raw_rows, raw_cols = len(canonical.data), len(canonical.data.columns)

        resolved_recs = self._resolve_and_validate_recommendations(
            canonical=canonical,
            selected_ids=selected_recommendation_ids,
            plan=plan,
            operation_overrides=operation_overrides,
            operation_values=operation_values,
            custom_transformations=custom_transformations,
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
        skip_cnt = sum(1 for r in op_results if r.status in ["SKIPPED", "WARNING", "REVIEW_ONLY"])

        total_requested = len(selected_recommendation_ids) + len(custom_transformations or [])

        return CleaningPreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            original_row_count=raw_rows,
            preview_row_count=len(working_df),
            row_count_change=len(working_df) - raw_rows,
            original_column_count=raw_cols,
            preview_column_count=len(working_df.columns),
            operations_requested=total_requested,
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
        operation_values: Optional[Dict[str, Any]] = None,
        custom_transformations: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[CleaningExecutionResult, CanonicalDataset]:
        """Execute selected cleaning operations on an explicit copy of raw data,
        applying any user-selected operation overrides, custom values, and custom column transformations.
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
            operation_values=operation_values,
            custom_transformations=custom_transformations,
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
            dataset_id=canonical.metadata.dataset_id,
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

        # Rerun Semantic Intelligence on the transformed dataset so semantic roles reflect the new dtypes/distributions
        from intelligence.semantic_analyzer import SemanticAnalyzer
        cleaned_canonical.semantic_profile = SemanticAnalyzer().analyze(
            cleaned_canonical,
            profile=cleaned_canonical.profile,
            apply_roles=True,
        )

        app_cnt = sum(1 for r in op_results if r.status == "APPLIED")
        skip_cnt = sum(1 for r in op_results if r.status in ["SKIPPED", "WARNING", "REVIEW_ONLY"])
        fail_cnt = sum(1 for r in op_results if r.status == "FAILED")
        total_requested = len(selected_recommendation_ids) + len(custom_transformations or [])

        execution_result = CleaningExecutionResult(
            dataset_id=canonical.metadata.dataset_id,
            original_row_count=raw_rows,
            cleaned_row_count=len(cleaned_df),
            row_count_change=len(cleaned_df) - raw_rows,
            original_column_count=raw_cols,
            cleaned_column_count=len(cleaned_df.columns),
            operations_requested=total_requested,
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
    operation_values: Optional[Dict[str, Any]] = None,
    custom_transformations: Optional[List[Dict[str, Any]]] = None,
) -> CleaningPreviewResult:
    """Convenience helper for non-mutating preview of cleaning operations."""
    executor = CleaningExecutor()
    return executor.preview(
        canonical=canonical,
        selected_recommendation_ids=selected_recommendation_ids,
        plan=plan,
        operation_overrides=operation_overrides,
        operation_values=operation_values,
        custom_transformations=custom_transformations,
    )


def execute_cleaning_plan(
    canonical: CanonicalDataset,
    selected_recommendation_ids: List[str],
    plan: Optional[CleaningPlan] = None,
    operation_overrides: Optional[Dict[str, str]] = None,
    operation_values: Optional[Dict[str, Any]] = None,
    custom_transformations: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[CleaningExecutionResult, CanonicalDataset]:
    """Convenience helper for batch cleaning execution on CanonicalDataset copy."""
    executor = CleaningExecutor()
    return executor.execute(
        canonical=canonical,
        selected_recommendation_ids=selected_recommendation_ids,
        plan=plan,
        operation_overrides=operation_overrides,
        operation_values=operation_values,
        custom_transformations=custom_transformations,
    )
