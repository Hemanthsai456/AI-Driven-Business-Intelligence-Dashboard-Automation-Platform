"""Unit tests for Stage F: Headline robustness floor and stability badge behavior.

Requirement:
If the selected insight's robustness is below the configured floor,
the headline must say so, with an amber "Low stability" badge,
and must NOT say "leads".
"""

import pytest
from orchestrator.panels import generate_headline_insight, build_dashboard_panels
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    ScoreBreakdown,
)


def test_headline_below_robustness_floor_says_low_stability_and_not_leads():
    """When robustness is below configured floor, headline must say so and not say 'leads'."""
    plan = CandidatePlan(
        dataset_id="test_ds",
        intent="Revenue by Region",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Region")],
        reasoning=PlanReasoning(interpretation="Total revenue by region", evidence=[]),
    )

    result = ExecutionResult(
        plan_id=plan.plan_id,
        status=ExecutionStatus.SUCCESS,
        columns=["Region", "sum_revenue"],
        rows=[
            {"Region": "North", "sum_revenue": 50000},
            {"Region": "South", "sum_revenue": 45000},
            {"Region": "West", "sum_revenue": 30000},
        ],
        row_count=3,
    )

    # Robustness = 0.20, which is below floor of 0.35
    low_rob_score = ScoreBreakdown(
        evidence=0.9,
        coverage=1.0,
        stability=0.20,
        assumptions=0.0,
        total=0.55,
        stability_status="TESTED",
    )

    headline = generate_headline_insight(plan, result, low_rob_score, robustness_floor=0.35)

    # 1. Headline must say "Low stability"
    assert "Low stability" in headline
    # 2. Headline must NOT say "leads"
    assert "leads" not in headline.lower()
    # 3. Mentions robustness percentage
    assert "20.0%" in headline

    # Also test build_dashboard_panels attaches amber badge metadata
    _, panels = build_dashboard_panels(
        winner_plan=plan,
        winner_result=result,
        winner_score=low_rob_score,
        alternates=[],
        robustness_floor=0.35,
    )

    headline_panel = panels[0]
    assert headline_panel.metadata.get("is_low_stability") is True
    assert headline_panel.metadata.get("badge") == "Low stability"
    assert headline_panel.metadata.get("badge_variant") == "amber"


def test_headline_above_robustness_floor_can_say_leads():
    """When robustness is above configured floor, standard winner phrasing with 'leads' is permitted."""
    plan = CandidatePlan(
        dataset_id="test_ds",
        intent="Revenue by Region",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column="Region")],
        reasoning=PlanReasoning(interpretation="Total revenue by region", evidence=[]),
    )

    result = ExecutionResult(
        plan_id=plan.plan_id,
        status=ExecutionStatus.SUCCESS,
        columns=["Region", "sum_revenue"],
        rows=[
            {"Region": "North", "sum_revenue": 50000},
            {"Region": "South", "sum_revenue": 45000},
        ],
        row_count=2,
    )

    high_rob_score = ScoreBreakdown(
        evidence=0.9,
        coverage=1.0,
        stability=0.85,
        assumptions=0.0,
        total=0.92,
        stability_status="TESTED",
    )

    headline = generate_headline_insight(plan, result, high_rob_score, robustness_floor=0.35)
    assert "leads" in headline
    assert "North" in headline
    assert "85.0%" in headline


def test_headline_kpi_below_floor_says_low_stability():
    """When KPI has robustness below floor, headline says low stability."""
    plan = CandidatePlan(
        dataset_id="test_ds",
        intent="Total Revenue",
        metric=MetricSpec(column="Revenue", aggregation=AggregationType.SUM),
        dimensions=[],
        reasoning=PlanReasoning(interpretation="Total revenue", evidence=[]),
    )

    result = ExecutionResult(
        plan_id=plan.plan_id,
        status=ExecutionStatus.SUCCESS,
        columns=["sum_revenue"],
        rows=[{"sum_revenue": 125000}],
        row_count=1,
    )

    low_rob_score = ScoreBreakdown(
        evidence=0.9,
        coverage=1.0,
        stability=0.25,
        assumptions=0.0,
        total=0.60,
        stability_status="TESTED",
    )

    headline = generate_headline_insight(plan, result, low_rob_score, robustness_floor=0.35)
    assert "Low stability" in headline
    assert "leads" not in headline.lower()
