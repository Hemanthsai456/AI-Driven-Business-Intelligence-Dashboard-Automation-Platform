"""Unit tests for chart mapping rules per insight type.

Requirements:
- CORRELATION -> scatter
- SEGMENT_GAP and RANKING -> bar
- COMPOSITION -> donut or stacked
- TREND -> line
- DISTRIBUTION -> histogram
"""

import pytest
from orchestrator.discovery.schemas import InsightType
from orchestrator.discovery.tiles import _determine_chart_type


def test_correlation_chart_type():
    assert _determine_chart_type(InsightType.CORRELATION) == "scatter"


def test_segment_gap_chart_type():
    assert _determine_chart_type(InsightType.SEGMENT_GAP) == "bar"


def test_ranking_chart_type():
    assert _determine_chart_type(InsightType.RANKING) == "bar"


def test_composition_chart_type():
    # <= 6 rows -> donut
    rows_donut = [{"category": f"Cat_{i}", "val": i * 10} for i in range(4)]
    assert _determine_chart_type(InsightType.COMPOSITION, rows=rows_donut) == "donut"

    # > 6 rows -> stacked
    rows_stacked = [{"category": f"Cat_{i}", "val": i * 10} for i in range(10)]
    assert _determine_chart_type(InsightType.COMPOSITION, rows=rows_stacked) == "stacked"


def test_trend_chart_type():
    assert _determine_chart_type(InsightType.TREND) == "line"


def test_distribution_chart_type():
    assert _determine_chart_type(InsightType.DISTRIBUTION) == "histogram"
    assert _determine_chart_type(InsightType.DISTRIBUTION_OUTLIERS) == "histogram"
