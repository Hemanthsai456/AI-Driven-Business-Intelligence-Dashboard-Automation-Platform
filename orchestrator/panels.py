"""Generic Dashboard Panel Generator for Stage C.

Generates canonical DashboardPanel structures according to deterministic selection rules
based solely on runtime roles and cardinality, without hardcoded dataset or column names.

Selection Rules:
- Temporal dimension (DATETIME role or granularity) -> LINE panel
- Categorical dimension with <= 12 groups -> BAR panel
- Categorical dimension with > 12 groups -> BAR panel (top 10 groups + consolidated "Other")
- No dimension -> KPI panel

Always emitted panels:
1. Headline insight sentence (metric, dimension, top group, robustness)
2. Winner's main chart (derived from selection rules)
3. Robustness panel (heatmap data: group x interpretation)
4. Alternate interpretations with scores
5. Underlying tabular data view
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.schemas import (
    AggregationType,
    AlternateInterpretation,
    CandidatePlan,
    DashboardPanel,
    ExecutionResult,
    Granularity,
    PanelType,
    RankedCandidate,
    ScoreBreakdown,
)


def _safe_format_value(val: Any) -> str:
    """Format numeric or string value for human-readable headline display."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return f"{int(val):,}"
        return f"{val:,.2f}"
    return str(val)


def _find_data_keys(
    rows: List[Dict[str, Any]],
    plan: CandidatePlan,
) -> Tuple[Optional[str], Optional[str]]:
    """Determine the active dimension column key and metric column key in result rows."""
    if not rows:
        dim = plan.dimensions[0].column if plan.dimensions else None
        return dim, plan.metric.column

    first_row = rows[0]
    keys = list(first_row.keys())

    # 1. Dimension key
    dim_key: Optional[str] = None
    if plan.dimensions:
        target_dim = plan.dimensions[0].column.lower()
        for k in keys:
            if k.lower() == target_dim:
                dim_key = k
                break
        if not dim_key:
            dim_key = plan.dimensions[0].column

    # 2. Metric key
    metric_key: Optional[str] = None
    target_metric = plan.metric.column.lower()
    for k in keys:
        if k != dim_key:
            if target_metric in k.lower():
                metric_key = k
                break
    if not metric_key:
        # Fall back to any non-dimension key or first numeric key
        non_dim = [k for k in keys if k != dim_key]
        metric_key = non_dim[0] if non_dim else (keys[0] if keys else plan.metric.column)

    return dim_key, metric_key


