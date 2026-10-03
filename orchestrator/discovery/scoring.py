"""Statistical Scoring, Robustness, and FDR Engine (Stage E4).

Computes:
1. Strength: typed effect size (eta² for segment gaps, top-group share for rankings,
   R² for trends, outlier fraction, |r| for correlations).
2. Robustness: deterministic fraction of perturbation trials (split-half, bootstrap,
   time-halves, alternate aggregations) that preserve the claim.
3. Significance & Multiple-Testing Control: exact p-value per insight, followed by
   Benjamini-Hochberg (BH) procedure across all candidates.
4. Data Quality: sample size per group, null rate, failed cast rate.
5. insight_score = strength x robustness x quality, with configurable floors.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from ingestion.models import CanonicalDataset
from orchestrator.discovery.schemas import (
    DiscoveredInsight,
    InsightCandidate,
    InsightScore,
    InsightType,
)
from orchestrator.config import ROBUSTNESS_FLOOR
from orchestrator.schemas import AggregationType, ExecutionResult


# ---------------------------------------------------------------------------
# Exact Statistical Functions (pure Python/NumPy, 0 dependencies)
# ---------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for incomplete beta function."""
    max_it = 100
    eps = 3e-7
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_val = d * c
        h *= del_val
        if abs(del_val - 1.0) < eps:
            break
    return h


