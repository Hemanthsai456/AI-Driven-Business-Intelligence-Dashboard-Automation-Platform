# Stage F: Power BI-Style Interactive Dashboard Engine

This document specifies **Stage F: Power BI-Style Interactive Dashboard View**, covering layout, responsive grid geometry, runtime slicers, dynamic tile filtering, and frontend-backend contracts.

---

## 1. Overview & Principles

Stage F provides an enterprise-grade, deterministic dashboard experience modeled after modern business intelligence suites (Power BI, Tableau, Looker):
1. **Dynamic Grid Layout**: Driven entirely by `DashboardSpec.tiles`, placing widgets deterministically on a 12-column grid.
2. **Context vs Scored Tiles**: KPI cards represent high-level summary context without p-values or strength badges. Scored analytical tiles include provenance badges, strength wording, and robustness indicators.
3. **No Hardcoded Tokens**: Zero hardcoded dataset, column, or color names. All styles use semantic CSS theme tokens with dual-mode light and dark support.
4. **Interactive Cross-Filtering**: Selecting values in runtime slicers or chart marks triggers instantaneous re-execution of tile plans via DuckDB.

---

## 2. Deterministic Grid Placement Rules

Tiles are laid out on a **12-column CSS grid** according to strict rules:

```
┌────────────────────────────────────────────────────────────────────────┐
│ ROW 1: KPI STRIP (up to 4 tiles, 3 columns each, w=3, h=2)             │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│ │ Total Sales  │ │ Total Units  │ │ Average Price│ │ Profit Margin│    │
│ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘    │
├────────────────────────────────────────────────────────────────────────┤
│ ROW 2: HERO & SIDE TILES (8 + 4 columns, h=4)                          │
│ ┌──────────────────────────────────────────────┐ ┌───────────────────┐ │
│ │ HERO TILE (Highest-scoring Trend or Ranking) │ │ SIDE TILE (e.g.   │ │
│ │ (w=8, h=4)                                   │ │ Composition Donut)│ │
│ │                                              │ │ (w=4, h=4)        │ │
│ └──────────────────────────────────────────────┘ └───────────────────┘ │
├────────────────────────────────────────────────────────────────────────┤
│ ROW 3+: 2- OR 3-COLUMN SUPPORTING GRID (w=6 or w=4, h=3)               │
│ ┌──────────────────────────────┐ ┌───────────────────────────────────┐ │
│ │ Distribution Histogram (w=6) │ │ Segment Comparison Bar (w=6)      │ │
│ └──────────────────────────────┘ └───────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### Chart Type Selection
- `CORRELATION` $\to$ `scatter`
- `SEGMENT_GAP` and `RANKING` $\to$ `bar`
- `COMPOSITION` $\to$ `donut` ($\le 6$ groups) or `stacked` ($> 6$ groups)
- `TREND` $\to$ `line`
- `DISTRIBUTION` / `DISTRIBUTION_OUTLIERS` $\to$ `histogram`

---

## 3. Interactive Slicers & Dynamic Tile Recompilation

### 1. Dynamic Slicer Generation
The backend automatically analyzes column roles and cardinality:
- **`date_range` control**: 1 per `DATETIME` column with min/max bounds.
- **`multi_select` control**: 1 per low-cardinality `DIMENSION` ($\le 12$ unique values).

### 2. Tile Query Endpoint
```http
POST /api/dashboard/{spec_id}/tile/{tile_id}/query
```

#### Request Payload:
```json
{
  "filters": [
    {
      "column": "Region",
      "operator": "=",
      "values": ["North"]
    }
  ]
}
```

#### Recompilation & Execution Workflow:
1. Validates columns against semantic profile roles.
2. Checks input values against SQL injection whitelist.
3. Recompiles the tile's stored `CandidatePlan` into parameterized DuckDB SQL with injected `WHERE` clauses.
4. Executes the query in isolated DuckDB memory.
5. Emits updated aggregated rows to the frontend without reloading or regenerating the entire dashboard.

---

## 4. Stability Badge & Robustness Floor

A single global robustness floor (`ROBUSTNESS_FLOOR = 0.35` in `orchestrator/config.py`) governs:
1. **Headline Badge**: If the winning insight has robustness $< 0.35$, the headline panel displays an amber **"Low stability"** warning badge and excludes definitive phrasing like *"leads"*.
2. **Discovery Pruning**: Discovery candidates with robustness $< 0.35$ are rejected at the scoring stage.
3. **Tie Resolution**: Ranker tie handling enforces a strict floor before triggering user clarification.

---

## 5. End-to-End Browser Mark Validation

The frontend rendering pipeline is validated using Playwright running headless Microsoft Edge:
- Loads a full dashboard from a fixture specification.
- Inspects SVG DOM mark elements (`.recharts-bar-rectangles path` and `rect`).
- Asserts that all rendered bars have `height > 0`.
- Protects against container collapsing, flexbox zero-height regressions, and missing mark rendering.
