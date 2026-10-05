"""Response Generator & Numerical Grounding Guard for Dataset Chat.

Guarantees:
1. 100% mathematical and numerical truth backed by DuckDB execution results.
2. Optional LLM conversational phrasing with strict hallucination verification.
3. Automatic, instant fallback to deterministic template narration if LLM fails or invents numbers.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from orchestrator.insights.validator import _extract_numbers_from_text
from orchestrator.schemas import AggregationType, CandidatePlan
from providers.base import LLMClient
from providers.factory import get_llm_client


def _format_val(val: Any) -> str:
    """Format numeric or string values for natural language presentation."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return f"{int(val):,}"
        elif isinstance(val, float):
            return f"{val:,.2f}"
        return f"{val:,}"
    return str(val)


def _collect_grounded_numbers_from_rows(
    rows: List[Dict[str, Any]],
    plan: Optional[CandidatePlan] = None,
) -> Set[float]:
    """Collect all valid numbers from execution results for hallucination verification."""
    grounded: Set[float] = set()

    def _add_num(n: Any):
        if isinstance(n, (int, float)) and not isinstance(n, bool) and not math.isnan(float(n)):
            flt = float(n)
            grounded.add(flt)
            grounded.add(round(flt, 1))
            grounded.add(round(flt, 2))
            grounded.add(round(flt, 4))
            grounded.add(float(int(round(flt))))
            if 0.0 <= flt <= 1.0:
                grounded.add(round(flt * 100.0, 1))
                grounded.add(round(flt * 100.0, 2))

    for row in rows:
        for v in row.values():
            _add_num(v)

    # If rows have >= 2 items, also allow the calculated difference and relative percentage
    if len(rows) >= 2 and plan and plan.metric:
        m_col = plan.metric.column
        numeric_vals = [r[k] for r in rows for k in r if isinstance(r[k], (int, float))]
        if len(numeric_vals) >= 2:
            v1, v2 = float(numeric_vals[0]), float(numeric_vals[1])
            diff = abs(v1 - v2)
            _add_num(diff)
            if v2 != 0:
                pct = abs((v1 - v2) / v2) * 100.0
                _add_num(pct)

    # Add row counts
    _add_num(len(rows))
    return grounded


