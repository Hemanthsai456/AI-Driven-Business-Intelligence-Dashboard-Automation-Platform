# Autonomous Overview Dashboard Engine Specification

**Status:** IMPLEMENTED & AUDITED  
**Audience:** Analytics Architects, Machine Learning Engineers, Frontend Developers  

---

## 1. Overview & Core Philosophy

The **Autonomous Overview Engine** (`orchestrator/overview/`) generates an end-to-end, multi-perspective business intelligence dashboard for any arbitrary dataset without requiring any prompt or manual SQL query.

### Non-Negotiable Principle: Generalized Analytical Reasoning
The engine **strictly rejects hardcoded column-name dictionaries or domain-specific mappings**. It does NOT map `"price" -> AVG` or `"sales" -> SUM` based on string matching. Instead, it reasons dynamically from:
1. **Dataset Grain & Entity Semantics**: Determining what a single row represents.
2. **Measure Properties**: Differentiating additive/extensive quantities from intensive rates, ratios, and averages.
3. **Cardinality & Distribution Geometry**: Evaluating distinct-to-total ratios, uniqueness, and missingness.
4. **Statistical Signal & Diversity**: Selecting complementary analytical perspectives (KPIs, Rankings, Compositions, Trends, Gaps, Correlations).

---

## 2. Architecture of the Overview Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                       Uploaded Dataset                          │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 1. Profiler & Semantic Intelligence (Roles, Cardinality, Stats) │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 2. Dataset Grain Inference (orchestrator/overview/reasoning.py) │
│    [ENTITY | TRANSACTION | REPEATED_OBSERVATION | SUMMARY]      │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 3. Measure & Aggregation Suitability Evaluation                 │
│    (Additive -> SUM, Rates/Averages/Unit -> AVG, Count -> COUNT)│
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 4. Candidate Generation across Diverse Analytical Families     │
│    [TOTAL_KPI, RANKING, COMPOSITION, TREND, SEGMENT_GAP, CORR] │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 5. Diversity-Aware Candidate Selection & Ranking                │
│    (Maximize dimension, metric, and analytical family spread)   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 6. 12-Column Grid DashboardSpec Assembly                        │
│    Row 1: KPI Strip | Row 2: Hero + Side | Row 3+: Grid Tiles   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│ 7. DuckDB Execution & Slicer Cross-Filtering Endpoint           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Dataset Grain Inference (`DatasetGrainType`)

The reasoning engine classifies the dataset grain to determine appropriate aggregation semantics:

| Grain Type | Definition | Exemplary Characteristics |
| :--- | :--- | :--- |
| `ENTITY` | 1 row represents an individual person, account, product, or subject. | High-uniqueness identifier exists; non-temporal; measure values describe static attributes. |
| `TRANSACTION_EVENT` | 1 row represents an event, sale, order, log entry, or transaction. | Contains timestamp columns; repetitive foreign keys (`CustomerID`, `StoreID`); additive quantities. |
| `REPEATED_OBSERVATION` | Repeated measurements over time or condition. | Multiple readings per entity over distinct chronological periods. |
| `GROUPED_SUMMARY` | Dataset is already aggregated. | Very low row count; pre-calculated totals; lack of unique transaction IDs. |
| `GENERAL_RECORD` | General tabular dataset. | Fallback when specific grain patterns are absent. |

---

## 4. Measure Semantics & Aggregation Suitability

The engine assigns an `AggregationSupportLevel` to candidate operations:
- `STRONGLY_SUPPORTED`: Natural primary analytical operation.
- `REASONABLY_SUPPORTED`: Valid secondary perspective.
- `WEAKLY_SUPPORTED`: Low analytical value.
- `INAPPROPRIATE`: Mathematically invalid (e.g., `SUM` on a unit price, discount percentage, or customer age).

