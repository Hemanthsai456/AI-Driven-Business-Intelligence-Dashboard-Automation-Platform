"""Greedy Diversity-Aware Dashboard Selection Engine (Stage E5).

Selects up to 8 diverse, high-value insights under hard constraints:
- At most 8 insights in total
- At most 2 per measure
- At most 2 per dimension
- At most one panel per (type, measure, dimension) combination
- Marginal utility = relevance (score + topic bias) - redundancy penalty

Layout:
- KPI strip first
- Trend next (if exists)
- Highest-scoring comparisons next
- If < 3 pass: render fewer with "the data doesn't support more", never pad.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from orchestrator.discovery.schemas import DiscoveredInsight, InsightType


def select_diverse_dashboard_insights(
    passed_insights: List[DiscoveredInsight],
    topic: Optional[str] = None,
    max_total: int = 8,
    max_per_measure: int = 2,
    max_per_dimension: int = 2,
    redundancy_penalty_weight: float = 0.20,
) -> Tuple[List[DiscoveredInsight], List[Dict[str, Any]], Optional[str]]:
    """Greedy diversity-aware selection from eligible insights.

    Returns:
        (selected_insights, selection_rejected_info, notice_message)
    """
    if not passed_insights:
        return [], [], "the data doesn't support more (no insights met statistical and quality floors)"

    topic_tokens = set(topic.lower().split()) if topic else set()

    def _compute_relevance(insight: DiscoveredInsight) -> float:
        cand = insight.candidate
        score = insight.score.total_score
        # Topic bias: if brief names a topic, boost candidates referencing that topic
        if topic_tokens:
            matches = 0
            if any(t in cand.measure.lower() for t in topic_tokens):
                matches += 1
            if cand.dimension and any(t in cand.dimension.lower() for t in topic_tokens):
                matches += 1
            if matches > 0:
                score += 0.25 * matches
        return score

    # Track usage counts
    measure_counts: Counter = Counter()
    dimension_counts: Counter = Counter()
    seen_combinations: Set[Tuple[str, str, Optional[str]]] = set()

    selected: List[DiscoveredInsight] = []
    pool = list(passed_insights)
    selection_rejected: List[Dict[str, Any]] = []

    while pool and len(selected) < max_total:
        best_candidate: Optional[DiscoveredInsight] = None
        best_marginal_score: float = -999.0
        best_idx: int = -1

        for idx, ins in enumerate(pool):
            c = ins.candidate
            m = c.measure
            d = c.dimension
            comb = (c.insight_type.value, m, d)

            # Check hard constraints
            if comb in seen_combinations:
                continue
            if measure_counts[m] >= max_per_measure:
                continue
            if d and dimension_counts[d] >= max_per_dimension:
                continue

            # Redundancy penalty
            relevance = _compute_relevance(ins)
            redundancy = 0.0
            if measure_counts[m] > 0:
                redundancy += redundancy_penalty_weight
            if d and dimension_counts[d] > 0:
                redundancy += redundancy_penalty_weight

            marginal = relevance - redundancy
            if marginal > best_marginal_score:
                best_marginal_score = marginal
                best_candidate = ins
                best_idx = idx

        if best_candidate is None:
            # No remaining candidate satisfies hard constraints
            break

        # Select the winning candidate
        selected.append(best_candidate)
        pool.pop(best_idx)

        # Update constraints
        m_sel = best_candidate.candidate.measure
        d_sel = best_candidate.candidate.dimension
        measure_counts[m_sel] += 1
        if d_sel:
            dimension_counts[d_sel] += 1
        seen_combinations.add((best_candidate.candidate.insight_type.value, m_sel, d_sel))

    # Any remaining unselected candidates in pool get rejection logged
    for remaining in pool:
        c = remaining.candidate
        comb = (c.insight_type.value, c.measure, c.dimension)
        if comb in seen_combinations:
            reason = f"Duplicate panel combination ({c.insight_type.value}, {c.measure}, {c.dimension})"
        elif measure_counts[c.measure] >= max_per_measure:
            reason = f"Exceeded limit of {max_per_measure} panels for measure '{c.measure}'"
        elif c.dimension and dimension_counts[c.dimension] >= max_per_dimension:
            reason = f"Exceeded limit of {max_per_dimension} panels for dimension '{c.dimension}'"
        else:
            reason = "Exceeded dashboard 8-panel diversity cap (lower marginal score than selected)"

        desc = (
            f"{c.insight_type.value}: {c.aggregation.value}({c.measure})"
            + (f" by {c.dimension}" if c.dimension else "")
        )
        selection_rejected.append({
            "candidate_id": c.candidate_id,
            "insight_type": c.insight_type.value,
            "description": desc,
            "measure": c.measure,
            "dimension": c.dimension,
            "rejection_stage": "DIVERSITY",
            "reason": reason,
            "score": remaining.score.total_score,
            "p_value": remaining.score.p_value,
        })

    # Layout Sorting:
    # 1. KPI strip first (TOTAL_KPI)
    # 2. Trend next (TREND)
    # 3. Highest-scoring comparisons next
    kpis: List[DiscoveredInsight] = []
    trends: List[DiscoveredInsight] = []
    comparisons: List[DiscoveredInsight] = []

    for ins in selected:
        if ins.candidate.insight_type == InsightType.TOTAL_KPI:
            kpis.append(ins)
        elif ins.candidate.insight_type == InsightType.TREND:
            trends.append(ins)
        else:
            comparisons.append(ins)

    # Sort each section by score descending
    kpis.sort(key=lambda x: x.score.total_score, reverse=True)
    trends.sort(key=lambda x: x.score.total_score, reverse=True)
    comparisons.sort(key=lambda x: x.score.total_score, reverse=True)

    ordered_selected = kpis + trends + comparisons

    # Assign rank numbers
    ranked_final: List[DiscoveredInsight] = []
    for rank_idx, item in enumerate(ordered_selected, start=1):
        ranked_final.append(
            DiscoveredInsight(
                candidate=item.candidate,
                execution_result=item.execution_result,
                score=item.score,
                narration=item.narration,
                why_chosen=item.why_chosen,
                rank=rank_idx,
            )
        )

    # Notice message if fewer than 3 insights pass
    notice: Optional[str] = None
    if len(ranked_final) < 3:
        notice = "the data doesn't support more (fewer than 3 insights passed statistical and quality floors)"

    return ranked_final, selection_rejected, notice
