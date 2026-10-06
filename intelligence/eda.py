"""Deterministic Exploratory Data Analysis (EDA) Engine.

Provides:
1. Automated EDA Summary:
   - Compact Dataset Summary
   - Numeric Distributions (10-bin histograms, summary statistics, skewness indication)
   - Categorical Distributions (Top 10 frequent categories, percentage, high-cardinality detection)
   - Pearson Correlation Matrix (handles constant columns, NaN, < 2 numeric columns)
   - Temporal Analysis (chronological aggregations over datetime if present)
   - Evidence-Grounded Observations (5-10 factual, non-causal statistical observations)
2. Manual Bivariate / Multivariate Exploration:
   - Type-aware queries (Scatter for Numeric x Numeric, Line for Datetime x Numeric, Grouped Bar for Categorical x Numeric)
   - Deterministic sampling for large scatter datasets (> 1,000 rows)
   - Read-only execution ensuring 100% dataset immutability
"""

from dataclasses import dataclass, field
import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from ingestion.models import CanonicalDataset, DataProfile, sanitize_json_value
from intelligence.semantic_analyzer import DatasetSemanticProfile, ColumnRole


@dataclass
class EDASummary:
    """Complete automated EDA summary for a dataset."""
    dataset_id: str
    dataset_summary: Dict[str, Any]
    numeric_distributions: List[Dict[str, Any]]
    categorical_distributions: List[Dict[str, Any]]
    correlation_analysis: Dict[str, Any]
    temporal_analysis: Optional[Dict[str, Any]]
    automated_observations: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_summary": self.dataset_summary,
            "numeric_distributions": self.numeric_distributions,
            "categorical_distributions": self.categorical_distributions,
            "correlation_analysis": self.correlation_analysis,
            "temporal_analysis": self.temporal_analysis,
            "automated_observations": self.automated_observations,
        }


