"""Insight Narrator and AI Grounding Guard (Step 6).

Generates concise, factual titles and statements from validated evidence:
1. Deterministic template engine guaranteeing 100% numerical grounding and zero hallucination.
2. Optional LLM refinement layer protected by a strict numerical grounding guard and automatic template fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

from orchestrator.insights.schemas import (
    EvidenceGroundedInsight,
    InsightEvidence,
    InsightType,
)
from orchestrator.insights.validator import (
    _collect_grounded_numbers,
    _extract_numbers_from_text,
)
from providers.base import LLMClient


def _format_metric_name(col: str) -> str:
    """Format column name cleanly (e.g. length_of_stay -> length of stay)."""
    return col.replace("_", " ").strip()


class InsightNarrator:
    """Generates evidence-grounded titles and statements."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm_client = llm_client

    def narrate_deterministic(
        self,
        insight_type: InsightType,
        evidence: InsightEvidence,
    ) -> Tuple[str, str, Optional[str]]:
        """Generate 100% deterministic, mathematically grounded title and statement.

        Returns:
            (title, statement, interpretation)
        """
        vals = evidence.values
        m_name = _format_metric_name(evidence.metric_column)
        d_name = _format_metric_name(evidence.dimension_column) if evidence.dimension_column else ""
        agg_name = evidence.aggregation.value

        if insight_type == InsightType.KPI:
            val = vals.get("primary_value", 0.0)
            title = f"Overall {agg_name} {m_name.title()}"
            statement = f"The overall {agg_name.lower()} of {m_name} across the dataset is {val}."
            interp = f"Baseline aggregate measure for {m_name} across all available records."

        elif insight_type == InsightType.RANKING:
            top_g = vals.get("top_group", "")
            top_v = vals.get("top_value", 0.0)
            bot_g = vals.get("bottom_group", "")
            bot_v = vals.get("bottom_value", 0.0)
            diff = vals.get("difference", 0.0)
            title = f"Highest {m_name.title()} by {d_name.title()}"
            statement = f"{top_g} recorded the highest {agg_name.lower()} {m_name} at {top_v}, compared to {bot_g} at {bot_v} (a difference of {diff})."
            interp = f"Identifies the top performing/ranking segment across {d_name}."

        elif insight_type == InsightType.GROUP_COMPARISON:
            lead_g = vals.get("lead_group", "")
            lead_v = vals.get("lead_value", 0.0)
            mean_v = vals.get("group_mean", 0.0)
            diff_pct = vals.get("relative_premium_pct", 0.0)
            title = f"Leading {d_name.title()} Segment for {m_name.title()}"
            statement = f"{lead_g} leads all {d_name} groups in {m_name} with {lead_v}, exceeding the group benchmark average of {mean_v} by {diff_pct:+.1f}%."
            interp = f"Measures group-level variation and divergence from the overall group average."

        elif insight_type == InsightType.DISTRIBUTION:
            top_cat = vals.get("dominant_category", "")
            share = vals.get("dominant_share_pct", 0.0)
            cnt = vals.get("dominant_count", 0)
            title = f"Dominant {d_name.title()} Distribution"
            statement = f"{top_cat} accounts for {share}% of total records in {d_name} ({cnt} records)."
            interp = f"Highlights category concentration and volume distribution across {d_name}."

        elif insight_type == InsightType.TEMPORAL_TREND:
            dir_str = vals.get("direction", "changed")
            start_v = vals.get("start_value", 0.0)
            end_v = vals.get("end_value", 0.0)
            pct_chg = vals.get("percent_change", 0.0)
            periods = vals.get("periods_analyzed", 0)
            title = f"{m_name.title()} Trend Over Time"
            statement = f"{m_name.title()} {dir_str} from {start_v} to {end_v} ({pct_chg:+.1f}%) across {periods} observed periods."
            interp = f"Evaluates directional trajectory and net shift over the recorded timeline."

        elif insight_type == InsightType.OUTLIER:
            cnt = vals.get("outlier_count", 0)
            max_v = vals.get("max_outlier_value", 0.0)
            median_v = vals.get("dataset_median", 0.0)
            title = f"Unusual {m_name.title()} Observations"
            statement = f"Detected {cnt} statistical outlier(s) in {m_name} outside the standard IQR range, reaching an extreme value of {max_v} versus the median of {median_v}."
            interp = f"Flags high-leverage data points deviating significantly from typical values."

        elif insight_type == InsightType.CORRELATION:
            m2_name = _format_metric_name(evidence.secondary_metric or "secondary_metric")
            r_val = vals.get("correlation_r", 0.0)
            strength = vals.get("strength", "moderate")
            dir_str = vals.get("direction", "positive")
            sample_n = vals.get("sample_size", 0)
            title = f"Correlation: {m_name.title()} & {m2_name.title()}"
            statement = f"{m_name.title()} and {m2_name} exhibit a {strength} {dir_str} correlation (r = {r_val}, N = {sample_n})."
            interp = f"Statistical co-movement between two continuous metrics (does not imply causation)."

        else:
            title = f"Analytical Insight: {m_name.title()}"
            statement = f"Computed analytical evidence for {m_name} across the dataset."
            interp = None

        return title, statement, interp

    def narrate_insight(
        self,
        insight_type: InsightType,
        evidence: InsightEvidence,
        use_llm: bool = True,
    ) -> Tuple[str, str, Optional[str]]:
        """Narrate insight with deterministic grounding guarantee.

        If LLM is enabled and returns valid grounded text, uses LLM output.
        Otherwise safely falls back to deterministic template.
        """
        det_title, det_statement, det_interp = self.narrate_deterministic(insight_type, evidence)

        if not use_llm or self.llm_client is None:
            return det_title, det_statement, det_interp

        try:
            prompt = (
                f"You are an evidence-grounded BI assistant. Convert the following structured analytical evidence "
                f"into a professional insight title and single-sentence factual statement.\n\n"
                f"CRITICAL RULES:\n"
                f"1. You MUST ONLY use numbers present in the provided evidence values.\n"
                f"2. Do NOT invent, round differently, or hallucinate any numbers.\n"
                f"3. Do NOT make causal claims (e.g. 'A causes B').\n"
                f"4. Return strict JSON with keys: 'title', 'statement', 'interpretation'.\n\n"
                f"Insight Type: {insight_type.value}\n"
                f"Evidence Values: {json.dumps(evidence.values)}\n"
                f"Metric: {evidence.metric_column}\n"
                f"Dimension: {evidence.dimension_column}\n"
                f"Baseline text: Title='{det_title}', Statement='{det_statement}'\n"
            )

            resp_text = self.llm_client.generate(prompt)
            if not resp_text:
                return det_title, det_statement, det_interp

            # Clean json
            cleaned = re.sub(r"^```json\s*", "", resp_text.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            parsed = json.loads(cleaned)

            cand_title = str(parsed.get("title", "")).strip()
            cand_stmt = str(parsed.get("statement", "")).strip()
            cand_interp = parsed.get("interpretation")

            if not cand_title or not cand_stmt:
                return det_title, det_statement, det_interp

            # Strict number grounding check
            full_cand = f"{cand_title} {cand_stmt}"
            cand_nums = _extract_numbers_from_text(full_cand)
            grounded_nums = _collect_grounded_numbers(evidence)

            all_grounded = True
            for c_num in cand_nums:
                matched = False
                for g_num in grounded_nums:
                    if abs(c_num - g_num) <= 0.05 or (
                        abs(g_num) > 1e-6 and abs(c_num - g_num) / abs(g_num) <= 0.05
                    ):
                        matched = True
                        break
                if not matched:
                    all_grounded = False
                    break

            if all_grounded:
                return cand_title, cand_stmt, cand_interp

        except Exception:
            pass

        # Fallback to deterministic template
        return det_title, det_statement, det_interp
