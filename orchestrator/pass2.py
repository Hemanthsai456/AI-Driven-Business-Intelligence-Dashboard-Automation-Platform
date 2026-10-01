"""Pass 2 Winner-Only Validation Engine.

Architecture references:
- ranker_v1_spec.md §6 (Pass 2 — Winner-Only Validation)
- orchestrator_conformance.md §1 & §4.2

Checks on winning candidate + real ExecutionResult:
1. Result non-empty: row_count > 0 and len(rows) > 0.
2. Cast-failure rate under threshold: failed_cast_rate <= FAILED_CAST_RATE_THRESHOLD.
3. Chart-type / data-shape compatibility:
   - KPI requires exactly 1 row (row_count == 1).
   - LINE / AREA requires at least one dimension with temporal granularity.
   - BAR requires at least one grouping dimension.
   - PIE requires row_count <= 20.
4. No unexpected nulls in the metric column:
   - All rows null for metric column is rejected.
   - For single-value KPI, metric value cannot be None.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from orchestrator.config import FAILED_CAST_RATE_THRESHOLD
from orchestrator.schemas import (
    CandidatePlan,
    ExecutionResult,
    Pass2Result,
    PassResult,
    ValidationIssue,
    ValidationStatus,
    VisualizationType,
)


def validate_pass2(
    plan: CandidatePlan,
    exec_result: ExecutionResult,
) -> PassResult:
    """Validate winning candidate against its real ExecutionResult.

    Args:
        plan: Winning candidate plan.
        exec_result: Real execution result from deterministic execution engine.

    Returns:
        PassResult(passed: bool, reasons: list[str]) with structured issues.
    """
    issues: List[ValidationIssue] = []
    reasons: List[str] = []

    # 1. Result non-empty
    if exec_result.row_count == 0 or len(exec_result.rows) == 0:
        msg = f"Execution result is empty (0 rows returned) for plan '{plan.plan_id}'."
        issues.append(
            ValidationIssue(
                check="result_non_empty",
                status=ValidationStatus.FAILED,
                message=msg,
            )
        )
        reasons.append(msg)

    # 2. Cast-failure rate under threshold
    if exec_result.failed_cast_rate > FAILED_CAST_RATE_THRESHOLD:
        msg = (
            f"Failed cast rate {exec_result.failed_cast_rate:.1%} exceeds threshold "
            f"{FAILED_CAST_RATE_THRESHOLD:.1%}."
        )
        issues.append(
            ValidationIssue(
                check="cast_failure_rate",
                status=ValidationStatus.FAILED,
                message=msg,
            )
        )
        reasons.append(msg)

    # 3. Plan-vs-result consistency & Metric presence
    result_cols_lower = {c.lower() for c in exec_result.columns}
    metric_col_lower = plan.metric.column.lower()
    metric_agg_lower = plan.metric.aggregation.value.lower()

    metric_key: Optional[str] = None
    for c in exec_result.columns:
        cl = c.lower()
        if cl == metric_col_lower or metric_col_lower in cl or metric_agg_lower in cl:
            metric_key = c
            break

    if not metric_key:
        msg = (
            f"Metric column '{plan.metric.column}' (or aggregation alias) not found "
            f"in execution result columns {exec_result.columns}."
        )
        issues.append(
            ValidationIssue(
                check="plan_result_consistency",
                status=ValidationStatus.FAILED,
                column=plan.metric.column,
                message=msg,
            )
        )
        reasons.append(msg)
    else:
        # 4. No unexpected nulls in the metric column
        if exec_result.rows:
            metric_values = [r.get(metric_key) for r in exec_result.rows]
            null_count = sum(1 for v in metric_values if v is None)
            total_count = len(metric_values)

            # Check if all rows are null
            if null_count == total_count:
                msg = f"Metric column '{metric_key}' contains only NULL values across all {total_count} rows."
                issues.append(
                    ValidationIssue(
                        check="metric_not_all_null",
                        status=ValidationStatus.FAILED,
                        column=metric_key,
                        message=msg,
                    )
                )
                reasons.append(msg)
            # For single-value KPI, the single metric value cannot be None
            elif plan.visualization == VisualizationType.KPI and null_count > 0:
                msg = f"KPI metric value for '{metric_key}' is NULL."
                issues.append(
                    ValidationIssue(
                        check="kpi_metric_null",
                        status=ValidationStatus.FAILED,
                        column=metric_key,
                        message=msg,
                    )
                )
                reasons.append(msg)

    # 5. Chart-type / data-shape compatibility
    viz = plan.visualization

    if viz == VisualizationType.KPI:
        if exec_result.row_count != 1:
            msg = f"KPI visualization requires exactly 1 result row, but got {exec_result.row_count} rows."
            issues.append(
                ValidationIssue(
                    check="viz_kpi_single_row",
                    status=ValidationStatus.FAILED,
                    message=msg,
                )
            )
            reasons.append(msg)

    elif viz in {VisualizationType.LINE, VisualizationType.AREA}:
        has_temporal_dim = any(d.granularity is not None for d in plan.dimensions)
        if not has_temporal_dim:
            msg = (
                f"{viz.value} visualization requires an ordered/temporal dimension with "
                "granularity, but none was specified."
            )
            issues.append(
                ValidationIssue(
                    check="viz_line_requires_datetime",
                    status=ValidationStatus.FAILED,
                    message=msg,
                )
            )
            reasons.append(msg)

    elif viz == VisualizationType.BAR:
        if not plan.dimensions:
            msg = "BAR visualization requires at least one grouping dimension."
            issues.append(
                ValidationIssue(
                    check="viz_bar_requires_dimension",
                    status=ValidationStatus.FAILED,
                    message=msg,
                )
            )
            reasons.append(msg)

    elif viz == VisualizationType.PIE:
        if exec_result.row_count > 20:
            msg = f"PIE visualization requires <= 20 rows (categorical breakdown), but got {exec_result.row_count} rows."
            issues.append(
                ValidationIssue(
                    check="viz_pie_row_limit",
                    status=ValidationStatus.FAILED,
                    message=msg,
                )
            )
            reasons.append(msg)

    passed = not any(issue.status == ValidationStatus.FAILED for issue in issues)
    return PassResult(
        plan_id=plan.plan_id,
        passed=passed,
        reasons=reasons,
        issues=issues,
        cascade_triggered=not passed,
    )
