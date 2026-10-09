"""Deterministic Cleaning Intelligence & Cleaning Plan Generator (Data Studio Part 4).

Consumes existing DataProfile, SemanticProfile, and QualityAssessment to detect
cleaning opportunities and produce a reviewable, non-mutating CleaningPlan.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from cleaning.models import CleaningPlan, CleaningRecommendation
from ingestion.models import CanonicalDataset, ColumnRole, DataProfile
from intelligence.profiler import DataProfiler
from intelligence.quality_assessor import QualityAssessor
from intelligence.semantic_analyzer import DatasetSemanticProfile, SemanticAnalyzer


class CleaningPlanner:
    """Generates deterministic cleaning plans and recommendations without mutating data."""

    def __init__(self) -> None:
        self.profiler = DataProfiler()
        self.semantic_analyzer = SemanticAnalyzer()
        self.quality_assessor = QualityAssessor()

    def generate_plan(
        self,
        canonical: CanonicalDataset,
        profile: Optional[DataProfile] = None,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
        quality_assessment: Optional[Any] = None,
    ) -> CleaningPlan:
        """Generate a deterministic CleaningPlan for the given CanonicalDataset."""
        if profile is None:
            profile = canonical.profile or self.profiler.profile(canonical, attach=False)
        if semantic_profile is None:
            semantic_profile = self.semantic_analyzer.analyze(canonical)

        df = canonical.data
        total_rows = canonical.metadata.row_count or len(df)
        dataset_id = canonical.metadata.dataset_id

        recommendations: List[CleaningRecommendation] = []
        affected_row_counts: List[int] = []

        # =====================================================================
        # 1. Dataset-Level Exact Duplicate Removal
        # =====================================================================
        dup_count = profile.dataset_summary.get("duplicate_row_count", 0)
        if dup_count == 0 and len(df) > 0:
            dup_count = int(df.duplicated().sum())

        if dup_count > 0:
            dup_pct = round((dup_count / max(total_rows, 1)) * 100, 2)
            recommendations.append(
                CleaningRecommendation(
                    recommendation_id=f"rec-dup-{dataset_id[:8]}",
                    column_name=None,
                    operation="REMOVE_DUPLICATES",
                    category="duplicates",
                    evidence=[
                        f"{dup_count} exact duplicate rows ({dup_pct}%) detected across all columns"
                    ],
                    affected_rows=dup_count,
                    affected_percentage=dup_pct,
                    confidence=1.0,
                    confidence_level="HIGH",
                    risk_level="LOW",
                    default_selected=True,
                    user_selected=True,
                    rationale=f"{dup_count} exact duplicate rows identified across all columns. Removing duplicate records prevents distorted statistical aggregations and inflated counts.",
                    expected_effect=f"Deduplicates dataset, reducing total row count from {total_rows} to {total_rows - dup_count} rows.",
                    requires_review=False,
                    status="RECOMMENDED",
                    params={"duplicate_count": dup_count},
                )
            )
            affected_row_counts.append(dup_count)

        # =====================================================================
        columns_schema = getattr(canonical.metadata, "schema", None) or getattr(canonical.metadata, "columns", [])
        for col_meta in columns_schema:
            col_name = getattr(col_meta, "original_name", str(col_meta))
            if col_name not in df.columns:
                continue

            series = df[col_name]
            stats = profile.column_statistics.get(col_name, {})
            ev = semantic_profile.column_evidences.get(col_name)
            role = ev.candidate_role if ev else ColumnRole.UNKNOWN

            non_null_series = series.dropna()
            non_null_cnt = len(non_null_series)
            null_count = stats.get("null_count", int(series.isna().sum()))
            null_pct = stats.get("null_percentage", round((null_count / max(total_rows, 1)) * 100, 2))

            # -----------------------------------------------------------------
            # 2A. Empty Strings / Whitespace Normalization
            # -----------------------------------------------------------------
            if (
                pd.api.types.is_string_dtype(series)
                or pd.api.types.is_object_dtype(series)
            ) and non_null_cnt > 0:
                empty_str_cnt = stats.get("empty_string_count")
                if empty_str_cnt is None:
                    empty_str_cnt = int((non_null_series.astype(str).str.strip() == "").sum())

                if empty_str_cnt > 0:
                    empty_pct = round((empty_str_cnt / max(total_rows, 1)) * 100, 2)
                    recommendations.append(
                        CleaningRecommendation(
                            recommendation_id=f"rec-empty-{col_name}",
                            column_name=col_name,
                            operation="NORMALIZE_EMPTY_STRINGS",
                            category="empty_values",
                            evidence=[
                                f"{empty_str_cnt} empty or whitespace-only strings detected ({empty_pct}%)"
                            ],
                            affected_rows=empty_str_cnt,
                            affected_percentage=empty_pct,
                            confidence=1.0,
                            confidence_level="HIGH",
                            risk_level="LOW",
                            default_selected=True,
                            user_selected=True,
                            rationale=f"Column contains {empty_str_cnt} empty or whitespace-only string entries. Normalizing them to standard NULL/NA values prevents distinct group fragmentation.",
                            expected_effect=f"Converts {empty_str_cnt} empty string entries into standard missing/null values.",
                            requires_review=False,
                            status="RECOMMENDED",
                            params={"empty_string_count": empty_str_cnt},
                        )
                    )
                    affected_row_counts.append(empty_str_cnt)

            # -----------------------------------------------------------------
            # 2B. Type Conversion Opportunities (Numeric, Datetime, Boolean)
            # -----------------------------------------------------------------
            if (
                pd.api.types.is_string_dtype(series)
                or pd.api.types.is_object_dtype(series)
            ) and non_null_cnt > 0:
                # 1. Numeric check
                parsed_num = pd.to_numeric(non_null_series, errors="coerce")
                parsed_num_cnt = int(parsed_num.notna().sum())
                if parsed_num_cnt >= int(0.95 * non_null_cnt) and non_null_cnt >= 3:
                    if parsed_num_cnt == non_null_cnt:
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-type-num-{col_name}",
                                column_name=col_name,
                                operation="CONVERT_NUMERIC",
                                category="type_conversion",
                                evidence=[
                                    f"100% of non-null values ({non_null_cnt}/{non_null_cnt}) parse as numeric numbers"
                                ],
                                affected_rows=non_null_cnt,
                                affected_percentage=round((non_null_cnt / max(total_rows, 1)) * 100, 2),
                                confidence=0.95,
                                confidence_level="HIGH",
                                risk_level="LOW",
                                default_selected=True,
                                user_selected=True,
                                rationale=f"All {non_null_cnt} text entries parse as numbers. Converting to numeric enables statistical aggregations and metrics computation.",
                                expected_effect=f"Coerces '{col_name}' data type to numeric (float64).",
                                requires_review=False,
                                status="RECOMMENDED",
                                params={"target_dtype": "float64"},
                            )
                        )
                    else:
                        unparseable = non_null_cnt - parsed_num_cnt
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-type-num-{col_name}",
                                column_name=col_name,
                                operation="CONVERT_NUMERIC",
                                category="type_conversion",
                                evidence=[
                                    f"{parsed_num_cnt} of {non_null_cnt} values parse as numbers ({round((parsed_num_cnt/non_null_cnt)*100, 1)}%)",
                                    f"{unparseable} unparseable entries will become NaN",
                                ],
                                affected_rows=non_null_cnt,
                                affected_percentage=round((non_null_cnt / max(total_rows, 1)) * 100, 2),
                                confidence=0.75,
                                confidence_level="MEDIUM",
                                risk_level="MEDIUM",
                                default_selected=False,
                                user_selected=False,
                                rationale=f"{parsed_num_cnt} of {non_null_cnt} values parse as numeric, but {unparseable} unparseable values exist. Verify unparseable entries before coercion.",
                                expected_effect=f"Coerces '{col_name}' to numeric, setting {unparseable} unparseable values to NaN.",
                                requires_review=True,
                                status="REVIEW_REQUIRED",
                                params={"target_dtype": "float64", "unparseable_count": unparseable},
                            )
                        )

                # 2. Datetime check
                elif (
                    role == ColumnRole.DATETIME
                    or stats.get("min_datetime") is not None
                ):
                    try:
                        parsed_dt = pd.to_datetime(non_null_series, errors="coerce", format="mixed")
                        parsed_dt_cnt = int(parsed_dt.notna().sum())
                        if parsed_dt_cnt >= int(0.90 * non_null_cnt) and non_null_cnt >= 2:
                            if parsed_dt_cnt == non_null_cnt:
                                recommendations.append(
                                    CleaningRecommendation(
                                        recommendation_id=f"rec-type-dt-{col_name}",
                                        column_name=col_name,
                                        operation="CONVERT_DATETIME",
                                        category="datetime_conversion",
                                        evidence=[
                                            f"100% of values ({non_null_cnt}/{non_null_cnt}) parse as valid date/timestamps"
                                        ],
                                        affected_rows=non_null_cnt,
                                        affected_percentage=round((non_null_cnt / max(total_rows, 1)) * 100, 2),
                                        confidence=0.90,
                                        confidence_level="HIGH",
                                        risk_level="LOW",
                                        default_selected=True,
                                        user_selected=True,
                                        rationale=f"All {non_null_cnt} text entries adhere to valid date formats. Converting to datetime enables time-series analytics and temporal trend charting.",
                                        expected_effect=f"Coerces '{col_name}' data type to datetime64[ns].",
                                        requires_review=False,
                                        status="RECOMMENDED",
                                        params={"target_dtype": "datetime64[ns]"},
                                    )
                                )
                            else:
                                unparseable_dt = non_null_cnt - parsed_dt_cnt
                                recommendations.append(
                                    CleaningRecommendation(
                                        recommendation_id=f"rec-type-dt-{col_name}",
                                        column_name=col_name,
                                        operation="CONVERT_DATETIME",
                                        category="datetime_conversion",
                                        evidence=[
                                            f"{parsed_dt_cnt} of {non_null_cnt} values parse as dates ({round((parsed_dt_cnt/non_null_cnt)*100, 1)}%)",
                                            f"{unparseable_dt} entries could not be parsed",
                                        ],
                                        affected_rows=non_null_cnt,
                                        affected_percentage=round((non_null_cnt / max(total_rows, 1)) * 100, 2),
                                        confidence=0.70,
                                        confidence_level="MEDIUM",
                                        risk_level="MEDIUM",
                                        default_selected=False,
                                        user_selected=False,
                                        rationale=f"{parsed_dt_cnt} of {non_null_cnt} entries parse as dates, with {unparseable_dt} unparseable items. Review date formatting consistency.",
                                        expected_effect=f"Coerces '{col_name}' to datetime, setting {unparseable_dt} invalid strings to NaT.",
                                        requires_review=True,
                                        status="REVIEW_REQUIRED",
                                        params={"target_dtype": "datetime64[ns]", "unparseable_count": unparseable_dt},
                                    )
                                )
                    except Exception:
                        pass

                # 3. Boolean normalization check
                unique_str_vals = {str(x).strip().lower() for x in non_null_series.unique()}
                if unique_str_vals.issubset({"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}) and len(unique_str_vals) <= 2:
                    recommendations.append(
                        CleaningRecommendation(
                            recommendation_id=f"rec-bool-{col_name}",
                            column_name=col_name,
                            operation="NORMALIZE_BOOLEAN",
                            category="boolean_normalization",
                            evidence=[
                                f"Distinct values {list(unique_str_vals)} represent boolean yes/no or true/false"
                            ],
                            affected_rows=non_null_cnt,
                            affected_percentage=round((non_null_cnt / max(total_rows, 1)) * 100, 2),
                            confidence=0.90,
                            confidence_level="HIGH",
                            risk_level="LOW",
                            default_selected=True,
                            user_selected=True,
                            rationale=f"Column values {list(unique_str_vals)} clearly express boolean states. Normalizing to boolean data type standardizes boolean logic.",
                            expected_effect=f"Converts '{col_name}' entries into standard boolean True/False.",
                            requires_review=False,
                            status="RECOMMENDED",
                            params={"target_dtype": "bool"},
                        )
                    )

            # -----------------------------------------------------------------
            # 2C. Missing Value Recommendations
            # -----------------------------------------------------------------
            if null_count > 0:
                affected_row_counts.append(null_count)

                # 1. Numeric Measure Column
                if role == ColumnRole.MEASURE or pd.api.types.is_numeric_dtype(series):
                    median_val = stats.get("median")
                    mean_val = stats.get("mean")
                    fill_val = median_val if median_val is not None else mean_val

                    if null_pct <= 10.0:
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-null-num-{col_name}",
                                column_name=col_name,
                                operation="IMPUTE_MEDIAN",
                                category="missing_values",
                                evidence=[
                                    f"{null_count} missing values ({null_pct}%)",
                                    "Column classified as numeric MEASURE",
                                    f"Deterministic median value: {fill_val}",
                                ],
                                affected_rows=null_count,
                                affected_percentage=null_pct,
                                confidence=0.90,
                                confidence_level="HIGH",
                                risk_level="LOW",
                                default_selected=True,
                                user_selected=True,
                                rationale=f"Numeric measure with low missingness ({null_count} rows, {null_pct}%). Median imputation ({fill_val}) preserves distribution central tendency without sensitivity to extreme values.",
                                expected_effect=f"Fills {null_count} missing numeric cells with median value ({fill_val}).",
                                requires_review=False,
                                status="RECOMMENDED",
                                params={"strategy": "median", "fill_value": fill_val},
                            )
                        )
                    elif null_pct <= 40.0:
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-null-num-{col_name}",
                                column_name=col_name,
                                operation="IMPUTE_MEDIAN",
                                category="missing_values",
                                evidence=[
                                    f"{null_count} missing values ({null_pct}%)",
                                    "Moderate missingness volume (>10%)",
                                    f"Computed median value: {fill_val}",
                                ],
                                affected_rows=null_count,
                                affected_percentage=null_pct,
                                confidence=0.70,
                                confidence_level="MEDIUM",
                                risk_level="MEDIUM",
                                default_selected=False,
                                user_selected=False,
                                rationale=f"Moderate missingness ({null_count} rows, {null_pct}%). Imputing {null_pct}% of entries may attenuate distribution variance. User review recommended before imputation.",
                                expected_effect=f"Fills {null_count} missing cells with median ({fill_val}).",
                                requires_review=True,
                                status="REVIEW_REQUIRED",
                                params={"strategy": "median", "fill_value": fill_val},
                            )
                        )
                    else:
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-null-high-{col_name}",
                                column_name=col_name,
                                operation="REVIEW_HIGH_MISSINGNESS",
                                category="missing_values",
                                evidence=[
                                    f"High missingness rate: {null_pct}% ({null_count}/{total_rows} rows)"
                                ],
                                affected_rows=null_count,
                                affected_percentage=null_pct,
                                confidence=0.50,
                                confidence_level="LOW",
                                risk_level="HIGH",
                                default_selected=False,
                                user_selected=False,
                                rationale=f"High missingness ({null_count} rows, {null_pct}%). Automated imputation would synthesize a majority of the column. Evaluate whether to retain or drop.",
                                expected_effect="No automated imputation applied; requires explicit user action.",
                                requires_review=True,
                                status="REVIEW_REQUIRED",
                                params={"strategy": "review_only"},
                            )
                        )

                # 2. Datetime Column Missingness
                elif role == ColumnRole.DATETIME or pd.api.types.is_datetime64_any_dtype(series) or stats.get("min_datetime") is not None:
                    recommendations.append(
                        CleaningRecommendation(
                            recommendation_id=f"rec-null-dt-{col_name}",
                            column_name=col_name,
                            operation="REVIEW_DATETIME_MISSING",
                            category="missing_values",
                            evidence=[
                                f"{null_count} missing timestamps ({null_pct}%)",
                                "Temporal sequencing constraint",
                            ],
                            affected_rows=null_count,
                            affected_percentage=null_pct,
                            confidence=0.70,
                            confidence_level="MEDIUM",
                            risk_level="MEDIUM",
                            default_selected=False,
                            user_selected=False,
                            rationale=f"Datetime column has {null_count} missing timestamps ({null_pct}%). Imputing dates arbitrarily could distort temporal sequences. Manual inspection recommended.",
                            expected_effect=f"Preserves {null_count} missing timestamps as NULL unless manually configured.",
                            requires_review=True,
                            status="REVIEW_REQUIRED",
                            params={"strategy": "leave_unchanged"},
                        )
                    )

                # 3. Identifier Column Missingness
                elif role == ColumnRole.IDENTIFIER:
                    recommendations.append(
                        CleaningRecommendation(
                            recommendation_id=f"rec-null-id-{col_name}",
                            column_name=col_name,
                            operation="REVIEW_IDENTIFIER_MISSING",
                            category="missing_values",
                            evidence=[
                                f"{null_count} missing key records ({null_pct}%)",
                                "Identifier uniqueness/integrity constraint",
                            ],
                            affected_rows=null_count,
                            affected_percentage=null_pct,
                            confidence=0.60,
                            confidence_level="LOW",
                            risk_level="HIGH",
                            default_selected=False,
                            user_selected=False,
                            rationale=f"Identifier column has {null_count} missing key values ({null_pct}%). Missing keys compromise record linkage and referential integrity. Review for record exclusion or source correction.",
                            expected_effect="Flagged for manual review; identifier records are not automatically imputed.",
                            requires_review=True,
                            status="REVIEW_REQUIRED",
                            params={"strategy": "review_only"},
                        )
                    )

                # 4. Categorical Dimension Column Missingness
                elif role == ColumnRole.DIMENSION or pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                    top_freq = stats.get("most_frequent_values", [])
                    has_dominant_mode = (
                        len(top_freq) > 0
                        and non_null_cnt > 0
                        and (top_freq[0]["count"] / non_null_cnt) >= 0.40
                    )

                    if (null_pct <= 25.0 or null_count <= 2) and has_dominant_mode:
                        mode_val = top_freq[0]["value"]
                        mode_share = round((top_freq[0]["count"] / non_null_cnt) * 100, 1)
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-null-dim-{col_name}",
                                column_name=col_name,
                                operation="FILL_MODE",
                                category="missing_values",
                                evidence=[
                                    f"{null_count} missing values ({null_pct}%)",
                                    f"Dominant mode '{mode_val}' represents {mode_share}% of non-null rows",
                                ],
                                affected_rows=null_count,
                                affected_percentage=null_pct,
                                confidence=0.85,
                                confidence_level="HIGH",
                                risk_level="LOW",
                                default_selected=True,
                                user_selected=True,
                                rationale=f"Categorical dimension with low missingness ({null_count} rows, {null_pct}%). Dominant category '{mode_val}' ({mode_share}%) provides a consistent mode imputation.",
                                expected_effect=f"Fills {null_count} missing cells with mode category '{mode_val}'.",
                                requires_review=False,
                                status="RECOMMENDED",
                                params={"strategy": "mode", "fill_value": mode_val},
                            )
                        )
                    else:
                        recommendations.append(
                            CleaningRecommendation(
                                recommendation_id=f"rec-null-dim-{col_name}",
                                column_name=col_name,
                                operation="FILL_UNKNOWN",
                                category="missing_values",
                                evidence=[
                                    f"{null_count} missing values ({null_pct}%)",
                                    "Categorical dimension without single dominant category",
                                ],
                                affected_rows=null_count,
                                affected_percentage=null_pct,
                                confidence=0.85,
                                confidence_level="HIGH",
                                risk_level="LOW",
                                default_selected=True,
                                user_selected=True,
                                rationale=f"Categorical dimension with {null_count} missing entries ({null_pct}%). Explicit 'Unknown' placeholder preserves missingness transparency without fabricating category membership.",
                                expected_effect=f"Fills {null_count} missing cells with 'Unknown'.",
                                requires_review=False,
                                status="RECOMMENDED",
                                params={"strategy": "constant", "fill_value": "Unknown"},
                            )
                        )

            # -----------------------------------------------------------------
            # 2D. Outlier Detection (DETECTION ONLY)
            # -----------------------------------------------------------------
            if (
                (role == ColumnRole.MEASURE or pd.api.types.is_numeric_dtype(series))
                and non_null_cnt >= 10
            ):
                q25 = stats.get("q25")
                q75 = stats.get("q75")
                if q25 is not None and q75 is not None:
                    iqr = float(q75 - q25)
                    if iqr > 0:
                        lower_bound = float(q25 - 1.5 * iqr)
                        upper_bound = float(q75 + 1.5 * iqr)
                        numeric_clean = pd.to_numeric(non_null_series, errors="coerce").dropna()
                        outlier_mask = (numeric_clean < lower_bound) | (numeric_clean > upper_bound)
                        outlier_cnt = int(outlier_mask.sum())

                        if outlier_cnt > 0 and outlier_cnt <= int(0.10 * non_null_cnt):
                            outlier_pct = round((outlier_cnt / max(total_rows, 1)) * 100, 2)
                            recommendations.append(
                                CleaningRecommendation(
                                    recommendation_id=f"rec-outlier-{col_name}",
                                    column_name=col_name,
                                    operation="REVIEW_OUTLIERS",
                                    category="outliers",
                                    evidence=[
                                        f"{outlier_cnt} statistical outliers detected outside 1.5x IQR bounds [{round(lower_bound, 2)}, {round(upper_bound, 2)}]"
                                    ],
                                    affected_rows=outlier_cnt,
                                    affected_percentage=outlier_pct,
                                    confidence=0.75,
                                    confidence_level="MEDIUM",
                                    risk_level="HIGH",
                                    default_selected=False,
                                    user_selected=False,
                                    rationale=f"Statistically unusual values detected ({outlier_cnt} values outside IQR bounds [{round(lower_bound, 2)}, {round(upper_bound, 2)}]). Automatic removal is not recommended by default to prevent discarding legitimate high-value business observations.",
                                    expected_effect="Flagged for analytical awareness; values remain in dataset.",
                                    requires_review=True,
                                    status="REVIEW_REQUIRED",
                                    params={
                                        "lower_bound": round(lower_bound, 2),
                                        "upper_bound": round(upper_bound, 2),
                                        "outlier_count": outlier_cnt,
                                    },
                                )
                            )

            # -----------------------------------------------------------------
            # 2E. Constant Column Flag
            # -----------------------------------------------------------------
            if stats.get("is_constant") or (non_null_cnt > 0 and non_null_series.nunique() == 1):
                recommendations.append(
                    CleaningRecommendation(
                        recommendation_id=f"rec-const-{col_name}",
                        column_name=col_name,
                        operation="REVIEW_CONSTANT_COLUMN",
                        category="invalid_values",
                        evidence=[
                            f"Column has zero variance (identical single value across all {non_null_cnt} rows)"
                        ],
                        affected_rows=total_rows,
                        affected_percentage=100.0,
                        confidence=0.80,
                        confidence_level="HIGH",
                        risk_level="MEDIUM",
                        default_selected=False,
                        user_selected=False,
                        rationale=f"Column '{col_name}' has zero variance. A constant column carries no analytical or segmentation value.",
                        expected_effect="Flagged for user review; potential candidate for dropping in modeling.",
                        requires_review=True,
                        status="REVIEW_REQUIRED",
                        params={"unique_count": 1},
                    )
                )

        # =====================================================================
        # 3. Plan Aggregation and Metadata Summary
        # =====================================================================
        recommended_cnt = sum(1 for r in recommendations if r.status == "RECOMMENDED")
        review_cnt = sum(1 for r in recommendations if r.requires_review)
        safe_cnt = sum(1 for r in recommendations if r.risk_level == "LOW")
        est_rows_affected = max(affected_row_counts) if affected_row_counts else 0

        return CleaningPlan(
            dataset_id=dataset_id,
            total_recommendations=len(recommendations),
            recommended_count=recommended_cnt,
            review_required_count=review_cnt,
            safe_count=safe_cnt,
            estimated_rows_affected=est_rows_affected,
            recommendations=recommendations,
        )


def generate_cleaning_plan(
    canonical: CanonicalDataset,
    profile: Optional[DataProfile] = None,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
    quality_assessment: Optional[Any] = None,
) -> CleaningPlan:
    """Convenience function to generate a CleaningPlan for a CanonicalDataset."""
    planner = CleaningPlanner()
    return planner.generate_plan(
        canonical=canonical,
        profile=profile,
        semantic_profile=semantic_profile,
        quality_assessment=quality_assessment,
    )
