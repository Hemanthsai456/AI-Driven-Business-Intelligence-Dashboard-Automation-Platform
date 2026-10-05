"""Structured Follow-Up Resolution for Multi-Turn Dataset Conversations.

Resolves pronoun and relative references using structured ConversationContext:
- "which one is highest" / "which is lowest"
- "show top 5" / "show bottom 3"
- "what about in [Category]?" / "how about for [Value]?"
- "what about total instead?" / "show sum"
- "now by [Dimension]"
- "compare [A] and [B]" / "compare highest and lowest"
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.chat.schemas import ConversationContext
from orchestrator.schemas import AggregationType, FilterSpec


class FollowUpResolver:
    """Resolves follow-up queries using previous structured analytical state."""

    def resolve_followup(
        self,
        message: str,
        context: ConversationContext,
        semantic_profile: DatasetSemanticProfile,
    ) -> Tuple[str, Optional[Dict[str, Any]], bool, Optional[List[str]]]:
        """Transform a follow-up query into an explicit, grounded analytical request.

        Returns:
            (synthesized_question, explicit_overrides, clarification_needed, clarification_options)
        """
        msg = message.strip()
        msg_lower = msg.lower()

        last_metric = context.last_metric
        last_agg = context.last_aggregation
        last_dims = context.last_dimensions or []
        last_rows = context.last_result_rows or []

        # 1. Extremum / Ranking Follow-ups: "which is highest", "which one is lowest", "top 5"
        extremum_match = re.search(
            r"\b(highest|maximum|max|top|best|most|lowest|minimum|min|bottom|worst|least)\b",
            msg_lower,
        )
        if extremum_match:
            term = extremum_match.group(1)
            is_desc = term in ("highest", "maximum", "max", "top", "best", "most")

            # Check for limit N (e.g. "top 5", "top 3", "bottom 10")
            limit_m = re.search(r"\b(?:top|bottom|highest|lowest)\s+(\d+)\b", msg_lower)
            limit_val = int(limit_m.group(1)) if limit_m else 1

            if last_metric and last_dims:
                dim = last_dims[0]
                agg_str = last_agg.value.lower() if last_agg else "average"
                m_str = last_metric.replace("_", " ")
                d_str = dim.replace("_", " ")

                if limit_val == 1:
                    qualifier = "highest" if is_desc else "lowest"
                    synth = f"Which {d_str} has the {qualifier} {agg_str} {m_str}?"
                else:
                    qualifier = "top" if is_desc else "bottom"
                    synth = f"Show me the {qualifier} {limit_val} {d_str}s by {agg_str} {m_str}."

                overrides = {
                    "metric": last_metric,
                    "aggregation": last_agg,
                    "dimension": dim,
                    "order_by": last_metric,
                    "order_direction": "DESC" if is_desc else "ASC",
                    "limit": limit_val,
                }
                return synth, overrides, False, None

            elif not last_dims and last_metric:
                # User asked for scalar metric previously, then asked "which is highest" without a dimension
                cat_cols = [
                    col for col, ev in semantic_profile.column_evidences.items()
                    if ev.candidate_role == ColumnRole.DIMENSION
                ]
                if len(cat_cols) > 1:
                    options = [f"By {c.replace('_', ' ')}" for c in cat_cols[:4]]
                    return (
                        msg,
                        None,
                        True,
                        options,
                    )
                elif cat_cols:
                    dim = cat_cols[0]
                    agg_str = last_agg.value.lower() if last_agg else "average"
                    m_str = last_metric.replace("_", " ")
                    d_str = dim.replace("_", " ")
                    synth = f"Which {d_str} has the highest {agg_str} {m_str}?"
                    return synth, None, False, None

        # 2. Comparison of Highest and Lowest: "compare highest and lowest", "compare the top and bottom"
        if re.search(r"\bcompare\s+(?:highest\s+and\s+lowest|top\s+and\s+bottom|the\s+two)\b", msg_lower):
            if last_rows and len(last_rows) >= 2 and last_dims:
                dim_col = last_dims[0]
                # Find first and last group
                first_group = str(last_rows[0].get(dim_col, ""))
                last_group = str(last_rows[-1].get(dim_col, ""))
                if first_group and last_group:
                    synth = f"Compare {first_group} and {last_group} for {last_metric.replace('_', ' ')}."
                    return synth, None, False, None

        # 3. Explicit Comparison of Entities: "compare Engineering and Sales", "compare North and South"
        comp_match = re.search(r"\bcompare\s+([a-z0-9_\s]+?)\s+and\s+([a-z0-9_\s]+)\b", msg_lower)
        if comp_match:
            ent1 = comp_match.group(1).strip()
            ent2 = comp_match.group(2).strip()
            # Clean filler words
            ent1 = re.sub(r"^(?:the|between)\s+", "", ent1).strip()
            ent2 = re.sub(r"^(?:the)\s+", "", ent2).strip()

            if last_metric:
                agg_str = last_agg.value.lower() if last_agg else "average"
                synth = f"Compare {ent1} and {ent2} by {agg_str} {last_metric.replace('_', ' ')}"
                if last_dims:
                    synth += f" in {last_dims[0].replace('_', ' ')}"
                return synth, None, False, None

        # 4. Aggregation Shift: "what about total instead?", "show sum instead"
        agg_shift_match = re.search(r"\b(total|sum|average|avg|count|maximum|max|minimum|min)\b", msg_lower)
        if agg_shift_match and ("instead" in msg_lower or "show" in msg_lower or "what about" in msg_lower):
            agg_word = agg_shift_match.group(1)
            new_agg = AggregationType.SUM if agg_word in ("total", "sum") else AggregationType.AVG
            if agg_word in ("maximum", "max"):
                new_agg = AggregationType.MAX
            elif agg_word in ("minimum", "min"):
                new_agg = AggregationType.MIN
            elif agg_word in ("count",):
                new_agg = AggregationType.COUNT

            if last_metric:
                m_str = last_metric.replace("_", " ")
                if last_dims:
                    d_str = last_dims[0].replace("_", " ")
                    synth = f"What is the {new_agg.value.lower()} {m_str} by {d_str}?"
                else:
                    synth = f"What is the {new_agg.value.lower()} {m_str}?"
                return synth, {"aggregation": new_agg}, False, None

        # 5. Entity / Subgroup Filter Drilling: "what about in IT?", "how about for Engineering?", "only North"
        drill_match = re.search(
            r"(?:what\s+about|how\s+about|and|only|for|in)\s+(?:in\s+|for\s+)?([a-z0-9_\-\s]+)",
            msg_lower,
        )
        if drill_match:
            candidate_val = drill_match.group(1).strip()
            # Remove punctuation
            candidate_val = re.sub(r"[?!.]", "", candidate_val).strip()

            if candidate_val and last_metric:
                agg_str = last_agg.value.lower() if last_agg else "average"
                m_str = last_metric.replace("_", " ")
                if last_dims:
                    d_str = last_dims[0].replace("_", " ")
                    synth = f"What is the {agg_str} {m_str} for {candidate_val} in {d_str}?"
                else:
                    synth = f"What is the {agg_str} {m_str} for {candidate_val}?"
                return synth, None, False, None

        # 6. Dimension Shift: "now by department", "break down by region", "show by date"
        dim_shift_match = re.search(r"(?:now\s+by|break\s+(?:it\s+)?down\s+by|show\s+by|grouped\s+by)\s+([a-z0-9_\-\s]+)", msg_lower)
        if dim_shift_match:
            target_dim = dim_shift_match.group(1).strip()
            target_dim = re.sub(r"[?!.]", "", target_dim).strip()
            if target_dim and last_metric:
                agg_str = last_agg.value.lower() if last_agg else "average"
                m_str = last_metric.replace("_", " ")
                synth = f"What is the {agg_str} {m_str} by {target_dim}?"
                return synth, None, False, None

        # 7. Fallback: If query contains pronouns "it", "that", "those", "them" without explicit trigger
        if any(p in _tokenize(msg_lower) for p in ("it", "that", "those", "them", "which")):
            if last_metric and last_dims:
                synth = f"{msg} for {last_metric.replace('_', ' ')} by {last_dims[0].replace('_', ' ')}"
                return synth, None, False, None
            elif last_metric:
                synth = f"{msg} for {last_metric.replace('_', ' ')}"
                return synth, None, False, None

        # Pass through unchanged if no pattern matched
        return msg, None, False, None


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z0-9_]+\b", text.lower()))
