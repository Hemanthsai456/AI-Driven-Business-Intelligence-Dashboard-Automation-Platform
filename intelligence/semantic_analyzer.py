"""Deterministic rule-based semantic role classification engine."""

from dataclasses import dataclass, field
from enum import Enum
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
        "balance", "age"
    }
    DATE_TOKENS = {"date", "time", "timestamp", "dt", "datetime", "created_at", "updated_at", "dob"}
    DIMENSION_TOKENS = {
        "name", "category", "type", "kind", "class", "group", "status", "state", "city",
        "country", "region", "segment", "dept", "department", "brand", "model", "gender",
        "genre", "level", "tier"
    }
    BOOLEAN_PREFIXES = ("is_", "has_", "can_", "should_", "flag_")
    BOOLEAN_EXACT = {"active", "enabled", "deleted", "is_active", "has_insurance", "deceased"}

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

        # Name Token Extraction & Disambiguation Check
        raw_name = col_name.lower().strip()
        clean_name = raw_name
        if re.search(r"\.\d+$", raw_name):
            clean_name = re.sub(r"\.\d+$", "", raw_name)
            evidence_statements.append("header contains pandas duplicate-disambiguation suffix (.1, .2)")

        tokens = set(re.split(r"[_\s#\-]+", clean_name))

        has_id_token = (
            any(t in self.ID_TOKENS for t in tokens)
            or clean_name.endswith(("_id", "_guid", "_uuid", "_code", "_key", "_pk", "_fk"))
            or clean_name in self.ID_TOKENS
        )
        has_measure_token = any(t in self.MEASURE_TOKENS for t in tokens)
        has_date_token = any(t in self.DATE_TOKENS for t in tokens)
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

        # Signal 2: Constant Column
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

        # Signal 4: Boolean Datatype or Boolean Characteristics
        series = df[col_name] if col_name in df.columns else None
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

        # Check for binary numeric/string values (0/1 or True/False represented as text)
        if distinct_cnt <= 2 and non_null_cnt > 0 and has_boolean_token:
            evidence_statements.append(f"low distinct count ({distinct_cnt}) with boolean naming pattern ('{clean_name}')")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DIMENSION,
                confidence=0.85,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        # Signal 5: Conflict Resolution — IDENTIFIER
        # High uniqueness OR ID naming token
        is_numeric = "int" in dtype_str or "float" in dtype_str
        unique_ratio = (distinct_cnt / non_null_cnt) if non_null_cnt > 0 else 0.0

        if (is_uniq or unique_ratio >= 0.98) and (has_id_token or not is_numeric):
            evidence_statements.append(f"high uniqueness ratio ({distinct_cnt}/{non_null_cnt} = {unique_ratio:.2f})")
            if has_id_token:
                evidence_statements.append(f"identifier naming pattern ('{clean_name}')")
            if is_numeric:
                evidence_statements.append("numeric identifier disambiguation (unique key overrides numeric dtype)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.IDENTIFIER,
                confidence=0.95 if has_id_token else 0.85,
                confidence_level="HIGH",
                evidence=evidence_statements,
            )

        if has_id_token and distinct_cnt > 1 and not has_measure_token:
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

        # Signal 6: MEASURE Candidate
        if is_numeric:
            evidence_statements.append(f"numeric datatype ({dtype_str})")
            evidence_statements.append(f"distinct count: {distinct_cnt}")
            if not is_uniq:
                evidence_statements.append("non-unique numeric distribution")

            # Low-cardinality numeric check (e.g. rating = 1..5, status = 1..4)
            if distinct_cnt <= 5 and not has_measure_token:
                evidence_statements.append(f"low distinct count ({distinct_cnt}) without explicit measure naming")
                if has_dimension_token:
                    evidence_statements.append(f"dimension naming pattern ('{clean_name}')")
                    return ColumnSemanticEvidence(
                        column_name=col_name,
                        candidate_role=ColumnRole.DIMENSION,
                        confidence=0.70,
                        confidence_level="MEDIUM",
                        evidence=evidence_statements,
                    )
                else:
                    evidence_statements.append("low-cardinality numeric values could represent discrete categories or scale ratings")
                    return ColumnSemanticEvidence(
                        column_name=col_name,
                        candidate_role=ColumnRole.UNKNOWN,
                        confidence=0.45,
                        confidence_level="LOW",
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

        # Signal 7: DATETIME Candidate (String/Object with date token)
        if ("object" in dtype_str or "str" in dtype_str) and has_date_token:
            evidence_statements.append(f"string/object datatype ({dtype_str}) with date naming token ('{clean_name}')")
            evidence_statements.append("candidate datetime (read-only: no aggressive type conversion applied)")
            return ColumnSemanticEvidence(
                column_name=col_name,
                candidate_role=ColumnRole.DATETIME,
                confidence=0.65,
                confidence_level="MEDIUM",
                evidence=evidence_statements,
            )

        # Signal 8: DIMENSION Candidate (String/Object or Categorical)
        if "object" in dtype_str or "str" in dtype_str or "category" in dtype_str:
            evidence_statements.append(f"text/categorical datatype ({dtype_str})")
            evidence_statements.append(f"distinct count: {distinct_cnt} out of {row_cnt} rows")

            if has_dimension_token:
                evidence_statements.append(f"dimension naming pattern ('{clean_name}')")

            # High cardinality description text check
            if distinct_cnt > 0.9 * non_null_cnt and non_null_cnt > 10 and not has_dimension_token:
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

        # Signal 9: Ambiguous Column -> UNKNOWN
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
