"""Deterministic Multi-Valued Cell Detection and Handling Engine (Data Studio Part 6.3).

Detects columns containing multiple logical values inside a single cell (e.g. "12,17",
"9876543210,8765432109", "Python;SQL;Java", "Red|Green|Blue").

Provides non-mutating previews and deterministic execution for:
1. KEEP AS IS (Leave Unchanged)
2. SPLIT INTO COLUMNS (with deterministic collision-safe naming)
3. EXPAND INTO ROWS (with context column duplication and warning)
"""

from dataclasses import dataclass, field
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DatasetMetadata,
    sanitize_json_value,
)
from intelligence.profiler import DataProfiler
from intelligence.semantic_analyzer import DatasetSemanticProfile, SemanticAnalyzer


# Standard regex for detecting thousands-separator formatted numbers (e.g., 1,250.50 or 1,000,000)
THOUSAND_SEPARATOR_REGEX = re.compile(
    r"^\s*[-+]?[\$€£¥₹]?\s*\d{1,3}(,\d{3})+(\.\d+)?\s*[%€£¥₹]?\s*$"
)

# Common delimiters tested for multi-valued cell detection
COMMON_DELIMITERS = [",", ";", "|", "/", ":"]


class MultiValueExecutionError(Exception):
    """Raised when multi-valued cell operation fails validation or invariants."""
    pass


@dataclass
class MultiValuedColumnCandidate:
    """Structured detection response for a column suspected of containing multi-valued cells."""

    column_name: str
    detected_delimiter: str
    affected_rows: int
    affected_percentage: float
    average_values_per_affected_row: float
    max_values_per_row: int
    examples: List[str]
    confidence: str  # "HIGH", "MEDIUM", "LOW", "REVIEW"
    recommendation: str  # "SPLIT_COLUMNS", "EXPAND_ROWS", "KEEP", "REVIEW"
    reason: str
    evidence: List[str] = field(default_factory=list)
    column_dtype: str = "object"
    semantic_role: str = "DIMENSION"

    def to_dict(self) -> Dict[str, Any]:
        """Convert candidate to a JSON-serializable dictionary."""
        return {
            "column_name": self.column_name,
            "detected_delimiter": self.detected_delimiter,
            "affected_rows": int(self.affected_rows),
            "affected_percentage": round(float(self.affected_percentage), 2),
            "average_values_per_affected_row": round(float(self.average_values_per_affected_row), 2),
            "max_values_per_row": int(self.max_values_per_row),
            "examples": [str(e) for e in self.examples],
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "reason": self.reason,
            "evidence": self.evidence,
            "column_dtype": self.column_dtype,
            "semantic_role": self.semantic_role,
        }


@dataclass
class MultiValuePreviewResult:
    """Non-mutating preview of a multi-valued cell operation (split or expand)."""

    dataset_id: str
    column_name: str
    action: str  # "SPLIT_COLUMNS" | "EXPAND_ROWS" | "KEEP"
    delimiter_used: str
    original_row_count: int
    resulting_row_count: int
    rows_added: int
    original_column_count: int
    resulting_column_count: int
    affected_rows: int
    generated_columns: List[str] = field(default_factory=list)
    warning_message: Optional[str] = None
    sample_before_after: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert preview result to a JSON-serializable dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "column_name": self.column_name,
            "action": self.action,
            "delimiter_used": self.delimiter_used,
            "original_row_count": int(self.original_row_count),
            "resulting_row_count": int(self.resulting_row_count),
            "rows_added": int(self.rows_added),
            "original_column_count": int(self.original_column_count),
            "resulting_column_count": int(self.resulting_column_count),
            "affected_rows": int(self.affected_rows),
            "generated_columns": self.generated_columns,
            "warning_message": self.warning_message,
            "sample_before_after": sanitize_json_value(self.sample_before_after),
            "warnings": self.warnings,
        }