### Evaluation Criteria:
1. **Additive / Extensive Quantities**: Quantities that accumulate naturally across transactions (e.g., revenue, volume, counts) support `SUM` as primary and `AVG` as secondary.
2. **Intensive Quantities & Rates**: Values representing per-unit prices, ratings, ratios, margins, or percentages are mathematically invalid under `SUM`. They strongly support `AVG`, `MEDIAN`, or distribution quantiles.
3. **Count Candidates**: For datasets where no continuous numeric measures exist, the engine synthesizes counting candidates (`COUNT(*)`, `COUNT(DISTINCT entity)`).

---

## 5. Grouping Dimension Selection

High-quality charts require analytically meaningful grouping dimensions:
- **Exclusion of High-Cardinality Identifiers**: Primary key columns with distinct-to-total ratio $\ge 0.90$ are excluded from grouping to avoid unreadable 10,000-slice charts.
- **Foreign Key Retention**: Repetitive identifier dimensions (`CustomerID`, `ProductID`) with moderate cardinality are retained as valid dimensions for ranking and grouping.
- **Low-to-Medium Cardinality Focus**: Categorical columns with 2 to 20 distinct values are prioritized for compositions and breakdowns.

---

## 6. Analytical Families & Diversity-Aware Selection

Candidates are generated across **six diverse analytical families**:

1. **`TOTAL_KPI`**: Headline measure totals or averages displayed on top KPI cards.
2. **`RANKING`**: Top/bottom category concentration share (e.g., Top 5 products by revenue).
3. **`COMPOSITION`**: Proportional distribution and share of total (e.g., revenue by region).
4. **`TREND`**: Chronological progression over temporal intervals ($R^2$, slope, direction).
5. **`SEGMENT_GAP`**: Categorical group disparity evaluated via ANOVA effect size ($\eta^2$).
6. **`CORRELATION`**: Bivariate Pearson correlation between continuous measures ($|r|$).

### Diversity-Aware Selection Algorithm
The ranker penalizes redundancy:
- Maximum of **one** tile per analytical family-dimension pair.
- Guarantees representation across multiple measures and multiple dimensions.
- Prevents a dashboard from containing five variations of the same measure.

---

## 7. Power BI-Style 12-Column Grid Layout

The overview dashboard arranges widgets deterministically on a **12-column responsive grid**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ ROW 1: KPI CONTEXT STRIP (Up to 4 tiles, w=3, h=2 each)                │
│ [ Total Revenue ]  [ Average Order ]  [ Total Volume ]  [ Active Stores│
├────────────────────────────────────────────────────────────────────────┤
│ ROW 2: HERO & SIDE TILES (h=4)                                         │
│ ┌──────────────────────────────────────────────┐ ┌───────────────────┐ │
│ │ HERO TILE (w=8, h=4)                         │ │ SIDE TILE (w=4)   │ │
│ │ Highest-scoring Trend Line or Segment Bar    │ │ Composition Donut │ │
│ └──────────────────────────────────────────────┘ └───────────────────┘ │
├────────────────────────────────────────────────────────────────────────┤
│ ROW 3+: SUPPORTING GRID (w=6 or w=4, h=3)                              │
│ ┌──────────────────────────────┐ ┌───────────────────────────────────┐ │
│ │ Supporting Visual 1 (w=6)    │ │ Supporting Visual 2 (w=6)         │ │
│ └──────────────────────────────┘ └───────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Runtime Slicers & Dynamic Cross-Filtering

Overview dashboards feature live interactive controls:

### Slicers
- `date_range`: Interactive temporal slider or date picker for datetime columns.
- `multi_select`: Checkbox dropdowns for low-cardinality dimensions ($\le 12$ distinct values).

### Dynamic Cross-Filtering Endpoint
`POST /api/dashboard/{spec_id}/tile/{tile_id}/query`
- When a user changes a slicer or clicks a chart slice, the frontend sends the active filter conditions.
- The backend dynamically recompiles the tile's candidate plan into parameterized DuckDB SQL with the injected filters.
- Returns updated rows and aggregations in real time without reloading the dashboard.

### Robustness Floor (`ROBUSTNESS_FLOOR = 0.35`)
- Configured centrally in `orchestrator/config.py`.
- If an insight's bootstrap stability score falls below `0.35`, the tile renders with an amber **"Low stability"** warning badge, alerting the user to sample volatility.
