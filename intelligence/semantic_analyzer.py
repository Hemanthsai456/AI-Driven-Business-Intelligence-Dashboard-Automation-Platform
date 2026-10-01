"""Deterministic rule-based semantic role classification engine."""

from dataclasses import dataclass, field
from enum import Enum
import datetime
import re
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DataProfile, sanitize_json_value
from intelligence.profiler import DataProfiler


@dataclass
class ColumnSemanticEvidence:
    """Structured semantic classification evidence for a single dataset column.

    Attributes:
        column_name: Name of the column.
        candidate_role: Inferred candidate semantic role (MEASURE, DIMENSION, DATETIME, IDENTIFIER, UNKNOWN).
        confidence: Deterministic confidence score from 0.0 to 1.0.
        confidence_level: Human-readable confidence category ("HIGH", "MEDIUM", "LOW", "NONE").
        evidence: List of deterministic evidence statements explaining why the candidate role was chosen.
    """

    column_name: str
    candidate_role: ColumnRole
    confidence: float
    confidence_level: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert semantic evidence to a JSON-serializable dictionary."""
        return {
            "column_name": self.column_name,
            "candidate_role": (
                self.candidate_role.value
                if isinstance(self.candidate_role, Enum)
                else str(self.candidate_role)
            ),
            "confidence": round(float(self.confidence), 2),
            "confidence_level": self.confidence_level,
            "evidence": self.evidence,
        }


@dataclass
class DatasetSemanticProfile:
    """Container holding rule-based semantic classification results for all columns in a dataset."""

    dataset_id: str
    column_evidences: Dict[str, ColumnSemanticEvidence] = field(default_factory=dict)
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def get_evidence(self, column_name: str) -> Optional[ColumnSemanticEvidence]:
        """Look up semantic evidence by column name."""
        return self.column_evidences.get(column_name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataset semantic profile to a JSON-serializable dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "generated_at": sanitize_json_value(self.generated_at),
            "column_evidences": {k: v.to_dict() for k, v in self.column_evidences.items()},
        }


class SemanticAnalyzer:
    """Deterministic, read-only rule-based engine for preliminary column semantic role classification."""

    # Token patterns for naming evidence
    ID_TOKENS = {"id", "guid", "uuid", "key", "code", "pk", "fk", "num", "number"}
    MEASURE_TOKENS = {
        "amount", "revenue", "sales", "price", "cost", "qty", "quantity", "val", "value",
        "count", "score", "total", "subtotal", "tax", "fee", "rate", "pct", "percentage",
        "weight", "height", "depth", "distance", "length", "margin", "profit", "discount",
        "balance", "age", "unit", "units", "volume"
    }
    DATE_TOKENS = {"date", "time", "timestamp", "dt", "datetime", "created_at", "updated_at", "dob"}
    TEMPORAL_PART_TOKENS = {"month", "day", "quarter", "qtr", "weekday", "dayofweek", "day_of_week"}
    DIMENSION_TOKENS = {
        "name", "category", "type", "kind", "class", "group", "status", "state", "city",
        "country", "region", "segment", "dept", "department", "brand", "model", "gender",
        "genre", "level", "tier"
    }
    BOOLEAN_PREFIXES = ("is_", "has_", "can_", "should_", "flag_")
    BOOLEAN_EXACT = {"active", "enabled", "deleted", "is_active", "has_insurance", "deceased"}

    CURRENCY_REGEX = re.compile(
        r"^\s*\(?[-+]?\s*[$€£¥₹]\s*[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?\s*$|"
        r"^\s*\(?[-+]?\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*[$€£¥₹]\)?\s*$|"
        r"^\s*\(?[-+]?\s*[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|INR|JPY|CAD|AUD)\b\)?\s*$",
        re.IGNORECASE,
    )
    PERCENT_REGEX = re.compile(r"^\s*[-+]?\s*\d+(?:\.\d+)?\s*%\s*$")
    UUID_REGEX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    CODE_ID_REGEX = re.compile(r"^[A-Za-z]{1,8}[-_#][0-9A-Za-z]{1,16}$")

    def _inspect_sample_patterns(self, series: Optional[pd.Series], sample_size: int = 50) -> Dict[str, Any]:
        """Inspect non-null sample string representations for currency, percentage, UUID, and code patterns."""
        if series is None or len(series) == 0:
            return {
                "currency_ratio": 0.0,
                "percentage_ratio": 0.0,
                "id_code_ratio": 0.0,
                "is_boolean_vals": False,
                "sample_values": [],
            }
        non_null = series.dropna()
        if len(non_null) == 0:
            return {
                "currency_ratio": 0.0,
                "percentage_ratio": 0.0,
                "id_code_ratio": 0.0,
                "is_boolean_vals": False,
                "sample_values": [],
            }
        sample_str = [
            str(x).strip()
            for x in non_null.head(sample_size)
            if str(x).strip() and str(x).strip().lower() not in {"nan", "none", "null", ""}
        ]
        if not sample_str:
            return {
                "currency_ratio": 0.0,
                "percentage_ratio": 0.0,
                "id_code_ratio": 0.0,
                "is_boolean_vals": False,
                "sample_values": [],
            }
        n = len(sample_str)
        cur_cnt = sum(1 for s in sample_str if self.CURRENCY_REGEX.match(s))
        pct_cnt = sum(1 for s in sample_str if self.PERCENT_REGEX.match(s))
        id_cnt = sum(1 for s in sample_str if self.UUID_REGEX.match(s) or self.CODE_ID_REGEX.match(s))

        bool_set = {"true", "false", "t", "f", "yes", "no", "y", "n"}
        is_bool = (
            non_null.nunique(dropna=True) <= 2
            and all(s.lower() in bool_set for s in sample_str)
        )
        return {
            "currency_ratio": cur_cnt / n,
            "percentage_ratio": pct_cnt / n,
            "id_code_ratio": id_cnt / n,
            "is_boolean_vals": is_bool,
            "sample_values": sample_str,
        }

    def analyze(
        self,
        canonical: CanonicalDataset,
        profile: Optional[DataProfile] = None,
        apply_roles: bool = False,
    ) -> DatasetSemanticProfile:
        """Analyze a CanonicalDataset and produce a DatasetSemanticProfile.

        This method is read-only regarding dataframe content and will never mutate the underlying canonical.data.

        Args:
            canonical: Target CanonicalDataset.
            profile: Existing DataProfile (if None, a profile will be computed on the fly).
            apply_roles: If True, updates column.semantic_role in canonical.metadata.schema with candidate roles.

        Returns:
            DatasetSemanticProfile containing ColumnSemanticEvidence per column.
        """
        if profile is None:
            if canonical.profile is not None:
                profile = canonical.profile
            else:
                profile = DataProfiler().profile(canonical, attach=False)

        dataset_id = canonical.metadata.dataset_id
        row_cnt = profile.dataset_summary.get("row_count", len(canonical.data))
        evidences: Dict[str, ColumnSemanticEvidence] = {}

        for col_meta in canonical.metadata.schema:
            col_name = col_meta.original_name
            ev = self._classify_column(col_meta, profile, row_cnt, canonical.data)
            evidences[col_name] = ev

            if apply_roles:
                col_meta.semantic_role = ev.candidate_role

        semantic_profile = DatasetSemanticProfile(
            dataset_id=dataset_id, column_evidences=evidences
        )

        canonical.add_audit_entry(
            action="SEMANTIC_ANALYSIS_COMPLETED",
            details={
                "dataset_id": dataset_id,
                "column_count": len(evidences),
                "roles_summary": {
                    role.value: sum(1 for e in evidences.values() if e.candidate_role == role)
                    for role in ColumnRole
                },
            },
        )

        return semantic_profile

    def _sample_datetime_parse_ratio(
        self, series: Optional[pd.Series], sample_size: int = 50
    ) -> float:
        """Sample up to sample_size non-null values and compute the fraction that parse as datetime."""
        if series is None or len(series) == 0:
            return 0.0
        non_null = series.dropna()
        if len(non_null) == 0:
            return 0.0
        sample = non_null.head(sample_size)
        success_count = 0
        import warnings

        for val in sample:
            val_str = str(val).strip()
            if not val_str:
                continue
            # Pure short digits like "123" are not datetimes
            if val_str.isdigit() and len(val_str) < 4:
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    pd.to_datetime(val_str, errors="raise")
                success_count += 1
            except Exception:
                pass
        return float(success_count / len(sample)) if len(sample) > 0 else 0.0

    def _classify_column(
        self,
        col_meta: ColumnMetadata,
        profile: DataProfile,
        row_cnt: int,
        df: pd.DataFrame,
    ) -> ColumnSemanticEvidence:
        col_name = col_meta.original_name
        col_stats = profile.column_statistics.get(col_name, {})
        evidence_statements: List[str] = []

        dtype_str = col_meta.detected_datatype.lower()
        non_null_cnt = col_stats.get("non_null_count", 0)
        null_cnt = col_stats.get("null_count", 0)
        null_pct = col_stats.get("null_percentage", 0.0)
        distinct_cnt = col_stats.get("distinct_count", 0)
        is_uniq = col_stats.get("is_unique", False)
        is_const = col_stats.get("is_constant", False)
        is_all_null = col_stats.get("is_all_null", False)
        cardinality_ratio = (distinct_cnt / non_null_cnt) if non_null_cnt > 0 else 0.0
        series = df[col_name] if col_name in df.columns else None

        # Data-driven metric summaries
        evidence_statements.append(f"cardinality ratio: {distinct_cnt}/{non_null_cnt} ({cardinality_ratio:.2%})")
        evidence_statements.append(f"uniqueness: {'unique (100%)' if is_uniq else f'non-unique ({distinct_cnt} distinct)'}")
        if null_pct > 0:
            evidence_statements.append(f"null ratio: {null_pct:.1f}% ({null_cnt}/{row_cnt} missing values)")

        # Name Token Extraction & Disambiguation Check
        stripped_name = col_name.strip()
        if re.search(r"\.\d+$", stripped_name):
            stripped_name = re.sub(r"\.\d+$", "", stripped_name)
            evidence_statements.append("header contains pandas duplicate-disambiguation suffix (.1, .2)")

        clean_name = stripped_name.lower()
        # Extract tokens from delimiters AND CamelCase/PascalCase boundaries
        camel_words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|\d+", stripped_name)
        tokens = set()
        for w in camel_words:
            tokens.update(re.split(r"[_\s#\-]+", w.lower()))
        tokens.update(re.split(r"[_\s#\-]+", clean_name))
        tokens = {t for t in tokens if t}

        has_id_token = (
            any(t in self.ID_TOKENS for t in tokens)
            or clean_name.endswith(("_id", "_guid", "_uuid", "_code", "_key", "_pk", "_fk"))
            or (clean_name.endswith("id") and len(clean_name) > 2 and clean_name not in {"grid", "solid", "fluid", "acid", "hybrid", "pyramid", "squid", "lipid"})
            or clean_name in self.ID_TOKENS
        )
        has_measure_token = any(t in self.MEASURE_TOKENS for t in tokens)
        has_date_token = any(t in self.DATE_TOKENS for t in tokens)
        has_temporal_part_token = any(t in self.TEMPORAL_PART_TOKENS for t in tokens)
        has_dimension_token = any(t in self.DIMENSION_TOKENS for t in tokens)
        has_boolean_token = clean_name.startswith(self.BOOLEAN_PREFIXES) or clean_name in self.BOOLEAN_EXACT

        # Signal 1: All-Null / Empty Column
        if is_all_null or row_cnt == 0:
            evidence_statements.append(f"column contains 100% missing values (null count: {null_cnt})")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.UNKNOWN,
                confidence=0.0,
                confidence_level="NONE",
                evidence=evidence_statements,
            )

        # Inspect data sample value patterns (currency, percentages, IDs, booleans)
        patterns = self._inspect_sample_patterns(series)

        # Signal 2: Boolean Datatype or Boolean Value Characteristics
        is_bool_dtype = "bool" in dtype_str or (series is not None and pd.api.types.is_bool_dtype(series))
        if is_bool_dtype:
            evidence_statements.append(f"boolean datatype ({dtype_str})")
            if has_boolean_token:
                evidence_statements.append(f"boolean naming pattern ('{clean_name}')")
            evidence_statements.append("binary true/false flags serve as categorical dimensions")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.90,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        if patterns["is_boolean_vals"]:
            evidence_statements.append("data-driven boolean values detected in sample (true/false/yes/no flags)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.88,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        if distinct_cnt <= 2 and non_null_cnt > 0 and has_boolean_token:
            evidence_statements.append(f"low distinct count ({distinct_cnt}) with boolean naming pattern ('{clean_name}')")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.85,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 3: Native Datetime
        if "datetime" in dtype_str:
            evidence_statements.append(f"native pandas datetime dtype ({dtype_str})")
            if has_date_token:
                evidence_statements.append(f"column name contains date token: '{clean_name}'")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DATETIME,
                confidence=0.95,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 4: Content-based String/Object Datetime Detection
        is_text_or_obj = "object" in dtype_str or "str" in dtype_str or "category" in dtype_str
        parse_ratio = self._sample_datetime_parse_ratio(series) if (is_text_or_obj and non_null_cnt > 0) else 0.0

        if parse_ratio >= 0.8:
            evidence_statements.append(f"string/object datatype ({dtype_str}) with content-based datetime pattern")
            evidence_statements.append(f"high sample datetime parse success ratio ({parse_ratio:.2f})")
            if has_date_token:
                evidence_statements.append(f"column name contains date token: '{clean_name}'")
            evidence_statements.append("candidate datetime (read-only: no aggressive type conversion applied)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DATETIME,
                confidence=0.92 if has_date_token else 0.88,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 5: Numeric vs Integer-Like Profiling
        is_numeric = "int" in dtype_str or "float" in dtype_str or (
            series is not None and pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        )
        is_integer_like = False
        is_continuous_float = False
        if is_numeric and non_null_cnt > 0 and series is not None:
            try:
                num_s = pd.to_numeric(series.dropna(), errors="coerce").dropna()
                if len(num_s) > 0:
                    if ((num_s % 1) == 0).all():
                        is_integer_like = True
                    else:
                        is_continuous_float = True
            except Exception:
                pass
        elif "int" in dtype_str:
            is_integer_like = True
        elif "float" in dtype_str:
            is_continuous_float = True

        is_integer = is_integer_like or ("int" in dtype_str)
        unique_ratio = cardinality_ratio

        # Signal 6: Dedicated Year-Range Signal (e.g. 1900-2100)
        # Evaluated before constant check so single-year calendar tables (e.g. Calendar.csv Year 2024)
        # are properly classified as DATETIME rather than UNKNOWN.
        if is_numeric and non_null_cnt > 0 and not has_measure_token and is_integer:
            min_val = col_stats.get("min")
            max_val = col_stats.get("max")
            if min_val is not None and max_val is not None:
                try:
                    min_f = float(min_val)
                    max_f = float(max_val)
                    if 1900 <= min_f and max_f <= 2100:
                        evidence_statements.append("numeric values fall entirely within calendar year range [1900, 2100]")
                        evidence_statements.append(f"detected year values from {int(min_f)} to {int(max_f)}")
                        if "year" in clean_name or has_date_token:
                            evidence_statements.append(f"column name indicates temporal year: '{clean_name}'")
                            return ColumnSemanticEvidence(
                                column_name=col_name,
                                candidate_role=ColumnRole.DATETIME,
                                confidence=0.92,
                                confidence_level="HIGH",
                                evidence=evidence_statements,
                            )
                        elif distinct_cnt > 1:
                            evidence_statements.append("numeric year distribution without date naming token")
                            return ColumnSemanticEvidence(
                                column_name=col_name,
                                candidate_role=ColumnRole.DATETIME,
                                confidence=0.85,
                                confidence_level="HIGH",
                                evidence=evidence_statements,
                            )
                except Exception:
                    pass

        # Signal 7: Dedicated Temporal Calendar Parts (Month 1-12, Day 1-31, Quarter 1-4)
        if is_numeric and has_temporal_part_token and not has_measure_token:
            min_val = col_stats.get("min")
            max_val = col_stats.get("max")
            if min_val is not None and max_val is not None:
                try:
                    min_f = float(min_val)
                    max_f = float(max_val)
                    if "month" in tokens and 1 <= min_f and max_f <= 12:
                        evidence_statements.append("numeric calendar component (month 1-12 represents temporal dimension, not an aggregatable measure)")
                        return ColumnSemanticEvidence(
                            column_name=col_name,
                            candidate_role=ColumnRole.DIMENSION,
                            confidence=0.88,
                            confidence_level="HIGH",
                            evidence=evidence_statements,
                        )
                    if "day" in tokens and 1 <= min_f and max_f <= 31:
                        evidence_statements.append("numeric calendar component (day 1-31 represents temporal dimension, not an aggregatable measure)")
                        return ColumnSemanticEvidence(
                            column_name=col_name,
                            candidate_role=ColumnRole.DIMENSION,
                            confidence=0.85,
                            confidence_level="HIGH",
                            evidence=evidence_statements,
                        )
                    if ("quarter" in tokens or "qtr" in tokens) and 1 <= min_f and max_f <= 4:
                        evidence_statements.append("numeric calendar component (quarter 1-4 represents temporal dimension, not an aggregatable measure)")
                        return ColumnSemanticEvidence(
                            column_name=col_name,
                            candidate_role=ColumnRole.DIMENSION,
                            confidence=0.88,
                            confidence_level="HIGH",
                            evidence=evidence_statements,
                        )
                except Exception:
                    pass

        # Signal 8: Constant Column (insufficient variation to serve as measure or identifier)
        if is_const:
            evidence_statements.append(f"constant column containing only 1 distinct non-null value ('{col_stats.get('min')}')")
            evidence_statements.append("insufficient variation to qualify as a measure")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.UNKNOWN,
                confidence=0.30,
                confidence_level="LOW",
                evidence=evidence_statements,
            )

        # Signal 9: Formatted Currency or Percentage Patterns (even if stored as string/object)
        if patterns["currency_ratio"] >= 0.8:
            evidence_statements.append(f"value-pattern evidence: {patterns['currency_ratio']:.0%} of sample values match formatted currency pattern")
            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=0.92,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        if patterns["percentage_ratio"] >= 0.8:
            evidence_statements.append(f"value-pattern evidence: {patterns['percentage_ratio']:.0%} of sample values match percentage pattern")
            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=0.90,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 10: Value-pattern UUID or Code Identifier
        if patterns["id_code_ratio"] >= 0.8 and (is_uniq or cardinality_ratio >= 0.85):
            evidence_statements.append(f"value-pattern evidence: structured identifier/UUID pattern detected ({patterns['id_code_ratio']:.0%} match, cardinality ratio {cardinality_ratio:.2f})")
            if has_id_token:
                evidence_statements.append(f"identifier naming pattern ('{clean_name}')")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.92,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 11: Conflict Resolution — IDENTIFIER
        # Part A — Uniqueness-based: high unique ratio is a strong identifier signal.
        #   Requires: integer dtype (not continuous float) OR explicit id naming token.
        #   If dtype is continuous float with no identifier name token, do NOT assign IDENTIFIER.
        has_id_signal = has_id_token or is_integer

        if (
            (is_uniq or unique_ratio >= 0.95)
            and has_id_signal
            and not is_continuous_float
            and not has_date_token
            and not has_measure_token  # explicit measure naming overrides uniqueness signal
        ):
            evidence_statements.append(f"high uniqueness ratio ({distinct_cnt}/{non_null_cnt} = {unique_ratio:.2f})")
            if has_id_token:
                evidence_statements.append(f"identifier naming pattern ('{clean_name}')")
            if is_integer:
                evidence_statements.append("numeric identifier disambiguation (unique key overrides numeric dtype)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.95 if has_id_token else 0.75,  # no id token → lower certainty
                confidence_level="HIGH" if has_id_token else "MEDIUM",
                evidence=evidence_statements,
            )

        # Part B — Name-based repeated IDs (Foreign keys)
        if has_id_token and distinct_cnt > 1 and not has_measure_token and not has_date_token:
            evidence_statements.append(f"identifier naming pattern ('{clean_name}')")
            evidence_statements.append(f"distinct count: {distinct_cnt}")
            if is_numeric:
                evidence_statements.append("numeric key/code pattern (id token overrides numeric dtype)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.88,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 12: Continuous Float MEASURE
        if is_numeric and is_continuous_float and distinct_cnt > 1 and not has_id_token:
            evidence_statements.append(f"continuous floating-point numeric distribution (distinct: {distinct_cnt}, min: {col_stats.get('min')}, max: {col_stats.get('max')})")
            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=0.92 if has_measure_token else 0.85,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 13: Numeric MEASURE / Low-cardinality DIMENSION
        if is_numeric:
            evidence_statements.append(f"numeric datatype ({dtype_str})")
            evidence_statements.append(f"distinct count: {distinct_cnt}")
            if not is_uniq:
                evidence_statements.append("non-unique numeric distribution")

            # Low-cardinality discrete numeric check (ratings 1..5, status 1..4)
            if distinct_cnt <= 5 and not has_measure_token:
                evidence_statements.append(f"low distinct count ({distinct_cnt}) without explicit measure naming")
                evidence_statements.append("low-cardinality numeric values represent discrete categories or scale ratings")
                if has_dimension_token:
                    evidence_statements.append(f"dimension naming pattern ('{clean_name}')")
                return ColumnSemanticEvidence(
                    column_name=col_name,
                    candidate_role=ColumnRole.DIMENSION,
                    confidence=0.70,
                    confidence_level="MEDIUM",
                    evidence=evidence_statements,
                )

            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")
                return ColumnSemanticEvidence(
                    column_name=col_name,
                    candidate_role=ColumnRole.MEASURE,
                    confidence=0.92,
                    confidence_level="HIGH",
                    evidence=evidence_statements,
                )

            if distinct_cnt > 5 and not has_id_token:
                return ColumnSemanticEvidence(
                    column_name=col_name,
                    candidate_role=ColumnRole.MEASURE,
                    confidence=0.82,
                    confidence_level="HIGH",
                    evidence=evidence_statements,
                )

        # Signal 14: String/Object with date token fallback
        if is_text_or_obj and has_date_token:
            evidence_statements.append(f"string/object datatype ({dtype_str}) with date naming token ('{clean_name}')")
            evidence_statements.append("candidate datetime (read-only: no aggressive type conversion applied)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DATETIME,
                confidence=0.65,
                confidence_level="MEDIUM",
                evidence=evidence_statements,
            )

        # Signal 15: DIMENSION Candidate (String/Object or Categorical)
        if is_text_or_obj:
            evidence_statements.append(f"text/categorical datatype ({dtype_str})")
            evidence_statements.append(f"distinct count: {distinct_cnt} out of {row_cnt} rows")

            if has_dimension_token:
                evidence_statements.append(f"dimension naming pattern ('{clean_name}')")

            if distinct_cnt > 0.9 * non_null_cnt and non_null_cnt > 5 and not has_dimension_token:
                evidence_statements.append("very high cardinality text (could be free-form description or narrative)")
                return ColumnSemanticEvidence(
                    column_name=col_name,
                    candidate_role=ColumnRole.DIMENSION,
                    confidence=0.60,
                    confidence_level="MEDIUM",
                    evidence=evidence_statements,
                )

            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.88 if distinct_cnt < row_cnt else 0.70,
                confidence_level="HIGH" if distinct_cnt < row_cnt else "MEDIUM",
                evidence=evidence_statements,
            )

        # Signal 16: Ambiguous Column -> UNKNOWN
        evidence_statements.append(f"ambiguous signals (datatype: {dtype_str}, distinct count: {distinct_cnt})")
        evidence_statements.append("insufficient evidence to reliably assign a specific semantic role")
        return ColumnSemanticEvidence(
            column_name=col_name,
            candidate_role=ColumnRole.UNKNOWN,
            confidence=0.40,
            confidence_level="LOW",
            evidence=evidence_statements,
        )


def analyze_semantics(
    canonical: CanonicalDataset,
    profile: Optional[DataProfile] = None,
    apply_roles: bool = False,
) -> DatasetSemanticProfile:
    """Convenience function to analyze semantic column roles of a CanonicalDataset."""
    return SemanticAnalyzer().analyze(canonical=canonical, profile=profile, apply_roles=apply_roles)