class MultiValueDetector:
    """Deterministic detection engine for multi-valued cells."""

    @staticmethod
    def is_numeric_comma_formatting(series: pd.Series) -> bool:
        """Determines if comma characters in a series are numeric thousand separators."""
        non_null_s = series.dropna().astype(str).str.strip()
        if len(non_null_s) == 0:
            return False

        comma_containing = non_null_s[non_null_s.str.contains(",", regex=False)]
        if len(comma_containing) == 0:
            return False

        # 1. Match against thousand-separator regex
        matches = comma_containing.apply(lambda x: bool(THOUSAND_SEPARATOR_REGEX.match(x)))
        if matches.mean() >= 0.8:
            return True

        # 2. Check if removing commas produces valid float/int for all comma-containing values
        def check_numeric_without_commas(val: str) -> bool:
            clean = re.sub(r"[\$€£¥₹\s%]", "", val).replace(",", "")
            try:
                float(clean)
                # Verify that comma was followed by exactly 3 digits (e.g. 1,250 not 12,17)
                parts = val.split(",")
                if len(parts) > 1:
                    for p in parts[1:]:
                        digits_in_part = re.findall(r"^\d+", p.strip())
                        if digits_in_part and len(digits_in_part[0]) != 3:
                            return False
                return True
            except ValueError:
                return False

        strict_numeric = comma_containing.apply(check_numeric_without_commas)
        if strict_numeric.mean() >= 0.8:
            return True

        return False

    def detect_candidates(
        self,
        canonical: CanonicalDataset,
        semantic_profile: Optional[DatasetSemanticProfile] = None,
    ) -> List[MultiValuedColumnCandidate]:
        """Detect columns that contain multiple logical values inside a single cell."""
        df = canonical.data
        total_rows = canonical.metadata.row_count or len(df)
        if total_rows == 0:
            return []

        candidates: List[MultiValuedColumnCandidate] = []

        for col in df.columns:
            col_name = str(col)
            series = df[col]
            dtype_str = str(series.dtype).lower()

            # Skip native numeric and boolean columns
            if pd.api.types.is_bool_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
                continue
            if pd.api.types.is_numeric_dtype(series):
                continue

            non_null_s = series.dropna().astype(str).str.strip()
            # Filter out empty strings
            non_null_s = non_null_s[non_null_s != ""]
            non_null_cnt = len(non_null_s)
            if non_null_cnt == 0:
                continue

            ev = semantic_profile.column_evidences.get(col_name) if semantic_profile else None
            role = ev.candidate_role.value if ev and hasattr(ev.candidate_role, "value") else (str(ev.candidate_role) if ev else "DIMENSION")

            # Test each candidate delimiter
            best_delimiter: Optional[str] = None
            best_affected_count = 0
            best_token_counts: List[int] = []
            best_examples: List[str] = []

            for delim in COMMON_DELIMITERS:
                # Check for numeric comma false-positive
                if delim == "," and self.is_numeric_comma_formatting(series):
                    continue

                # Count affected rows for this delimiter
                affected_vals = []
                token_counts = []

                for val in non_null_s:
                    if delim in val:
                        tokens = [t.strip() for t in val.split(delim) if t.strip()]
                        if len(tokens) >= 2:
                            affected_vals.append(val)
                            token_counts.append(len(tokens))

                affected_count = len(affected_vals)
                if affected_count > best_affected_count:
                    best_affected_count = affected_count
                    best_delimiter = delim
                    best_token_counts = token_counts
                    best_examples = affected_vals[:5]

            # Require at least 1 affected row and at least 5% (or >= 2 rows if dataset > 5 rows)
            min_affected = 2 if total_rows > 5 else 1
            if best_delimiter and best_affected_count >= min_affected:
                affected_pct = round((best_affected_count / total_rows) * 100, 2)
                avg_tokens = round(float(np.mean(best_token_counts)), 2) if best_token_counts else 0.0
                max_tokens = int(max(best_token_counts)) if best_token_counts else 0

                # Determine confidence & recommendation
                confidence = "HIGH"
                recommendation = "SPLIT_COLUMNS"
                reason = f"Column contains {best_delimiter}-separated multi-valued tokens across {best_affected_count} rows ({affected_pct}%)."

                if best_delimiter in [";", "|"]:
                    confidence = "HIGH"
                    if max_tokens > 4 or avg_tokens > 3.0:
                        recommendation = "EXPAND_ROWS"
                        reason = f"High token count ({avg_tokens} avg, max {max_tokens}) separated by '{best_delimiter}'. Expanding rows standardizes granular records."
                    else:
                        recommendation = "SPLIT_COLUMNS"
                        reason = f"Consistent structured tokens ({avg_tokens} avg) separated by '{best_delimiter}'. Splitting creates explicit dimension columns."
                elif best_delimiter == ",":
                    if affected_pct >= 20.0 or avg_tokens <= 3.0:
                        confidence = "HIGH"
                        recommendation = "SPLIT_COLUMNS"
                        reason = f"Comma-delimited multi-values detected across {best_affected_count} rows ({affected_pct}%)."
                    elif affected_pct >= 5.0:
                        confidence = "MEDIUM"
                        recommendation = "SPLIT_COLUMNS"
                        reason = f"Comma-delimited tokens detected ({affected_pct}% of rows). Verify intended split."
                    else:
                        confidence = "REVIEW"
                        recommendation = "REVIEW"
                        reason = f"Low frequency of comma-delimited tokens ({best_affected_count} rows). Review recommended before transforming."
                else:
                    confidence = "MEDIUM"
                    recommendation = "SPLIT_COLUMNS"

                evidence = [
                    f"Detected delimiter: '{best_delimiter}'",
                    f"Affected records: {best_affected_count} of {total_rows} ({affected_pct}%)",
                    f"Tokens per affected row: {avg_tokens} avg (max {max_tokens})",
                    f"Sample: {', '.join(repr(e) for e in best_examples[:3])}",
                ]

                candidates.append(
                    MultiValuedColumnCandidate(
                        column_name=col_name,
                        detected_delimiter=best_delimiter,
                        affected_rows=best_affected_count,
                        affected_percentage=affected_pct,
                        average_values_per_affected_row=avg_tokens,
                        max_values_per_row=max_tokens,
                        examples=best_examples,
                        confidence=confidence,
                        recommendation=recommendation,
                        reason=reason,
                        evidence=evidence,
                        column_dtype=dtype_str,
                        semantic_role=role,
                    )
                )

        return candidates


