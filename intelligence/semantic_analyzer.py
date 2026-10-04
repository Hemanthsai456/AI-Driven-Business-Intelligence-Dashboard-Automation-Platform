"""Deterministic rule-based semantic role classification engine."""

from dataclasses import dataclass, field
from enum import Enum
import datetime
import re
from typing import Any, Dict, List, Optional, Set, Tuple
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
        sub_role: Optional sub-role classification ("FOREIGN_KEY", "PRIMARY_KEY", "DERIVED", etc.).
        derived_parts: If DERIVED, names of contributing columns.
        derived_op: If DERIVED, arithmetic operation ("product", "ratio", "sum").
        aggregation_default: Default aggregation operator ("SUM", "AVG", "COUNT", "MEDIAN").
        aggregation_category: Aggregation category ("ADDITIVE", "INTENSIVE", "SCORE", "DURATION", "RATE", "COUNT").
        conflicts: List of conflicting semantic observations considered during classification.
    """

    column_name: str
    candidate_role: ColumnRole
    confidence: float
    confidence_level: str
    evidence: List[str] = field(default_factory=list)
    sub_role: Optional[str] = None
    derived_parts: Optional[List[str]] = None
    derived_op: Optional[str] = None
    aggregation_default: Optional[str] = None
    aggregation_category: Optional[str] = None
    conflicts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert semantic evidence to a JSON-serializable dictionary."""
        d: Dict[str, Any] = {
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
        if self.sub_role is not None:
            d["sub_role"] = self.sub_role
        if self.derived_parts is not None:
            d["derived_parts"] = self.derived_parts
        if self.derived_op is not None:
            d["derived_op"] = self.derived_op
        if self.aggregation_default is not None:
            d["aggregation_default"] = self.aggregation_default
        if self.aggregation_category is not None:
            d["aggregation_category"] = self.aggregation_category
        if self.conflicts:
            d["conflicts"] = self.conflicts
        return d


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
    ID_TOKENS = {"id", "guid", "uuid", "key", "code", "pk", "fk", "num", "number", "identifier"}

    # Categorized Measure Tokens for aggregation and measure detection
    INTENSIVE_TOKENS = {
        "temp", "temperature", "pressure", "humidity", "speed", "velocity", "voltage",
        "current", "power", "vibration", "frequency", "density", "viscosity", "altitude",
        "salary", "wage", "pay", "compensation", "unitprice", "unit_price", "price_per", "cost_per",
    }
    DURATION_TOKENS = {
        "delivery_time", "length_of_stay", "duration", "latency", "delay", "wait_time",
        "transit_time", "response_time", "stay", "elapsed", "runtime", "period", "age", "tenure",
    }
    SCORE_TOKENS = {
        "score", "marks", "mark", "gpa", "performance", "performance_score",
        "satisfaction", "points", "accuracy", "loss",
    }
    RATE_TOKENS = {
        "rate", "ratio", "pct", "percent", "percentage", "margin", "discount", "proportion",
        "share", "yield", "fraction",
    }
    ADDITIVE_TOKENS = {
        "sales", "revenue", "profit", "amount", "total", "subtotal", "cost", "expense",
        "spend", "tax", "fee", "budget", "balance",
    }
    COUNT_TOKENS = {
        "quantity", "qty", "units", "volume", "count", "headcount", "inventory", "stock",
        "orders", "transactions", "items", "rows", "records",
    }

    MEASURE_TOKENS = (
        INTENSIVE_TOKENS
        | DURATION_TOKENS
        | SCORE_TOKENS
        | RATE_TOKENS
        | ADDITIVE_TOKENS
        | COUNT_TOKENS
        | {
            "price", "val", "value", "weight", "height", "depth", "distance", "length",
            "width", "size", "reading", "readings", "measurement", "metric", "income",
        }
    )

    DATE_TOKENS = {"date", "time", "timestamp", "dt", "datetime", "created_at", "updated_at", "dob"}
    TEMPORAL_PART_TOKENS = {"month", "day", "quarter", "qtr", "weekday", "dayofweek", "day_of_week"}
    DIMENSION_TOKENS = {
        "name", "category", "type", "kind", "class", "group", "status", "state", "city",
        "country", "region", "segment", "dept", "department", "brand", "model", "gender",
        "genre", "level", "tier", "rating", "grade", "rank"
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

    def __init__(
        self,
        foreign_key_threshold: float = 0.90,
        derived_tolerance: float = 1e-3,
    ) -> None:
        self.foreign_key_threshold = foreign_key_threshold
        self.derived_tolerance = derived_tolerance

    def _infer_measure_aggregation(
        self,
        clean_name: str,
        tokens: Set[str],
        col_stats: Dict[str, Any],
        is_continuous_float: bool,
    ) -> Tuple[str, str, List[str]]:
        """Infer aggregation category (ADDITIVE, INTENSIVE, DURATION, SCORE, RATE, COUNT) and default agg (SUM vs AVG)."""
        ev_notes: List[str] = []

        # 1. Rate / Percentage / Ratio
        if (
            any(t in tokens for t in self.RATE_TOKENS)
            or clean_name.endswith(("_pct", "_percent", "_percentage", "_rate", "_ratio", "_margin", "_discount", "_share"))
        ):
            ev_notes.append(f"measure semantics: rate/percentage indicator in '{clean_name}' suggests intensive average aggregation (AVG)")
            return "RATE", "AVG", ev_notes

        # 2. Durations / Time Spans / Latency
        if (
            any(t in tokens for t in self.DURATION_TOKENS)
            or clean_name.endswith(("_time", "_duration", "_latency", "_delay", "_stay", "_period", "_age", "_tenure"))
        ):
            ev_notes.append(f"measure semantics: duration/time-span indicator in '{clean_name}' suggests duration average aggregation (AVG)")
            return "DURATION", "AVG", ev_notes

        # 3. Scores / Ratings / Performance / Grades
        if (
            any(t in tokens for t in self.SCORE_TOKENS)
            or clean_name.endswith(("_score", "_rating", "_grade", "_gpa", "_marks", "_mark", "_points", "_rank"))
        ):
            ev_notes.append(f"measure semantics: score/rating scale indicator in '{clean_name}' suggests central-tendency aggregation (AVG)")
            return "SCORE", "AVG", ev_notes

        # 4. Intensive Physical Properties / Environmental States / Pay Rates
        if (
            any(t in tokens for t in self.INTENSIVE_TOKENS)
            or clean_name.endswith(("_temp", "_temperature", "_pressure", "_humidity", "_speed", "_velocity", "_voltage", "_salary", "_wage", "_pay"))
        ):
            ev_notes.append(f"measure semantics: intensive physical/rate measurement in '{clean_name}' suggests intensive aggregation (AVG)")
            return "INTENSIVE", "AVG", ev_notes

        # 5. Discrete Counts / Quantities / Items
        if any(t in tokens for t in self.COUNT_TOKENS) or clean_name.endswith(("_qty", "_count", "_units", "_volume", "_items")):
            ev_notes.append(f"measure semantics: discrete count/quantity indicator in '{clean_name}' suggests additive aggregation (SUM)")
            return "COUNT", "SUM", ev_notes

        # 6. Additive Totals / Monetary Totals
        if any(t in tokens for t in self.ADDITIVE_TOKENS) or clean_name.endswith(("_sales", "_revenue", "_profit", "_amount", "_cost", "_total", "_spend", "_expense", "_tax", "_fee", "_budget", "_balance")):
            ev_notes.append(f"measure semantics: additive monetary/volume indicator in '{clean_name}' suggests additive aggregation (SUM)")
            return "ADDITIVE", "SUM", ev_notes

        # 7. Distribution characteristics fallback:
        if is_continuous_float:
            min_v = col_stats.get("min")
            if min_v is not None and float(min_v) < 0:
                ev_notes.append("continuous float measure with negative values suggests intensive aggregation (AVG)")
                return "INTENSIVE", "AVG", ev_notes
            ev_notes.append("continuous floating-point measurement defaults to intensive aggregation (AVG)")
            return "INTENSIVE", "AVG", ev_notes

        # Default for general numeric measure (e.g. integer amounts without specific intensive tokens)
        ev_notes.append("general numeric measure defaults to additive aggregation (SUM)")
        return "ADDITIVE", "SUM", ev_notes

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

    def _detect_derived_measures(
        self,
        evidences: Dict[str, ColumnSemanticEvidence],
        df: pd.DataFrame,
    ) -> None:
        """Detect if a numeric measure is an arithmetic combination (product, ratio, sum) of others."""
        if df is None or df.empty:
            return

        numeric_measures = [
            col for col, ev in evidences.items()
            if ev.candidate_role == ColumnRole.MEASURE and col in df.columns and pd.api.types.is_numeric_dtype(df[col])
        ]
        if len(numeric_measures) < 3:
            return

        # Phase 1: Products and Sums (composites)
        for m in numeric_measures:
            sm_orig = pd.to_numeric(df[m], errors="coerce")
            found = False
            for i in range(len(numeric_measures)):
                if found:
                    break
                a = numeric_measures[i]
                if a == m:
                    continue
                sa_orig = pd.to_numeric(df[a], errors="coerce")
                for j in range(i, len(numeric_measures)):
                    b = numeric_measures[j]
                    if b == m:
                        continue
                    sb_orig = pd.to_numeric(df[b], errors="coerce")

                    valid_mask = sm_orig.notna() & sa_orig.notna() & sb_orig.notna()
                    if valid_mask.sum() < 5:
                        continue
                    sm = sm_orig[valid_mask]
                    sa = sa_orig[valid_mask]
                    sb = sb_orig[valid_mask]

                    # 1. Product: m ≈ a * b
                    prod = sa * sb
                    if np.allclose(sm, prod, rtol=self.derived_tolerance, atol=1e-4):
                        evidences[m].sub_role = "DERIVED"
                        evidences[m].derived_parts = [a, b]
                        evidences[m].derived_op = "product"
                        evidences[m].evidence.append(
                            f"derived measure: {m} ≈ {a} * {b} (product arithmetic relationship)"
                        )
                        found = True
                        break

                    # 2. Sum: m ≈ a + b
                    total = sa + sb
                    if np.allclose(sm, total, rtol=self.derived_tolerance, atol=1e-4):
                        evidences[m].sub_role = "DERIVED"
                        evidences[m].derived_parts = [a, b]
                        evidences[m].derived_op = "sum"
                        evidences[m].evidence.append(
                            f"derived measure: {m} ≈ {a} + {b} (sum arithmetic relationship)"
                        )
                        found = True
                        break

        # Phase 2: Explicit ratios (only for measures not already involved as factors of derived products)
        for m in numeric_measures:
            if evidences[m].sub_role == "DERIVED":
                continue
            # If m is a factor of an already-detected derived product/sum, don't mark m as ratio
            is_factor = any(
                ev.sub_role == "DERIVED" and ev.derived_parts and m in ev.derived_parts
                for ev in evidences.values()
            )
            if is_factor:
                continue

            sm_orig = pd.to_numeric(df[m], errors="coerce")
            for a in numeric_measures:
                if a == m:
                    continue
                sa_orig = pd.to_numeric(df[a], errors="coerce")
                for b in numeric_measures:
                    if b in (m, a):
                        continue
                    sb_orig = pd.to_numeric(df[b], errors="coerce")
                    valid_mask = sm_orig.notna() & sa_orig.notna() & sb_orig.notna()
                    if valid_mask.sum() < 5:
                        continue
                    sm = sm_orig[valid_mask]
                    sa = sa_orig[valid_mask]
                    sb = sb_orig[valid_mask]

                    non_zero = sb != 0
                    if non_zero.sum() >= 5:
                        ratio = sa[non_zero] / sb[non_zero]
                        if np.allclose(sm[non_zero], ratio, rtol=self.derived_tolerance, atol=1e-4):
                            evidences[m].sub_role = "DERIVED"
                            evidences[m].derived_parts = [a, b]
                            evidences[m].derived_op = "ratio"
                            evidences[m].evidence.append(
                                f"derived measure: {m} ≈ {a} / {b} (ratio arithmetic relationship)"
                            )
                            break
                if evidences[m].sub_role == "DERIVED":
                    break

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

        # Detect derived measures across numeric measures
        self._detect_derived_measures(evidences, canonical.data)

        if apply_roles:
            for col_meta in canonical.metadata.schema:
                col_name = col_meta.original_name
                if col_name in evidences:
                    ev = evidences[col_name]
                    col_meta.semantic_role = ev.candidate_role
                    col_meta.sub_role = ev.sub_role

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
            # Pure text with no digits (e.g. month names "January", weekday "Monday") are categorical, not timestamps
            if not any(c.isdigit() for c in val_str):
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
        conflicts: List[str] = []

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
            or clean_name.endswith(("_id", "_guid", "_uuid", "_code", "_key", "_pk", "_fk", "_num", "_no"))
            or (clean_name.endswith("id") and len(clean_name) > 2 and clean_name not in {"grid", "solid", "fluid", "acid", "hybrid", "pyramid", "squid", "lipid", "valid", "rapid"})
            or clean_name in self.ID_TOKENS
        )
        has_measure_token = (
            any(t in self.MEASURE_TOKENS for t in tokens)
            or any(t in clean_name for t in self.MEASURE_TOKENS)
        )
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
                conflicts=conflicts,
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
                conflicts=conflicts,
            )

        if patterns["is_boolean_vals"]:
            evidence_statements.append("data-driven boolean values detected in sample (true/false/yes/no flags)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.88,
                confidence_level="HIGH",
                evidence=evidence_statements,
                conflicts=conflicts,
            )

        if distinct_cnt <= 2 and non_null_cnt > 0 and has_boolean_token:
            evidence_statements.append(f"low distinct count ({distinct_cnt}) with boolean naming pattern ('{clean_name}')")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.85,
                confidence_level="HIGH",
                evidence=evidence_statements,
                conflicts=conflicts,
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
                conflicts=conflicts,
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
                conflicts=conflicts,
            )

        # Signal 5: Numeric vs Integer-Like Profiling
        is_numeric = "int" in dtype_str or "float" in dtype_str or (
            series is not None and pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        )
        is_integer_like = False
        is_continuous_float = False
        is_sequential_index = False

        if is_numeric and non_null_cnt > 0 and series is not None:
            try:
                num_s = pd.to_numeric(series.dropna(), errors="coerce").dropna()
                if len(num_s) > 0:
                    if ((num_s % 1) == 0).all():
                        is_integer_like = True
                        if len(num_s) >= 3:
                            sorted_uniq = np.sort(num_s.unique())
                            if len(sorted_uniq) == non_null_cnt:
                                diffs = np.diff(sorted_uniq)
                                if np.all(diffs == 1):
                                    is_sequential_index = True
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
                                conflicts=conflicts,
                            )
                        elif distinct_cnt > 1:
                            evidence_statements.append("numeric year distribution without date naming token")
                            return ColumnSemanticEvidence(
                                column_name=col_name,
                                candidate_role=ColumnRole.DATETIME,
                                confidence=0.85,
                                confidence_level="HIGH",
                                evidence=evidence_statements,
                                conflicts=conflicts,
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
                            conflicts=conflicts,
                        )
                    if "day" in tokens and 1 <= min_f and max_f <= 31:
                        evidence_statements.append("numeric calendar component (day 1-31 represents temporal dimension, not an aggregatable measure)")
                        return ColumnSemanticEvidence(
                            column_name=col_name,
                            candidate_role=ColumnRole.DIMENSION,
                            confidence=0.85,
                            confidence_level="HIGH",
                            evidence=evidence_statements,
                            conflicts=conflicts,
                        )
                    if ("quarter" in tokens or "qtr" in tokens) and 1 <= min_f and max_f <= 4:
                        evidence_statements.append("numeric calendar component (quarter 1-4 represents temporal dimension, not an aggregatable measure)")
                        return ColumnSemanticEvidence(
                            column_name=col_name,
                            candidate_role=ColumnRole.DIMENSION,
                            confidence=0.88,
                            confidence_level="HIGH",
                            evidence=evidence_statements,
                            conflicts=conflicts,
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
                conflicts=conflicts,
            )

        # Signal 9: Formatted Currency or Percentage Patterns (even if stored as string/object)
        if patterns["currency_ratio"] >= 0.8:
            evidence_statements.append(f"value-pattern evidence: {patterns['currency_ratio']:.0%} of sample values match formatted currency pattern")
            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")
            agg_cat, agg_def, agg_notes = self._infer_measure_aggregation(clean_name, tokens, col_stats, is_continuous_float)
            evidence_statements.extend(agg_notes)
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=0.92,
                confidence_level="HIGH",
                evidence=evidence_statements,
                aggregation_category=agg_cat,
                aggregation_default=agg_def,
                conflicts=conflicts,
            )

        if patterns["percentage_ratio"] >= 0.8:
            evidence_statements.append(f"value-pattern evidence: {patterns['percentage_ratio']:.0%} of sample values match percentage pattern")
            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")
            agg_cat, agg_def, agg_notes = self._infer_measure_aggregation(clean_name, tokens, col_stats, is_continuous_float)
            evidence_statements.extend(agg_notes)
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=0.90,
                confidence_level="HIGH",
                evidence=evidence_statements,
                aggregation_category=agg_cat,
                aggregation_default=agg_def,
                conflicts=conflicts,
            )

        # Signal 10: Value-pattern UUID or Code Identifier
        if patterns["id_code_ratio"] >= 0.8 and (is_uniq or cardinality_ratio >= 0.85):
            evidence_statements.append(f"value-pattern evidence: structured identifier/UUID pattern detected ({patterns['id_code_ratio']:.0%} match, cardinality ratio {cardinality_ratio:.2f})")
            if has_id_token:
                evidence_statements.append(f"identifier naming pattern ('{clean_name}')")
            is_fk = (cardinality_ratio < self.foreign_key_threshold) and (distinct_cnt < non_null_cnt)
            sub_role = "FOREIGN_KEY" if is_fk else ("PRIMARY_KEY" if (is_uniq or cardinality_ratio >= self.foreign_key_threshold) else None)
            if is_fk:
                evidence_statements.append(f"foreign key sub-role: repeated identifier values (cardinality ratio {cardinality_ratio:.2%} < {self.foreign_key_threshold:.0%})")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.92,
                confidence_level="HIGH",
                evidence=evidence_statements,
                sub_role=sub_role,
                conflicts=conflicts,
            )

        # Signal 11: IDENTIFIER Candidate
        # Case A — Explicit ID token (e.g. customer_id, store_id, product_id, sale_id, employee_id)
        if has_id_token and not has_measure_token and not has_date_token and distinct_cnt > 1:
            evidence_statements.append(f"identifier naming pattern ('{clean_name}')")
            evidence_statements.append(f"distinct count: {distinct_cnt}")
            if is_numeric:
                evidence_statements.append("numeric key/code pattern (id token overrides numeric dtype)")
            is_fk = (cardinality_ratio < self.foreign_key_threshold) and (distinct_cnt < non_null_cnt)
            sub_role = "FOREIGN_KEY" if is_fk else ("PRIMARY_KEY" if (is_uniq or cardinality_ratio >= self.foreign_key_threshold) else None)
            if is_fk:
                evidence_statements.append(f"foreign key sub-role: repeated identifier values (cardinality ratio {cardinality_ratio:.2%} < {self.foreign_key_threshold:.0%})")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.95 if (is_uniq or cardinality_ratio >= 0.90) else 0.88,
                confidence_level="HIGH",
                evidence=evidence_statements,
                sub_role=sub_role,
                conflicts=conflicts,
            )

        # Case B — Sequential Integer Index without measure token (e.g. row index 1..N or 10001..1000N)
        if is_sequential_index and not has_measure_token and not has_date_token:
            evidence_statements.append("dense sequential integer sequence (step=1) represents primary record index/key")
            evidence_statements.append(f"high uniqueness ratio ({distinct_cnt}/{non_null_cnt} = {unique_ratio:.2f})")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.90,
                confidence_level="HIGH",
                evidence=evidence_statements,
                sub_role="PRIMARY_KEY",
                conflicts=conflicts,
            )

        # Signal 12: Numeric MEASURE / Low-cardinality DIMENSION
        if is_numeric:
            evidence_statements.append(f"numeric datatype ({dtype_str})")
            evidence_statements.append(f"distinct count: {distinct_cnt}")

            # Low-cardinality discrete numeric check (ratings 1..5, status 1..4) without additive measure naming
            if distinct_cnt <= 5 and (not has_measure_token or has_dimension_token) and not is_continuous_float:
                evidence_statements.append(f"low distinct count ({distinct_cnt}) without explicit additive measure naming")
                evidence_statements.append("low-cardinality numeric values represent discrete categories or scale ratings")
                if has_dimension_token:
                    evidence_statements.append(f"dimension naming pattern ('{clean_name}')")
                return ColumnSemanticEvidence(
                    column_name=col_name,
                    candidate_role=ColumnRole.DIMENSION,
                    confidence=0.70,
                    confidence_level="MEDIUM",
                    evidence=evidence_statements,
                    conflicts=conflicts,
                )

            # Record conflict if high uniqueness on measure
            if (is_uniq or unique_ratio >= 0.90) and not has_id_token:
                conflicts.append(
                    f"high cardinality ratio ({unique_ratio:.1%}) observed; continuous numeric distribution and measurement semantics confirm MEASURE role"
                )
                evidence_statements.append(f"high cardinality continuous numeric distribution ({distinct_cnt} distinct values)")
            elif not is_uniq:
                evidence_statements.append("non-unique numeric distribution")

            if is_continuous_float:
                evidence_statements.append(f"continuous floating-point numeric distribution (min: {col_stats.get('min')}, max: {col_stats.get('max')})")

            if has_measure_token:
                evidence_statements.append(f"measure naming indicator: '{clean_name}'")

            agg_cat, agg_def, agg_notes = self._infer_measure_aggregation(clean_name, tokens, col_stats, is_continuous_float)
            evidence_statements.extend(agg_notes)

            conf_score = 0.92 if has_measure_token else (0.85 if is_continuous_float else 0.82)

            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.MEASURE,
                confidence=conf_score,
                confidence_level="HIGH",
                evidence=evidence_statements,
                aggregation_category=agg_cat,
                aggregation_default=agg_def,
                conflicts=conflicts,
            )

        # Signal 13: String/Object with date token fallback
        if is_text_or_obj and has_date_token:
            evidence_statements.append(f"string/object datatype ({dtype_str}) with date naming token ('{clean_name}')")
            evidence_statements.append("candidate datetime (read-only: no aggressive type conversion applied)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DATETIME,
                confidence=0.65,
                confidence_level="MEDIUM",
                evidence=evidence_statements,
                conflicts=conflicts,
            )

        # Signal 14: DIMENSION Candidate (String/Object or Categorical)
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
                    conflicts=conflicts,
                )

            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.88 if distinct_cnt < row_cnt else 0.70,
                confidence_level="HIGH" if distinct_cnt < row_cnt else "MEDIUM",
                evidence=evidence_statements,
                conflicts=conflicts,
            )

        # Signal 15: Ambiguous Column -> UNKNOWN
        evidence_statements.append(f"ambiguous signals (datatype: {dtype_str}, distinct count: {distinct_cnt})")
        evidence_statements.append("insufficient evidence to reliably assign a specific semantic role")
        return ColumnSemanticEvidence(
            column_name=col_name,
            candidate_role=ColumnRole.UNKNOWN,
            confidence=0.40,
            confidence_level="LOW",
            evidence=evidence_statements,
            conflicts=conflicts,
        )


def analyze_semantics(
    canonical: CanonicalDataset,
    profile: Optional[DataProfile] = None,
    apply_roles: bool = False,
) -> DatasetSemanticProfile:
    """Convenience function to analyze semantic column roles of a CanonicalDataset."""
    return SemanticAnalyzer().analyze(canonical=canonical, profile=profile, apply_roles=apply_roles)
