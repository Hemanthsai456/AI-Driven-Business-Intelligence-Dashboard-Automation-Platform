# Exploratory Data Analysis (EDA) Engine Specification

**Status:** IMPLEMENTED & AUDITED  
**Audience:** Data Scientists, Analytics Engineers, Frontend Developers  

---

## 1. Overview & Core Principles

The **Exploratory Data Analysis (EDA) Engine** (`intelligence/eda.py`) provides deterministic, read-only statistical profiling and interactive visual exploration for any uploaded dataset.

### Core Principles
1. **100% Read-Only Immutability**: All computations operate strictly on copies or read-only references; neither the `CanonicalDataset` nor its metadata are mutated.
2. **Zero LLM Dependency for Calculations**: All metrics, bin intervals, quantiles, correlation coefficients, and frequencies are computed deterministically with **NumPy** and **Pandas**.
3. **Dual Exploration Modes**:
   - **Automated EDA Summary**: One-click comprehensive dataset characterization.
   - **Manual Ad-Hoc Exploration**: User-driven bivariate and multivariate slicing with automatic visualization mapping.
4. **Theme-Adaptive Rendering**: Chart marks, axes, grid lines, and tooltips react dynamically to light and dark theme modes using centralized theme tokens.

---

## 2. Automated EDA Summary Architecture

The automated summary endpoint (`GET /api/datasets/{dataset_id}/eda`) returns an `EDASummary` object containing six analytical modules:

```
┌────────────────────────────────────────────────────────┐
│                   AUTOMATED EDA SUMMARY                │
├────────────────────────────────────────────────────────┤
│ 1. Compact Dataset Profile                             │
│ 2. Numeric Distributions (10-Bin Histograms + Skew)    │
│ 3. Categorical Distributions (Top 10 + High Card)      │
│ 4. Pearson Correlation Matrix (Bivariate Heatmap)      │
│ 5. Temporal Analysis (Chronological Aggregations)      │
│ 6. Automated Statistical Observations (Factual Bullets)│
└────────────────────────────────────────────────────────┘
```

### 2.1 Compact Dataset Profile
- Total row count, column count, total missing cells, and overall missingness rate.
- Column breakdown by physical and semantic types: counts of numeric measures, categorical dimensions, datetime fields, and booleans.

### 2.2 Numeric Distributions
For every numeric column (or column classified as `MEASURE`):
- **Summary Statistics**: Min, Max, Mean, Standard Deviation, Median, Q25, Q75, Interquartile Range (IQR).
- **10-Bin Histograms**: Uniform 10-bin intervals across $[min, max]$, returning bin edges and frequency counts.
- **Skewness Indication**: Computed using sample skewness formula:
  - $\text{Skew} > 1.0$: Strong Right-Skewed (Long tail on high values).
  - $\text{Skew} < -1.0$: Strong Left-Skewed (Long tail on low values).
  - $-1.0 \le \text{Skew} \le 1.0$: Approximately Symmetric / Normal.

### 2.3 Categorical Distributions
For every categorical column (or column classified as `DIMENSION`):
- **Top 10 Categories**: Frequency count and percentage share of total non-null rows.
- **Other Category Binning**: Tail values beyond top 10 are grouped into `"Other"` to preserve visual clarity.
- **High-Cardinality Flag**: Marked if distinct value ratio $> 0.20$ or total distinct count $> 50$, warning against inappropriate grouping.

### 2.4 Pearson Correlation Matrix
For all numeric column pairs $(X, Y)$:
- Calculates bivariate Pearson correlation coefficient $r \in [-1.0, 1.0]$:
  $$r = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sqrt{\sum (x_i - \bar{x})^2 \sum (y_i - \bar{y})^2}}$$
- **Constant Column Guard**: Zero-variance columns are automatically flagged with $r = 0.0$ to prevent division-by-zero runtime exceptions.
- **Missingness Handling**: Computed on pairwise non-null intersections.

### 2.5 Temporal Analysis
If one or more columns represent chronological timestamps (`DATETIME` or datetime-like strings):
- Automatic detection of temporal grain (Yearly, Monthly, Daily).
- Computes chronological row counts and trends of primary numeric measures across the timeline.

### 2.6 Automated Statistical Observations
Generates 5 to 10 evidence-grounded factual bullet points summarizing key dataset characteristics without causal speculation:
- Identification of dominant categories (e.g., *"Category 'Electronics' represents 42.1% of all records"*).
- Strong positive or negative correlations (e.g., *"'UnitPrice' and 'TotalSales' exhibit a strong positive correlation (r = 0.88)"*).
- Outlier warnings and extreme skewness alerts.

---

## 3. Manual Ad-Hoc Exploration (`intelligence/eda.py`)

Users can explore relationships between arbitrary columns via `POST /api/datasets/{dataset_id}/eda/explore`:

### 3.1 Type-Aware Chart Selection
The engine dynamically determines the optimal chart geometry based on column data types:

| Variable Selection | Chart Type | Aggregation / Behavior |
| :--- | :--- | :--- |
| **Numeric $\times$ Numeric** | Scatter Plot | Direct coordinate mapping $(x, y)$. |
| **Datetime $\times$ Numeric** | Line Chart | Chronologically sorted aggregation (AVG or SUM). |
| **Categorical $\times$ Numeric** | Grouped Bar Chart | Aggregated metric grouped by category. |
| **Single Numeric** | Histogram | 10-bin frequency distribution. |
| **Single Categorical** | Bar Chart | Category frequency count. |

### 3.2 Deterministic Sampling for Large Datasets
- For scatter plots where row count exceeds **1,000 rows**, the engine applies deterministic pseudo-random sampling (fixed seed) down to 1,000 points.
- Guarantees instant browser rendering while preserving the statistical distribution shape and boundary outliers.

---

## 4. Frontend Implementation & Theme Compatibility

The EDA UI (`frontend/components/data_studio/EDATab.tsx`) integrates with the platform's centralized theme architecture (`frontend/lib/chartTheme.ts`):

- **Zero Hardcoded CSS Colors**: Backgrounds, grid strokes, axes, and text labels bind directly to design tokens (`var(--surface)`, `var(--border)`, `var(--text)`, `var(--muted-foreground)`).
- **Light & Dark Theme Switch Reaction**: Charts update instantly upon theme toggle without requiring canvas reload or page refresh.
- **Tooltip Styling**: Custom theme-aware tooltips with high contrast against both light surfaces (`#FFFFFF`) and dark elevated containers (`#222B34`).
- **High-Contrast Chart Marks**: Uses curated palette series (`chartSeries`) specifically calibrated for readability across both light and dark backgrounds.
