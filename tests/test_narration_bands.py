"""Unit tests for narration effect-size bands and boundary conditions."""

import pytest
from orchestrator.discovery.narration import EFFECT_SIZE_BANDS, get_strength_wording
from orchestrator.discovery.schemas import InsightType


def test_r_0_42_is_moderate():
    """Explicit user test requirement: r = 0.42 must map to 'moderate'."""
    assert get_strength_wording(InsightType.CORRELATION, 0.42) == "moderate"
    assert get_strength_wording(InsightType.CORRELATION, -0.42) == "moderate"


def test_correlation_band_boundaries():
    """Test every boundary of CORRELATION: [0.10, 0.30, 0.50, 0.70]."""
    # 0.0 to < 0.10 -> negligible
    assert get_strength_wording(InsightType.CORRELATION, 0.0) == "negligible"
    assert get_strength_wording(InsightType.CORRELATION, 0.099) == "negligible"

    # 0.10 to < 0.30 -> weak
    assert get_strength_wording(InsightType.CORRELATION, 0.10) == "weak"
    assert get_strength_wording(InsightType.CORRELATION, 0.299) == "weak"

    # 0.30 to < 0.50 -> moderate
    assert get_strength_wording(InsightType.CORRELATION, 0.30) == "moderate"
    assert get_strength_wording(InsightType.CORRELATION, 0.499) == "moderate"

    # 0.50 to < 0.70 -> strong
    assert get_strength_wording(InsightType.CORRELATION, 0.50) == "strong"
    assert get_strength_wording(InsightType.CORRELATION, 0.699) == "strong"

    # >= 0.70 -> very strong
    assert get_strength_wording(InsightType.CORRELATION, 0.70) == "very strong"
    assert get_strength_wording(InsightType.CORRELATION, 0.95) == "very strong"


def test_segment_gap_band_boundaries():
    """Test every boundary of SEGMENT_GAP: [0.01, 0.06, 0.14]."""
    # < 0.01 -> negligible
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.0) == "negligible"
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.009) == "negligible"

    # 0.01 to < 0.06 -> weak
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.01) == "weak"
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.059) == "weak"

    # 0.06 to < 0.14 -> moderate
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.06) == "moderate"
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.139) == "moderate"

    # >= 0.14 -> strong
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.14) == "strong"
    assert get_strength_wording(InsightType.SEGMENT_GAP, 0.35) == "strong"


def test_trend_band_boundaries():
    """Test every boundary of TREND: [0.10, 0.30, 0.50, 0.70]."""
    assert get_strength_wording(InsightType.TREND, 0.05) == "negligible"
    assert get_strength_wording(InsightType.TREND, 0.10) == "weak"
    assert get_strength_wording(InsightType.TREND, 0.30) == "moderate"
    assert get_strength_wording(InsightType.TREND, 0.50) == "strong"
    assert get_strength_wording(InsightType.TREND, 0.70) == "very strong"


def test_ranking_band_boundaries():
    """Test every boundary of RANKING: [0.20, 0.50]."""
    assert get_strength_wording(InsightType.RANKING, 0.15) == "weak"
    assert get_strength_wording(InsightType.RANKING, 0.20) == "moderate"
    assert get_strength_wording(InsightType.RANKING, 0.49) == "moderate"
    assert get_strength_wording(InsightType.RANKING, 0.50) == "strong"
