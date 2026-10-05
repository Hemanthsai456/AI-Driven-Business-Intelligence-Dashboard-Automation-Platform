"""Evidence-Grounded Insight Handler for Dataset Chat.

Answers questions about:
- Top dataset findings and automated insights
- Statistical significance & evidence backing each insight
- Provenance and DuckDB queries powering insights
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from ingestion.models import CanonicalDataset
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.insights import EvidenceGroundedInsight, generate_grounded_insights


class InsightChatHandler:
    """Answers conversational queries regarding Evidence-Grounded Insights."""

    def handle_insight_query(
        self,
        question: str,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        cached_insights: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate conversational answer referencing validated Step 6 insights."""
        q_lower = question.lower()

        # 1. Obtain validated insights (using Step 6 engine)
        insights_list: List[Dict[str, Any]] = []
        if cached_insights:
            insights_list = cached_insights
        else:
            res = generate_grounded_insights(
                dataset=dataset,
                semantic_profile=semantic_profile,
                max_insights=5,
                use_llm=False,
            )
            insights_list = [i.model_dump() for i in res.insights]

        if not insights_list:
            return {
                "answer": "No statistically significant or distinctive insights met the strict validation criteria for this dataset.",
                "data": [],
                "columns": [],
                "row_count": 0,
                "evidence": {},
            }

        # 2. If user asked for the strongest / top insight specifically
        if any(w in q_lower for w in ("strongest", "most important", "top finding", "key insight")):
            top_i = insights_list[0]
            title = top_i.get("title", "Top Insight")
            stmt = top_i.get("statement", "")
            interp = top_i.get("interpretation", "")
            itype = top_i.get("type", "INSIGHT")
            ev_vals = top_i.get("evidence", {}).get("values", {})
            compiled_sql = top_i.get("provenance", {}).get("compiled_sql", "")

            answer = (
                f"**Top Finding: {title}**\n\n"
                f"{stmt}\n\n"
                f"*Context*: {interp}\n"
                f"*Insight Type*: `{itype}`"
            )

            return {
                "answer": answer,
                "data": [
                    {
                        "metric": top_i.get("evidence", {}).get("metric_column", "N/A"),
                        "dimension": top_i.get("evidence", {}).get("dimension_column", "N/A"),
                        "type": itype,
                        "title": title,
                        "statement": stmt,
                    }
                ],
                "columns": ["metric", "dimension", "type", "title", "statement"],
                "row_count": 1,
                "compiled_sql": compiled_sql,
                "evidence": ev_vals,
                "insights": insights_list,
            }

        # 3. Present list of top insights
        lines = ["Here are the key evidence-grounded insights discovered in this dataset:"]
        table_rows = []

        for idx, ins in enumerate(insights_list[:4], 1):
            title = ins.get("title", "")
            stmt = ins.get("statement", "")
            lines.append(f"{idx}. **{title}**: {stmt}")
            table_rows.append({
                "rank": idx,
                "type": ins.get("type", ""),
                "title": title,
                "statement": stmt,
            })

        answer_text = "\n\n".join(lines)

        return {
            "answer": answer_text,
            "data": table_rows,
            "columns": ["rank", "type", "title", "statement"],
            "row_count": len(table_rows),
            "evidence": {"total_insights": len(insights_list)},
            "insights": insights_list,
        }
