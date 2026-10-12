# Stage E: Automated Insight Discovery Engine

This document provides the complete architectural and mathematical specification of **Stage E: Autonomous Insight Discovery Mode** within **DashCrate**.

---

## 1. Overview & Objectives

Stage E transforms the system from single-query answering into an autonomous insight discovery engine. When a user presents a generic brief (e.g., *"give me a dashboard"*, *"explore this data"*, or an empty prompt), Stage E systematically discovers statistically grounded analytical findings rather than hallucinating generic charts.

### Core Principles
1. **Zero Hallucination Numbers**: Numbers and facts are computed exclusively by deterministic engines (DuckDB and NumPy/SciPy statistical models). Agents and LLMs propose only target plan signatures, never computed values.
2. **Exhaustive Candidate Enumeration**: Enumerates typed candidates across 8 statistical categories.
3. **Statistical Significance & FDR Control**: Benjamini-Hochberg False Discovery Rate (FDR) control at $\alpha=0.05$ rigorously eliminates spurious noise patterns.
4. **Number-Grounded Narration**: All generated text strings pass through a grounding guard verifying that every emitted statistic matches exact engine calculation results.

---

## 2. Seven-Stage Pipeline Architecture

```
┌────────────────────────────────────────────────────────┐
│ E1: Deterministic Candidate Insight Enumerator         │
│     (KPI, Ranking, Composition, Trend, Outliers, etc.)  │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ E2: Agent Proposals (Bounded Statistical Summaries)    │
│     (External Agent / LLM, strictly plan targets)      │
└───────────────────────────┬────────────────────────────┘
                            │ Combined & Deduplicated Plans
┌───────────────────────────▼────────────────────────────┐
│ E3: Execution & Pass 1 Validation                      │
│     (Compiler + Isolated DuckDB Workers + Pass 1a/1b)  │
└───────────────────────────┬────────────────────────────┘
                            │ Validated Result Tables
┌───────────────────────────▼────────────────────────────┐
│ E4: Multi-Objective Statistical Scoring & FDR Gate    │
│     (Strength, Robustness, FDR Control, Quality)       │
└───────────────────────────┬────────────────────────────┘
                            │ Passed Scored Insights
┌───────────────────────────▼────────────────────────────┐
│ E5: Diversity-Aware Dashboard Selection                │
│     (Coverage across metrics, dimensions, and types)   │
└───────────────────────────┬────────────────────────────┘
                            │ Selected Insights
┌───────────────────────────▼────────────────────────────┐
│ E6: Narration & Number Grounding Guard                 │
│     (Deterministic template / LLM grounded check)      │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ E7: Power BI-Style Tile Grid Assembly & Spec Emission   │
│     (12-column grid, KPI strip, hero, side, slicers)   │
└────────────────────────────────────────────────────────┘
```

---

## 3. Insight Types & Statistical Formulations

| Insight Type | Aggregation / Operands | Statistical Metric / Effect Size | Significance Test |
| :--- | :--- | :--- | :--- |
| **`TOTAL_KPI`** | `SUM` (extensive) or `AVG` (intensive) | Baseline summary indicator | Excluded from FDR by convention (descriptive baseline) |
| **`RANKING`** | Top-group share over $k$ categories | Normalized share: $\frac{p_{\text{top}} - 1/k}{1 - 1/k} \in [0, 1]$ | ANOVA $F$-test (measures) or Chi-square goodness-of-fit (counts) |
| **`COMPOSITION`** | Share of total | Concentration share | Same as ranking |
| **`TREND`** | Linear regression over time | Coefficient of determination $R^2 \in [0, 1]$ | $t$-test on slope coefficient $t = \frac{\beta_1}{\text{SE}(\beta_1)}$ |
| **`PERIOD_CHANGE`** | Period-over-period percentage change | Relative change $\min(1.0, \|\Delta\| / \|y_0\|)$ | $t$-test on period difference |
| **`CORRELATION`** | Bivariate Pearson correlation | Absolute Pearson $\|r\| \in [0, 1]$ | $t$-test on correlation $t = r \sqrt{\frac{n-2}{1-r^2}}$ |
| **`SEGMENT_GAP`** | Categorical group disparity | ANOVA effect size $\eta^2 = \frac{\text{SS}_{\text{between}}}{\text{SS}_{\text{total}}}$ | One-way ANOVA $F$-statistic $F = \frac{\text{MS}_{\text{between}}}{\text{MS}_{\text{within}}}$ |
| **`DISTRIBUTION_OUTLIERS`** | $Z$-score $> 3.0$ frequency | Outlier fraction effect size | Binomial / normal approximation against $P(\|Z\| > 3.0) \approx 0.0027$ |

---

## 4. Derived Measure Arithmetic Pruning

When measures have exact algebraic dependencies:
$$M_{\text{composite}} \approx M_A \times M_B \quad \text{or} \quad M_{\text{composite}} \approx M_A + M_B$$
Correlations between the composite and its factors (e.g. `TotalSales` with `Quantity` or `UnitPrice`) are flagged as `is_arithmetic=True` during candidate generation and automatically pruned before scoring with rejection reason:
`"arithmetic relationship"`

---

## 5. Multiple Testing Control: Benjamini-Hochberg FDR

Given $m$ statistical candidate hypotheses sorted by ascending $p$-value:
$$p_{(1)} \le p_{(2)} \le \dots \le p_{(m)}$$
For a false discovery rate $\alpha = 0.05$, find the largest index $k$ such that:
$$p_{(k)} \le \frac{k}{m} \alpha$$
All hypotheses $i \le k$ are declared statistically significant and survive the FDR gate. All $i > k$ are rejected with typed reasons:
`"Failed FDR control (p=0.4674 > critical threshold 0.0089)"`

### Empirical Noise Gate Benchmark (100 Seeds)
A pure Gaussian noise dataset ($N=100$) evaluated across 100 seeds yields an exact false-discovery count of **5/100 (5.0%)**, matching theoretical FDR expectations:
```
[NOISE GATE AT 100 SEEDS]: exact false-discovery count = 5/100 (rate: 5.0%)
Seeds with false discoveries: [(31, ['RANKING', 'COMPOSITION']), (41, ['DISTRIBUTION_OUTLIERS']), (53, ['RANKING', 'COMPOSITION']), (54, ['DISTRIBUTION_OUTLIERS']), (80, ['RANKING', 'COMPOSITION'])]
```

---

## 6. Narration Effect-Size Bands

Narration wording derives deterministically from configured effect-size bands:

```python
EFFECT_SIZE_BANDS = {
    InsightType.CORRELATION: [
        (0.00, 0.15, "negligible"),
        (0.15, 0.30, "weak"),
        (0.30, 0.50, "moderate"),
        (0.50, 0.70, "strong"),
        (0.70, 1.01, "very strong"),
    ],
    InsightType.RANKING: [
        (0.00, 0.10, "uniform"),
        (0.10, 0.25, "moderate lead"),
        (0.25, 0.50, "clear lead"),
        (0.50, 1.01, "dominant"),
    ],
}
```
For example, a Pearson correlation of $r = 0.42$ maps deterministically to `"moderate"`.
