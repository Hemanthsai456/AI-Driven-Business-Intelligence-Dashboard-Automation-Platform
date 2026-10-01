"""Automated Data Cleaning Engine implementing Stage 2 of the pipeline."""

import math
import re
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DataProfile,
    DatasetMetadata,
    sanitize_json_value,
)
from intelligence.profiler import DataProfiler
from intelligence.semantic_analyzer import DatasetSemanticProfile, SemanticAnalyzer

from cleaning.models import (
    CleaningChange,
    CleaningConfig,
    CleaningReport,
    CleaningResult,
)


class DataCleaner:
    """Automated data cleaner that executes between Ingestion and Profiling.

    This cleaner adheres strictly to the non-mutating guarantee:
    the input CanonicalDataset and its DataFrame are never modified in place.
    A new CanonicalDataset is produced alongside an audit-grade CleaningReport.
    """

    CURRENCY_CLEAN_REGEX = re.compile(r"[$€£¥₹\s,]|USD|EUR|GBP|INR|JPY|CAD|AUD", re.IGNORECASE)

    def __init__(self, config: Optional[CleaningConfig] = None):
        self.config = config or CleaningConfig()

    def clean(
        self,
        canonical: CanonicalDataset,
        profile: Optional[DataProfile] = None,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
    ) -> CleaningResult:
        """Execute automated cleaning rules against a CanonicalDataset.

        Args:
            canonical: Input canonical dataset. The underlying data is never mutated.
            profile: Optional preliminary profile. If None, generated automatically.
            semantic_profile: Optional semantic role profile. If None, generated automatically.

        Returns:
            CleaningResult containing the new cleaned CanonicalDataset and the detailed CleaningReport.
        """
        # Read-only invariant: deep copy dataframe so original is untouched
        df = canonical.data.copy(deep=True)
        initial_rows, initial_cols = int(len(df)), int(len(df.columns))
        changes: List[CleaningChange] = []

        # 1. Preliminary Profiling & Semantic Inference if not supplied
        if profile is None:
            profile = (
                canonical.profile
                if canonical.profile is not None
                else DataProfiler().profile(canonical, attach=False)
            )

        if semantic_profile is None:
            semantic_profile = SemanticAnalyzer().analyze(
                canonical=canonical, profile=profile, apply_roles=False
            )

        # 2. Rule: Deduplication
        if self.config.deduplicate and len(df) > 0:
            dup_mask = df.duplicated()
            dup_count = int(dup_mask.sum())
            if dup_count > 0:
                df = df.drop_duplicates().reset_index(drop=True)
                changes.append(
                    CleaningChange(
                        rule="deduplicate",
                        column=None,
                        count=dup_count,
                        details={"removed_duplicate_rows": dup_count},
                    )
                )

        # 3. Rule: Column-Level Missingness Drop Threshold
        if self.config.null_drop_threshold < 1.0 and len(df) > 0:
            cols_to_drop = []
            for col in df.columns:
                null_frac = float(df[col].isna().sum() / len(df))
                if null_frac >= self.config.null_drop_threshold:
                    cols_to_drop.append((col, null_frac))

            for col, frac in cols_to_drop:
                df = df.drop(columns=[col])
                changes.append(
                    CleaningChange(
                        rule="drop_column_missingness",
                        column=col,
                        count=len(df),
                        details={
                            "null_percentage": round(frac * 100.0, 2),
                            "threshold": round(self.config.null_drop_threshold * 100.0, 2),
                        },
                    )
                )

        # 4. Rule: Type Coercion (driven by semantic roles & value inspection)
        if self.config.coerce_types and len(df) > 0:
            for col in list(df.columns):
                series = df[col]
                ev = semantic_profile.get_evidence(col)
                role = ev.candidate_role if ev else ColumnRole.UNKNOWN
                dtype_str = str(series.dtype).lower()
                is_obj = "object" in dtype_str or "str" in dtype_str or "category" in dtype_str

                if is_obj:
                    non_null_s = series.dropna().astype(str).str.strip()
                    if len(non_null_s) == 0:
                        continue

                    # 4.1 Currency Coercion (for MEASURE or strings with currency symbols)
                    if role == ColumnRole.MEASURE or non_null_s.str.contains(r"[$€£¥₹]|USD|EUR", regex=True).mean() >= 0.5:
                        converted_vals, conv_cnt = self._coerce_currency_series(series)
                        if conv_cnt > 0:
                            df[col] = converted_vals
                            changes.append(
                                CleaningChange(
                                    rule="coerce_currency",
                                    column=col,
                                    count=conv_cnt,
                                    details={"new_dtype": str(converted_vals.dtype)},
                                )
                            )
                            continue

                    # 4.2 Percentage Coercion (for MEASURE or strings with %)
                    if role == ColumnRole.MEASURE or non_null_s.str.contains(r"%", regex=True).mean() >= 0.5:
                        converted_vals, conv_cnt = self._coerce_percentage_series(series)
                        if conv_cnt > 0:
                            df[col] = converted_vals
                            changes.append(
                                CleaningChange(
                                    rule="coerce_percentage",
                                    column=col,
                                    count=conv_cnt,
                                    details={"new_dtype": str(converted_vals.dtype)},
                                )
                            )
                            continue

                    # 4.3 General Numeric Coercion (for MEASURE with commas/whitespace)
                    if role == ColumnRole.MEASURE:
                        converted_vals, conv_cnt = self._coerce_numeric_series(series)
                        if conv_cnt > 0:
                            df[col] = converted_vals
                            changes.append(
                                CleaningChange(
                                    rule="coerce_numeric",
                                    column=col,
                                    count=conv_cnt,
                                    details={"new_dtype": str(converted_vals.dtype)},
                                )
                            )
                            continue

                    # 4.4 Datetime Coercion (for DATETIME columns)
                    if role == ColumnRole.DATETIME:
                        converted_vals, conv_cnt, ambig_cnt, ambig_samples = self._coerce_datetime_series(series)
                        if ambig_cnt > 0:
                            changes.append(
                                CleaningChange(
                                    rule="ambiguous_date_detected",
                                    column=col,
                                    count=ambig_cnt,
                                    details={
                                        "warning": "Ambiguous day/month format detected across date strings; left un-coerced to avoid guessing.",
                                        "sample_values": ambig_samples,
                                    },
                                )
                            )
                        elif conv_cnt > 0:
                            df[col] = converted_vals
                            changes.append(
                                CleaningChange(
                                    rule="coerce_datetime",
                                    column=col,
                                    count=conv_cnt,
                                    details={"new_dtype": "datetime64[ns]"},
                                )
                            )
                        continue

        # 5. Rule: Whitespace & Case Normalization for Categories (DIMENSION)
        if self.config.normalize_categories and len(df) > 0:
            for col in list(df.columns):
                series = df[col]
                ev = semantic_profile.get_evidence(col)
                role = ev.candidate_role if ev else ColumnRole.UNKNOWN
                dtype_str = str(series.dtype).lower()
                is_obj = "object" in dtype_str or "str" in dtype_str or "category" in dtype_str

                if role == ColumnRole.DIMENSION and is_obj and not pd.api.types.is_numeric_dtype(series):
                    non_nulls = series.dropna()
                    if len(non_nulls) == 0:
                        continue
                    col_distinct = int(non_nulls.nunique())
                    cardinality_ratio = col_distinct / max(len(non_nulls), 1)
                    avg_len = float(non_nulls.astype(str).str.len().mean())

                    # Applies only to low-cardinality dimensions and leaves free text alone.
                    # A column is "free text" if its strings average >= 40 characters,
                    # regardless of cardinality (so even a 5-row free-text column is not normalized).
                    # Short strings like region/category names are always candidates for normalization.
                    is_low_cardinality = (cardinality_ratio <= 0.25 or col_distinct <= 30)
                    is_free_text = avg_len >= 40

                    if is_low_cardinality and not is_free_text:
                        has_text = any(isinstance(v, str) and re.search(r"[a-zA-Z]", v) for v in non_nulls.head(20))
                        if has_text:
                            normalized, norm_cnt = self._normalize_categorical_series(series)
                            if norm_cnt > 0:
                                df[col] = normalized
                                changes.append(
                                    CleaningChange(
                                        rule="normalize_category",
                                        column=col,
                                        count=norm_cnt,
                                        details={"operation": "map_to_most_frequent_spelling"},
                                    )
                                )

        # 6. Rule: Null Handling per Semantic Role
        if self.config.handle_nulls and len(df) > 0:
            for col in list(df.columns):
                series = df[col]
                ev = semantic_profile.get_evidence(col)
                role = ev.candidate_role if ev else ColumnRole.UNKNOWN
                null_cnt = int(series.isna().sum())

                if null_cnt > 0:
                    # 6.1 Measures -> Not imputed by default; report null counts with imputation opt-in
                    if role == ColumnRole.MEASURE:
                        if self.config.impute_measures:
                            filled_series, fill_cnt, median_val = self._impute_measure_nulls(series)
                            if fill_cnt > 0:
                                df[col] = filled_series
                                changes.append(
                                    CleaningChange(
                                        rule="fill_null_measure",
                                        column=col,
                                        count=fill_cnt,
                                        details={
                                            "strategy": self.config.measure_null_fill_strategy,
                                            "imputed_value": median_val,
                                        },
                                    )
                                )
                        else:
                            changes.append(
                                CleaningChange(
                                    rule="report_null_measure",
                                    column=col,
                                    count=null_cnt,
                                    details={
                                        "null_count": null_cnt,
                                        "imputed": False,
                                        "note": "Measures not imputed by default; imputation is opt-in via config.",
                                    },
                                )
                            )

                    # 6.2 Dimensions -> "Unknown" Imputation (or median if purely numeric dimension like ratings)
                    elif role == ColumnRole.DIMENSION:
                        is_numeric_dim = pd.api.types.is_numeric_dtype(series) or (
                            len(series.dropna()) > 0
                            and all(isinstance(v, (int, float, np.number)) for v in series.dropna())
                        )
                        if is_numeric_dim:
                            filled_series, fill_cnt, median_val = self._impute_measure_nulls(series)
                            if fill_cnt > 0:
                                df[col] = filled_series
                                changes.append(
                                    CleaningChange(
                                        rule="fill_null_dimension",
                                        column=col,
                                        count=fill_cnt,
                                        details={
                                            "strategy": "median_numeric_dim",
                                            "imputed_value": median_val,
                                        },
                                    )
                                )
                        else:
                            fill_val = self.config.dimension_null_fill_value
                            df[col] = series.fillna(fill_val)
                            changes.append(
                                CleaningChange(
                                    rule="fill_null_dimension",
                                    column=col,
                                    count=null_cnt,
                                    details={"imputed_value": fill_val},
                                )
                            )

        # 7. Construct Cleaned CanonicalDataset Metadata and Profile
        cleaned_schema: List[ColumnMetadata] = []
        for col in df.columns:
            orig_meta = canonical.metadata.get_column(col)
            ev = semantic_profile.get_evidence(col)
            role = ev.candidate_role if ev else ColumnRole.UNKNOWN
            col_null_cnt = int(df[col].isna().sum())
            col_len = len(df)
            col_null_pct = round(float((col_null_cnt / col_len) * 100.0), 4) if col_len > 0 else 0.0
            col_distinct = int(df[col].nunique(dropna=True))
            col_uniq = bool(df[col].is_unique) if col_len > 0 else False
            sample_vals = [
                sanitize_json_value(v)
                for v in df[col].dropna().head(5).tolist()
            ]

            cleaned_schema.append(
                ColumnMetadata(
                    original_name=col,
                    normalized_name=orig_meta.normalized_name if orig_meta else col.lower(),
                    detected_datatype=str(df[col].dtype),
                    semantic_role=role,
                    null_count=col_null_cnt,
                    null_percentage=col_null_pct,
                    distinct_count=col_distinct,
                    is_unique=col_uniq,
                    sample_values=sample_vals,
                )
            )

        cleaned_meta = DatasetMetadata(
            dataset_id=f"{canonical.metadata.dataset_id}_cleaned",
            name=f"{canonical.metadata.name} (Cleaned)",
            source_type=canonical.metadata.source_type,
            row_count=len(df),
            column_count=len(df.columns),
            schema=cleaned_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )

        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=df)

        # Build clean audit profile
        cleaned_profile = DataProfiler().profile(cleaned_canonical, attach=True)
        cleaned_canonical.profile = cleaned_profile

        report = CleaningReport(
            dataset_id=canonical.metadata.dataset_id,
            initial_rows=initial_rows,
            final_rows=int(len(df)),
            initial_columns=initial_cols,
            final_columns=int(len(df.columns)),
            changes=changes,
        )

        cleaned_canonical.add_audit_entry(
            action="DATA_CLEANED",
            details={
                "total_changes": report.total_changes,
                "changes_by_rule": report.changes_by_rule,
            },
        )

        return CleaningResult(dataset=cleaned_canonical, report=report)

    # -------------------------------------------------------------------------
    # Helper Transformation Methods
    # -------------------------------------------------------------------------

    def _coerce_currency_series(self, series: pd.Series) -> Tuple[pd.Series, int]:
        """Convert currency string series ($1,200.50, €450, ($50.00)) to float64."""
        conv_cnt = 0
        converted_values = []
        is_modified = False

        for val in series:
            if pd.isna(val):
                converted_values.append(np.nan)
                continue
            val_str = str(val).strip()
            # Handle accounting negative format ($50.00) -> -50.00
            is_negative = False
            if val_str.startswith("(") and val_str.endswith(")"):
                is_negative = True
                val_str = val_str[1:-1].strip()

            cleaned_str = self.CURRENCY_CLEAN_REGEX.sub("", val_str).strip()
            try:
                num = float(cleaned_str)
                if is_negative:
                    num = -num
                converted_values.append(num)
                conv_cnt += 1
                is_modified = True
            except ValueError:
                converted_values.append(np.nan)

        if not is_modified:
            return series, 0

        res_series = pd.Series(converted_values, index=series.index, dtype="float64")
        return res_series, conv_cnt

    def _coerce_percentage_series(self, series: pd.Series) -> Tuple[pd.Series, int]:
        """Convert percentage strings (15.5%, 10%) to float numeric."""
        conv_cnt = 0
        converted_values = []
        is_modified = False

        for val in series:
            if pd.isna(val):
                converted_values.append(np.nan)
                continue
            val_str = str(val).strip().replace(",", "")
            if val_str.endswith("%"):
                val_str = val_str[:-1].strip()
                try:
                    num = float(val_str)
                    converted_values.append(num)
                    conv_cnt += 1
                    is_modified = True
                except ValueError:
                    converted_values.append(np.nan)
            else:
                try:
                    num = float(val_str)
                    converted_values.append(num)
                except ValueError:
                    converted_values.append(np.nan)

        if not is_modified:
            return series, 0

        res_series = pd.Series(converted_values, index=series.index, dtype="float64")
        return res_series, conv_cnt

    def _coerce_numeric_series(self, series: pd.Series) -> Tuple[pd.Series, int]:
        """Convert commified or spaced numeric strings ('1,200', ' 450.5 ') to float."""
        conv_cnt = 0
        converted_values = []
        is_modified = False

        for val in series:
            if pd.isna(val):
                converted_values.append(np.nan)
                continue
            val_str = str(val).strip().replace(",", "")
            try:
                num = float(val_str)
                converted_values.append(num)
                if val_str != str(val):
                    conv_cnt += 1
                    is_modified = True
            except ValueError:
                converted_values.append(np.nan)

        if not is_modified:
            return series, 0

        res_series = pd.Series(converted_values, index=series.index, dtype="float64")
        return res_series, conv_cnt

    def _coerce_datetime_series(
        self, series: pd.Series
    ) -> Tuple[pd.Series, int, int, List[str]]:
        """Convert mixed-format date strings to pandas datetime64, detecting ambiguous day/month."""
        non_null_s = series.dropna().astype(str).str.strip()
        if len(non_null_s) == 0:
            return series, 0, 0, []

        # Check for potential day/month ambiguity in strings like XX/YY/ZZZZ or XX-YY-ZZZZ
        # If parts 1 and 2 are both <= 12 in rows, and there are no unambiguous hints (>12),
        # or conflicting patterns, log ambiguous date strings instead of silently guessing.
        slash_dash_pat = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$")
        ambig_candidates = []
        has_first_gt_12 = False
        has_second_gt_12 = False
        matched_any_slash = False

        for v in non_null_s.head(50):
            m = slash_dash_pat.match(v)
            if m:
                matched_any_slash = True
                p1, p2 = int(m.group(1)), int(m.group(2))
                if p1 > 12:
                    has_first_gt_12 = True
                if p2 > 12:
                    has_second_gt_12 = True
                if p1 <= 12 and p2 <= 12:
                    ambig_candidates.append(v)

        # Ambiguous if both parts <= 12 and cannot deduce format conclusively,
        # or if contradictory (some have p1 > 12, others have p2 > 12)
        if matched_any_slash:
            if (has_first_gt_12 and has_second_gt_12) or (ambig_candidates and not (has_first_gt_12 or has_second_gt_12)):
                # Ambiguous day/month format
                return series, 0, len(ambig_candidates), ambig_candidates[:5]

        try:
            parsed = pd.to_datetime(series, format="mixed", errors="coerce")
            conv_cnt = int(parsed.notna().sum())
            if conv_cnt > 0:
                return parsed, conv_cnt, 0, []
        except Exception:
            pass

        return series, 0, 0, []

    def _normalize_categorical_series(self, series: pd.Series) -> Tuple[pd.Series, int]:
        """Normalize whitespace and map variants to the most frequent original spelling.

        Rule:
        - Group all values that are identical after strip + lower + collapse-whitespace.
        - If one raw variant has a higher frequency, it wins (original spelling preserved).
        - If all variants in a cluster are tied in frequency, use stripped + title-case as
          the canonical form (e.g. ' north ' and 'NORTH' → 'North').
        - Single-entry clusters still get whitespace-stripped and title-cased if the raw
          value differs from the canonical form.
        """
        from collections import Counter

        non_nulls = series.dropna()
        if len(non_nulls) == 0:
            return series, 0

        # Count frequencies of each exact raw representation
        raw_counts = Counter(non_nulls)

        # Group by canonical normalized key (stripped whitespace, lowercased)
        clusters: Dict[str, Counter] = {}
        for raw_val, count in raw_counts.items():
            if not isinstance(raw_val, str):
                continue
            key = re.sub(r"\s+", " ", raw_val.strip()).lower()
            if not key:
                continue
            if key not in clusters:
                clusters[key] = Counter()
            clusters[key][raw_val] += count

        # Determine best canonical spelling for each cluster
        mapping: Dict[Any, Any] = {}
        for key, counts in clusters.items():
            title_canonical = key.title()  # stripped + title-cased form

            if len(counts) == 1:
                # Single raw variant: normalize whitespace and case
                (raw_val, _) = next(iter(counts.items()))
                clean_val = re.sub(r"\s+", " ", raw_val.strip()).title()
                if raw_val != clean_val:
                    mapping[raw_val] = clean_val
            else:
                # Multiple variants: pick most frequent raw spelling
                sorted_variants = counts.most_common()
                top_count = sorted_variants[0][1]
                top_variants = [v for v, c in sorted_variants if c == top_count]

                if len(top_variants) == 1:
                    # Clear winner
                    best_spelling = top_variants[0]
                    best_spelling_clean = re.sub(r"\s+", " ", best_spelling.strip())
                else:
                    # Tied: fall back to stripped + title-cased canonical
                    best_spelling_clean = title_canonical

                for raw_val in counts.keys():
                    if raw_val != best_spelling_clean:
                        mapping[raw_val] = best_spelling_clean

        if not mapping:
            return series, 0

        norm_cnt = 0
        normalized_values = []
        for val in series:
            if pd.isna(val):
                normalized_values.append(val)
            elif val in mapping:
                normalized_values.append(mapping[val])
                norm_cnt += 1
            else:
                normalized_values.append(val)

        return pd.Series(normalized_values, index=series.index, dtype=series.dtype), norm_cnt

    def _impute_measure_nulls(self, series: pd.Series) -> Tuple[pd.Series, int, Optional[float]]:
        """Impute nulls in numeric measure with median."""
        null_mask = series.isna()
        null_cnt = int(null_mask.sum())
        if null_cnt == 0:
            return series, 0, None

        numeric_non_null = pd.to_numeric(series.dropna(), errors="coerce").dropna()
        if len(numeric_non_null) == 0:
            return series, 0, None

        median_val = float(numeric_non_null.median())
        if math.isnan(median_val):
            return series, 0, None

        # Round median to 2 decimal places if float
        median_val = round(median_val, 2)
        filled = series.fillna(median_val)
        return filled, null_cnt, median_val


def clean_dataset(
    canonical: CanonicalDataset,
    profile: Optional[DataProfile] = None,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
    config: Optional[CleaningConfig] = None,
) -> Tuple[CanonicalDataset, CleaningReport]:
    """Convenience functional interface for cleaning a CanonicalDataset."""
    cleaner = DataCleaner(config=config)
    result = cleaner.clean(canonical, profile=profile, semantic_profile=semantic_profile)
    return result.dataset, result.report
