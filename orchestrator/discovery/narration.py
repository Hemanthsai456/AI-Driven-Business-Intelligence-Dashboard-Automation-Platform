"""Narration, Hallucination Guard, and Explainability Engine (Stage E6).

Generates grounded one-sentence insights from executed numbers.
Strictly verifies that every number in the sentence appears in the executed result
or directly verified derived properties, and drops any sentence that fails the check.
Generates 'why this was chosen' lines and aggregates 'considered but rejected' lists.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from orchestrator.discovery.schemas import DiscoveredInsight, InsightType
from orchestrator.schemas import ExecutionResult


def _extract_numbers_from_sentence(text: str) -> List[float]:
    """Extract all numeric tokens (integers, floats, percentages, formatted numbers)."""
    # Matches numbers like 1,234.56, 12.5%, -0.85, 42
    raw_tokens = re.findall(r"[-+]?\b\d+(?:,\d{3})*(?:\.\d+)?%?\b", text)
    numbers: List[float] = []
    for tok in raw_tokens:
        clean = tok.replace("%", "").replace(",", "")
        try:
            val = float(clean)
            numbers.append(val)
        except ValueError:
            pass
    return numbers


def _extract_grounded_numbers(
    exec_result: ExecutionResult,
    details: Dict[str, Any],
) -> Set[float]:
    """Collect all valid reference numbers from executed rows and verified details."""
    numbers: Set[float] = set()

    # Numbers from execution rows
    for r in exec_result.rows or []:
        for v in r.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                numbers.add(round(float(v), 2))
                numbers.add(round(float(v), 1))
                numbers.add(round(float(v), 4))
                numbers.add(float(v))

    # Row count
    numbers.add(float(exec_result.row_count))

    # Verified computed metrics in details
    for k, v in details.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v_flt = float(v)
            numbers.add(round(v_flt, 2))
            numbers.add(round(v_flt, 1))
            numbers.add(round(v_flt, 4))
            numbers.add(v_flt)
            # If percentage representation (0.625 -> 62.5)
            if 0.0 <= v_flt <= 1.0:
                pct = v_flt * 100.0
                numbers.add(round(pct, 1))
                numbers.add(round(pct, 2))

    return numbers


def verify_numbers_grounded(
    sentence: str,
    exec_result: ExecutionResult,
    details: Dict[str, Any],
    tolerance: float = 0.05,
) -> bool:
    """Verify that every number in the sentence exists in the executed/computed ground truth."""
    sentence_nums = _extract_numbers_from_sentence(sentence)
    if not sentence_nums:
        return True

    grounded_nums = _extract_grounded_numbers(exec_result, details)

    for s_num in sentence_nums:
        matched = False
        for g_num in grounded_nums:
            if abs(s_num - g_num) <= tolerance or (
                abs(g_num) > 1e-6 and abs(s_num - g_num) / abs(g_num) <= tolerance
            ):
                matched = True
                break
        if not matched:
            return False

    return True


def _format_val(val: Any) -> str:
    """Safely format numbers for sentence inclusion."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return f"{int(val):,}"
        if abs(val) >= 100:
            return f"{val:,.1f}"
        return f"{val:.2f}"
    return str(val)


# ---------------------------------------------------------------------------
# Configured Effect-Size Bands
# ---------------------------------------------------------------------------
EFFECT_SIZE_BANDS: Dict[Any, List[Tuple[float, str]]] = {
    InsightType.CORRELATION: [
        (0.10, "negligible"),
        (0.30, "weak"),
        (0.50, "moderate"),
        (0.70, "strong"),
        (float("inf"), "very strong"),
    ],
    InsightType.SEGMENT_GAP: [
        (0.01, "negligible"),
        (0.06, "weak"),
        (0.14, "moderate"),
        (float("inf"), "strong"),
    ],
    InsightType.TREND: [
        (0.10, "negligible"),
        (0.30, "weak"),
        (0.50, "moderate"),
        (0.70, "strong"),
        (float("inf"), "very strong"),
    ],
    InsightType.RANKING: [
        (0.20, "weak"),
        (0.50, "moderate"),
        (float("inf"), "strong"),
    ],
    "DEFAULT": [
        (0.30, "weak"),
        (0.60, "moderate"),
        (float("inf"), "strong"),
    ],
}


