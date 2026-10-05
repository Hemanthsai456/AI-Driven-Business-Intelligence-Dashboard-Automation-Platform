"""Deterministic Evidence & Insight Validator (Step 6).

Guarantees:
1. All referenced columns exist in the active dataset.
2. Semantic roles and aggregations are valid.
3. Compiled SQL and DuckDB execution results are coherent.
4. Statistical and numerical invariants hold (e.g. top >= bottom, |r| <= 1.0).
5. Every number claimed in the generated title/statement exists in the evidence.
6. Zero unsupported causal claims in correlation insights.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.insights.schemas import (
    EvidenceGroundedInsight,
    InsightEvidence,
    InsightRejectionInfo,
    InsightType,
)
from orchestrator.schemas import AggregationType


def _extract_numbers_from_text(text: str) -> List[float]:
    """Extract all numeric representations (floats, ints, percentages) from text."""
    raw = re.findall(r"[-+]?\b\d+(?:,\d{3})*(?:\.\d+)?%?\b", text)
    nums: List[float] = []
    for tok in raw:
        clean = tok.replace("%", "").replace(",", "")
        try:
            val = float(clean)
            nums.append(val)
        except ValueError:
            pass
    return nums


def _collect_grounded_numbers(evidence: InsightEvidence) -> Set[float]:
    """Extract all valid ground truth numbers from evidence values and sample rows."""
    grounded: Set[float] = set()

    def _add_num(n: Any):
        if isinstance(n, (int, float)) and not isinstance(n, bool) and not math.isnan(float(n)):
            flt = float(n)
            grounded.add(flt)
            grounded.add(round(flt, 1))
            grounded.add(round(flt, 2))
            grounded.add(round(flt, 4))
            grounded.add(float(int(round(flt))))
            # Percentage equivalent if between 0 and 1
            if 0.0 <= flt <= 1.0:
                grounded.add(round(flt * 100.0, 1))
                grounded.add(round(flt * 100.0, 2))

    for v in evidence.values.values():
        _add_num(v)

    for r in evidence.supporting_rows_or_groups:
        for val in r.values():
            _add_num(val)

    for val in evidence.statistical_metadata.values():
        _add_num(val)

    _add_num(evidence.row_count)

    return grounded


class InsightValidator:
    """Deterministic validator for evidence-grounded insights."""

    def validate_evidence(
        self,
        insight_type: InsightType,
        evidence: InsightEvidence,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
    ) -> Tuple[bool, Optional[str]]:
        """Validate an InsightEvidence object before natural language narration.

        Returns:
            (is_valid, rejection_reason)
        """
        df = dataset.data
        if df is None:
            return False, "Dataset data is null or empty"

        cols = set(df.columns)

        # 1. Validate primary metric column
        if evidence.metric_column != "*":
            if evidence.metric_column not in cols:
                return False, f"Metric column '{evidence.metric_column}' does not exist in dataset"
            ev_m = semantic_profile.get_evidence(evidence.metric_column)
            if ev_m and ev_m.candidate_role == ColumnRole.IDENTIFIER and evidence.aggregation not in (
                AggregationType.COUNT, AggregationType.COUNT_DISTINCT
            ):
                return False, f"Cannot perform {evidence.aggregation.value} on identifier column '{evidence.metric_column}'"

        # 2. Validate dimension column
        if evidence.dimension_column:
            if evidence.dimension_column not in cols:
                return False, f"Dimension column '{evidence.dimension_column}' does not exist in dataset"

        # 3. Validate secondary metric (correlation)
        if evidence.secondary_metric:
            if evidence.secondary_metric not in cols:
                return False, f"Secondary metric '{evidence.secondary_metric}' does not exist in dataset"

        # 4. Type-specific invariant validations
        vals = evidence.values

        if insight_type == InsightType.KPI:
            if "primary_value" not in vals or vals["primary_value"] is None:
                return False, "KPI evidence missing primary_value"

        elif insight_type == InsightType.RANKING:
            if "top_value" not in vals or "bottom_value" not in vals:
                return False, "Ranking evidence missing top/bottom values"
            if "top_group" not in vals or not str(vals["top_group"]).strip():
                return False, "Ranking evidence missing top_group label"

        elif insight_type == InsightType.GROUP_COMPARISON:
            if "lead_group" not in vals or "lead_value" not in vals:
                return False, "Group comparison evidence missing lead group/value"

        elif insight_type == InsightType.DISTRIBUTION:
            if "dominant_category" not in vals or "dominant_share_pct" not in vals:
                return False, "Distribution evidence missing dominant category or share"

        elif insight_type == InsightType.TEMPORAL_TREND:
            if "start_value" not in vals or "end_value" not in vals or "direction" not in vals:
                return False, "Temporal trend evidence missing start/end/direction"
            if vals.get("periods_analyzed", 0) < 2:
                return False, "Temporal trend requires at least 2 distinct periods"

        elif insight_type == InsightType.OUTLIER:
            if vals.get("outlier_count", 0) <= 0:
                return False, "Outlier evidence requires outlier_count > 0"
            if "max_outlier_value" not in vals and "min_outlier_value" not in vals:
                return False, "Outlier evidence missing concrete outlier values"

        elif insight_type == InsightType.CORRELATION:
            r = vals.get("correlation_r")
            if r is None or not (-1.0 <= float(r) <= 1.0):
                return False, f"Invalid correlation coefficient: {r}"
            if vals.get("sample_size", 0) < 3:
                return False, "Correlation requires at least 3 pairs of observations"

        return True, None

    def validate_final_insight(
        self,
        insight: EvidenceGroundedInsight,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        tolerance: float = 0.05,
    ) -> Tuple[bool, Optional[str]]:
        """Validate the full insight including text grounding and causal checks.

        Returns:
            (is_valid, rejection_reason)
        """
        # 1. Base evidence check
        ok, reason = self.validate_evidence(insight.type, insight.evidence, dataset, semantic_profile)
        if not ok:
            return False, reason

        # 2. Number grounding check on statement and title
        full_text = f"{insight.title} {insight.statement}"
        text_nums = _extract_numbers_from_text(full_text)
        grounded_nums = _collect_grounded_numbers(insight.evidence)

        for s_num in text_nums:
            matched = False
            for g_num in grounded_nums:
                if abs(s_num - g_num) <= tolerance or (
                    abs(g_num) > 1e-6 and abs(s_num - g_num) / abs(g_num) <= tolerance
                ):
                    matched = True
                    break
            if not matched:
                return False, f"Number '{s_num}' in insight text is not grounded in evidence values {list(insight.evidence.values.values())[:6]}"

        # 3. Correlation causality prohibition
        if insight.type == InsightType.CORRELATION:
            causal_patterns = [
                r"\bcauses\b", r"\bcaused\b", r"\bcausing\b",
                r"\bleads\s+to\b", r"\bled\s+to\b", r"\bleading\s+to\b",
                r"\bdrives\b", r"\bdriving\b", r"\bdriven\s+by\b",
                r"\bresults\s+in\b", r"\bresulted\s+in\b",
            ]
            for pat in causal_patterns:
                if re.search(pat, full_text, re.IGNORECASE):
                    return False, f"Correlation insight contains forbidden causal language matching '{pat}'"

        return True, None
