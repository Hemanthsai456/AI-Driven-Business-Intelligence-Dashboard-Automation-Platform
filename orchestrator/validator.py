"""Pass 1a and Pass 1b validation engines for analytical candidate plans.

Architecture references:
- orchestrator_conformance.md §1 & §4.2 (Binding Resolutions C2, C3, C4)
- ranker_v1_spec.md §Pass 1a and §Pass 1b
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
from intelligence.schema_validator import AnalysisReadiness, ReadinessStatus
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.config import (
    FAILED_CAST_RATE_THRESHOLD,
    RESULT_ROW_CAP,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    Pass1aResult,
    Pass1bResult,
    Pass2Result,
    PassResult,
    ValidationIssue,
    ValidationStatus,
)
from orchestrator.pass2 import validate_pass2

# Whitelisted operators for filters
ALLOWED_FILTER_OPERATORS: Set[str] = {
    "=",
    "!=",
    "<>",
    "<",
    "<=",
    ">",
    ">=",
    "IN",
    "BETWEEN",
    "NOT IN",
    "IS NULL",
    "IS NOT NULL",
    "LIKE",
    "ILIKE",
}


def is_plan_structurally_valid(plan: CandidatePlan) -> bool:
    """Validate structural integrity of candidate plan before dedup/agreement.

    Rejects plans with missing metrics or malformed/unapproved filter operators (e.g. '=====').
    Whitelisted operators: =, !=, <>, <, <=, >, >=, IN, BETWEEN, NOT IN, IS NULL, IS NOT NULL, LIKE, ILIKE.
    """
    if not plan.metric or not plan.metric.column:
        return False

    for flt in plan.filters:
        op = flt.operator.strip().upper()
        if op not in ALLOWED_FILTER_OPERATORS and flt.operator.strip() not in ALLOWED_FILTER_OPERATORS:
            return False

    return True

# Role compatibility matrices
MEASURE_ONLY_AGGS: Set[AggregationType] = {
    AggregationType.SUM,
    AggregationType.AVG,
    AggregationType.STDDEV,
    AggregationType.MEDIAN,
}

ORDERABLE_AGGS: Set[AggregationType] = {
    AggregationType.MIN,
    AggregationType.MAX,
}

ANY_ROLE_AGGS: Set[AggregationType] = {
    AggregationType.COUNT,
    AggregationType.COUNT_DISTINCT,
}


def _get_column_role_and_confidence(
    col_name: str,
    semantic_profile: DatasetSemanticProfile,
) -> tuple[Optional[ColumnRole], float, str]:
    """Retrieve candidate role, confidence score, and level for a column from the profile."""
    ev = semantic_profile.get_evidence(col_name)
    if ev is None:
        return None, 0.0, "UNKNOWN"
    return ev.candidate_role, ev.confidence, ev.confidence_level


def validate_pass1a(
    plan: CandidatePlan,
    semantic_profile: DatasetSemanticProfile,
    readiness: Optional[AnalysisReadiness] = None,
) -> Pass1aResult:
    """Pass 1a Pre-Dispatch Validation.

    Performs structural, semantic, and schema checks before dispatching to DuckDB:
    1. Binding Resolution C3: Refuse dispatch immediately if readiness == NOT_READY.
    2. Column Existence: Metric, dimensions, filters, and comparisons must exist in profile.
    3. Role/Aggregation Compatibility:
       - SUM/AVG/STDDEV/MEDIAN require MEASURE role.
       - MIN/MAX require MEASURE, DATETIME, or DIMENSION.
       - COUNT/COUNT_DISTINCT allowed on any role.
       - UNKNOWN role is strictly rejected for analytical metrics (auto KPIs).
    4. Granularity Requirements:
       - Any dimension specifying a temporal Granularity MUST have DATETIME role.
    5. Filter Operator Whitelist:
       - Only approved comparison and null-checking operators allowed.
    6. Low-Confidence Warnings:
       - Columns with confidence < 0.70 or level == "LOW" generate WARNING issues (non-fatal).
    """
    issues: List[ValidationIssue] = []

    # 1. Binding Resolution C3: Dispatch refused if readiness is NOT_READY
    if readiness is not None:
        status_val = (
            readiness.status.value
            if isinstance(readiness.status, ReadinessStatus)
            else str(readiness.status)
        )
        if status_val == ReadinessStatus.NOT_READY.value:
            issues.append(
                ValidationIssue(
                    check="dataset_readiness",
                    status=ValidationStatus.FAILED,
                    message="Dispatch refused: dataset readiness status is NOT_READY (C3 binding resolution).",
                )
            )
            return Pass1aResult(plan_id=plan.plan_id, passed=False, issues=issues)

    available_cols = set(semantic_profile.column_evidences.keys())

    # 2. Metric Column Checks
    metric_col = plan.metric.column
    if metric_col not in available_cols:
        issues.append(
            ValidationIssue(
                check="metric_column_exists",
                status=ValidationStatus.FAILED,
                column=metric_col,
                message=f"Metric column '{metric_col}' does not exist in dataset semantic profile.",
            )
        )
    else:
        role, conf, conf_level = _get_column_role_and_confidence(metric_col, semantic_profile)
        agg = plan.metric.aggregation

        # Reject UNKNOWN role for metric
        if role == ColumnRole.UNKNOWN or role is None:
            issues.append(
                ValidationIssue(
                    check="unknown_role_rejected",
                    status=ValidationStatus.FAILED,
                    column=metric_col,
                    message=f"Column '{metric_col}' has UNKNOWN semantic role and cannot be used as an analytical metric.",
                )
            )
        else:
            # Aggregation compatibility check
            if agg in MEASURE_ONLY_AGGS:
                if role != ColumnRole.MEASURE:
                    issues.append(
                        ValidationIssue(
                            check="role_aggregation_compat",
                            status=ValidationStatus.FAILED,
                            column=metric_col,
                            message=f"Aggregation '{agg.value}' requires MEASURE role, but column '{metric_col}' has role '{role.value}'.",
                        )
                    )
            elif agg in ORDERABLE_AGGS:
                if role not in {ColumnRole.MEASURE, ColumnRole.DATETIME, ColumnRole.DIMENSION}:
                    issues.append(
                        ValidationIssue(
                            check="role_aggregation_compat",
                            status=ValidationStatus.FAILED,
                            column=metric_col,
                            message=f"Aggregation '{agg.value}' is not valid for column '{metric_col}' with role '{role.value}'.",
                        )
                    )

            # Low confidence warning
            if conf_level == "LOW" or conf < 0.70:
                issues.append(
                    ValidationIssue(
                        check="column_confidence",
                        status=ValidationStatus.WARNING,
                        column=metric_col,
                        message=f"Metric column '{metric_col}' has LOW semantic confidence ({conf:.2f}).",
                    )
                )

    # 3. Dimension Checks
    for dim in plan.dimensions:
        dim_col = dim.column
        if dim_col not in available_cols:
            issues.append(
                ValidationIssue(
                    check="dimension_column_exists",
                    status=ValidationStatus.FAILED,
                    column=dim_col,
                    message=f"Dimension column '{dim_col}' does not exist in dataset semantic profile.",
                )
            )
        else:
            role, conf, conf_level = _get_column_role_and_confidence(dim_col, semantic_profile)
            if dim.granularity is not None:
                # Temporal granularity requires DATETIME role
                if role != ColumnRole.DATETIME:
                    issues.append(
                        ValidationIssue(
                            check="granularity_requires_datetime",
                            status=ValidationStatus.FAILED,
                            column=dim_col,
                            message=(
                                f"Dimension '{dim_col}' specifies temporal granularity '{dim.granularity.value}', "
                                f"which requires DATETIME role, but column has role '{role.value if role else 'UNKNOWN'}'."
                            ),
                        )
                    )
            if conf_level == "LOW" or conf < 0.70:
                issues.append(
                    ValidationIssue(
                        check="column_confidence",
                        status=ValidationStatus.WARNING,
                        column=dim_col,
                        message=f"Dimension column '{dim_col}' has LOW semantic confidence ({conf:.2f}).",
                    )
                )

    # 4. Filter Checks
    for flt in plan.filters:
        flt_col = flt.column
        if flt_col not in available_cols:
            issues.append(
                ValidationIssue(
                    check="filter_column_exists",
                    status=ValidationStatus.FAILED,
                    column=flt_col,
                    message=f"Filter column '{flt_col}' does not exist in dataset semantic profile.",
                )
            )
        else:
            _, conf, conf_level = _get_column_role_and_confidence(flt_col, semantic_profile)
            if conf_level == "LOW" or conf < 0.70:
                issues.append(
                    ValidationIssue(
                        check="column_confidence",
                        status=ValidationStatus.WARNING,
                        column=flt_col,
                        message=f"Filter column '{flt_col}' has LOW semantic confidence ({conf:.2f}).",
                    )
                )

        op_clean = flt.operator.strip().upper()
        if op_clean not in ALLOWED_FILTER_OPERATORS and flt.operator.strip() not in ALLOWED_FILTER_OPERATORS:
            issues.append(
                ValidationIssue(
                    check="filter_operator_whitelist",
                    status=ValidationStatus.FAILED,
                    column=flt_col,
                    message=f"Filter operator '{flt.operator}' is not in the approved whitelist ({sorted(ALLOWED_FILTER_OPERATORS)}).",
                )
            )

    # 5. Comparison Checks
    if plan.comparison is not None:
        comp_col = plan.comparison.column
        if comp_col not in available_cols:
            issues.append(
                ValidationIssue(
                    check="comparison_column_exists",
                    status=ValidationStatus.FAILED,
                    column=comp_col,
                    message=f"Comparison column '{comp_col}' does not exist in dataset semantic profile.",
                )
            )

    passed = not any(issue.status == ValidationStatus.FAILED for issue in issues)
    return Pass1aResult(plan_id=plan.plan_id, passed=passed, issues=issues)


def validate_pass1b(
    plan: CandidatePlan,
    exec_result: ExecutionResult,
) -> Pass1bResult:
    """Pass 1b Post-Execution Validation.

    Validates execution results produced by DuckDB before ranking:
    1. Execution Success: Status must be ExecutionStatus.SUCCESS.
    2. Non-empty Result: Execution must return at least 1 row.
    3. Metric Not All-Null: The metric result must not be completely null across all rows.
    4. Row Cap: Row count must not exceed RESULT_ROW_CAP.
    5. Failed Cast Rate: Datetime TRY_CAST failure rate must not exceed FAILED_CAST_RATE_THRESHOLD.
    """
    issues: List[ValidationIssue] = []

    # 1. Execution Success
    if exec_result.status != ExecutionStatus.SUCCESS:
        issues.append(
            ValidationIssue(
                check="execution_status",
                status=ValidationStatus.FAILED,
                message=f"Execution failed with status '{exec_result.status.value}': {exec_result.error_message or 'Unknown error'}",
            )
        )
        return Pass1bResult(plan_id=plan.plan_id, passed=False, issues=issues)

    # 2. Row Cap Check
    if exec_result.row_count > RESULT_ROW_CAP:
        issues.append(
            ValidationIssue(
                check="result_row_cap",
                status=ValidationStatus.FAILED,
                message=f"Result row count ({exec_result.row_count}) exceeds maximum allowed cap of {RESULT_ROW_CAP}.",
            )
        )

    # 3. Non-Empty Result Check
    if exec_result.row_count == 0:
        issues.append(
            ValidationIssue(
                check="non_empty_result",
                status=ValidationStatus.FAILED,
                message="Execution produced an empty result set (0 rows).",
            )
        )
    else:
        # 4. Metric Not All-Null Check
        # Identify metric column in returned rows (usually last column or matching alias)
        metric_col_name = None
        for col in exec_result.columns:
            if plan.metric.column.lower() in col.lower() or plan.metric.aggregation.value.lower() in col.lower():
                metric_col_name = col
                break
        if not metric_col_name and exec_result.columns:
            metric_col_name = exec_result.columns[-1]

        if metric_col_name and exec_result.rows:
            metric_values = [row.get(metric_col_name) for row in exec_result.rows]
            all_null = all(v is None for v in metric_values)
            if all_null:
                issues.append(
                    ValidationIssue(
                        check="metric_not_all_null",
                        status=ValidationStatus.FAILED,
                        column=plan.metric.column,
                        message=f"Metric '{plan.metric.column}' evaluated to NULL across all {exec_result.row_count} rows.",
                    )
                )

    # 5. Failed Cast Rate Check
    if exec_result.failed_cast_rate > FAILED_CAST_RATE_THRESHOLD:
        issues.append(
            ValidationIssue(
                check="failed_cast_rate",
                status=ValidationStatus.FAILED,
                message=(
                    f"Datetime TRY_CAST failure rate ({exec_result.failed_cast_rate:.1%}) "
                    f"exceeds maximum threshold of {FAILED_CAST_RATE_THRESHOLD:.1%}."
                ),
            )
        )
    elif exec_result.failed_cast_count > 0:
        issues.append(
            ValidationIssue(
                check="failed_cast_warning",
                status=ValidationStatus.WARNING,
                message=f"Datetime TRY_CAST had {exec_result.failed_cast_count} failed casts ({exec_result.failed_cast_rate:.1%}).",
            )
        )

    passed = not any(issue.status == ValidationStatus.FAILED for issue in issues)
    return Pass1bResult(plan_id=plan.plan_id, passed=passed, issues=issues)

# validate_pass2 is implemented in and re-exported from orchestrator.pass2
