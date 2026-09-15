"""Deterministic Data Profiling Engine for CanonicalDatasets."""

import datetime
import hashlib
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from ingestion.models import CanonicalDataset, DataProfile, sanitize_json_value


class DataProfiler:
    """Read-only, deterministic profiler for analyzing dataset physical and statistical properties."""

    def profile(self, canonical: CanonicalDataset, attach: bool = True) -> DataProfile:
        """Generate a DataProfile for a CanonicalDataset.

        This method is read-only and will never mutate the underlying canonical.data DataFrame.

        Args:
            canonical: The target CanonicalDataset to profile.
            attach: If True, attaches the generated profile to canonical.profile and logs an audit entry.

        Returns:
            Populated DataProfile dataclass instance.
        """
        df = canonical.data
        row_cnt = int(len(df))
        col_cnt = int(len(df.columns))

        # 1. Dataset-level Summary Statistics
        dup_row_cnt = int(df.duplicated().sum()) if row_cnt > 0 else 0
        total_cells = row_cnt * col_cnt
        overall_missing_cnt = int(df.isna().sum().sum()) if total_cells > 0 else 0
        overall_missing_pct = (
            round(float((overall_missing_cnt / total_cells) * 100.0), 4)
            if total_cells > 0
            else 0.0
        )

        dataset_summary = {
            "row_count": row_cnt,
            "column_count": col_cnt,
            "duplicate_row_count": dup_row_cnt,
            "duplicate_row_percentage": (
                round(float((dup_row_cnt / row_cnt) * 100.0), 4) if row_cnt > 0 else 0.0
            ),
            "total_cells": total_cells,
            "overall_missing_count": overall_missing_cnt,
            "overall_missing_percentage": overall_missing_pct,
        }

        column_statistics: Dict[str, Dict[str, Any]] = {}
        quality_issues: List[Dict[str, Any]] = []

        # Record dataset-level quality issue if duplicates exist
        if dup_row_cnt > 0:
            quality_issues.append(
                {
                    "issue_type": "duplicate_rows",
                    "severity": "warning",
                    "target": "dataset",
                    "message": f"Dataset contains {dup_row_cnt} duplicate rows.",
                }
            )

        # 2. Column-level Statistics
        for col in df.columns:
            col_str = str(col)
            series = df[col]

            try:
                non_null_series = series.dropna()
                non_null_cnt = int(len(non_null_series))
                null_cnt = int(series.isna().sum())
                null_pct = (
                    round(float((null_cnt / row_cnt) * 100.0), 4) if row_cnt > 0 else 0.0
                )
                distinct_cnt = int(series.nunique(dropna=True))
                is_uniq = bool(series.is_unique) if row_cnt > 0 else False
                is_const = bool(distinct_cnt == 1) if non_null_cnt > 0 else False
                is_all_null = bool(null_cnt == row_cnt) if row_cnt > 0 else True

                obs_flags: List[str] = []
                if is_all_null:
                    obs_flags.append("all_null_column")
                    quality_issues.append(
                        {
                            "issue_type": "all_null_column",
                            "severity": "warning",
                            "target": col_str,
                            "message": f"Column '{col_str}' contains 100% missing values.",
                        }
                    )
                else:
                    if null_pct >= 50.0:
                        obs_flags.append("high_missingness")
                        quality_issues.append(
                            {
                                "issue_type": "high_missingness",
                                "severity": "warning",
                                "target": col_str,
                                "message": f"Column '{col_str}' has {null_pct:.1f}% missing values.",
                            }
                        )
                    if is_const:
                        obs_flags.append("constant_column")
                        quality_issues.append(
                            {
                                "issue_type": "constant_column",
                                "severity": "info",
                                "target": col_str,
                                "message": f"Column '{col_str}' contains only 1 distinct non-null value.",
                            }
                        )
                    if is_uniq and row_cnt > 1:
                        obs_flags.append("candidate_identifier_cardinality")

                col_stats: Dict[str, Any] = {
                    "column_name": col_str,
                    "detected_datatype": str(series.dtype),
                    "total_count": row_cnt,
                    "non_null_count": non_null_cnt,
                    "null_count": null_cnt,
                    "null_percentage": null_pct,
                    "distinct_count": distinct_cnt,
                    "is_unique": is_uniq,
                    "is_constant": is_const,
                    "is_all_null": is_all_null,
                    "observations": obs_flags,
                }

                # Numeric Column Statistics
                if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                    if non_null_cnt > 0:
                        col_stats["min"] = sanitize_json_value(non_null_series.min())
                        col_stats["max"] = sanitize_json_value(non_null_series.max())
                        col_stats["mean"] = sanitize_json_value(non_null_series.mean())
                        col_stats["median"] = sanitize_json_value(non_null_series.median())
                        col_stats["std"] = (
                            sanitize_json_value(non_null_series.std())
                            if non_null_cnt > 1
                            else 0.0
                        )
                        col_stats["q25"] = sanitize_json_value(non_null_series.quantile(0.25))
                        col_stats["q75"] = sanitize_json_value(non_null_series.quantile(0.75))
                        col_stats["zero_count"] = int((non_null_series == 0).sum())
                        col_stats["negative_count"] = int((non_null_series < 0).sum())
                        if pd.api.types.is_float_dtype(series):
                            col_stats["infinite_count"] = int(np.isinf(non_null_series).sum())
                    else:
                        col_stats.update(
                            {
                                "min": None,
                                "max": None,
                                "mean": None,
                                "median": None,
                                "std": None,
                                "q25": None,
                                "q75": None,
                                "zero_count": 0,
                                "negative_count": 0,
                                "infinite_count": 0,
                            }
                        )

                # Boolean Column Statistics
                elif pd.api.types.is_bool_dtype(series):
                    col_stats["true_count"] = int((series == True).sum())
                    col_stats["false_count"] = int((series == False).sum())

                # Categorical / Text / Object Column Statistics
                elif (
                    pd.api.types.is_string_dtype(series)
                    or pd.api.types.is_object_dtype(series)
                    or isinstance(series.dtype, pd.CategoricalDtype)
                ):
                    col_stats["empty_string_count"] = (
                        int((non_null_series.astype(str).str.strip() == "").sum())
                        if non_null_cnt > 0
                        else 0
                    )
                    # Deterministic top frequent values (sort by count desc, then value asc)
                    if non_null_cnt > 0:
                        vc = non_null_series.value_counts()
                        sorted_items = sorted(vc.items(), key=lambda x: (-x[1], str(x[0])))
                        top_freq = [
                            {"value": sanitize_json_value(val), "count": int(cnt)}
                            for val, cnt in sorted_items[:10]
                        ]
                        col_stats["most_frequent_values"] = top_freq
                    else:
                        col_stats["most_frequent_values"] = []

                # Datetime Column Statistics
                elif pd.api.types.is_datetime64_any_dtype(series):
                    if non_null_cnt > 0:
                        col_stats["min_datetime"] = sanitize_json_value(non_null_series.min())
                        col_stats["max_datetime"] = sanitize_json_value(non_null_series.max())
                        col_stats["distinct_dates_count"] = int(
                            non_null_series.dt.date.nunique(dropna=True)
                        )
                    else:
                        col_stats.update(
                            {"min_datetime": None, "max_datetime": None, "distinct_dates_count": 0}
                        )

                column_statistics[col_str] = col_stats

            except Exception as e:
                # Safe fallback so a single column exception never crashes the profiling run
                column_statistics[col_str] = {
                    "column_name": col_str,
                    "detected_datatype": str(series.dtype),
                    "error": f"Failed to profile column '{col_str}': {e}",
                }

        # 3. Correlation Matrix Calculation (Numeric columns with >=2 numeric cols & >=2 rows)
        correlation_matrix: Dict[str, Dict[str, float]] = {}
        num_cols = [
            str(c)
            for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
        ]
        if len(num_cols) >= 2 and row_cnt >= 2:
            try:
                corr_df = df[num_cols].corr(method="pearson")
                for c1 in num_cols:
                    correlation_matrix[c1] = {}
                    for c2 in num_cols:
                        val = corr_df.loc[c1, c2]
                        correlation_matrix[c1][c2] = (
                            sanitize_json_value(val) if not pd.isna(val) else None
                        )
            except Exception:
                correlation_matrix = {}

        # 4. Construct DataProfile object
        profile_id = (
            f"prof_{canonical.metadata.dataset_id}_"
            f"{hashlib.md5(canonical.metadata.dataset_id.encode()).hexdigest()[:6]}"
        )
        profile = DataProfile(
            profile_id=profile_id,
            dataset_id=canonical.metadata.dataset_id,
            dataset_summary=dataset_summary,
            column_statistics=column_statistics,
            quality_issues=quality_issues,
            correlation_matrix=correlation_matrix,
        )

        if attach:
            canonical.profile = profile
            canonical.add_audit_entry(
                action="PROFILED",
                details={
                    "profile_id": profile_id,
                    "quality_issues_count": len(quality_issues),
                    "numeric_columns_count": len(num_cols),
                },
            )

        return profile


def profile_dataset(canonical: CanonicalDataset, attach: bool = True) -> DataProfile:
    """Convenience function to profile a CanonicalDataset deterministically."""
    return DataProfiler().profile(canonical=canonical, attach=attach)
