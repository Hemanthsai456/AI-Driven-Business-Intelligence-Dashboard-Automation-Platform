"""Rule-based baseline analytical generator (deterministic heuristic without LLM)."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from providers.base import LLMClient
from providers.types import GeneratorCallLog


class RuleBasedBaselineClient(LLMClient):
    """Deterministic rule-based baseline generator.
    
    Honestly labeled as a heuristic baseline, not an LLM. Excluded from LLM provider
    counts and consensus/agreement calculations.
    """

    def __init__(
        self,
        model_name: str = "rule_based_baseline",
        **kwargs: Any,
    ):
        super().__init__("rule_based_baseline", model_name)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
        generator_label: str = "rule_based_baseline",
    ) -> Tuple[Dict[str, Any], GeneratorCallLog]:
        start = time.perf_counter()

        # Parse available columns and intent from prompt text dynamically
        measures: List[str] = []
        dimensions: List[str] = []
        dates: List[str] = []

        for line in prompt.splitlines():
            # Line format e.g.: "- total_sales (Role: ColumnRole.MEASURE, Confidence: ...)"
            m_role = re.search(r"-\s+([A-Za-z0-9_]+)\s+\(Role:\s+(?:ColumnRole\.)?([A-Za-z_]+)", line)
            if m_role:
                col, role = m_role.group(1), m_role.group(2).upper()
                if "MEASURE" in role:
                    measures.append(col)
                elif "DATETIME" in role or "DATE" in role:
                    dates.append(col)
                elif "DIMENSION" in role or "IDENTIFIER" in role:
                    dimensions.append(col)

        # Extract dataset id and intent
        ds_match = re.search(r"Dataset ID:\s*([A-Za-z0-9_\-\.]+)", prompt)
        dataset_id = ds_match.group(1) if ds_match else "dataset_01"

        intent_match = re.search(r"User Intent:\s*(.+)", prompt)
        intent_text = intent_match.group(1).strip() if intent_match else "Analyze primary business metrics"

        # Check for Target Semantic Interpretations in prompt
        interp_metric_match = re.search(r"Metric:\s*([A-Za-z0-9_]+)\s*\[([A-Za-z_]+)\]", prompt)
        interp_dims_match = re.search(r"Dimensions:\s*\[([^\]]*)\]", prompt)

        metric_col: Optional[str] = None
        agg_func: str = "SUM"
        dim_col: Optional[str] = None

        if interp_metric_match:
            cand_m = interp_metric_match.group(1)
            cand_a = interp_metric_match.group(2).upper()
            if cand_m in measures or cand_m in dimensions or cand_m == "*":
                metric_col = cand_m
                if cand_a in ("SUM", "AVG", "COUNT", "MIN", "MAX", "MEDIAN", "STDDEV", "COUNT_DISTINCT"):
                    agg_func = cand_a

        if interp_dims_match:
            raw_dims = [d.strip().strip("'\"") for d in interp_dims_match.group(1).split(",") if d.strip().strip("'\"")]
            for d in raw_dims:
                if d in dimensions or d in dates:
                    dim_col = d
                    break

        intent_lower = intent_text.lower()

        # Prioritize matching measures explicitly mentioned in user intent
        if not metric_col:
            for m in measures:
                if re.search(r"\b" + re.escape(m.lower()) + r"\b", intent_lower) or m.lower() in intent_lower:
                    metric_col = m
                    break

        if not metric_col:
            metric_col = measures[0] if measures else (dimensions[0] if dimensions else "*")

        # Prioritize matching dimensions explicitly mentioned in user intent
        if not dim_col:
            for d in dimensions:
                if re.search(r"\b" + re.escape(d.lower()) + r"\b", intent_lower) or d.lower() in intent_lower:
                    dim_col = d
                    break
            if not dim_col:
                for dt in dates:
                    if re.search(r"\b" + re.escape(dt.lower()) + r"\b", intent_lower) or dt.lower() in intent_lower:
                        dim_col = dt
                        break

        if not dim_col:
            dim_col = dimensions[0] if dimensions else (dates[0] if dates else None)

        # Determine aggregation function if not already extracted from interpretation
        if not interp_metric_match:
            if any(w in intent_lower for w in ["avg", "average", "mean"]):
                agg_func = "AVG"
            elif any(w in intent_lower for w in ["count", "number of", "how many"]):
                agg_func = "COUNT"
            elif any(w in intent_lower for w in ["min", "minimum", "lowest"]):
                agg_func = "MIN"
            elif any(w in intent_lower for w in ["max", "maximum", "highest"]):
                agg_func = "MAX"
            elif "median" in intent_lower:
                agg_func = "MEDIAN"
            else:
                agg_func = "SUM" if metric_col in measures else "COUNT"

        # Ranking & limits
        order_by: Optional[str] = None
        order_dir: Optional[str] = None
        limit_val: Optional[int] = None

        top_match = re.search(r"\b(?:top|highest|best)\s+(\d+)\b", intent_lower)
        if top_match:
            limit_val = int(top_match.group(1))
            order_dir = "DESC"
            order_by = "metric"
        bot_match = re.search(r"\b(?:bottom|lowest|worst)\s+(\d+)\b", intent_lower)
        if bot_match:
            limit_val = int(bot_match.group(1))
            order_dir = "ASC"
            order_by = "metric"

        dims_spec = []
        if dim_col:
            if dim_col in dates:
                dims_spec.append({"column": dim_col, "granularity": "MONTH"})
                vis_type = "LINE"
            else:
                dims_spec.append({"column": dim_col, "granularity": None})
                vis_type = "BAR"
        else:
            vis_type = "KPI"

        dim_desc = dim_col if dim_col else "entire dataset"
        plan_dict = {
            "plan_id": str(uuid4()),
            "dataset_id": dataset_id,
            "intent": intent_text,
            "metric": {
                "column": metric_col,
                "aggregation": agg_func,
            },
            "dimensions": dims_spec,
            "filters": [],
            "comparison": None,
            "order_by": order_by,
            "order_direction": order_dir,
            "limit": limit_val,
            "visualization": vis_type,
            "generator": generator_label,
            "provider": "rule_based_baseline",
            "supporting_providers": [],
            "supporting_count": 0,
            "providers_responded": 1,
            "reasoning": {
                "interpretation": f"Aggregated {metric_col} ({agg_func}) grouped by {dim_desc} (rule-based baseline heuristic).",
                "evidence": [
                    f"Selected candidate measure column '{metric_col}'.",
                    f"Grouped across categorical dimension '{dim_desc}'.",
                    "Generated by deterministic rule-based baseline planner (non-LLM).",
                ],
            },
        }

        elapsed = max(0.001, time.perf_counter() - start)
        call_log = GeneratorCallLog(
            model=self.model_name,
            provider="rule_based_baseline",
            generator=generator_label,
            steps=1,
            input_tokens=len(prompt.split()),
            output_tokens=65,
            latency_seconds=round(elapsed, 4),
            estimated_cost_usd=0.0,
        )

        return plan_dict, call_log


# Backward compatibility alias
ZeroCostLocalClient = RuleBasedBaselineClient