class MultiValueHandler:
    """Handles preview and application of multi-valued cell transformations on DataFrame copies."""

    @staticmethod
    def _validate_inputs(
        df: pd.DataFrame,
        column_name: str,
        delimiter: str,
    ) -> None:
        """Validate column existence and delimiter validity."""
        if column_name not in df.columns:
            raise MultiValueExecutionError(f"Target column '{column_name}' does not exist in dataset.")
        if not delimiter or not isinstance(delimiter, str) or len(delimiter) == 0:
            raise MultiValueExecutionError("Delimiter must be a valid non-empty string.")

    @staticmethod
    def _generate_collision_safe_column_names(
        existing_columns: List[str],
        base_column: str,
        count: int,
    ) -> List[str]:
        """Generate deterministic, collision-safe column names (e.g. col_1, col_2)."""
        existing_set = set(existing_columns)
        # Exclude base_column itself from collision set since it will be replaced/handled
        existing_set.discard(base_column)

        new_names: List[str] = []
        for i in range(1, count + 1):
            candidate = f"{base_column}_{i}"
            if candidate not in existing_set:
                new_names.append(candidate)
                existing_set.add(candidate)
            else:
                # Collision fallback: try col_split_i or increment
                fallback = f"{base_column}_split_{i}"
                suffix_idx = 1
                while fallback in existing_set:
                    fallback = f"{base_column}_part_{i}_{suffix_idx}"
                    suffix_idx += 1
                new_names.append(fallback)
                existing_set.add(fallback)

        return new_names

    def preview_split(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        delimiter: str = ",",
    ) -> MultiValuePreviewResult:
        """Generate a non-mutating preview of splitting a multi-valued column into new columns."""
        df = canonical.data
        self._validate_inputs(df, column_name, delimiter)

        total_rows = len(df)
        orig_cols = list(df.columns)

        if total_rows == 0:
            return MultiValuePreviewResult(
                dataset_id=canonical.metadata.dataset_id,
                column_name=column_name,
                action="SPLIT_COLUMNS",
                delimiter_used=delimiter,
                original_row_count=0,
                resulting_row_count=0,
                rows_added=0,
                original_column_count=len(orig_cols),
                resulting_column_count=len(orig_cols),
                affected_rows=0,
                generated_columns=[],
                sample_before_after=[],
            )

        # Tokenize values
        def tokenize(val: Any) -> List[str]:
            if pd.isna(val) or val is None:
                return []
            val_str = str(val).strip()
            if val_str == "" or val_str.lower() == "nan" or val_str.lower() == "none":
                return []
            return [t.strip() for t in val_str.split(delimiter)]

        tokenized_series = df[column_name].apply(tokenize)
        token_lengths = tokenized_series.apply(len)
        max_tokens = int(max(token_lengths.max(), 2))
        affected_mask = token_lengths >= 2
        affected_count = int(affected_mask.sum())

        generated_cols = self._generate_collision_safe_column_names(
            orig_cols, column_name, max_tokens
        )

        # Build sample before/after
        sample_changes: List[Dict[str, Any]] = []
        sample_indices = df.index[affected_mask].tolist()[:10]
        if not sample_indices:
            sample_indices = df.index[:5].tolist()

        for idx in sample_indices:
            orig_val = df.loc[idx, column_name]
            toks = tokenized_series.loc[idx]
            after_dict = {
                col_name: (toks[i] if i < len(toks) and toks[i] != "" else None)
                for i, col_name in enumerate(generated_cols)
            }
            sample_changes.append({
                "row_index": int(idx),
                "before": orig_val,
                "after": after_dict,
            })

        return MultiValuePreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            column_name=column_name,
            action="SPLIT_COLUMNS",
            delimiter_used=delimiter,
            original_row_count=total_rows,
            resulting_row_count=total_rows,
            rows_added=0,
            original_column_count=len(orig_cols),
            resulting_column_count=len(orig_cols) - 1 + len(generated_cols),
            affected_rows=affected_count,
            generated_columns=generated_cols,
            warning_message=None,
            sample_before_after=sample_changes,
            warnings=[],
        )

    def apply_split(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        delimiter: str = ",",
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Execute column split on a deep copy of DataFrame, returning new CanonicalDataset."""
        raw_df = canonical.data
        self._validate_inputs(raw_df, column_name, delimiter)

        working_df = raw_df.copy(deep=True)
        total_rows = len(working_df)
        orig_cols = list(working_df.columns)

        if total_rows == 0:
            return canonical, {"affected_rows": 0, "generated_columns": []}

        def tokenize(val: Any) -> List[str]:
            if pd.isna(val) or val is None:
                return []
            val_str = str(val).strip()
            if val_str == "" or val_str.lower() == "nan" or val_str.lower() == "none":
                return []
            return [t.strip() for t in val_str.split(delimiter)]

        tokenized_series = working_df[column_name].apply(tokenize)
        max_tokens = int(max(tokenized_series.apply(len).max(), 2))
        affected_count = int((tokenized_series.apply(len) >= 2).sum())

        generated_cols = self._generate_collision_safe_column_names(
            orig_cols, column_name, max_tokens
        )

        # Build generated columns series
        new_columns_dict = {}
        for i, col_name in enumerate(generated_cols):
            new_columns_dict[col_name] = tokenized_series.apply(
                lambda toks: toks[i] if i < len(toks) and toks[i] != "" else None
            )

        # Replace original column position with generated columns
        col_pos = orig_cols.index(column_name)
        working_df = working_df.drop(columns=[column_name])
        for offset, col_name in enumerate(generated_cols):
            working_df.insert(col_pos + offset, col_name, new_columns_dict[col_name])

        # Construct new schema metadata
        from ingestion.loaders import CSVLoader
        loader = CSVLoader()
        new_schema = loader.extract_column_metadata(working_df)

        cleaned_meta = DatasetMetadata(
            dataset_id=canonical.metadata.dataset_id,
            name=f"{canonical.metadata.name} (Split {column_name})",
            source_type=canonical.metadata.source_type,
            row_count=len(working_df),
            column_count=len(working_df.columns),
            schema=new_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )
        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=working_df)

        audit_info = {
            "action": "SPLIT_COLUMNS",
            "column_name": column_name,
            "delimiter": delimiter,
            "affected_rows": affected_count,
            "generated_columns": generated_cols,
            "new_columns_count": len(generated_cols),
        }
        cleaned_canonical.add_audit_entry("SPLIT_COLUMNS", audit_info)

        return cleaned_canonical, audit_info

    def preview_expand(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        delimiter: str = ",",
    ) -> MultiValuePreviewResult:
        """Generate a non-mutating preview of expanding multi-valued cells into rows."""
        df = canonical.data
        self._validate_inputs(df, column_name, delimiter)

        total_rows = len(df)
        orig_cols = list(df.columns)

        if total_rows == 0:
            return MultiValuePreviewResult(
                dataset_id=canonical.metadata.dataset_id,
                column_name=column_name,
                action="EXPAND_ROWS",
                delimiter_used=delimiter,
                original_row_count=0,
                resulting_row_count=0,
                rows_added=0,
                original_column_count=len(orig_cols),
                resulting_column_count=len(orig_cols),
                affected_rows=0,
                generated_columns=[],
                warning_message="Expanding values duplicates the other fields in affected rows.",
                sample_before_after=[],
            )

        def split_val(v: Any) -> List[Any]:
            if pd.isna(v) or v is None:
                return [v]
            v_str = str(v).strip()
            if v_str == "" or v_str.lower() == "nan" or v_str.lower() == "none":
                return [np.nan]
            toks = [t.strip() for t in v_str.split(delimiter) if t.strip()]
            return toks if toks else [np.nan]

        split_series = df[column_name].apply(split_val)
        lengths = split_series.apply(len)
        affected_mask = lengths >= 2
        affected_count = int(affected_mask.sum())
        resulting_row_count = int(lengths.sum())
        rows_added = resulting_row_count - total_rows

        # Build sample before/after
        sample_changes: List[Dict[str, Any]] = []
        sample_indices = df.index[affected_mask].tolist()[:5]

        for idx in sample_indices:
            orig_row = df.loc[idx].to_dict()
            toks = split_series.loc[idx]
            expanded_rows = []
            for t in toks:
                row_copy = dict(orig_row)
                row_copy[column_name] = t
                expanded_rows.append(row_copy)

            sample_changes.append({
                "original_row_index": int(idx),
                "before_value": orig_row.get(column_name),
                "before_row": {k: sanitize_json_value(v) for k, v in orig_row.items()},
                "expanded_values": toks,
                "resulting_rows_count": len(expanded_rows),
                "after_rows": [{k: sanitize_json_value(v) for k, v in r.items()} for r in expanded_rows],
            })

        return MultiValuePreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            column_name=column_name,
            action="EXPAND_ROWS",
            delimiter_used=delimiter,
            original_row_count=total_rows,
            resulting_row_count=resulting_row_count,
            rows_added=rows_added,
            original_column_count=len(orig_cols),
            resulting_column_count=len(orig_cols),
            affected_rows=affected_count,
            generated_columns=[column_name],
            warning_message="Expanding values duplicates the other fields in affected rows.",
            sample_before_after=sample_changes,
            warnings=["Expanding values duplicates the other fields in affected rows."],
        )

    def apply_expand(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        delimiter: str = ",",
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Execute row expansion on a deep copy of DataFrame, returning new CanonicalDataset."""
        raw_df = canonical.data
        self._validate_inputs(raw_df, column_name, delimiter)

        working_df = raw_df.copy(deep=True)
        total_rows = len(working_df)

        if total_rows == 0:
            return canonical, {"affected_rows": 0, "rows_added": 0}

        def split_val(v: Any) -> List[Any]:
            if pd.isna(v) or v is None:
                return [v]
            v_str = str(v).strip()
            if v_str == "" or v_str.lower() == "nan" or v_str.lower() == "none":
                return [np.nan]
            toks = [t.strip() for t in v_str.split(delimiter) if t.strip()]
            return toks if toks else [np.nan]

        split_series = working_df[column_name].apply(split_val)
        affected_count = int((split_series.apply(len) >= 2).sum())

        working_df["__multivalue_temp__"] = split_series
        exploded_df = working_df.explode("__multivalue_temp__").reset_index(drop=True)
        exploded_df[column_name] = exploded_df["__multivalue_temp__"]
        exploded_df = exploded_df.drop(columns=["__multivalue_temp__"])

        rows_added = len(exploded_df) - total_rows

        # Construct new schema metadata
        from ingestion.loaders import CSVLoader
        loader = CSVLoader()
        new_schema = loader.extract_column_metadata(exploded_df)

        cleaned_meta = DatasetMetadata(
            dataset_id=canonical.metadata.dataset_id,
            name=f"{canonical.metadata.name} (Expanded {column_name})",
            source_type=canonical.metadata.source_type,
            row_count=len(exploded_df),
            column_count=len(exploded_df.columns),
            schema=new_schema,
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )
        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=exploded_df)

        audit_info = {
            "action": "EXPAND_ROWS",
            "column_name": column_name,
            "delimiter": delimiter,
            "affected_rows": affected_count,
            "original_row_count": total_rows,
            "resulting_row_count": len(exploded_df),
            "rows_added": rows_added,
        }
        cleaned_canonical.add_audit_entry("EXPAND_ROWS", audit_info)

        return cleaned_canonical, audit_info

    def preview_keep(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        delimiter: str = ",",
    ) -> MultiValuePreviewResult:
        """Generate a non-mutating preview of keeping multi-valued cells unchanged."""
        df = canonical.data
        self._validate_inputs(df, column_name, delimiter)
        total_rows = len(df)
        orig_cols = list(df.columns)

        sample_changes: List[Dict[str, Any]] = []
        sample_indices = df.index[:5].tolist()
        for idx in sample_indices:
            sample_changes.append({
                "row_index": int(idx),
                "before": df.loc[idx, column_name],
                "after": df.loc[idx, column_name],
            })

        return MultiValuePreviewResult(
            dataset_id=canonical.metadata.dataset_id,
            column_name=column_name,
            action="KEEP",
            delimiter_used=delimiter,
            original_row_count=total_rows,
            resulting_row_count=total_rows,
            rows_added=0,
            original_column_count=len(orig_cols),
            resulting_column_count=len(orig_cols),
            affected_rows=0,
            generated_columns=[column_name],
            warning_message=None,
            sample_before_after=sample_changes,
            warnings=[],
        )

    def apply_keep(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        delimiter: str = ",",
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Keep dataset unchanged, adding an audit entry on a copy."""
        df = canonical.data
        self._validate_inputs(df, column_name, delimiter)
        working_df = df.copy(deep=True)

        cleaned_meta = DatasetMetadata(
            dataset_id=canonical.metadata.dataset_id,
            name=canonical.metadata.name,
            source_type=canonical.metadata.source_type,
            row_count=len(working_df),
            column_count=len(working_df.columns),
            schema=list(canonical.metadata.schema),
            custom_metadata=dict(canonical.metadata.custom_metadata),
        )
        cleaned_canonical = CanonicalDataset(metadata=cleaned_meta, data=working_df)
        audit_info = {
            "action": "KEEP",
            "column_name": column_name,
            "delimiter": delimiter,
            "affected_rows": 0,
            "rows_added": 0,
        }
        cleaned_canonical.add_audit_entry("KEEP", audit_info)
        return cleaned_canonical, audit_info

    def preview(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        action: str,
        delimiter: str = ",",
    ) -> MultiValuePreviewResult:
        """Dispatch preview based on action: SPLIT_COLUMNS, EXPAND_ROWS, or KEEP."""
        normalized_action = action.upper().strip()
        if normalized_action in ["SPLIT", "SPLIT_COLUMNS"]:
            return self.preview_split(canonical, column_name, delimiter)
        elif normalized_action in ["EXPAND", "EXPAND_ROWS"]:
            return self.preview_expand(canonical, column_name, delimiter)
        elif normalized_action in ["KEEP", "KEEP_AS_IS", "LEAVE_UNCHANGED"]:
            return self.preview_keep(canonical, column_name, delimiter)
        else:
            raise MultiValueExecutionError(
                f"Unsupported multi-value action '{action}'. Allowed actions: 'KEEP', 'SPLIT_COLUMNS', 'EXPAND_ROWS'."
            )

    def apply(
        self,
        canonical: CanonicalDataset,
        column_name: str,
        action: str,
        delimiter: str = ",",
    ) -> Tuple[CanonicalDataset, Dict[str, Any]]:
        """Dispatch apply based on action: SPLIT_COLUMNS, EXPAND_ROWS, or KEEP."""
        normalized_action = action.upper().strip()
        if normalized_action in ["SPLIT", "SPLIT_COLUMNS"]:
            return self.apply_split(canonical, column_name, delimiter)
        elif normalized_action in ["EXPAND", "EXPAND_ROWS"]:
            return self.apply_expand(canonical, column_name, delimiter)
        elif normalized_action in ["KEEP", "KEEP_AS_IS", "LEAVE_UNCHANGED"]:
            return self.apply_keep(canonical, column_name, delimiter)
        else:
            raise MultiValueExecutionError(
                f"Unsupported multi-value action '{action}'. Allowed actions: 'KEEP', 'SPLIT_COLUMNS', 'EXPAND_ROWS'."
            )