class EDAEngine:
    """Deterministic, read-only Exploratory Data Analysis engine."""

    def generate_summary(
        self,
        canonical: CanonicalDataset,
        profile: Optional[DataProfile] = None,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
    ) -> EDASummary:
        """Generate a complete automated EDA summary for the dataset.

        Does not mutate canonical.data or any existing profile metadata.
        """
        df = canonical.data
        row_cnt = int(len(df))
        col_cnt = int(len(df.columns))
        dataset_id = canonical.metadata.dataset_id if canonical.metadata else "unknown_dataset"

        # 1. Classify Column Types (Physical + Semantic)
        numeric_cols: List[str] = []
        categorical_cols: List[str] = []
        datetime_cols: List[str] = []
        boolean_cols: List[str] = []

        for col in df.columns:
            col_str = str(col)
            series = df[col]
            ev = semantic_profile.column_evidences.get(col_str) if semantic_profile else None
            role = ev.candidate_role if ev else None

            if pd.api.types.is_bool_dtype(series) or (row_cnt > 0 and series.dropna().isin([True, False]).all() and series.dropna().dtype == bool):
                boolean_cols.append(col_str)
            elif pd.api.types.is_datetime64_any_dtype(series) or role == ColumnRole.DATETIME:
                datetime_cols.append(col_str)
            elif (pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)) or role == ColumnRole.MEASURE:
                numeric_cols.append(col_str)
            else:
                # Check if string/object column represents dates
                is_dt = False
                if row_cnt > 0:
                    try:
                        non_null_s = series.dropna()
                        if len(non_null_s) > 0 and ("date" in col_str.lower() or "time" in col_str.lower() or "year" in col_str.lower() or "timestamp" in col_str.lower()):
                            parsed_dt = pd.to_datetime(non_null_s, errors="coerce", format="mixed")
                            if len(parsed_dt.dropna()) >= 0.8 * len(non_null_s):
                                datetime_cols.append(col_str)
                                is_dt = True
                    except Exception:
                        pass
                if not is_dt:
                    categorical_cols.append(col_str)

        # Dataset Summary Metrics
        dup_row_cnt = int(df.duplicated().sum()) if row_cnt > 0 else 0
        dup_row_pct = round(float((dup_row_cnt / row_cnt) * 100.0), 2) if row_cnt > 0 else 0.0
        total_cells = row_cnt * col_cnt
        missing_cells_cnt = int(df.isna().sum().sum()) if total_cells > 0 else 0
        missing_cells_pct = round(float((missing_cells_cnt / total_cells) * 100.0), 2) if total_cells > 0 else 0.0

        dataset_summary = {
            "row_count": row_cnt,
            "column_count": col_cnt,
            "numeric_columns_count": len(numeric_cols),
            "categorical_columns_count": len(categorical_cols),
            "datetime_columns_count": len(datetime_cols),
            "boolean_columns_count": len(boolean_cols),
            "total_cells": total_cells,
            "missing_cells_count": missing_cells_cnt,
            "missing_cells_percentage": missing_cells_pct,
            "duplicate_rows_count": dup_row_cnt,
            "duplicate_rows_percentage": dup_row_pct,
        }

        # 2. Numeric Distributions
        numeric_distributions: List[Dict[str, Any]] = []
        for col_name in numeric_cols:
            series = pd.to_numeric(df[col_name], errors="coerce")
            non_null = series.dropna()
            non_null_cnt = len(non_null)
            null_cnt = int(series.isna().sum())
            null_pct = round(float((null_cnt / row_cnt) * 100.0), 2) if row_cnt > 0 else 0.0

            if non_null_cnt > 0:
                mean_val = float(non_null.mean())
                median_val = float(non_null.median())
                std_val = float(non_null.std()) if non_null_cnt > 1 else 0.0
                min_val = float(non_null.min())
                max_val = float(non_null.max())
                q25_val = float(non_null.quantile(0.25))
                q75_val = float(non_null.quantile(0.75))
                zero_cnt = int((non_null == 0).sum())
                negative_cnt = int((non_null < 0).sum())

                # Deterministic Skewness & Shape
                skewness: Optional[float] = None
                distribution_shape = "Symmetric"
                if non_null_cnt >= 3 and std_val > 1e-9:
                    try:
                        raw_skew = float(non_null.skew())
                        if not math.isnan(raw_skew):
                            skewness = round(raw_skew, 2)
                            if skewness > 0.5:
                                distribution_shape = "Right-skewed"
                            elif skewness < -0.5:
                                distribution_shape = "Left-skewed"
                            else:
                                distribution_shape = "Roughly Symmetric"
                    except Exception:
                        pass

                # Deterministic 10-bin Histogram
                histogram: List[Dict[str, Any]] = []
                try:
                    finite_vals = non_null[np.isfinite(non_null)]
                    if len(finite_vals) >= 2 and float(finite_vals.min()) != float(finite_vals.max()):
                        counts, bin_edges = np.histogram(finite_vals, bins=10)
                        histogram = [
                            {
                                "bin_start": sanitize_json_value(round(float(bin_edges[i]), 2)),
                                "bin_end": sanitize_json_value(round(float(bin_edges[i+1]), 2)),
                                "bin_label": f"{round(float(bin_edges[i]), 1)}–{round(float(bin_edges[i+1]), 1)}",
                                "count": int(counts[i]),
                                "percentage": round(float(counts[i] / non_null_cnt * 100.0), 1) if non_null_cnt > 0 else 0.0,
                            }
                            for i in range(len(counts))
                        ]
                    elif len(finite_vals) > 0:
                        single_val = float(finite_vals.iloc[0])
                        histogram = [
                            {
                                "bin_start": sanitize_json_value(round(single_val, 2)),
                                "bin_end": sanitize_json_value(round(single_val, 2)),
                                "bin_label": f"{round(single_val, 1)}",
                                "count": int(len(finite_vals)),
                                "percentage": 100.0,
                            }
                        ]
                except Exception:
                    histogram = []

                numeric_distributions.append({
                    "column_name": col_name,
                    "row_count": row_cnt,
                    "non_null_count": non_null_cnt,
                    "mean": sanitize_json_value(round(mean_val, 2)),
                    "median": sanitize_json_value(round(median_val, 2)),
                    "std": sanitize_json_value(round(std_val, 2)),
                    "min": sanitize_json_value(min_val),
                    "max": sanitize_json_value(max_val),
                    "q1": sanitize_json_value(round(q25_val, 2)),
                    "q3": sanitize_json_value(round(q75_val, 2)),
                    "q25": sanitize_json_value(round(q25_val, 2)),
                    "q75": sanitize_json_value(round(q75_val, 2)),
                    "zero_count": zero_cnt,
                    "negative_count": negative_cnt,
                    "null_count": null_cnt,
                    "null_percentage": null_pct,
                    "skewness": skewness,
                    "skew_label": distribution_shape,
                    "distribution_shape": distribution_shape,
                    "histogram": histogram,
                })
            else:
                numeric_distributions.append({
                    "column_name": col_name,
                    "row_count": row_cnt,
                    "non_null_count": 0,
                    "mean": None,
                    "median": None,
                    "std": None,
                    "min": None,
                    "max": None,
                    "q1": None,
                    "q3": None,
                    "q25": None,
                    "q75": None,
                    "zero_count": 0,
                    "negative_count": 0,
                    "null_count": null_cnt,
                    "null_percentage": null_pct,
                    "skewness": None,
                    "skew_label": "All Null",
                    "distribution_shape": "All Null",
                    "histogram": [],
                })

        # 3. Categorical Distributions
        categorical_distributions: List[Dict[str, Any]] = []
        for col_name in categorical_cols:
            series = df[col_name]
            non_null = series.dropna()
            non_null_cnt = len(non_null)
            null_cnt = int(series.isna().sum())
            null_pct = round(float((null_cnt / row_cnt) * 100.0), 2) if row_cnt > 0 else 0.0
            distinct_cnt = int(non_null.nunique())

            top_categories: List[Dict[str, Any]] = []
            if non_null_cnt > 0:
                vc = non_null.value_counts()
                sorted_items = sorted(vc.items(), key=lambda x: (-x[1], str(x[0])))
                for val, cnt in sorted_items[:10]:
                    pct = round(float((cnt / non_null_cnt) * 100.0), 1)
                    val_str = str(val) if val != "" else "<Empty String>"
                    top_categories.append({
                        "category": val_str,
                        "value": val_str,
                        "count": int(cnt),
                        "percentage": pct,
                    })

            categorical_distributions.append({
                "column_name": col_name,
                "row_count": row_cnt,
                "distinct_count": distinct_cnt,
                "null_count": null_cnt,
                "null_percentage": null_pct,
                "is_high_cardinality": bool(distinct_cnt > 10),
                "cardinality_note": f"Column has {distinct_cnt} unique values ({round(distinct_cnt / max(non_null_cnt, 1) * 100, 1)}% unique ratio)." if distinct_cnt > 10 else None,
                "top_categories": top_categories,
            })

        # 4. Correlation Analysis (Pearson)
        usable_numeric_cols: List[str] = []
        for col in numeric_cols:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            # Must have at least 2 non-null rows and non-zero standard deviation
            if len(s) >= 2 and float(s.std()) > 1e-9:
                usable_numeric_cols.append(col)

        correlation_analysis: Dict[str, Any] = {}
        if len(usable_numeric_cols) < 2:
            correlation_analysis = {
                "is_available": False,
                "status": "INSUFFICIENT_NUMERIC_COLUMNS",
                "message": "Correlation analysis requires at least two usable numeric columns.",
                "columns": usable_numeric_cols,
                "matrix": {},
                "strong_pairs": [],
                "top_correlated_pairs": [],
            }
        else:
            try:
                num_df = df[usable_numeric_cols].apply(pd.to_numeric, errors="coerce")
                corr_df = num_df.corr(method="pearson")
                
                # Build deterministic matrix dict
                matrix_dict: Dict[str, Dict[str, Optional[float]]] = {}
                for c1 in usable_numeric_cols:
                    matrix_dict[c1] = {}
                    for c2 in usable_numeric_cols:
                        val = corr_df.loc[c1, c2] if (c1 in corr_df.index and c2 in corr_df.columns) else np.nan
                        if pd.isna(val) or math.isnan(val) or math.isinf(val):
                            matrix_dict[c1][c2] = None
                        else:
                            matrix_dict[c1][c2] = round(float(val), 2)

                # Identify notable correlation pairs (sorted by absolute correlation descending)
                pairs: List[Dict[str, Any]] = []
                for i in range(len(usable_numeric_cols)):
                    for j in range(i + 1, len(usable_numeric_cols)):
                        col1 = usable_numeric_cols[i]
                        col2 = usable_numeric_cols[j]
                        val = matrix_dict[col1].get(col2)
                        if val is not None:
                            abs_val = abs(val)
                            strength = "Weak"
                            if abs_val >= 0.7:
                                strength = "Strong"
                            elif abs_val >= 0.4:
                                strength = "Moderate"
                            
                            direction = "Positive" if val > 0 else "Negative" if val < 0 else "None"
                            pairs.append({
                                "col1": col1,
                                "col2": col2,
                                "correlation": val,
                                "absolute_correlation": abs_val,
                                "strength": strength,
                                "direction": direction,
                                "description": f"{col1} and {col2} show a {strength.lower()} {direction.lower()} correlation (r = {val:.2f})."
                            })

                pairs.sort(key=lambda x: -x["absolute_correlation"])

                correlation_analysis = {
                    "is_available": True,
                    "status": "SUCCESS",
                    "message": None,
                    "columns": usable_numeric_cols,
                    "matrix": matrix_dict,
                    "strong_pairs": pairs,
                    "top_correlated_pairs": pairs,
                }
            except Exception as e:
                correlation_analysis = {
                    "is_available": False,
                    "status": "ERROR",
                    "message": f"Correlation analysis could not be calculated: {e}",
                    "columns": usable_numeric_cols,
                    "matrix": {},
                    "strong_pairs": [],
                    "top_correlated_pairs": [],
                }

        # 5. Temporal Analysis
        temporal_analysis: Optional[Dict[str, Any]] = None
        target_dt_col: Optional[str] = None
        for col in datetime_cols:
            parsed = pd.to_datetime(df[col], errors="coerce").dropna()
            if len(parsed) > 0:
                target_dt_col = col
                break

        # Fallback check for parseable text date if no explicit datetime
        if not target_dt_col:
            for col in categorical_cols:
                if "date" in col.lower() or "time" in col.lower() or "year" in col.lower() or "timestamp" in col.lower():
                    parsed = pd.to_datetime(df[col], errors="coerce").dropna()
                    if len(parsed) >= 0.8 * row_cnt and len(parsed) > 0:
                        target_dt_col = col
                        break

        if target_dt_col and len(numeric_cols) > 0:
            target_measure = numeric_cols[0]
            try:
                temp_df = df[[target_dt_col, target_measure]].copy()
                temp_df["__dt__"] = pd.to_datetime(temp_df[target_dt_col], errors="coerce")
                temp_df["__val__"] = pd.to_numeric(temp_df[target_measure], errors="coerce")
                valid_temp = temp_df.dropna(subset=["__dt__", "__val__"]).copy()

                if len(valid_temp) > 0:
                    earliest_dt = valid_temp["__dt__"].min()
                    latest_dt = valid_temp["__dt__"].max()
                    span_days = int((latest_dt - earliest_dt).days)

                    # Determine aggregation granularity: day, month, or year
                    if span_days > 730:
                        valid_temp["__period__"] = valid_temp["__dt__"].dt.to_period("Y").astype(str)
                        granularity = "year"
                    elif span_days > 60:
                        valid_temp["__period__"] = valid_temp["__dt__"].dt.to_period("M").astype(str)
                        granularity = "month"
                    else:
                        valid_temp["__period__"] = valid_temp["__dt__"].dt.to_period("D").astype(str)
                        granularity = "day"

                    # Deterministic chronological aggregation
                    agg_series = valid_temp.groupby("__period__")["__val__"].agg(["mean", "count"]).reset_index()
                    agg_series = agg_series.sort_values(by="__period__")

                    series_data = [
                        {
                            "period": str(row["__period__"]),
                            "value": sanitize_json_value(round(float(row["mean"]), 2)),
                            "count": int(row["count"]),
                        }
                        for _, row in agg_series.iterrows()
                    ]

                    # Trend direction calculation
                    trend_direction = "Stable"
                    if len(series_data) >= 2:
                        first_val = series_data[0]["value"]
                        last_val = series_data[-1]["value"]
                        if first_val is not None and last_val is not None and first_val != 0:
                            if last_val > first_val * 1.05:
                                trend_direction = "Upward"
                            elif last_val < first_val * 0.95:
                                trend_direction = "Downward"

                    data_points = [
                        {
                            "period": item["period"],
                            "metric_value": item["value"],
                            "value": item["value"],
                            "count": item["count"],
                        }
                        for item in series_data
                    ]

                    temporal_analysis = {
                        "is_available": True,
                        "status": "SUCCESS",
                        "message": None,
                        "datetime_column": target_dt_col,
                        "measure_column": target_measure,
                        "time_granularity": granularity,
                        "granularity": granularity,
                        "temporal_span_days": span_days,
                        "earliest_date": earliest_dt.strftime("%Y-%m-%d"),
                        "latest_date": latest_dt.strftime("%Y-%m-%d"),
                        "date_range": {
                            "min_date": earliest_dt.strftime("%Y-%m-%d"),
                            "max_date": latest_dt.strftime("%Y-%m-%d"),
                        },
                        "total_points": len(series_data),
                        "trend_direction": trend_direction,
                        "series": series_data,
                        "data_points": data_points,
                    }
                else:
                    temporal_analysis = {
                        "is_available": False,
                        "status": "EMPTY_DATA",
                        "message": "No valid non-null datetime and numeric observations found.",
                        "datetime_column": target_dt_col,
                        "measure_column": target_measure,
                        "series": [],
                        "data_points": [],
                    }
            except Exception as e:
                temporal_analysis = {
                    "is_available": False,
                    "status": "ERROR",
                    "message": f"Temporal analysis could not be computed: {e}",
                    "datetime_column": target_dt_col,
                    "series": [],
                    "data_points": [],
                }
        else:
            temporal_analysis = {
                "is_available": False,
                "status": "NO_DATETIME_COLUMN",
                "message": "No datetime column detected in dataset for temporal exploration.",
                "datetime_column": None,
                "series": [],
                "data_points": [],
            }

        # 6. Automated Observations (5-10 Evidence-Grounded Factual Insights)
        automated_observations: List[Dict[str, Any]] = []

        # Observation 1: Missingness
        cols_with_missing = [d for d in numeric_distributions + categorical_distributions if d["null_count"] > 0]
        if cols_with_missing:
            highest_missing = max(cols_with_missing, key=lambda x: x["null_percentage"])
            obs_text = f"{highest_missing['column_name']} has {highest_missing['null_count']} missing values ({highest_missing['null_percentage']}% of rows)."
            automated_observations.append({
                "id": "obs_missingness",
                "type": "missing_values",
                "category": "missingness",
                "text": obs_text,
                "observation": obs_text,
                "severity": "warning",
                "evidence": {
                    "column": highest_missing["column_name"],
                    "missing_count": highest_missing["null_count"],
                    "missing_percentage": highest_missing["null_percentage"],
                    "total_rows": row_cnt,
                }
            })
        elif row_cnt > 0:
            obs_text = "The dataset contains 100% complete records with zero missing values across all columns."
            automated_observations.append({
                "id": "obs_missingness",
                "type": "missing_values",
                "category": "missingness",
                "text": obs_text,
                "observation": obs_text,
                "severity": "info",
                "evidence": {
                    "total_cells": total_cells,
                    "missing_cells": 0,
                    "completeness_percentage": 100.0,
                }
            })

        # Observation 2: Duplicate rows
        if dup_row_cnt > 0:
            obs_text = f"Found {dup_row_cnt} duplicate rows ({dup_row_pct}% of total records)."
            automated_observations.append({
                "id": "obs_duplicates",
                "type": "duplicates",
                "category": "duplicates",
                "text": obs_text,
                "observation": obs_text,
                "severity": "warning",
                "evidence": {
                    "duplicate_row_count": dup_row_cnt,
                    "duplicate_row_percentage": dup_row_pct,
                    "total_rows": row_cnt,
                }
            })

        # Observation 3: Numeric Range & Median (Primary Measure)
        if numeric_distributions:
            primary_num = numeric_distributions[0]
            if primary_num["min"] is not None and primary_num["max"] is not None:
                obs_text = f"{primary_num['column_name']} ranges from {primary_num['min']} to {primary_num['max']} with a median of {primary_num['median']}."
                automated_observations.append({
                    "id": f"obs_range_{primary_num['column_name']}",
                    "type": "distribution",
                    "category": "distribution",
                    "text": obs_text,
                    "observation": obs_text,
                    "severity": "info",
                    "evidence": {
                        "column": primary_num["column_name"],
                        "min": primary_num["min"],
                        "max": primary_num["max"],
                        "median": primary_num["median"],
                        "mean": primary_num["mean"],
                        "std": primary_num["std"],
                    }
                })

        # Observation 4: Skewness / Distribution Shape
        skewed_cols = [d for d in numeric_distributions if d.get("skewness") is not None and abs(d["skewness"]) > 0.5]
        if skewed_cols:
            most_skewed = max(skewed_cols, key=lambda x: abs(x["skewness"]))
            obs_text = f"{most_skewed['column_name']} exhibits a {most_skewed['distribution_shape'].lower()} distribution (skewness = {most_skewed['skewness']})."
            automated_observations.append({
                "id": f"obs_skew_{most_skewed['column_name']}",
                "type": "skewness",
                "category": "distribution",
                "text": obs_text,
                "observation": obs_text,
                "severity": "notice",
                "evidence": {
                    "column": most_skewed["column_name"],
                    "skewness": most_skewed["skewness"],
                    "distribution_shape": most_skewed["distribution_shape"],
                }
            })

        # Observation 5: Correlation
        if correlation_analysis.get("is_available") and correlation_analysis.get("strong_pairs"):
            top_pair = correlation_analysis["strong_pairs"][0]
            if top_pair["absolute_correlation"] >= 0.4:
                automated_observations.append({
                    "id": "obs_correlation",
                    "type": "correlation",
                    "category": "correlation",
                    "text": top_pair["description"],
                    "observation": top_pair["description"],
                    "severity": "info",
                    "evidence": {
                        "column_1": top_pair["col1"],
                        "column_2": top_pair["col2"],
                        "correlation_coefficient": top_pair["correlation"],
                        "strength": top_pair["strength"],
                        "direction": top_pair["direction"],
                    }
                })

        # Observation 6: Dominant Categorical Dimension
        if categorical_distributions:
            primary_cat = categorical_distributions[0]
            if primary_cat["top_categories"]:
                top_item = primary_cat["top_categories"][0]
                obs_text = f"{primary_cat['column_name']} contains {primary_cat['distinct_count']} distinct categories, with '{top_item['value']}' representing {top_item['percentage']}% of records."
                automated_observations.append({
                    "id": f"obs_cat_{primary_cat['column_name']}",
                    "type": "cardinality",
                    "category": "cardinality",
                    "text": obs_text,
                    "observation": obs_text,
                    "severity": "info",
                    "evidence": {
                        "column": primary_cat["column_name"],
                        "distinct_count": primary_cat["distinct_count"],
                        "top_value": top_item["value"],
                        "top_value_count": top_item["count"],
                        "top_value_percentage": top_item["percentage"],
                    }
                })

        # Observation 7: Temporal Span
        if temporal_analysis and temporal_analysis.get("is_available"):
            obs_text = f"Temporal records in {temporal_analysis['datetime_column']} span {temporal_analysis['temporal_span_days']} days from {temporal_analysis['earliest_date']} to {temporal_analysis['latest_date']}."
            automated_observations.append({
                "id": "obs_temporal",
                "type": "temporal",
                "category": "temporal",
                "text": obs_text,
                "observation": obs_text,
                "severity": "info",
                "evidence": {
                    "datetime_column": temporal_analysis["datetime_column"],
                    "temporal_span_days": temporal_analysis["temporal_span_days"],
                    "earliest_date": temporal_analysis["earliest_date"],
                    "latest_date": temporal_analysis["latest_date"],
                    "granularity": temporal_analysis["time_granularity"],
                }
            })

        # Cap observations to maximum 8 concise items
        automated_observations = automated_observations[:8]

        return EDASummary(
            dataset_id=dataset_id,
            dataset_summary=dataset_summary,
            numeric_distributions=numeric_distributions,
            categorical_distributions=categorical_distributions,
            correlation_analysis=correlation_analysis,
            temporal_analysis=temporal_analysis,
            automated_observations=automated_observations,
        )

    def explore(
        self,
        canonical: CanonicalDataset,
        chart_type: str,
        x_column: str,
        y_column: Optional[str] = None,
        group_by: Optional[str] = None,
        aggregation: str = "mean",
        time_granularity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform interactive, type-aware exploration on the dataset without mutation."""
        df = canonical.data
        row_cnt = int(len(df))

        if row_cnt == 0:
            return {
                "chart_type": chart_type,
                "is_supported": False,
                "error_message": "Dataset contains 0 rows.",
                "data": [],
            }

        if x_column not in df.columns:
            return {
                "chart_type": chart_type,
                "is_supported": False,
                "error_message": f"Column '{x_column}' does not exist in dataset.",
                "data": [],
            }

        if y_column and y_column not in df.columns:
            return {
                "chart_type": chart_type,
                "is_supported": False,
                "error_message": f"Column '{y_column}' does not exist in dataset.",
                "data": [],
            }

        if group_by and group_by not in df.columns:
            group_by = None

        norm_chart_type = chart_type.lower().strip()

        # 1. SCATTER PLOT: Numeric x Numeric
        if norm_chart_type == "scatter":
            if not y_column:
                return {
                    "chart_type": "scatter",
                    "is_supported": False,
                    "error_message": "Scatter plot requires both an X-axis and Y-axis numeric column.",
                    "data": [],
                }

            x_s = pd.to_numeric(df[x_column], errors="coerce")
            y_s = pd.to_numeric(df[y_column], errors="coerce")

            if x_s.dropna().empty or y_s.dropna().empty:
                return {
                    "chart_type": "scatter",
                    "is_supported": False,
                    "error_message": f"Both '{x_column}' and '{y_column}' must contain numeric values for a scatter plot.",
                    "data": [],
                }

            plot_df = pd.DataFrame({"x": x_s, "y": y_s})
            if group_by:
                plot_df["group"] = df[group_by].astype(str).fillna("Unknown")
            else:
                plot_df["group"] = "All"

            valid_pts = plot_df.dropna(subset=["x", "y"])
            total_valid = len(valid_pts)

            if total_valid == 0:
                return {
                    "chart_type": "scatter",
                    "is_supported": False,
                    "error_message": "No valid non-null numeric pairs found for scatter plot.",
                    "data": [],
                }

            # Deterministic Sampling if > 1,000 points
            is_sampled = False
            sample_size = total_valid
            if total_valid > 1000:
                is_sampled = True
                step = math.ceil(total_valid / 1000)
                valid_pts = valid_pts.iloc[::step].copy()
                sample_size = len(valid_pts)

            # Compute correlation coefficient
            corr_val: Optional[float] = None
            try:
                c = float(valid_pts["x"].corr(valid_pts["y"]))
                if not math.isnan(c) and not math.isinf(c):
                    corr_val = round(c, 2)
            except Exception:
                pass

            data_pts = [
                {
                    "x": sanitize_json_value(round(float(row["x"]), 3) if isinstance(row["x"], float) else row["x"]),
                    "y": sanitize_json_value(round(float(row["y"]), 3) if isinstance(row["y"], float) else row["y"]),
                    "group": str(row["group"]),
                }
                for _, row in valid_pts.iterrows()
            ]

            return {
                "chart_type": "scatter",
                "is_supported": True,
                "error_message": None,
                "x_column": x_column,
                "y_column": y_column,
                "group_by": group_by,
                "total_points": total_valid,
                "rendered_points": sample_size,
                "is_sampled": is_sampled,
                "correlation": corr_val,
                "data": data_pts,
            }

        # 2. LINE CHART: Datetime x Numeric
        elif norm_chart_type == "line":
            if not y_column:
                return {
                    "chart_type": "line",
                    "is_supported": False,
                    "error_message": "Line chart requires a numeric Y-axis column.",
                    "data": [],
                }

            dt_s = pd.to_datetime(df[x_column], errors="coerce")
            y_s = pd.to_numeric(df[y_column], errors="coerce")

            if dt_s.dropna().empty:
                return {
                    "chart_type": "line",
                    "is_supported": False,
                    "error_message": f"Column '{x_column}' must contain valid date or timestamp values for a chronological line chart.",
                    "data": [],
                }

            if y_s.dropna().empty:
                return {
                    "chart_type": "line",
                    "is_supported": False,
                    "error_message": f"Column '{y_column}' must contain numeric values for a line chart.",
                    "data": [],
                }

            plot_df = pd.DataFrame({"__dt__": dt_s, "__val__": y_s})
            if group_by:
                plot_df["group"] = df[group_by].astype(str).fillna("Unknown")

            valid_df = plot_df.dropna(subset=["__dt__", "__val__"])
            if valid_df.empty:
                return {
                    "chart_type": "line",
                    "is_supported": False,
                    "error_message": "No valid non-null date and numeric pairs found.",
                    "data": [],
                }

            # Determine Granularity
            span_days = int((valid_df["__dt__"].max() - valid_df["__dt__"].min()).days)
            gran = time_granularity or ("year" if span_days > 730 else "month" if span_days > 60 else "day")

            if gran == "year":
                valid_df["__period__"] = valid_df["__dt__"].dt.to_period("Y").astype(str)
            elif gran == "quarter":
                valid_df["__period__"] = valid_df["__dt__"].dt.to_period("Q").astype(str)
            elif gran == "month":
                valid_df["__period__"] = valid_df["__dt__"].dt.to_period("M").astype(str)
            else:
                valid_df["__period__"] = valid_df["__dt__"].dt.to_period("D").astype(str)

            agg_func = "mean"
            if aggregation in ("sum", "median", "count", "min", "max"):
                agg_func = aggregation

            if group_by:
                agg_df = valid_df.groupby(["__period__", "group"])["__val__"].agg([agg_func, "count"]).reset_index()
                agg_df = agg_df.sort_values(by="__period__")
                data_rows = [
                    {
                        "period": str(row["__period__"]),
                        "group": str(row["group"]),
                        "value": sanitize_json_value(round(float(row[agg_func]), 2)),
                        "count": int(row["count"]),
                    }
                    for _, row in agg_df.iterrows()
                ]
            else:
                agg_df = valid_df.groupby("__period__")["__val__"].agg([agg_func, "count"]).reset_index()
                agg_df = agg_df.sort_values(by="__period__")
                data_rows = [
                    {
                        "period": str(row["__period__"]),
                        "value": sanitize_json_value(round(float(row[agg_func]), 2)),
                        "count": int(row["count"]),
                    }
                    for _, row in agg_df.iterrows()
                ]

            return {
                "chart_type": "line",
                "is_supported": True,
                "error_message": None,
                "x_column": x_column,
                "y_column": y_column,
                "group_by": group_by,
                "time_granularity": gran,
                "aggregation": agg_func,
                "temporal_span_days": span_days,
                "data": data_rows,
            }

        # 3. GROUPED BAR CHART: Categorical x Numeric (or Categorical x Categorical count)
        elif norm_chart_type in ("bar", "grouped_bar", "box"):
            if y_column:
                # Categorical x Numeric
                y_s = pd.to_numeric(df[y_column], errors="coerce")
                if y_s.dropna().empty:
                    return {
                        "chart_type": "bar",
                        "is_supported": False,
                        "error_message": f"Column '{y_column}' must contain numeric values for aggregation in a bar chart.",
                        "data": [],
                    }

                plot_df = pd.DataFrame({"cat": df[x_column].astype(str).fillna("Unknown"), "val": y_s})
                if group_by:
                    plot_df["group"] = df[group_by].astype(str).fillna("Unknown")

                valid_df = plot_df.dropna(subset=["val"])
                if valid_df.empty:
                    return {
                        "chart_type": "bar",
                        "is_supported": False,
                        "error_message": "No valid non-null rows found for bar chart.",
                        "data": [],
                    }

                agg_func = "mean"
                if aggregation in ("sum", "median", "count", "min", "max"):
                    agg_func = aggregation

                # Limit to top 20 distinct categories to prevent overflow
                top_cats = valid_df["cat"].value_counts().head(20).index.tolist()
                valid_df = valid_df[valid_df["cat"].isin(top_cats)]

                if group_by:
                    agg_df = valid_df.groupby(["cat", "group"])["val"].agg([agg_func, "count"]).reset_index()
                    agg_df = agg_df.sort_values(by=agg_func, ascending=False)
                    data_rows = [
                        {
                            "category": str(row["cat"]),
                            "group": str(row["group"]),
                            "value": sanitize_json_value(round(float(row[agg_func]), 2)),
                            "count": int(row["count"]),
                        }
                        for _, row in agg_df.iterrows()
                    ]
                else:
                    agg_df = valid_df.groupby("cat")["val"].agg([agg_func, "count"]).reset_index()
                    agg_df = agg_df.sort_values(by=agg_func, ascending=False)
                    data_rows = [
                        {
                            "category": str(row["cat"]),
                            "value": sanitize_json_value(round(float(row[agg_func]), 2)),
                            "count": int(row["count"]),
                        }
                        for _, row in agg_df.iterrows()
                    ]

                return {
                    "chart_type": "bar",
                    "is_supported": True,
                    "error_message": None,
                    "x_column": x_column,
                    "y_column": y_column,
                    "group_by": group_by,
                    "aggregation": agg_func,
                    "data": data_rows,
                }
            else:
                # Categorical Frequency Count
                s = df[x_column].astype(str).fillna("<Null>")
                vc = s.value_counts().head(20)
                sorted_items = sorted(vc.items(), key=lambda x: (-x[1], str(x[0])))
                data_rows = [
                    {
                        "category": str(val),
                        "value": int(cnt),
                        "count": int(cnt),
                    }
                    for val, cnt in sorted_items
                ]
                return {
                    "chart_type": "bar",
                    "is_supported": True,
                    "error_message": None,
                    "x_column": x_column,
                    "y_column": None,
                    "aggregation": "count",
                    "data": data_rows,
                }

        # 4. UNIVARIATE DISTRIBUTION / HISTOGRAM
        elif norm_chart_type == "distribution":
            num_s = pd.to_numeric(df[x_column], errors="coerce").dropna()
            if not num_s.empty:
                finite_vals = num_s[np.isfinite(num_s)]
                counts, bin_edges = np.histogram(finite_vals, bins=10)
                data_rows = [
                    {
                        "bin_start": sanitize_json_value(round(float(bin_edges[i]), 2)),
                        "bin_end": sanitize_json_value(round(float(bin_edges[i+1]), 2)),
                        "bin_label": f"{round(float(bin_edges[i]), 1)}–{round(float(bin_edges[i+1]), 1)}",
                        "value": int(counts[i]),
                        "count": int(counts[i]),
                    }
                    for i in range(len(counts))
                ]
                return {
                    "chart_type": "distribution",
                    "is_supported": True,
                    "error_message": None,
                    "x_column": x_column,
                    "y_column": None,
                    "mean": sanitize_json_value(round(float(num_s.mean()), 2)),
                    "median": sanitize_json_value(round(float(num_s.median()), 2)),
                    "std": sanitize_json_value(round(float(num_s.std()), 2)) if len(num_s) > 1 else 0.0,
                    "data": data_rows,
                }
            else:
                return {
                    "chart_type": "distribution",
                    "is_supported": False,
                    "error_message": f"Column '{x_column}' does not contain numeric data for distribution analysis.",
                    "data": [],
                }

        else:
            return {
                "chart_type": chart_type,
                "is_supported": False,
                "error_message": f"Unsupported chart type '{chart_type}'. Supported: 'scatter', 'line', 'bar', 'distribution'.",
                "data": [],
            }
