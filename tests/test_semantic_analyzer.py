"""Comprehensive unit tests for the deterministic rule-based Semantic Analyzer."""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ingestion import CSVLoader, CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence import (
    ColumnSemanticEvidence,
    DataProfiler,
    DatasetSemanticProfile,
    SemanticAnalyzer,
    analyze_semantics,
    profile_dataset,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_obvious_numeric_measure():
    """Verify numeric column with measure naming is classified as MEASURE."""
    df = pd.DataFrame({"total_sales": [150.5, 200.0, 350.75, 400.0, 125.0]})
    meta = DatasetMetadata("ds-measure", "Measure", "pandas", 5, 1, [ColumnMetadata("total_sales", "total_sales", "float64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("total_sales")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.MEASURE
    assert ev.confidence >= 0.85
    assert ev.confidence_level == "HIGH"
    assert any("numeric" in s for s in ev.evidence)
    assert any("sales" in s for s in ev.evidence)


def test_numeric_identifier():
    """Verify numeric column with ID token (e.g. customer_id) is classified as IDENTIFIER."""
    df = pd.DataFrame({"customer_id": [1001, 1002, 1003, 1004, 1005]})
    meta = DatasetMetadata("ds-num-id", "Num ID", "pandas", 5, 1, [ColumnMetadata("customer_id", "customer_id", "int64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("customer_id")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.confidence >= 0.85
    assert any("numeric key/code pattern" in s or "numeric identifier disambiguation" in s for s in ev.evidence)


def test_text_and_categorical_dimension():
    """Verify string/categorical text column is classified as DIMENSION."""
    df = pd.DataFrame({"department": ["Sales", "HR", "Sales", "IT", "HR"]})
    meta = DatasetMetadata("ds-dim", "Dim", "pandas", 5, 1, [ColumnMetadata("department", "department", "object")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("department")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.DIMENSION
    assert ev.confidence >= 0.80


def test_true_datetime_column():
    """Verify pandas datetime64 column is classified as DATETIME with high confidence."""
    df = pd.DataFrame({"order_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])})
    meta = DatasetMetadata("ds-dt", "DT", "pandas", 3, 1, [ColumnMetadata("order_date", "order_date", "datetime64[ns]")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("order_date")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.DATETIME
    assert ev.confidence >= 0.90


def test_boolean_column():
    """Verify boolean column is classified as DIMENSION, not MEASURE."""
    df = pd.DataFrame({"is_active": [True, False, True, True, False]})
    meta = DatasetMetadata("ds-bool", "Bool", "pandas", 5, 1, [ColumnMetadata("is_active", "is_active", "bool")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("is_active")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.DIMENSION
    assert ev.candidate_role != ColumnRole.MEASURE
    assert ev.confidence >= 0.85


def test_unique_string_identifier():
    """Verify unique text string identifier (e.g. uuid_code) is classified as IDENTIFIER."""
    df = pd.DataFrame({"uuid_code": ["usr_111", "usr_222", "usr_333"]})
    meta = DatasetMetadata("ds-uuid", "UUID", "pandas", 3, 1, [ColumnMetadata("uuid_code", "uuid_code", "object")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("uuid_code")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert ev.confidence >= 0.85


def test_high_cardinality_text():
    """Verify high-cardinality text description is classified as DIMENSION."""
    df = pd.DataFrame({"description": [f"Item description {i}" for i in range(20)]})
    meta = DatasetMetadata("ds-desc", "Desc", "pandas", 20, 1, [ColumnMetadata("description", "description", "object")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("description")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.DIMENSION


def test_constant_numeric_column():
    """Verify constant numeric column returns UNKNOWN role due to zero variation."""
    df = pd.DataFrame({"status_flag": [1, 1, 1, 1]})
    meta = DatasetMetadata("ds-const", "Const", "pandas", 4, 1, [ColumnMetadata("status_flag", "status_flag", "int64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("status_flag")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.UNKNOWN
    assert ev.confidence_level == "LOW"


def test_all_null_column():
    """Verify all-null column returns UNKNOWN role with 0.0 confidence."""
    df = pd.DataFrame({"empty_col": [None, None, None]})
    meta = DatasetMetadata("ds-null", "Null", "pandas", 3, 1, [ColumnMetadata("empty_col", "empty_col", "object")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("empty_col")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.UNKNOWN
    assert ev.confidence == 0.0
    assert ev.confidence_level == "NONE"


def test_low_cardinality_numeric():
    """Verify low-cardinality numeric column (rating 1..5) without measure tokens returns UNKNOWN/DIMENSION."""
    df = pd.DataFrame({"rating": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]})
    meta = DatasetMetadata("ds-rate", "Rate", "pandas", 10, 1, [ColumnMetadata("rating", "rating", "int64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("rating")

    assert ev is not None
    # Low cardinality numeric without measure token should not be high confidence measure
    assert ev.candidate_role in (ColumnRole.UNKNOWN, ColumnRole.DIMENSION)


def test_ambiguous_column():
    """Verify ambiguous integer column (e.g. year) returns low confidence candidate or UNKNOWN."""
    df = pd.DataFrame({"year": [2020, 2021, 2022, 2023]})
    meta = DatasetMetadata("ds-year", "Year", "pandas", 4, 1, [ColumnMetadata("year", "year", "int64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("year")

    assert ev is not None
    assert ev.confidence < 0.85  # Not high confidence false certainty


def test_naming_based_supporting_evidence():
    """Verify naming token evidence appears explicitly in evidence explanations."""
    df = pd.DataFrame({"unit_price": [10.5, 20.0, 15.0]})
    meta = DatasetMetadata("ds-price", "Price", "pandas", 3, 1, [ColumnMetadata("unit_price", "unit_price", "float64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("unit_price")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.MEASURE
    assert any("price" in s for s in ev.evidence)


def test_conflicting_evidence_resolution():
    """Verify conflicts between numeric dtype and ID naming/uniqueness are resolved in favor of IDENTIFIER."""
    df = pd.DataFrame({"transaction_id": [10001, 10002, 10003]})
    meta = DatasetMetadata("ds-txn", "Txn", "pandas", 3, 1, [ColumnMetadata("transaction_id", "transaction_id", "int64")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("transaction_id")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.IDENTIFIER
    assert any("numeric key/code pattern" in s or "numeric identifier disambiguation" in s for s in ev.evidence)


def test_pandas_disambiguated_header():
    """Verify disambiguated header (name.1) identifies duplicate suffix in evidence."""
    df = pd.DataFrame({"name.1": ["Alice", "Bob", "Charlie"]})
    meta = DatasetMetadata("ds-dup", "Dup", "pandas", 3, 1, [ColumnMetadata("name.1", "name.1", "object")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("name.1")

    assert ev is not None
    assert any("pandas duplicate-disambiguation suffix" in s for s in ev.evidence)


def test_string_datetime_candidate():
    """Verify string column with date naming token (e.g. admission_date) is candidate DATETIME without type mutation."""
    df = pd.DataFrame({"admission_date": ["2026-01-01", "2026-01-02", "2026-01-03"]})
    meta = DatasetMetadata("ds-adm", "Adm", "pandas", 3, 1, [ColumnMetadata("admission_date", "admission_date", "object")])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    ev = sem_profile.get_evidence("admission_date")

    assert ev is not None
    assert ev.candidate_role == ColumnRole.DATETIME
    assert canonical.data["admission_date"].dtype == object  # No type mutation!


def test_empty_dataset_semantics():
    """Verify empty dataset executes cleanly without crashing."""
    df_empty = pd.DataFrame(columns=["a", "b"])
    meta = DatasetMetadata("ds-emp", "Emp", "pandas", 0, 2, [ColumnMetadata("a", "a", "object"), ColumnMetadata("b", "b", "float64")])
    canonical = CanonicalDataset(meta, df_empty)
    profile = profile_dataset(canonical)

    sem_profile = analyze_semantics(canonical, profile)
    assert len(sem_profile.column_evidences) == 2


def test_read_only_dataframe_invariance():
    """Verify semantic analysis never mutates underlying DataFrame."""
    df = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    df_copy = df.copy(deep=True)
    meta = DatasetMetadata("ds-inv", "Inv", "pandas", 3, 2, [ColumnMetadata("x", "x", "int64"), ColumnMetadata("y", "y", "object")])
    canonical = CanonicalDataset(meta, df)

    analyze_semantics(canonical)
    pd.testing.assert_frame_equal(canonical.data, df_copy)


def test_deterministic_repeated_classification():
    """Verify repeated classification runs produce identical DatasetSemanticProfiles."""
    loader = CSVLoader()
    canonical = loader.load(FIXTURES_DIR / "baseline.csv")
    profile = profile_dataset(canonical)

    sp1 = analyze_semantics(canonical, profile)
    sp2 = analyze_semantics(canonical, profile)

    sp2.generated_at = sp1.generated_at
    assert sp1.to_dict() == sp2.to_dict()


def test_apply_roles_option():
    """Verify apply_roles=True updates column.semantic_role in canonical metadata schema."""
    df = pd.DataFrame({"sales_amount": [100.0, 200.0]})
    meta = DatasetMetadata("ds-apply", "Apply", "pandas", 2, 1, [ColumnMetadata("sales_amount", "sales_amount", "float64", ColumnRole.UNKNOWN)])
    canonical = CanonicalDataset(meta, df)

    assert canonical.metadata.schema[0].semantic_role == ColumnRole.UNKNOWN
    analyze_semantics(canonical, apply_roles=True)
    assert canonical.metadata.schema[0].semantic_role == ColumnRole.MEASURE


def test_semantic_profile_json_serialization():
    """Verify dataset semantic profile serializes to JSON cleanly."""
    loader = CSVLoader()
    canonical = loader.load(FIXTURES_DIR / "baseline.csv")

    sem_profile = analyze_semantics(canonical)
    sem_dict = sem_profile.to_dict()

    json_str = json.dumps(sem_dict)
    assert isinstance(json_str, str)
    assert "column_evidences" in sem_dict
