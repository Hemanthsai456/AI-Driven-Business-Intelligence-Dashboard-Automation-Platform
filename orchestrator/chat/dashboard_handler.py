"""Dashboard Provenance & Explanation Handler for Dataset Chat.

Answers questions about:
- Why specific visual chart types (Bar, KPI, Line) were chosen
- How KPI summary numbers and metrics were calculated
- SQL provenance behind dashboard tiles
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from ingestion.models import CanonicalDataset
from intelligence.profiler import DataProfile
from intelligence.schema_validator import AnalysisReadiness
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.overview.planner import generate_overview_dashboard
from orchestrator.schemas import DashboardSpec


class DashboardExplanationHandler:
    """Answers conversational queries regarding generated Overview Dashboards and visual provenance."""

    def handle_dashboard_query(
        self,
        question: str,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        readiness: Optional[AnalysisReadiness] = None,
        data_profile: Optional[DataProfile] = None,
        cached_spec: Optional[DashboardSpec] = None,
    ) -> Dict[str, Any]:
        """Generate explanation of dashboard architecture and tile SQL provenance."""
        q_lower = question.lower()

        # 1. Obtain DashboardSpec
        spec = cached_spec
        if not spec:
            spec = generate_overview_dashboard(
                dataset=dataset,
                semantic_profile=semantic_profile,
                readiness=readiness,
                data_profile=data_profile,
                use_llm=False,
            )

        tiles = spec.tiles or []
        kpi_tiles = [t for t in tiles if t.chart_type == "kpi"]
        hero_tiles = [t for t in tiles if t.chart_type in ("bar", "line", "horizontal_bar", "histogram")]

        # 2. If asking about SQL for dashboard/hero
        if any(w in q_lower for w in ("sql", "query", "code")):
            primary_tile = hero_tiles[0] if hero_tiles else (tiles[0] if tiles else None)
            sql_text = primary_tile.compiled_sql if primary_tile else "SELECT * FROM source_data"
            t_title = primary_tile.title if primary_tile else "Dashboard Tile"

            answer = (
                f"**SQL Provenance for `{t_title}`**:\n\n"
                f"```sql\n{sql_text}\n```\n\n"
                f"*Execution Engine*: Sandboxed In-Memory DuckDB\n"
                f"*Data Rows Returned*: {len(primary_tile.data) if primary_tile else 0}"
            )

            return {
                "answer": answer,
                "data": primary_tile.data if primary_tile else [],
                "columns": list(primary_tile.data[0].keys()) if primary_tile and primary_tile.data else [],
                "row_count": len(primary_tile.data) if primary_tile else 0,
                "compiled_sql": sql_text,
                "evidence": {"tile_id": primary_tile.tile_id if primary_tile else "none"},
            }

        # 3. If asking why a chart/metric was chosen
        primary_kpi = kpi_tiles[0] if kpi_tiles else None
        primary_hero = hero_tiles[0] if hero_tiles else None

        kpi_name = primary_kpi.title if primary_kpi else "Executive Metric"
        kpi_agg = primary_kpi.plan.metric.aggregation.value if primary_kpi and primary_kpi.plan and primary_kpi.plan.metric else "AGG"
        hero_name = primary_hero.title if primary_hero else "Distribution Chart"
        hero_dim = primary_hero.dimensions[0] if primary_hero and primary_hero.dimensions else "Category"

        answer = (
            f"**Dashboard Architecture Rationale**:\n\n"
            f"1. **Headline & Executive Summary**: *\"{spec.headline}\"*\n"
            f"2. **Primary KPI (`{kpi_name}`)**: Selected using **{kpi_agg}** aggregation based on semantic intelligence rules for measure intensity.\n"
            f"3. **Hero Visual (`{hero_name}`)**: Grouped by `{hero_dim}` because it represents the highest-information categorical breakdown without high-cardinality noise.\n"
            f"4. **Layout Grid**: Formatted with KPI cards, comparative bar charts, and data distributions grounded in DuckDB queries."
        )

        tile_summary_rows = [
            {
                "tile": t.title,
                "chart_type": t.chart_type,
                "metric": ", ".join(t.metrics),
                "dimension": ", ".join(t.dimensions) if t.dimensions else "None",
            }
            for t in tiles
        ]

        return {
            "answer": answer,
            "data": tile_summary_rows,
            "columns": ["tile", "chart_type", "metric", "dimension"],
            "row_count": len(tile_summary_rows),
            "evidence": {"spec_id": spec.spec_id, "tile_count": len(tiles)},
        }
