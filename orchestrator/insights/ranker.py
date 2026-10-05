"""Insight Ranking, Deduplication, and Diversity Selector (Step 6).

Implements:
1. Deterministic scoring of evidence strength and analytical relevance.
2. Exact deduplication of redundant claims.
3. Diversity-aware selection across the 7 insight types.
"""

from __future__ import annotations

import math
from typing import Dict, List, Set, Tuple

from orchestrator.insights.schemas import (
    EvidenceGroundedInsight,
    InsightType,
)


def _compute_insight_importance(insight: EvidenceGroundedInsight) -> float:
    """Compute deterministic importance score (0.0 to 1.0) based on analytical magnitude."""
    itype = insight.type
    vals = insight.evidence.values
    stats = insight.evidence.statistical_metadata

    score = 0.50

    if itype == InsightType.KPI:
        # Base KPI has baseline importance
        score = 0.70

    elif itype == InsightType.RANKING:
        diff_pct = abs(float(vals.get("difference_pct", 0.0)))
        # Scale by spread (e.g. 100% spread -> +0.25)
        spread_boost = min(0.30, diff_pct / 400.0)
        score = 0.65 + spread_boost

    elif itype == InsightType.GROUP_COMPARISON:
        prem_pct = abs(float(vals.get("relative_premium_pct", 0.0)))
        score = 0.60 + min(0.30, prem_pct / 300.0)

    elif itype == InsightType.DISTRIBUTION:
        share = float(vals.get("dominant_share_pct", 0.0))
        # High concentration (> 50%) is more notable
        score = 0.55 + min(0.30, (share / 100.0) * 0.30)

    elif itype == InsightType.TEMPORAL_TREND:
        pct_chg = abs(float(vals.get("percent_change", 0.0)))
        score = 0.68 + min(0.28, pct_chg / 200.0)

    elif itype == InsightType.OUTLIER:
        frac = float(vals.get("outlier_fraction_pct", 0.0))
        score = 0.65 + min(0.25, (1.0 - (frac / 100.0)) * 0.25)

    elif itype == InsightType.CORRELATION:
        r_val = abs(float(vals.get("correlation_r", 0.0)))
        score = 0.60 + (r_val * 0.35)

    return round(min(1.0, max(0.1, score)), 3)


class InsightRanker:
    """Ranks, deduplicates, and selects a diverse set of evidence-grounded insights."""

    def select_top_insights(
        self,
        insights: List[EvidenceGroundedInsight],
        max_insights: int = 8,
    ) -> List[EvidenceGroundedInsight]:
        """Deduplicate, score, and select top diverse insights.

        Strategy:
        1. Remove exact duplicate signatures (same type + metric + dimension).
        2. Assign computed importance scores.
        3. Round-robin / diversity guarantee across insight types.
        """
        if not insights:
            return []

        # 1. Deduplicate by logical signature
        unique_insights: List[EvidenceGroundedInsight] = []
        seen_signatures: Set[str] = set()

        for ins in insights:
            sig = f"{ins.type.value}:{ins.evidence.metric_column}:{ins.evidence.dimension_column}:{ins.evidence.secondary_metric}"
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                unique_insights.append(ins)

        # 2. Score and sort by importance descending
        scored: List[Tuple[float, EvidenceGroundedInsight]] = []
        for ins in unique_insights:
            imp = _compute_insight_importance(ins)
            # Create scored copy with updated importance
            updated_ins = EvidenceGroundedInsight(
                insight_id=ins.insight_id,
                type=ins.type,
                title=ins.title,
                statement=ins.statement,
                interpretation=ins.interpretation,
                importance=imp,
                confidence=ins.confidence,
                evidence=ins.evidence,
                warnings=ins.warnings,
                provenance=ins.provenance,
            )
            scored.append((imp, updated_ins))

        scored.sort(key=lambda x: x[0], reverse=True)

        # 3. Diversity-aware selection: pick top 1 per insight type first, then fill remaining
        selected: List[EvidenceGroundedInsight] = []
        by_type: Dict[InsightType, List[EvidenceGroundedInsight]] = {}
        for imp, ins in scored:
            by_type.setdefault(ins.type, []).append(ins)

        # Desired type priority order for balanced coverage
        type_order = [
            InsightType.KPI,
            InsightType.RANKING,
            InsightType.TEMPORAL_TREND,
            InsightType.GROUP_COMPARISON,
            InsightType.CORRELATION,
            InsightType.OUTLIER,
            InsightType.DISTRIBUTION,
        ]

        # First pass: take highest scoring per type
        for t in type_order:
            if t in by_type and by_type[t]:
                selected.append(by_type[t].pop(0))
                if len(selected) >= max_insights:
                    break

        # Second pass: fill remaining slots with highest scoring remaining
        if len(selected) < max_insights:
            remaining = [ins for type_list in by_type.values() for ins in type_list]
            remaining.sort(key=lambda x: x.importance, reverse=True)
            for ins in remaining:
                if len(selected) >= max_insights:
                    break
                selected.append(ins)

        return selected