def get_strength_wording(insight_type: Any, value: float) -> str:
    """Return qualitative strength wording from configured effect-size bands."""
    bands = EFFECT_SIZE_BANDS.get(insight_type, EFFECT_SIZE_BANDS["DEFAULT"])
    abs_val = abs(float(value))
    for threshold, label in bands:
        if abs_val < threshold:
            return label
    return "strong"


def generate_panel_narration(
    insight: DiscoveredInsight,
) -> Tuple[Optional[str], str]:
    """Generate a verified one-sentence insight and 'why this was chosen' line.

    If any number in the sentence fails verification against executed results,
    the sentence is dropped (returns None).
    """
    cand = insight.candidate
    score = insight.score
    details = score.details
    res = insight.execution_result
    itype = cand.insight_type
    m = cand.measure
    d = cand.dimension or ""

    raw_sentence: Optional[str] = None

    if itype == InsightType.TOTAL_KPI:
        val_str = _format_val(details.get("value"))
        n_samples = details.get("n_samples", res.row_count)
        raw_sentence = f"Total {cand.aggregation.value} of {m} is {val_str} across {n_samples} records."

    elif itype == InsightType.RANKING:
        top_g = details.get("top_group", "Top category")
        top_v = _format_val(details.get("top_val"))
        top_share = round(float(details.get("top_share", 0.0)) * 100, 1)
        raw_sentence = f"Top category {top_g} leads with {top_v} in {cand.aggregation.value} of {m}, accounting for {top_share}% of total."

    elif itype == InsightType.TREND:
        direction = details.get("direction", "upward")
        first_v = _format_val(details.get("first_val"))
        last_v = _format_val(details.get("last_val"))
        growth = abs(round(float(details.get("growth_pct", 0.0)), 1))
        strength_word = get_strength_wording(itype, score.strength)
        raw_sentence = f"{m} displays a {strength_word} {direction} trend over {d} from {first_v} to {last_v} (a change of {growth}%)."

    elif itype == InsightType.SEGMENT_GAP:
        k = details.get("k_groups", 2)
        eta = round(float(details.get("eta_squared", 0.0)), 2)
        strength_word = get_strength_wording(itype, eta)
        raw_sentence = f"{strength_word.capitalize()} segment differences observed across {k} groups in {d} for {m} with an effect size of {eta}."

    elif itype == InsightType.CORRELATION:
        m2 = cand.secondary_measure or "comparison measure"
        r_val = round(float(details.get("r", 0.0)), 2)
        strength_word = get_strength_wording(itype, abs(r_val))
        raw_sentence = f"{strength_word.capitalize()} correlation observed between {m} and {m2} with Pearson r of {r_val}."

    elif itype == InsightType.COMPOSITION:
        top_g = details.get("top_group", "Top segment")
        top_share = round(float(details.get("top_share", 0.0)) * 100, 1)
        raw_sentence = f"{top_g} accounts for {top_share}% of total {m} across {d}."

    elif itype == InsightType.PERIOD_CHANGE:
        growth = abs(round(float(details.get("growth_pct", 0.0)), 1))
        raw_sentence = f"Period change for {m} shifted by {growth}% across {d}."

    elif itype == InsightType.DISTRIBUTION_OUTLIERS:
        cnt = details.get("outlier_count", 0)
        pct = round(float(details.get("outlier_frac", 0.0)) * 100, 1)
        raw_sentence = f"Identified {cnt} extreme outlier records in {m}, representing {pct}% of distribution."

    # Grounding check: verify every number appears in executed result / derived stats
    verified_sentence: Optional[str] = None
    if raw_sentence:
        is_grounded = verify_numbers_grounded(raw_sentence, res, details)
        if is_grounded:
            verified_sentence = raw_sentence
        else:
            # Drop sentence failing grounding check
            verified_sentence = None

    # Why this was chosen line
    strength_label = get_strength_wording(itype, score.strength)
    why_chosen = (
        f"Strength: {score.strength:.2f} ({strength_label} effect size), "
        f"Robustness: {round(score.robustness * 100, 1)}% (perturbation preservation), "
        f"Significance: p={score.p_value:.4f} (passed Benjamini-Hochberg FDR control)."
    )

    return verified_sentence, why_chosen