def is_temporal_dimension(
    plan: CandidatePlan,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> bool:
    """Check if the primary dimension represents a temporal axis."""
    if not plan.dimensions:
        return False

    dim = plan.dimensions[0]
    if dim.granularity is not None:
        return True

    dim_col = dim.column
    if semantic_profile and dim_col in semantic_profile.column_evidences:
        role = semantic_profile.column_evidences[dim_col].candidate_role
        if role == ColumnRole.DATETIME:
            return True

    # Fallback to lexical hints for datetime names
    lower = dim_col.lower()
    temporal_hints = ("date", "time", "year", "month", "day", "quarter", "week", "timestamp")
    return any(hint in lower for hint in temporal_hints)


def generate_headline_insight(
    plan: CandidatePlan,
    result: ExecutionResult,
    score: ScoreBreakdown,
) -> str:
    """Generate a single headline insight sentence from the spec.

    Includes: metric, dimension, top group, and robustness.
    """
    metric_str = f"{plan.metric.aggregation.value} of {plan.metric.column}"

    # Robustness representation
    if score.stability is not None:
        robustness_str = f"{round(score.stability * 100, 1)}%"
    else:
        robustness_str = "untested"

    rows = result.rows or []
    if not plan.dimensions or not rows:
        # No dimension (KPI)
        val = rows[0].get(result.columns[0]) if (rows and result.columns) else "N/A"
        formatted_val = _safe_format_value(val)
        return (
            f"Total {metric_str} is {formatted_val}, with {robustness_str} "
            "rank stability across variant interpretations."
        )

    dim_col, metric_col = _find_data_keys(rows, plan)
    if not metric_col or not dim_col:
        return (
            f"{metric_str} analyzed across {plan.dimensions[0].column}, "
            f"with {robustness_str} rank stability across variant interpretations."
        )

    # Find the top group by metric value
    try:
        sorted_rows = sorted(
            rows,
            key=lambda r: float(r.get(metric_col) or 0) if isinstance(r.get(metric_col), (int, float, str)) and str(r.get(metric_col)).replace(".", "", 1).isdigit() else 0,
            reverse=True,
        )
    except Exception:
        sorted_rows = rows

    top_row = sorted_rows[0] if sorted_rows else {}
    top_group = top_row.get(dim_col, "Top group")
    top_val = _safe_format_value(top_row.get(metric_col))

    return (
        f"{top_group} leads with {top_val} in {metric_str} across {dim_col}, "
        f"with {robustness_str} rank stability across variant interpretations."
    )


def select_main_chart_panel(
    plan: CandidatePlan,
    result: ExecutionResult,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> DashboardPanel:
    """Apply selection rules to construct the winner's main visual panel.

    Rules:
    - No dimension -> KPI
    - Temporal dimension -> LINE
    - Categorical <= 12 groups -> BAR
    - Categorical > 12 groups -> BAR (top 10 + "Other")
    """
    rows = result.rows or []
    dim_key, metric_key = _find_data_keys(rows, plan)

    # Rule 1: No dimension -> KPI
    if not plan.dimensions or not dim_key:
        kpi_val = rows[0].get(metric_key or (result.columns[0] if result.columns else "value")) if rows else 0
        return DashboardPanel(
            panel_id=str(uuid4()),
            panel_type=PanelType.KPI,
            title=f"Total {plan.metric.aggregation.value} {plan.metric.column}",
            description=f"Aggregated {plan.metric.aggregation.value} across all records",
            data=[{"value": kpi_val, "metric": plan.metric.column, "aggregation": plan.metric.aggregation.value}],
            x_key=None,
            y_keys=[metric_key or plan.metric.column],
            metadata={
                "metric": plan.metric.column,
                "aggregation": plan.metric.aggregation.value,
                "cardinality": 0,
            },
        )

    # Rule 2: Temporal dimension -> LINE
    if is_temporal_dimension(plan, semantic_profile):
        title = f"{plan.metric.aggregation.value} of {plan.metric.column} over {dim_key}"
        return DashboardPanel(
            panel_id=str(uuid4()),
            panel_type=PanelType.LINE,
            title=title,
            description=f"Temporal trend by {dim_key}",
            data=rows,
            x_key=dim_key,
            y_keys=[metric_key] if metric_key else [],
            metadata={
                "metric": plan.metric.column,
                "dimension": dim_key,
                "aggregation": plan.metric.aggregation.value,
                "cardinality": len(rows),
                "is_temporal": True,
            },
        )

    # Categorical Dimension
    cardinality = len(rows)

    # Rule 3: Categorical <= 12 groups -> BAR
    if cardinality <= 12:
        title = f"{plan.metric.aggregation.value} of {plan.metric.column} by {dim_key}"
        return DashboardPanel(
            panel_id=str(uuid4()),
            panel_type=PanelType.BAR,
            title=title,
            description=f"Comparison across {cardinality} categories",
            data=rows,
            x_key=dim_key,
            y_keys=[metric_key] if metric_key else [],
            metadata={
                "metric": plan.metric.column,
                "dimension": dim_key,
                "aggregation": plan.metric.aggregation.value,
                "cardinality": cardinality,
                "collapsed": False,
            },
        )

    # Rule 4: Categorical > 12 groups -> BAR (top 10 + "Other")
    try:
        sorted_rows = sorted(
            rows,
            key=lambda r: float(r.get(metric_key) or 0) if isinstance(r.get(metric_key), (int, float, str)) and str(r.get(metric_key)).replace(".", "", 1).isdigit() else 0,
            reverse=True,
        )
    except Exception:
        sorted_rows = list(rows)

    top_10 = sorted_rows[:10]
    remainder = sorted_rows[10:]

    # Compute aggregate for "Other"
    agg_type = plan.metric.aggregation
    remainder_vals = [
        float(r.get(metric_key) or 0)
        for r in remainder
        if isinstance(r.get(metric_key), (int, float, str))
        and str(r.get(metric_key)).replace(".", "", 1).isdigit()
    ]

    if agg_type == AggregationType.AVG:
        other_val = sum(remainder_vals) / len(remainder_vals) if remainder_vals else 0.0
    else:
        other_val = sum(remainder_vals)

    other_row = {
        dim_key: "Other",
        metric_key: round(other_val, 4) if isinstance(other_val, float) else other_val,
        "_is_other": True,
        "_grouped_count": len(remainder),
    }

    compressed_data = list(top_10) + [other_row]

    title = f"{plan.metric.aggregation.value} of {plan.metric.column} by {dim_key} (Top 10 + Other)"
    return DashboardPanel(
        panel_id=str(uuid4()),
        panel_type=PanelType.BAR,
        title=title,
        description=f"Top 10 of {cardinality} categories, remaining {len(remainder)} grouped into 'Other'",
        data=compressed_data,
        x_key=dim_key,
        y_keys=[metric_key] if metric_key else [],
        metadata={
            "metric": plan.metric.column,
            "dimension": dim_key,
            "aggregation": plan.metric.aggregation.value,
            "cardinality": cardinality,
            "collapsed": True,
            "top_k": 10,
            "other_count": len(remainder),
        },
    )


def build_robustness_heatmap_panel(
    plan: CandidatePlan,
    result: ExecutionResult,
    score: ScoreBreakdown,
) -> DashboardPanel:
    """Build a robustness panel showing the winner's rank under each valid variant.

    Data format: group x interpretation matrix for heatmap rendering.
    """
    rows = result.rows or []
    dim_key, metric_key = _find_data_keys(rows, plan)

    # 1. Base rankings for the winner
    if not plan.dimensions or not dim_key or not rows:
        return DashboardPanel(
            panel_id=str(uuid4()),
            panel_type=PanelType.HEATMAP,
            title="Robustness Across Variant Interpretations",
            description="KPI aggregation without dimension groups has no rank order to perturb.",
            data=[],
            metadata={
                "status": "UNTESTED",
                "message": "Scalar metric (no dimension groups)",
                "variants_valid": score.variants_valid,
            },
        )

    # Determine top groups to include in heatmap (up to 10 for clarity)
    try:
        sorted_rows = sorted(
            rows,
            key=lambda r: float(r.get(metric_key) or 0) if isinstance(r.get(metric_key), (int, float, str)) and str(r.get(metric_key)).replace(".", "", 1).isdigit() else 0,
            reverse=True,
        )
    except Exception:
        sorted_rows = list(rows)

    top_groups = [str(r.get(dim_key)) for r in sorted_rows[:10]]
    winner_ranks = {g: idx + 1 for idx, g in enumerate(top_groups)}

    interpretations = ["Winner (Base)"]
    valid_variants = score.variant_details or []

    for v in valid_variants:
        desc = v.get("description", "variant")
        if desc not in interpretations:
            interpretations.append(desc)

    # Construct group x interpretation matrix
    heatmap_data: List[Dict[str, Any]] = []
    matrix: List[List[Any]] = []

    for g in top_groups:
        row_dict: Dict[str, Any] = {
            "group": g,
            "Winner (Base)": winner_ranks.get(g, 1),
        }
        row_matrix_vals = [winner_ranks.get(g, 1)]

        for v in valid_variants:
            desc = v.get("description", "variant")
            v_ranks = v.get("group_ranks", {})
            v_rank = v_ranks.get(g)
            if v_rank is None:
                # If variant lacked this group or was unranked
                row_dict[desc] = "-"
                row_matrix_vals.append(None)
            else:
                row_dict[desc] = v_rank
                row_matrix_vals.append(v_rank)

        heatmap_data.append(row_dict)
        matrix.append(row_matrix_vals)

    status_str = score.stability_status
    if score.stability is not None:
        desc_str = f"Stability Score: {round(score.stability, 3)} ({round(score.stability * 100, 1)}% agreement across {len(valid_variants)} valid variants)"
    else:
        desc_str = "Robustness untested (insufficient valid perturbation variants in dataset schema)"

    return DashboardPanel(
        panel_id=str(uuid4()),
        panel_type=PanelType.HEATMAP,
        title="Robustness Across Variant Interpretations",
        description=desc_str,
        data=heatmap_data,
        x_key="group",
        y_keys=interpretations,
        metadata={
            "groups": top_groups,
            "interpretations": interpretations,
            "matrix": matrix,
            "stability_score": score.stability,
            "stability_status": status_str,
            "variants_attempted": score.variants_attempted,
            "variants_valid": score.variants_valid,
            "variants_failed": score.variants_failed,
        },
    )


def build_alternates_panel(
    alternates: List[AlternateInterpretation],
) -> DashboardPanel:
    """Build a panel presenting runner-up alternate interpretations with scores."""
    data = []
    for alt in alternates:
        dims = [d.column for d in alt.plan.dimensions]
        dim_str = dims[0] if len(dims) == 1 else (", ".join(dims) if dims else "None")
        interp = (
            alt.plan.reasoning.interpretation
            if alt.plan.reasoning and alt.plan.reasoning.interpretation
            else f"{alt.plan.metric.aggregation.value} of {alt.plan.metric.column} by {dim_str}"
        )
        data.append({
            "plan_id": alt.plan.plan_id,
            "interpretation": interp,
            "metric": alt.plan.metric.column,
            "aggregation": alt.plan.metric.aggregation.value,
            "dimension": dim_str,
            "visualization": alt.plan.visualization.value,
            "score": round(alt.score, 4),
            "reason_not_winner": alt.reason_not_winner,
        })

    return DashboardPanel(
        panel_id=str(uuid4()),
        panel_type=PanelType.ALTERNATES,
        title="Alternate Candidate Interpretations",
        description="Scored candidate alternatives considered during ranking",
        data=data,
        metadata={"count": len(alternates)},
    )


def build_table_panel(
    plan: CandidatePlan,
    result: ExecutionResult,
) -> DashboardPanel:
    """Build raw data table panel for demoted 'Data' tab."""
    return DashboardPanel(
        panel_id=str(uuid4()),
        panel_type=PanelType.TABLE,
        title="Execution Records",
        description=f"Raw results from query ({result.row_count} rows)",
        data=result.rows or [],
        metadata={
            "columns": result.columns or [],
            "row_count": result.row_count,
            "compiled_sql": result.compiled_sql,
        },
    )


def build_dashboard_panels(
    winner_plan: CandidatePlan,
    winner_result: ExecutionResult,
    winner_score: ScoreBreakdown,
    alternates: List[AlternateInterpretation],
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> Tuple[str, List[DashboardPanel]]:
    """Assemble the complete generic dashboard panels list and headline insight.

    Always emits:
    1. Headline insight sentence
    2. Winner's main chart (KPI, BAR, or LINE based on rules)
    3. Robustness panel (heatmap data)
    4. Alternate interpretations with scores
    5. Underlying table data view
    """
    # 1. Headline insight sentence
    headline = generate_headline_insight(
        plan=winner_plan,
        result=winner_result,
        score=winner_score,
    )

    panels: List[DashboardPanel] = []

    # Headline Insight Panel
    headline_panel = DashboardPanel(
        panel_id=str(uuid4()),
        panel_type=PanelType.INSIGHT,
        title="Key Analytical Finding",
        description=headline,
        data=[{"headline": headline}],
        metadata={
            "metric": winner_plan.metric.column,
            "aggregation": winner_plan.metric.aggregation.value,
            "stability": winner_score.stability,
        },
    )
    panels.append(headline_panel)

    # 2. Winner's Main Chart
    main_chart = select_main_chart_panel(
        plan=winner_plan,
        result=winner_result,
        semantic_profile=semantic_profile,
    )
    panels.append(main_chart)

    # 3. Robustness Panel (Heatmap Data)
    robustness_panel = build_robustness_heatmap_panel(
        plan=winner_plan,
        result=winner_result,
        score=winner_score,
    )
    panels.append(robustness_panel)

    # 4. Alternate Interpretations
    if alternates:
        alternates_panel = build_alternates_panel(alternates)
        panels.append(alternates_panel)

    # 5. Underlying Tabular Data
    table_panel = build_table_panel(
        plan=winner_plan,
        result=winner_result,
    )
    panels.append(table_panel)

    return headline, panels