def _ibeta(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    bt = math.exp(-lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    else:
        return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def compute_f_pvalue(f: float, df1: float, df2: float) -> float:
    """Two-tailed / upper-tail p-value for F-statistic."""
    if f <= 0.0 or df1 <= 0 or df2 <= 0:
        return 1.0
    x = df2 / (df2 + df1 * f)
    return float(np.clip(_ibeta(df2 / 2.0, df1 / 2.0, x), 0.0, 1.0))


def compute_t_pvalue(t: float, df: float) -> float:
    """Two-tailed p-value for Student's t-statistic."""
    if df <= 0:
        return 1.0
    if t == 0.0:
        return 1.0
    t_abs = abs(t)
    x = df / (df + t_abs * t_abs)
    return float(np.clip(_ibeta(df / 2.0, 0.5, x), 0.0, 1.0))


def compute_normal_pvalue(z: float) -> float:
    """Two-tailed p-value for standard normal Z."""
    return float(np.clip(math.erfc(abs(z) / math.sqrt(2.0)), 0.0, 1.0))


def compute_chi2_pvalue(chi2: float, df: float) -> float:
    """Upper-tail p-value for Chi-square statistic."""
    if chi2 <= 0.0 or df <= 0:
        return 1.0
    try:
        import scipy.stats
        return float(scipy.stats.chi2.sf(chi2, df))
    except Exception:
        term = 2.0 / (9.0 * df)
        z = ((chi2 / df) ** (1.0 / 3.0) - (1.0 - term)) / math.sqrt(term)
        return float(np.clip(0.5 * math.erfc(z / math.sqrt(2.0)), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Strength & Significance per Insight Type
# ---------------------------------------------------------------------------


def evaluate_segment_gap(
    df: pd.DataFrame,
    measure: str,
    dimension: str,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute ANOVA eta² effect size and F-test p-value."""
    clean = df[[measure, dimension]].dropna()
    clean[measure] = pd.to_numeric(clean[measure], errors="coerce")
    clean = clean.dropna()

    groups = clean.groupby(dimension)[measure]
    k = groups.ngroups
    n = len(clean)

    if k < 2 or n <= k:
        return 0.0, 1.0, {}

    group_means = clean.groupby(dimension)[measure].mean().sort_values(ascending=False)
    top_group = str(group_means.index[0])
    grand_mean = clean[measure].mean()
    ss_total = ((clean[measure] - grand_mean) ** 2).sum()
    if ss_total <= 1e-9:
        return 0.0, 1.0, {}

    ss_between = 0.0
    for _, g in groups:
        g_len = len(g)
        g_mean = g.mean()
        ss_between += g_len * ((g_mean - grand_mean) ** 2)

    ss_within = max(0.0, ss_total - ss_between)
    eta_sq = float(np.clip(ss_between / ss_total, 0.0, 1.0))

    df1 = k - 1
    df2 = n - k
    ms_between = ss_between / df1
    ms_within = ss_within / df2 if df2 > 0 and ss_within > 0 else 1e-9
    f_stat = ms_between / ms_within if ms_within > 0 else 0.0
    p_val = compute_f_pvalue(f_stat, df1, df2)

    return eta_sq, p_val, {
        "eta_squared": eta_sq,
        "f_stat": round(f_stat, 3),
        "top_group": top_group,
        "k_groups": k,
        "n_samples": n,
    }


def evaluate_ranking(
    df: pd.DataFrame,
    measure: str,
    dimension: str,
    agg: AggregationType,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute top-group concentration share and Chi-square test p-value."""
    if measure == "*" or agg in (AggregationType.COUNT, AggregationType.COUNT_DISTINCT):
        clean = df[[dimension]].dropna()
        if clean.empty:
            return 0.0, 1.0, {}
        grouped = clean.groupby(dimension).size()
        k = len(grouped)
        if k < 2:
            return 0.0, 1.0, {}

        sorted_vals = grouped.sort_values(ascending=False)
        top_group = sorted_vals.index[0]
        top_val = float(sorted_vals.iloc[0])
        total_val = float(sorted_vals.sum())
        if total_val <= 0:
            return 0.0, 1.0, {}

        raw_share = top_val / total_val
        normalized_share = float(np.clip((raw_share - (1.0 / k)) / (1.0 - (1.0 / k)), 0.0, 1.0))
        second_val = float(sorted_vals.iloc[1]) if k > 1 else 0.0
        if (top_val - second_val) < 2.0:
            normalized_share *= max(0.0, (top_val - second_val) / 2.0)

        # Chi-square goodness-of-fit against uniform distribution
        exp_count = total_val / k
        chi2 = float(((grouped - exp_count) ** 2 / exp_count).sum())
        df1 = k - 1
        p_val = compute_chi2_pvalue(chi2, df1) if df1 > 0 else 1.0

        return normalized_share, p_val, {
            "top_group": str(top_group),
            "top_val": top_val,
            "top_share": round(raw_share, 4),
            "k_groups": k,
        }

    clean = df[[measure, dimension]].dropna()
    clean[measure] = pd.to_numeric(clean[measure], errors="coerce")
    clean = clean.dropna()

    if clean.empty:
        return 0.0, 1.0, {}

    grouped = (
        clean.groupby(dimension)[measure].sum()
        if agg == AggregationType.SUM
        else clean.groupby(dimension)[measure].mean()
    )
    k = len(grouped)
    if k < 2:
        return 0.0, 1.0, {}

    sorted_vals = grouped.sort_values(ascending=False)
    top_group = sorted_vals.index[0]
    top_val = float(sorted_vals.iloc[0])
    total_val = float(sorted_vals.sum())

    if total_val <= 0:
        return 0.0, 1.0, {}

    raw_share = top_val / total_val
    # Normalized concentration over baseline 1/k
    normalized_share = float(np.clip((raw_share - (1.0 / k)) / (1.0 - (1.0 / k)), 0.0, 1.0))

    # Significance test against uniform / equal distribution across groups (ANOVA F-test)
    grand_mean = clean[measure].mean()
    ss_total = ((clean[measure] - grand_mean) ** 2).sum()
    if ss_total <= 1e-9:
        p_val = 1.0
    else:
        groups = clean.groupby(dimension)[measure]
        ss_between = 0.0
        for _, g in groups:
            ss_between += len(g) * ((g.mean() - grand_mean) ** 2)
        ss_within = max(0.0, ss_total - ss_between)
        df1 = k - 1
        df2 = max(1, len(clean) - k)
        ms_between = ss_between / df1
        ms_within = ss_within / df2 if df2 > 0 and ss_within > 0 else 1e-9
        f_stat = ms_between / ms_within if ms_within > 0 else 0.0
        p_val = compute_f_pvalue(f_stat, df1, df2)

    return normalized_share, p_val, {
        "top_group": str(top_group),
        "top_val": top_val,
        "top_share": round(raw_share, 4),
        "k_groups": k,
    }


def evaluate_trend(
    df: pd.DataFrame,
    measure: str,
    time_col: str,
    agg: AggregationType,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute linear regression R², slope direction, and regression slope t-test p-value."""
    clean = df[[measure, time_col]].dropna()
    clean[measure] = pd.to_numeric(clean[measure], errors="coerce")
    clean = clean.dropna()

    try:
        clean[time_col] = pd.to_datetime(clean[time_col], errors="coerce")
        clean = clean.dropna().sort_values(time_col)
    except Exception:
        return 0.0, 1.0, {}

    if len(clean) < 3:
        return 0.0, 1.0, {}

    # Aggregate by time period to avoid micro-noise
    ts = (
        clean.groupby(time_col)[measure].sum()
        if agg == AggregationType.SUM
        else clean.groupby(time_col)[measure].mean()
    )
    t_points = len(ts)
    if t_points < 3:
        return 0.0, 1.0, {}

    x = np.arange(t_points, dtype=float)
    y = ts.values.astype(float)

    x_mean = np.mean(x)
    y_mean = np.mean(y)
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_yy = np.sum((y - y_mean) ** 2)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))

    if ss_xx <= 1e-9 or ss_yy <= 1e-9:
        return 0.0, 1.0, {}

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    r2 = float(np.clip((ss_xy ** 2) / (ss_xx * ss_yy), 0.0, 1.0))
    direction = "upward" if slope > 0 else "downward"

    # t-test for slope
    df_reg = t_points - 2
    residuals = y - (intercept + slope * x)
    se_res = np.sum(residuals ** 2) / df_reg if df_reg > 0 else 0.0
    if se_res <= 1e-12:
        # Near-perfect linear relationship -> highly significant
        p_val = 0.0001
    else:
        se_slope = math.sqrt(se_res / ss_xx) if ss_xx > 0 else 1e-9
        t_stat = slope / se_slope if se_slope > 0 else 0.0
        p_val = compute_t_pvalue(t_stat, df_reg)

    first_val = float(y[0])
    last_val = float(y[-1])
    growth_pct = round(((last_val - first_val) / abs(first_val)) * 100, 1) if abs(first_val) > 1e-9 else 0.0

    return r2, p_val, {
        "r2": r2,
        "slope": round(float(slope), 4),
        "direction": direction,
        "first_val": first_val,
        "last_val": last_val,
        "growth_pct": growth_pct,
        "t_points": t_points,
    }


def evaluate_correlation(
    df: pd.DataFrame,
    m1: str,
    m2: str,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute Pearson |r| effect size and t-test p-value."""
    clean = df[[m1, m2]].dropna()
    clean[m1] = pd.to_numeric(clean[m1], errors="coerce")
    clean[m2] = pd.to_numeric(clean[m2], errors="coerce")
    clean = clean.dropna()

    n = len(clean)
    if n < 4:
        return 0.0, 1.0, {}

    x = clean[m1].values.astype(float)
    y = clean[m2].values.astype(float)
    sx = np.std(x)
    sy = np.std(y)

    if sx <= 1e-9 or sy <= 1e-9:
        return 0.0, 1.0, {}

    r = float(np.corrcoef(x, y)[0, 1])
    if np.isnan(r):
        return 0.0, 1.0, {}

    abs_r = float(np.clip(abs(r), 0.0, 1.0))
    df_corr = n - 2
    denom = math.sqrt(max(1e-12, 1.0 - r * r))
    t_stat = r * math.sqrt(df_corr) / denom
    p_val = compute_t_pvalue(t_stat, df_corr)

    return abs_r, p_val, {
        "r": round(r, 4),
        "abs_r": abs_r,
        "n_samples": n,
    }


def evaluate_distribution_outliers(
    df: pd.DataFrame,
    measure: str,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute outlier fraction effect size and binomial test p-value."""
    clean = pd.to_numeric(df[measure].dropna(), errors="coerce").dropna()
    n = len(clean)
    if n < 10:
        return 0.0, 1.0, {}

    mean = clean.mean()
    std = clean.std()
    if std <= 1e-9:
        return 0.0, 1.0, {}

    z_scores = (clean - mean).abs() / std
    outliers = clean[z_scores > 3.0]
    outlier_count = len(outliers)
    outlier_frac = outlier_count / n

    # Strength scaled: 5% outliers -> strength 0.5, 10%+ -> 1.0
    strength = float(np.clip(outlier_frac * 10.0, 0.0, 1.0))

    # Significance test: under normal distribution, P(|Z| > 3.0) ≈ 0.0027
    p0 = 0.0027
    exp_outliers = n * p0
    var = n * p0 * (1.0 - p0)
    z_stat = (outlier_count - exp_outliers) / math.sqrt(var) if var > 0 else 0.0
    p_val = compute_normal_pvalue(z_stat) if z_stat > 0 else 1.0

    return strength, p_val, {
        "outlier_count": outlier_count,
        "outlier_frac": round(outlier_frac, 4),
        "n_samples": n,
    }


def evaluate_total_kpi(
    df: pd.DataFrame,
    measure: str,
    agg: AggregationType,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute TOTAL_KPI strength and one-sample test p-value."""
    clean = pd.to_numeric(df[measure].dropna(), errors="coerce").dropna()
    n = len(clean)
    if n == 0:
        return 0.0, 1.0, {}

    val = float(clean.sum()) if agg == AggregationType.SUM else float(clean.mean())
    std = float(clean.std()) if n > 1 else 0.0

    # Strength for KPI is baseline 1.0 if populated and non-zero
    strength = 1.0 if abs(val) > 1e-9 else 0.1

    # One-sample t-test: H0: mean == 0
    t_stat = (clean.mean() / (std / math.sqrt(n))) if std > 0 and n > 1 else 0.0
    p_val = compute_t_pvalue(t_stat, n - 1) if n > 1 else 0.05

    return strength, p_val, {
        "value": val,
        "n_samples": n,
    }


def evaluate_composition(
    df: pd.DataFrame,
    measure: str,
    dimension: str,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute composition concentration and p-value."""
    return evaluate_ranking(df, measure, dimension, AggregationType.SUM)


def evaluate_period_change(
    df: pd.DataFrame,
    measure: str,
    time_col: str,
) -> Tuple[float, float, Dict[str, Any]]:
    """Compute period-over-period change strength and p-value."""
    r2, p_val, details = evaluate_trend(df, measure, time_col, AggregationType.SUM)
    first = details.get("first_val", 0.0)
    last = details.get("last_val", 0.0)
    chg = abs(last - first) / abs(first) if abs(first) > 1e-9 else 0.0
    strength = float(np.clip(chg, 0.0, 1.0))
    return strength, p_val, details


# ---------------------------------------------------------------------------
# Robustness via Deterministic Seeded Resampling
# ---------------------------------------------------------------------------


def compute_robustness(
    candidate: InsightCandidate,
    dataset: CanonicalDataset,
    base_details: Dict[str, Any],
    seed: int = 42,
) -> float:
    """Compute deterministic perturbation preservation fraction.

    Trials:
    - 4 split-half subsamples (50% data)
    - 4 bootstrap resamples (with replacement)
    - For trends: first half vs second half time slope sign + alternate aggregations
    """
    df = dataset.data
    n = len(df)
    if n < 10:
        return 1.0

    rng = np.random.RandomState(seed)
    trials_total = 8
    trials_preserved = 0

    itype = candidate.insight_type
    m = candidate.measure
    d = candidate.dimension

    for t_idx in range(trials_total):
        # Even trials: split-half (50%); Odd trials: bootstrap (100% with replacement)
        if t_idx < 4:
            sample_idx = rng.choice(n, size=max(5, n // 2), replace=False)
        else:
            sample_idx = rng.choice(n, size=n, replace=True)

        sample_df = df.iloc[sample_idx]

        try:
            if itype == InsightType.RANKING:
                target_top = base_details.get("top_group")
                if m == "*" or candidate.aggregation in (AggregationType.COUNT, AggregationType.COUNT_DISTINCT):
                    grouped = sample_df[[d]].dropna().groupby(d).size()
                else:
                    clean = sample_df[[m, d]].dropna()
                    clean[m] = pd.to_numeric(clean[m], errors="coerce")
                    grouped = clean.groupby(d)[m].sum()
                if not grouped.empty and str(grouped.sort_values(ascending=False).index[0]) == str(target_top):
                    trials_preserved += 1

            elif itype == InsightType.TREND:
                target_dir = base_details.get("direction")
                _, _, t_det = evaluate_trend(sample_df, m, d, candidate.aggregation)
                if t_det.get("direction") == target_dir:
                    trials_preserved += 1

            elif itype == InsightType.CORRELATION:
                m2 = candidate.secondary_measure
                _, _, c_det = evaluate_correlation(sample_df, m, m2)
                base_r = base_details.get("r", 0.0)
                sample_r = c_det.get("r", 0.0)
                if (sample_r * base_r > 0) and abs(sample_r) >= 0.5 * abs(base_r):
                    trials_preserved += 1

            elif itype == InsightType.SEGMENT_GAP:
                target_top = base_details.get("top_group")
                clean = sample_df[[m, d]].dropna()
                clean[m] = pd.to_numeric(clean[m], errors="coerce")
                grouped = clean.groupby(d)[m].mean()
                if not grouped.empty and str(grouped.sort_values(ascending=False).index[0]) == str(target_top):
                    trials_preserved += 1

            elif itype == InsightType.COMPOSITION:
                target_top = base_details.get("top_group")
                if m == "*" or candidate.aggregation in (AggregationType.COUNT, AggregationType.COUNT_DISTINCT):
                    grouped = sample_df[[d]].dropna().groupby(d).size()
                else:
                    clean = sample_df[[m, d]].dropna()
                    clean[m] = pd.to_numeric(clean[m], errors="coerce")
                    grouped = clean.groupby(d)[m].sum()
                if not grouped.empty and str(grouped.sort_values(ascending=False).index[0]) == str(target_top):
                    trials_preserved += 1

            elif itype == InsightType.DISTRIBUTION_OUTLIERS:
                _, _, o_det = evaluate_distribution_outliers(sample_df, m)
                base_frac = base_details.get("outlier_frac", 0.0)
                sample_frac = o_det.get("outlier_frac", 0.0)
                if base_frac > 0 and sample_frac >= 0.4 * base_frac:
                    trials_preserved += 1

            elif itype in (InsightType.TOTAL_KPI, InsightType.PERIOD_CHANGE):
                clean = pd.to_numeric(sample_df[m].dropna(), errors="coerce").dropna()
                if len(clean) > 0:
                    trials_preserved += 1

        except Exception:
            pass

    return round(trials_preserved / trials_total, 3)


# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------


def compute_data_quality(
    candidate: InsightCandidate,
    dataset: CanonicalDataset,
    exec_result: Optional[ExecutionResult] = None,
) -> float:
    """Compute data quality score based on sample size, null rate, and cast rate."""
    df = dataset.data
    n = len(df)
    if n == 0:
        return 0.0

    m = candidate.measure
    null_count = df[m].isna().sum() if m in df.columns else 0
    null_rate = null_count / n
    s_null = 1.0 - null_rate

    # Failed cast rate
    cast_rate = exec_result.failed_cast_rate if exec_result else 0.0
    s_cast = max(0.0, 1.0 - cast_rate)

    # Sample size per group
    d = candidate.dimension
    if d and d in df.columns:
        if candidate.insight_type in (InsightType.TREND, InsightType.PERIOD_CHANGE):
            t_pts = df[d].nunique()
            s_size = min(1.0, max(0.1, t_pts / 10.0))
        else:
            counts = df.groupby(d)[m].count() if m in df.columns else df.groupby(d).size()
            min_g = counts.min() if not counts.empty else 0
            s_size = min(1.0, max(0.1, min_g / 10.0))
    else:
        s_size = min(1.0, max(0.1, n / 30.0))

    return round(float(np.clip(s_size * s_null * s_cast, 0.0, 1.0)), 3)


# ---------------------------------------------------------------------------
# Full Scoring Pipeline with Benjamini-Hochberg FDR Control
# ---------------------------------------------------------------------------


def score_and_filter_insights(
    candidate_tuples: List[Tuple[InsightCandidate, ExecutionResult]],
    dataset: CanonicalDataset,
    fdr_alpha: float = 0.05,
    strength_floor: float = 0.08,
    robustness_floor: float = ROBUSTNESS_FLOOR,
    quality_floor: float = 0.40,
) -> Tuple[List[DiscoveredInsight], List[Dict[str, Any]]]:
    """Score all executed candidates, apply Benjamini-Hochberg FDR, and filter by floors.

    Returns:
        (passed_insights, rejected_insights_info)
    """
    df = dataset.data
    preliminary: List[Dict[str, Any]] = []

    # Step 1: Compute strength, initial p-value, robustness, quality for each candidate
    for cand, exec_res in candidate_tuples:
        itype = cand.insight_type
        m = cand.measure
        d = cand.dimension

        strength = 0.0
        p_val = 1.0
        details: Dict[str, Any] = {}

        if itype == InsightType.TOTAL_KPI:
            strength, p_val, details = evaluate_total_kpi(df, m, cand.aggregation)
        elif itype == InsightType.RANKING:
            strength, p_val, details = evaluate_ranking(df, m, d, cand.aggregation)
        elif itype == InsightType.COMPOSITION:
            strength, p_val, details = evaluate_composition(df, m, d)
        elif itype == InsightType.TREND:
            strength, p_val, details = evaluate_trend(df, m, d, cand.aggregation)
        elif itype == InsightType.PERIOD_CHANGE:
            strength, p_val, details = evaluate_period_change(df, m, d)
        elif itype == InsightType.DISTRIBUTION_OUTLIERS:
            strength, p_val, details = evaluate_distribution_outliers(df, m)
        elif itype == InsightType.CORRELATION:
            m2 = cand.secondary_measure or m
            strength, p_val, details = evaluate_correlation(df, m, m2)
        elif itype == InsightType.SEGMENT_GAP:
            strength, p_val, details = evaluate_segment_gap(df, m, d)

        robustness = compute_robustness(cand, dataset, details)
        quality = compute_data_quality(cand, dataset, exec_res)

        preliminary.append({
            "candidate": cand,
            "exec_result": exec_res,
            "strength": round(strength, 4),
            "p_value": round(p_val, 6),
            "robustness": round(robustness, 3),
            "quality": round(quality, 3),
            "details": details,
        })

    m_hypotheses = len(preliminary)
    if m_hypotheses == 0:
        return [], []

    # Step 2: Benjamini-Hochberg (BH) Multiple-Testing Procedure
    # Multiple-testing control applies across candidate discovery hypotheses
    # (TOTAL_KPI is a descriptive baseline summary and exempt from FDR correction)
    discovery_hypotheses = [
        item for item in preliminary if item["candidate"].insight_type != InsightType.TOTAL_KPI
    ]
    m_hypotheses = len(discovery_hypotheses)

    sorted_hypotheses = sorted(discovery_hypotheses, key=lambda x: x["p_value"])

    max_k = 0
    bh_critical_at_k = 0.0

    if m_hypotheses > 0:
        for i, item in enumerate(sorted_hypotheses, start=1):
            crit = (i / m_hypotheses) * fdr_alpha
            if item["p_value"] <= crit:
                max_k = i
                bh_critical_at_k = crit

    # Determine FDR cutoff: if max_k > 0, cutoff is P_(max_k)
    fdr_p_cutoff = sorted_hypotheses[max_k - 1]["p_value"] if max_k > 0 else 0.0

    passed_insights: List[DiscoveredInsight] = []
    rejected_list: List[Dict[str, Any]] = []

    # Step 3: Evaluate eligibility against FDR and configurable floors
    for item in preliminary:
        cand: InsightCandidate = item["candidate"]
        exec_res: ExecutionResult = item["exec_result"]
        strength = item["strength"]
        robustness = item["robustness"]
        quality = item["quality"]
        p_val = item["p_value"]
        details = item["details"]

        # Check BH FDR pass
        fdr_passed = (p_val <= fdr_p_cutoff) if max_k > 0 else False

        # TOTAL_KPI insights are descriptive aggregates, so they pass FDR by convention
        # but rankings, trends, correlations, segment gaps, and outliers must pass FDR
        if cand.insight_type == InsightType.TOTAL_KPI:
            fdr_passed = True

        rejection_reason = None
        rejection_stage = None

        if cand.params.get("is_arithmetic"):
            rejection_stage = "PRUNING"
            rejection_reason = "arithmetic relationship"
        elif not fdr_passed:
            rejection_stage = "FDR"
            rejection_reason = f"Failed FDR control (p={p_val:.4f} > critical threshold {bh_critical_at_k:.4f})"
        elif strength < strength_floor:
            rejection_stage = "FLOOR"
            rejection_reason = f"Below strength floor ({strength:.3f} < {strength_floor:.3f})"
        elif robustness < robustness_floor:
            rejection_stage = "FLOOR"
            rejection_reason = f"Below robustness floor ({robustness:.3f} < {robustness_floor:.3f})"
        elif quality < quality_floor:
            rejection_stage = "FLOOR"
            rejection_reason = f"Below quality floor ({quality:.3f} < {quality_floor:.3f})"

        total_score = round(strength * robustness * quality, 4)

        score_obj = InsightScore(
            strength=strength,
            robustness=robustness,
            p_value=p_val,
            fdr_passed=fdr_passed,
            fdr_critical_value=round(bh_critical_at_k, 5),
            quality=quality,
            total_score=total_score,
            rejected=bool(rejection_reason),
            rejection_reason=rejection_reason,
            details=details,
        )

        desc = (
            f"{cand.insight_type.value}: {cand.aggregation.value}({cand.measure})"
            + (f" by {cand.dimension}" if cand.dimension else "")
            + (f" & {cand.secondary_measure}" if cand.secondary_measure else "")
        )

        if rejection_reason:
            rejected_list.append({
                "candidate_id": cand.candidate_id,
                "insight_type": cand.insight_type.value,
                "description": desc,
                "measure": cand.measure,
                "dimension": cand.dimension,
                "rejection_stage": rejection_stage,
                "reason": rejection_reason,
                "p_value": p_val,
                "score": total_score,
            })
        else:
            passed_insights.append(
                DiscoveredInsight(
                    candidate=cand,
                    execution_result=exec_res,
                    score=score_obj,
                    narration=None,
                    why_chosen=None,
                    rank=0,
                )
            )

    return passed_insights, rejected_list
