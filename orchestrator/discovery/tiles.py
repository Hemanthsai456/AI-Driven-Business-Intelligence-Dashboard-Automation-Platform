"""Power BI-Style Dashboard Tile Generation and Deterministic Grid Placement.

Rules:
1. Row 1: KPI strip, up to 4 KPI tiles (3 columns each, w=3, h=2).
2. Row 2: Hero tile (highest-scoring TREND or RANKING, 8 columns, w=8, h=4)
          plus one side tile (4 columns, w=4, h=4, e.g. COMPOSITION as donut or horizontal bar).
3. Next rows: remaining tiles in a 2- or 3-column grid (w=6 or w=4, h=3), ordered by priority.
4. Tile anatomy: Title (insight sentence), chart type, provenance badge, evidence chips.
5. Runtime Slicers: 1 date-range per DATETIME column, multi-select per low-cardinality dimension (<= 12 values).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from ingestion.models import CanonicalDataset
from orchestrator.schemas import (
    CandidatePlan,
    DashboardTile,
    RankedCandidate,
    SlicerDef,
    SlicerOption,
    TileEvidence,
    TileSize,
)
from orchestrator.discovery.schemas import DiscoveredInsight, InsightType


def _format_provenance(proposed_by: str) -> str:
    """Format generator provenance for badge display."""
    p_lower = (proposed_by or "rule_baseline").lower()
    if "gemini" in p_lower:
        return "Gemini"
    if "groq" in p_lower:
        return "Groq"
    if "agent" in p_lower:
        return "agent"
    return "rule-based baseline"


def _determine_chart_type(
    insight_type: InsightType | str,
    rows: Optional[List[Dict[str, Any]]] = None,
    dim_key: Optional[str] = None,
) -> str:
    """Determine chart type based on insight semantics:
    - CORRELATION -> scatter
    - SEGMENT_GAP and RANKING -> bar
    - COMPOSITION -> donut or stacked
    - TREND -> line
    - DISTRIBUTION -> histogram
    """
    rows = rows or []
    itype_str = (insight_type.value if hasattr(insight_type, "value") else str(insight_type or "")).upper()
    if itype_str == "TOTAL_KPI":
        return "kpi"
    if itype_str == "TREND":
        return "line"
    if itype_str == "COMPOSITION":
        return "donut" if len(rows) <= 6 else "stacked"
    if itype_str == "CORRELATION":
        return "scatter"
    if itype_str in ("DISTRIBUTION", "DISTRIBUTION_OUTLIERS"):
        return "histogram"
    if itype_str in ("RANKING", "SEGMENT_GAP"):
        return "bar"
    return "bar"


def _format_kpi_title(measure_name: str, agg: Optional[Any] = None) -> str:
    """Format KPI tile title according to measure semantics, choosing SUM or AVG, never 'Total AVG'."""
    clean = re.sub(r"([a-z])([A-Z])", r"\1 \2", measure_name).replace("_", " ").strip()
    clean_lower = clean.lower()

    # Determine whether SUM or AVG fits measure semantics
    avg_tokens = {"price", "unitprice", "rate", "pct", "percentage", "ratio", "score", "margin", "discount", "rating", "age"}
    agg_str = (agg.value if hasattr(agg, "value") else str(agg or "")).upper()
    is_avg = agg_str == "AVG" or any(t in clean_lower for t in avg_tokens)

    # Format title cleanly without repetition
    title_col = clean.title()
    for prefix in ("Total ", "Average ", "Avg "):
        if title_col.startswith(prefix):
            title_col = title_col[len(prefix):].strip()

    if is_avg:
        return f"Average {title_col}"
    else:
        return f"Total {title_col}"


def build_slicer_definitions(
    dataset: Optional[CanonicalDataset] = None,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> List[SlicerDef]:
    """Build runtime slicers dynamically from dataset.

    Rules:
    - 1 date-range control per datetime column
    - 1 multi-select control per low-cardinality dimension (<= 12 values)
    No hardcoded columns.
    """
    slicers: List[SlicerDef] = []
    if dataset is None or dataset.data is None or dataset.data.empty:
        return slicers

    df = dataset.data
    roles = semantic_profile.column_evidences if semantic_profile else {}

    for col in df.columns:
        role = roles.get(col).candidate_role if (roles and col in roles) else None
        series = df[col].dropna()
        if series.empty:
            continue

        # 1. Datetime column -> date-range slicer
        is_datetime = False
        if role == ColumnRole.DATETIME:
            is_datetime = True
        elif "date" in col.lower() or "time" in col.lower() or "timestamp" in col.lower():
            is_datetime = True

        if is_datetime:
            try:
                min_val = str(series.min())[:10]
                max_val = str(series.max())[:10]
                slicers.append(
                    SlicerDef(
                        id=f"slicer_{col}",
                        column=col,
                        role="DATETIME",
                        control_type="date_range",
                        min_date=min_val,
                        max_date=max_val,
                    )
                )
                continue
            except Exception:
                pass

        # 2. Categorical / Dimension column with <= 12 unique values -> multi-select
        unique_vals = series.unique()
        cardinality = len(unique_vals)
        if 1 < cardinality <= 12 and (role in (ColumnRole.DIMENSION, ColumnRole.UNKNOWN) or role is None):
            # Compute top value counts
            val_counts = series.value_counts().head(12)
            options = [
                SlicerOption(
                    value=val,
                    label=str(val),
                    count=int(cnt),
                )
                for val, cnt in val_counts.items()
            ]
            slicers.append(
                SlicerDef(
                    id=f"slicer_{col}",
                    column=col,
                    role="DIMENSION",
                    control_type="multi_select",
                    options=options,
                )
            )

    return slicers


def build_dashboard_tiles(
    discovered_insights: List[DiscoveredInsight],
    winner_ranked: Optional[RankedCandidate] = None,
    dataset: Optional[CanonicalDataset] = None,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> List[DashboardTile]:
    """Build Power BI-style tiles placed according to deterministic grid rules.

    Placement rules:
    Row 1: KPI strip, up to 4 KPI tiles (3 columns each, w=3, h=2).
    Row 2: Hero tile (highest-scoring TREND or RANKING, 8 columns, w=8, h=4)
           plus one side tile (4 columns, w=4, h=4, e.g. COMPOSITION as donut or horizontal bar).
    Next rows: remaining tiles in a 2- or 3-column masonry grid (w=6 or w=4, h=3), ordered by priority.
    """
    tiles: List[DashboardTile] = []
    if not discovered_insights and not winner_ranked:
        return tiles

    # Separate insights by category
    kpi_insights: List[DiscoveredInsight] = []
    visual_insights: List[DiscoveredInsight] = []

    for ins in discovered_insights:
        if ins.candidate.insight_type in (InsightType.TOTAL_KPI, InsightType.PERIOD_CHANGE) and not ins.candidate.dimension:
            kpi_insights.append(ins)
        else:
            visual_insights.append(ins)

    # Sort each group by score descending
    kpi_insights.sort(key=lambda x: x.score.total_score, reverse=True)
    visual_insights.sort(key=lambda x: x.score.total_score, reverse=True)

    # If no KPI insights discovered, synthesize up to 2 from measures if available
    if not kpi_insights and winner_ranked and winner_ranked.execution_result.rows:
        w_res = winner_ranked.execution_result
        w_plan = winner_ranked.plan
        # Create a KPI tile
        val = w_res.rows[0].get(w_res.columns[0]) if w_res.columns else 0
        kpi_title = _format_kpi_title(w_plan.metric.column, w_plan.metric.aggregation)
        kpi_tile = DashboardTile(
            id=f"tile_kpi_{uuid4().hex[:8]}",
            title=kpi_title,
            chart_type="kpi",
            size=TileSize(w=3, h=2),
            priority=1,
            generator=_format_provenance("rule_baseline"),
            evidence=None,
            plan=w_plan,
            compiled_sql=w_res.compiled_sql,
            data=w_res.rows,
            x_key=None,
            y_keys=[w_res.columns[0]] if w_res.columns else ["value"],
            metrics=[w_plan.metric.column],
            dimensions=[],
        )
        tiles.append(kpi_tile)

    # --- ROW 1: KPI STRIP (up to 4 tiles, 3 columns each) ---
    selected_kpis = kpi_insights[:4]
    for idx, kpi in enumerate(selected_kpis):
        res = kpi.execution_result
        cand = kpi.candidate
        col = cand.measure
        title = _format_kpi_title(col, cand.aggregation)
        tiles.append(
            DashboardTile(
                id=f"tile_kpi_{cand.candidate_id[:8]}",
                title=title,
                chart_type="kpi",
                size=TileSize(w=3, h=2),
                priority=idx + 1,
                candidate_id=cand.candidate_id,
                generator=_format_provenance(cand.proposed_by),
                evidence=None,
                why_chosen=kpi.why_chosen,
                plan=cand.plan,
                compiled_sql=res.compiled_sql,
                data=res.rows,
                x_key=None,
                y_keys=[res.columns[0]] if res.columns else ["value"],
                metrics=[cand.measure],
                dimensions=[],
            )
        )

    # If no visual insights discovered, synthesize baseline visual tile from dataset
    if not visual_insights and dataset is not None and dataset.data is not None and not dataset.data.empty:
        import pandas as pd
        df = dataset.data
        measures = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        dims = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() <= 50]
        if measures and dims:
            m_col = measures[0]
            d_col = dims[0]
            ev_m = semantic_profile.get_evidence(m_col) if semantic_profile else None
            is_avg = ev_m and ev_m.aggregation_default == "AVG"
            from orchestrator.schemas import MetricSpec, DimensionSpec, AggregationType, PlanReasoning
            base_agg = AggregationType.AVG if is_avg else AggregationType.SUM
            grouped = df.groupby(d_col)[m_col].mean().reset_index() if is_avg else df.groupby(d_col)[m_col].sum().reset_index()
            rows = grouped.to_dict(orient="records")
            base_title = f"Average {m_col} by {d_col}" if is_avg else f"Total {m_col} by {d_col}"
            cand_plan = CandidatePlan(
                dataset_id=dataset.metadata.dataset_id if hasattr(dataset, "metadata") else "ds",
                intent=base_title,
                metric=MetricSpec(column=m_col, aggregation=base_agg),
                dimensions=[DimensionSpec(column=d_col)],
                reasoning=PlanReasoning(interpretation=base_title, evidence=[]),
            )
            base_tile = DashboardTile(
                id=f"tile_base_{uuid4().hex[:8]}",
                title=base_title,
                chart_type="bar",
                size=TileSize(w=8, h=4),
                priority=len(tiles) + 1,
                generator="rule-based baseline",
                evidence=TileEvidence(strength=1.0, robustness=0.8, score=0.8, n=len(rows)),
                plan=cand_plan,
                data=rows,
                x_key=d_col,
                y_keys=[m_col],
                dimensions=[d_col],
                metrics=[m_col],
            )
            tiles.append(base_tile)

    # --- ROW 2: HERO TILE (8 cols) + SIDE TILE (4 cols) ---
    # Hero: highest-scoring TREND or RANKING
    hero_ins: Optional[DiscoveredInsight] = None
    side_ins: Optional[DiscoveredInsight] = None
    remaining_visuals: List[DiscoveredInsight] = []

    # First look for TREND or RANKING for hero
    for ins in visual_insights:
        if hero_ins is None and ins.candidate.insight_type in (InsightType.TREND, InsightType.RANKING):
            hero_ins = ins
        else:
            remaining_visuals.append(ins)

    # If no TREND/RANKING, take top visual insight
    if hero_ins is None and remaining_visuals:
        hero_ins = remaining_visuals.pop(0)

    # Now select side tile: prefer COMPOSITION, else top remaining
    side_candidates = [ins for ins in remaining_visuals if ins.candidate.insight_type == InsightType.COMPOSITION]
    if side_candidates:
        side_ins = side_candidates[0]
        remaining_visuals.remove(side_ins)
    elif remaining_visuals:
        side_ins = remaining_visuals.pop(0)

    # Helper to construct visual tile
    def _create_visual_tile(ins: DiscoveredInsight, size: TileSize, priority: int) -> DashboardTile:
        cand = ins.candidate
        res = ins.execution_result
        score = ins.score
        rows = res.rows or []
        dim = cand.dimension
        measure = cand.measure

        # Determine keys
        x_key = dim
        if not x_key and res.columns:
            x_key = res.columns[0]
        y_keys = [c for c in res.columns if c != x_key]
        if not y_keys and res.columns:
            y_keys = [res.columns[-1]]

        chart_type = _determine_chart_type(cand.insight_type, rows, x_key)

        return DashboardTile(
            id=f"tile_{cand.candidate_id[:8]}",
            title=ins.narration or f"{cand.insight_type.value} of {measure} across {dim}",
            chart_type=chart_type,
            size=size,
            priority=priority,
            candidate_id=cand.candidate_id,
            generator=_format_provenance(cand.proposed_by),
            evidence=TileEvidence(
                strength=score.strength,
                robustness=score.robustness,
                fdr_passed=score.fdr_passed,
                score=score.total_score,
                n=res.row_count,
            ),
            why_chosen=ins.why_chosen,
            plan=cand.plan,
            compiled_sql=res.compiled_sql,
            data=rows,
            x_key=x_key,
            y_keys=y_keys,
            dimensions=[dim] if dim else [],
            metrics=[measure],
        )

    current_priority = len(selected_kpis) + 1
    if hero_ins:
        tiles.append(_create_visual_tile(hero_ins, TileSize(w=8, h=4), current_priority))
        current_priority += 1

    if side_ins:
        tiles.append(_create_visual_tile(side_ins, TileSize(w=4, h=4), current_priority))
        current_priority += 1

    # --- NEXT ROWS: REMAINING TILES (masonry grid, w=6, h=3 each) ---
    for ins in remaining_visuals:
        tiles.append(_create_visual_tile(ins, TileSize(w=6, h=3), current_priority))
        current_priority += 1

    return tiles
