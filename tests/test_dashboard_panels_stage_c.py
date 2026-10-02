"""Backend tests for Stage C Dashboard Panels and Selection Rules.

Verifies:
1. Selection rule: no dimension -> KPI panel
2. Selection rule: temporal dimension -> LINE panel
3. Selection rule: categorical <= 12 groups -> BAR panel (full groups)
4. Selection rule: categorical > 12 groups -> BAR panel (top 10 + "Other")
5. Always emitted: headline insight sentence (metric, dimension, top group, robustness)
6. Always emitted: winner's main chart
7. Always emitted: robustness panel (heatmap data: group x interpretation)
8. Always emitted: alternate interpretations with scores
9. Full DashboardSpec integration: panels list properly populated
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from intelligence.semantic_analyzer import (
    ColumnRole,
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
)
from orchestrator.panels import (
    build_alternates_panel,
    build_dashboard_panels,
    build_robustness_heatmap_panel,
    build_table_panel,
    generate_headline_insight,
    is_temporal_dimension,
    select_main_chart_panel,
)
from orchestrator.schemas import (
    AggregationType,
    AlternateInterpretation,
    CandidatePlan,
    DashboardPanel,
    DashboardSpec,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    MetricSpec,
    OrchestratorTrace,
    PanelType,
    PlanReasoning,
    RankedCandidate,
    ScoreBreakdown,
    VisualizationType,
)
from orchestrator.winner import select_winner


def _create_mock_candidate(
    plan_id: str,
    metric_col: str = "metric_val",
    agg: AggregationType = AggregationType.SUM,
    dim_col: str | None = "cat_col",
    granularity: Granularity | None = None,
) -> CandidatePlan:
    dimensions = []
    if dim_col is not None:
        dimensions.append(DimensionSpec(column=dim_col, granularity=granularity))
    return CandidatePlan(
        plan_id=plan_id,
        dataset_id="test_ds.csv",
        intent="Analyze test intent",
        generator="test_generator",
        metric=MetricSpec(column=metric_col, aggregation=agg),
        dimensions=dimensions,
        filters=[],
        visualization=VisualizationType.BAR if dim_col else VisualizationType.KPI,
        reasoning=PlanReasoning(interpretation=f"{agg.value} of {metric_col}"),
    )


# ---------------------------------------------------------------------------
# 1. Rule: No Dimension -> KPI Panel
# ---------------------------------------------------------------------------

def test_panel_selection_no_dimension_produces_kpi():
    """When a plan has no dimension, main chart selection produces a single-value KPI panel."""
    plan = _create_mock_candidate("p_kpi", metric_col="revenue", agg=AggregationType.SUM, dim_col=None)
    result = ExecutionResult(
        plan_id="p_kpi",
        status=ExecutionStatus.SUCCESS,
        columns=["sum_revenue"],
        rows=[{"sum_revenue": 154200.5}],
        row_count=1,
    )

    panel = select_main_chart_panel(plan, result)

    assert panel.panel_type == PanelType.KPI
    assert "revenue" in panel.title.lower()
    assert len(panel.data) == 1
    assert panel.data[0]["value"] == 154200.5
    assert panel.metadata["cardinality"] == 0


# ---------------------------------------------------------------------------
# 2. Rule: Temporal Dimension -> LINE Panel
# ---------------------------------------------------------------------------

def test_panel_selection_temporal_dimension_produces_line():
    """When a dimension is temporal (via granularity or datetime role), produces a LINE panel."""
    # Sub-case A: Dimension with explicit granularity
    plan_a = _create_mock_candidate(
        "p_temporal_gran",
        metric_col="sales",
        agg=AggregationType.SUM,
        dim_col="OrderDate",
        granularity=Granularity.MONTH,
    )
    result_a = ExecutionResult(
        plan_id="p_temporal_gran",
        status=ExecutionStatus.SUCCESS,
        columns=["OrderDate", "sum_sales"],
        rows=[
            {"OrderDate": "2024-01-01", "sum_sales": 100},
            {"OrderDate": "2024-02-01", "sum_sales": 150},
            {"OrderDate": "2024-03-01", "sum_sales": 200},
        ],
        row_count=3,
    )

    panel_a = select_main_chart_panel(plan_a, result_a)
    assert panel_a.panel_type == PanelType.LINE
    assert panel_a.x_key == "OrderDate"
    assert "sales" in panel_a.title.lower()
    assert len(panel_a.data) == 3

    # Sub-case B: Dimension recognized via semantic profile ColumnRole.DATETIME
    plan_b = _create_mock_candidate("p_temporal_role", metric_col="spend", dim_col="EventTimestamp")
    semantic_profile = DatasetSemanticProfile(
        dataset_id="test_ds.csv",
        column_evidences={
            "EventTimestamp": ColumnSemanticEvidence(
                column_name="EventTimestamp",
                candidate_role=ColumnRole.DATETIME,
                confidence=0.95,
                confidence_level="HIGH",
            ),
            "spend": ColumnSemanticEvidence(
                column_name="spend",
                candidate_role=ColumnRole.MEASURE,
                confidence=0.90,
                confidence_level="HIGH",
            ),
        },
    )
    result_b = ExecutionResult(
        plan_id="p_temporal_role",
        status=ExecutionStatus.SUCCESS,
        columns=["EventTimestamp", "sum_spend"],
        rows=[{"EventTimestamp": "2024-Q1", "sum_spend": 50}],
        row_count=1,
    )

    panel_b = select_main_chart_panel(plan_b, result_b, semantic_profile=semantic_profile)
    assert panel_b.panel_type == PanelType.LINE
    assert panel_b.metadata["is_temporal"] is True


# ---------------------------------------------------------------------------
# 3. Rule: Categorical Dimension <= 12 Groups -> BAR Panel (All Groups)
# ---------------------------------------------------------------------------

def test_panel_selection_categorical_le_12_produces_full_bar():
    """Categorical dimension with <= 12 distinct groups renders a BAR panel containing all groups."""
    plan = _create_mock_candidate("p_cat_5", metric_col="active_users", dim_col="Region")
    rows = [{"Region": f"Region_{i}", "sum_active_users": i * 10} for i in range(1, 6)]
    result = ExecutionResult(
        plan_id="p_cat_5",
        status=ExecutionStatus.SUCCESS,
        columns=["Region", "sum_active_users"],
        rows=rows,
        row_count=5,
    )

    panel = select_main_chart_panel(plan, result)

    assert panel.panel_type == PanelType.BAR
    assert panel.metadata["cardinality"] == 5
    assert panel.metadata["collapsed"] is False
    assert len(panel.data) == 5
    assert panel.x_key == "Region"


# ---------------------------------------------------------------------------
# 4. Rule: Categorical Dimension > 12 Groups -> BAR Panel (Top 10 + "Other")
# ---------------------------------------------------------------------------

def test_panel_selection_categorical_gt_12_compresses_to_top10_plus_other():
    """Categorical dimension with > 12 groups renders a BAR panel compressed to top 10 plus 'Other'."""
    plan = _create_mock_candidate("p_cat_25", metric_col="units", agg=AggregationType.SUM, dim_col="ItemCode")
    # 25 categories with descending metric values 250 down to 10
    rows = [{"ItemCode": f"Item_{i}", "sum_units": i * 10} for i in range(25, 0, -1)]
    result = ExecutionResult(
        plan_id="p_cat_25",
        status=ExecutionStatus.SUCCESS,
        columns=["ItemCode", "sum_units"],
        rows=rows,
        row_count=25,
    )

    panel = select_main_chart_panel(plan, result)

    assert panel.panel_type == PanelType.BAR
    assert panel.metadata["cardinality"] == 25
    assert panel.metadata["collapsed"] is True
    assert panel.metadata["top_k"] == 10
    assert panel.metadata["other_count"] == 15

    # Exactly 11 rows: top 10 + 1 'Other'
    assert len(panel.data) == 11
    # First 10 items match top 10 items
    assert panel.data[0]["ItemCode"] == "Item_25"
    assert panel.data[0]["sum_units"] == 250
    assert panel.data[9]["ItemCode"] == "Item_16"
    assert panel.data[9]["sum_units"] == 160

    # 11th item is consolidated 'Other'
    other_row = panel.data[10]
    assert other_row["ItemCode"] == "Other"
    assert other_row["_is_other"] is True
    # Sum of items 15 down to 1 = sum(150, 140, ..., 10) = 1200
    expected_sum = sum(i * 10 for i in range(15, 0, -1))
    assert other_row["sum_units"] == expected_sum


# ---------------------------------------------------------------------------
# 5. Always Emitted: Headline Insight Sentence
# ---------------------------------------------------------------------------

def test_headline_insight_generation():
    """Headline insight incorporates metric, dimension, top group, and robustness."""
    plan = _create_mock_candidate("p_head", metric_col="Profit", agg=AggregationType.SUM, dim_col="Segment")
    result = ExecutionResult(
        plan_id="p_head",
        status=ExecutionStatus.SUCCESS,
        columns=["Segment", "sum_Profit"],
        rows=[
            {"Segment": "Enterprise", "sum_Profit": 85000.0},
            {"Segment": "Consumer", "sum_Profit": 32000.0},
        ],
        row_count=2,
    )
    score_tested = ScoreBreakdown(
        evidence=0.8,
        coverage=0.9,
        stability=0.785,
        assumptions=0.0,
        total=0.85,
        stability_status="TESTED",
    )

    headline = generate_headline_insight(plan, result, score_tested)

    # Must contain top group, metric, dimension, robustness
    assert "Enterprise" in headline
    assert "Profit" in headline
    assert "Segment" in headline
    assert "78.5%" in headline

    # Case where robustness is None (UNTESTED)
    score_untested = ScoreBreakdown(
        evidence=0.8,
        coverage=0.9,
        stability=None,
        assumptions=0.0,
        total=0.85,
        stability_status="UNTESTED",
    )
    headline_untested = generate_headline_insight(plan, result, score_untested)
    assert "Enterprise" in headline_untested
    assert "untested" in headline_untested.lower()


# ---------------------------------------------------------------------------
# 6. Always Emitted: Robustness Heatmap Panel
# ---------------------------------------------------------------------------

def test_robustness_heatmap_panel_emits_group_by_interpretation():
    """Robustness panel produces a group x interpretation matrix with ranking values."""
    plan = _create_mock_candidate("p_rob", metric_col="Score", dim_col="Department")
    result = ExecutionResult(
        plan_id="p_rob",
        status=ExecutionStatus.SUCCESS,
        columns=["Department", "sum_Score"],
        rows=[
            {"Department": "Eng", "sum_Score": 100},
            {"Department": "Sales", "sum_Score": 80},
            {"Department": "HR", "sum_Score": 50},
        ],
        row_count=3,
    )
    score = ScoreBreakdown(
        evidence=0.9,
        coverage=0.9,
        stability=0.82,
        assumptions=0.0,
        total=0.88,
        stability_status="TESTED",
        variants_attempted=2,
        variants_valid=2,
        variant_details=[
            {
                "description": "alternate_measure:Headcount",
                "top1_match": 1.0,
                "spearman": 0.85,
                "score": 0.925,
                "group_ranks": {"Eng": 1, "Sales": 3, "HR": 2},
            },
            {
                "description": "alternate_aggregation:AVG",
                "top1_match": 1.0,
                "spearman": 1.0,
                "score": 1.0,
                "group_ranks": {"Eng": 1, "Sales": 2, "HR": 3},
            },
        ],
    )

    panel = build_robustness_heatmap_panel(plan, result, score)

    assert panel.panel_type == PanelType.HEATMAP
    assert panel.x_key == "group"
    assert "Winner (Base)" in panel.y_keys
    assert "alternate_measure:Headcount" in panel.y_keys
    assert "alternate_aggregation:AVG" in panel.y_keys

    # Verify rows in heatmap data
    assert len(panel.data) == 3
    eng_row = next(r for r in panel.data if r["group"] == "Eng")
    assert eng_row["Winner (Base)"] == 1
    assert eng_row["alternate_measure:Headcount"] == 1
    assert eng_row["alternate_aggregation:AVG"] == 1

    sales_row = next(r for r in panel.data if r["group"] == "Sales")
    assert sales_row["Winner (Base)"] == 2
    assert sales_row["alternate_measure:Headcount"] == 3
    assert sales_row["alternate_aggregation:AVG"] == 2


# ---------------------------------------------------------------------------
# 7. Always Emitted: Alternate Interpretations Panel
# ---------------------------------------------------------------------------

def test_alternate_interpretations_panel():
    """Alternate interpretations panel provides scored runner-ups with rationale."""
    alt_plan = _create_mock_candidate("p_alt", metric_col="Cost", dim_col="Vendor")
    alternates = [
        AlternateInterpretation(
            plan=alt_plan,
            score=0.742,
            reason_not_winner="Rank 2 (score: 0.742)",
        )
    ]

    panel = build_alternates_panel(alternates)

    assert panel.panel_type == PanelType.ALTERNATES
    assert len(panel.data) == 1
    item = panel.data[0]
    assert item["plan_id"] == "p_alt"
    assert item["score"] == 0.742
    assert "Vendor" in item["dimension"]
    assert "Rank 2" in item["reason_not_winner"]


# ---------------------------------------------------------------------------
# 8. Full Integration: build_dashboard_panels & DashboardSpec
# ---------------------------------------------------------------------------

def test_build_dashboard_panels_and_dashboardspec_integration():
    """Full DashboardSpec properly receives headline and panels list."""
    c1 = _create_mock_candidate("p1_winner", metric_col="Revenue", dim_col="Category")
    r1 = ExecutionResult(
        plan_id="p1_winner",
        status=ExecutionStatus.SUCCESS,
        columns=["Category", "sum_Revenue"],
        rows=[{"Category": "Electronics", "sum_Revenue": 50000}, {"Category": "Apparel", "sum_Revenue": 30000}],
        row_count=2,
    )
    s1 = ScoreBreakdown(evidence=0.9, coverage=0.8, stability=0.75, assumptions=0.0, total=0.82)

    c2 = _create_mock_candidate("p2_alt", metric_col="Units", dim_col="Category")
    r2 = ExecutionResult(
        plan_id="p2_alt",
        status=ExecutionStatus.SUCCESS,
        columns=["Category", "sum_Units"],
        rows=[{"Category": "Electronics", "sum_Units": 500}],
        row_count=1,
    )
    s2 = ScoreBreakdown(evidence=0.7, coverage=0.7, stability=0.6, assumptions=0.0, total=0.65)

    ranked = [(c1, r1, s1, 1), (c2, r2, s2, 2)]

    spec = select_winner(
        ranked=ranked,
        dataset_id="test_sales.csv",
        intent="Show revenue by category",
        context_hash="hash_123",
    )

    assert isinstance(spec, DashboardSpec)
    assert spec.headline is not None
    assert "Electronics" in spec.headline
    assert "Revenue" in spec.headline

    assert len(spec.panels) >= 4
    panel_types = [p.panel_type for p in spec.panels]
    assert PanelType.INSIGHT in panel_types
    assert PanelType.BAR in panel_types
    assert PanelType.HEATMAP in panel_types
    assert PanelType.ALTERNATES in panel_types
    assert PanelType.TABLE in panel_types