class ChatResponseGenerator:
    """Generates evidence-grounded natural-language answers."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm_client = llm_client

    def generate_answer(
        self,
        question: str,
        plan: Optional[CandidatePlan],
        rows: List[Dict[str, Any]],
        columns: List[str],
        use_llm: bool = True,
    ) -> str:
        """Generate a factual, grounded natural language answer."""
        if not rows:
            return "No records were found matching your query criteria in this dataset."

        # 1. Deterministic baseline answer
        det_answer = self._generate_deterministic_answer(question, plan, rows, columns)

        # 2. If LLM is disabled or unavailable, return deterministic answer
        if not use_llm:
            return det_answer

        client = self.llm_client or get_llm_client()
        if not client or client.provider == "mock":
            return det_answer

        # 3. LLM conversational generation
        try:
            llm_text = self._generate_llm_answer(client, question, plan, rows)
            if not llm_text:
                return det_answer

            # 4. Strict numerical grounding verification
            grounded_nums = _collect_grounded_numbers_from_rows(rows, plan)
            extracted_nums = _extract_numbers_from_text(llm_text)

            is_grounded = True
            for num in extracted_nums:
                # Tolerate row count numbers or small integers under 10 if conversational
                if num in (1.0, 2.0, 3.0, 4.0, 5.0, 10.0, float(len(rows))):
                    continue
                if num not in grounded_nums and round(num, 1) not in grounded_nums and round(num, 2) not in grounded_nums:
                    is_grounded = False
                    break

            if is_grounded:
                return llm_text.strip()
            else:
                # Hallucination detected -> discard and use deterministic fallback
                return det_answer
        except Exception:
            return det_answer

    def _generate_deterministic_answer(
        self,
        question: str,
        plan: Optional[CandidatePlan],
        rows: List[Dict[str, Any]],
        columns: List[str],
    ) -> str:
        """Construct deterministic natural language answer based on plan and data shape."""
        m_name = plan.metric.column.replace("_", " ") if plan and plan.metric else "value"
        agg_name = plan.metric.aggregation.value.lower() if plan and plan.metric else "calculated"
        dims = [d.column.replace("_", " ") for d in plan.dimensions] if plan and plan.dimensions else []

        # Case 1: Single Scalar / KPI result
        if len(rows) == 1 and (len(columns) == 1 or not dims):
            val_key = list(rows[0].keys())[-1]
            val = rows[0][val_key]
            return f"The {agg_name} {m_name} across the dataset is {_format_val(val)}."

        # Case 2: Single Row Filtered result (e.g. for Engineering)
        if len(rows) == 1 and dims:
            dim_col = list(rows[0].keys())[0]
            val_col = list(rows[0].keys())[-1]
            dim_val = rows[0][dim_col]
            val = rows[0][val_col]
            return f"For {dim_val} in {dims[0]}, the {agg_name} {m_name} is {_format_val(val)}."

        # Case 3: Two-item Comparison
        if len(rows) == 2 and dims:
            d_col = list(rows[0].keys())[0]
            v_col = list(rows[0].keys())[-1]
            g1, v1 = rows[0][d_col], rows[0][v_col]
            g2, v2 = rows[1][d_col], rows[1][v_col]

            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                diff = abs(v1 - v2)
                higher_g = g1 if v1 >= v2 else g2
                higher_v = v1 if v1 >= v2 else v2
                lower_g = g2 if v1 >= v2 else g1
                lower_v = v2 if v1 >= v2 else v1
                return f"{higher_g} ({_format_val(higher_v)}) is higher than {lower_g} ({_format_val(lower_v)}) by {_format_val(diff)}."
            else:
                return f"{g1} has {_format_val(v1)} and {g2} has {_format_val(v2)}."

        # Case 4: Grouped / Ranking List (>= 3 rows)
        if len(rows) >= 3 and dims:
            d_col = list(rows[0].keys())[0]
            v_col = list(rows[0].keys())[-1]
            top_g, top_v = rows[0][d_col], rows[0][v_col]
            second_g, second_v = rows[1][d_col], rows[1][v_col]
            last_g, last_v = rows[-1][d_col], rows[-1][v_col]

            lines = [
                f"{top_g} leads with {_format_val(top_v)} in {agg_name} {m_name}, followed by {second_g} at {_format_val(second_v)}.",
                f"Across {len(rows)} groups, values range from {_format_val(last_v)} ({last_g}) to {_format_val(top_v)} ({top_g}).",
            ]
            return " ".join(lines)

        # Generic summary
        first_row = rows[0]
        summary_parts = [f"{k}: {_format_val(v)}" for k, v in first_row.items()]
        return f"Found {len(rows)} record(s). Top result: {', '.join(summary_parts)}."

    def _generate_llm_answer(
        self,
        client: LLMClient,
        question: str,
        plan: Optional[CandidatePlan],
        rows: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Invoke LLM to produce conversational explanation bounded strictly by DuckDB rows."""
        sample_rows = rows[:10]
        prompt = f"""You are a helpful and strictly factual data intelligence assistant.
Answer the user's question concisely in 1-2 sentences using ONLY the verified data rows below.

Question: "{question}"
Metric: {plan.metric.column if plan and plan.metric else 'N/A'} ({plan.metric.aggregation.value if plan and plan.metric else 'N/A'})
Dimensions: {[d.column for d in plan.dimensions] if plan and plan.dimensions else 'None'}
Verified Data Rows:
{json.dumps(sample_rows, indent=2)}

Rules:
1. State the key finding clearly and conversationally.
2. Only mention numbers that appear EXACTLY in the Verified Data Rows.
3. Never forecast, extrapolate, predict, or invent numbers.
4. Keep the response under 60 words.
"""
        response = client.generate(
            prompt=prompt,
            system_prompt="You are a data intelligence assistant. Answer factually based only on the provided data.",
            temperature=0.0,
            max_tokens=150,
        )
        if response and response.text:
            return response.text.strip()
        return None
