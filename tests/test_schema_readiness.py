"""Comprehensive tests for the deterministic Schema Validation and Analysis-Readiness engine.

Tests validate behavior and public contracts, not private implementation details.

Coverage:
    1.  Valid normal dataset + profile + semantic profile → READY
    2.  Missing dataframe (data=None) → NOT_READY
    3.  Zero-column dataset → NOT_READY
    4.  Zero-row dataset → READY_WITH_WARNINGS
    5.  All-null column (with profile) → READY_WITH_WARNINGS
    6.  Disambiguated headers (name / name.1) → READY
    7.  Metadata column name mismatch → NOT_READY
    8.  Profile dataset_id mismatch → NOT_READY
    9.  Semantic profile references nonexistent column → NOT_READY
    10. High-missingness warning → READY_WITH_WARNINGS
    11. Constant-column warning → READY_WITH_WARNINGS
    12. Read-only dataframe invariance
    13. Deterministic repeated validation
    14. JSON serialization
    15. Structured result fields present
    16. Audit event emitted
    17. Multiple simultaneous warnings
    18. Step 1–4 tests remain green (verified by running full suite)
    19. Warning != cleaning (95% null column)
    20. Profile row count mismatch → NOT_READY
    21. Profile ghost column reference → NOT_READY
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DataProfile,
    DatasetMetadata,
)
from intelligence import (
    DataProfiler,
    SemanticAnalyzer,
    analyze_semantics,
    profile_dataset,
)
from intelligence.schema_validator import (
    AnalysisReadiness,
    ReadinessCheck,
    ReadinessStatus,
    SchemaValidator,
    assess_readiness,
)
from intelligence.semantic_analyzer import ColumnSemanticEvidence, DatasetSemanticProfile

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_simple_canonical(
    dataset_id: str = "ds-test",
    col_names: list = None,
    row_count: int = 5,
    dtype: str = "float64",
) -> CanonicalDataset:
    """Create a minimal but structurally valid CanonicalDataset inline."""
    if col_names is None:
        col_names = ["value"]
    data = {name: list(range(row_count)) for name in col_names}
    df = pd.DataFrame(data).astype({name: dtype for name in col_names})
    schema = [ColumnMetadata(name, name, dtype) for name in col_names]
    meta = DatasetMetadata(dataset_id, dataset_id, "pandas", row_count, len(col_names), schema)
    return CanonicalDataset(meta, df)


# ---------------------------------------------------------------------------
# Test 1 — Valid dataset → READY
# ---------------------------------------------------------------------------


def test_valid_dataset_is_ready():
    """A fully valid dataset with profile and semantic profile must be READY."""
    canonical = _make_simple_canonical("ds-ok", ["revenue", "region"], row_count=10)
    profile = profile_dataset(canonical, attach=False)
    sem_profile = analyze_semantics(canonical, profile)

    result = assess_readiness(canonical, profile, sem_profile)

    assert result.status == ReadinessStatus.READY
    assert len(result.blocking_issues) == 0
    assert len(result.warnings) == 0
    assert result.dataset_id == "ds-ok"
    assert result.checked_row_count == 10
    assert result.checked_column_count == 2


# ---------------------------------------------------------------------------
# Test 2 — Missing dataframe → NOT_READY
# ---------------------------------------------------------------------------


def test_missing_dataframe_is_not_ready():
    """When canonical.data is None (or not a DataFrame) the result must be NOT_READY."""
    canonical = _make_simple_canonical("ds-no-df")
    canonical.data = None  # simulate missing/invalid dataframe

    result = assess_readiness(canonical)

    assert result.status == ReadinessStatus.NOT_READY
    assert len(result.blocking_issues) >= 1
    assert any("DataFrame" in issue for issue in result.blocking_issues)
    # Must not crash — checks list has at least the dataframe_exists check
    assert any(c.check_name == "dataframe_exists" for c in result.checks)


# ---------------------------------------------------------------------------
# Test 3 — Zero-column dataset → NOT_READY
# ---------------------------------------------------------------------------


def test_zero_column_dataset_is_not_ready():
    """A DataFrame with no columns must be NOT_READY."""
    df = pd.DataFrame(index=range(3))  # 3 rows, 0 columns
    meta = DatasetMetadata("ds-0col", "ZeroCol", "pandas", 3, 0, [])
    canonical = CanonicalDataset(meta, df)

    result = assess_readiness(canonical)

    assert result.status == ReadinessStatus.NOT_READY
    assert any("no columns" in issue.lower() for issue in result.blocking_issues)
    assert result.checked_column_count == 0


# ---------------------------------------------------------------------------
# Test 4 — Zero-row dataset → READY_WITH_WARNINGS
# ---------------------------------------------------------------------------


def test_zero_row_dataset_is_ready_with_warnings():
    """A structurally valid dataset with zero rows must be READY_WITH_WARNINGS."""
    df = pd.DataFrame({"col_a": pd.Series([], dtype="float64")})
    meta = DatasetMetadata("ds-0row", "ZeroRow", "pandas", 0, 1, [
        ColumnMetadata("col_a", "col_a", "float64"),
    ])
    canonical = CanonicalDataset(meta, df)

    result = assess_readiness(canonical)

    assert result.status == ReadinessStatus.READY_WITH_WARNINGS
    assert len(result.blocking_issues) == 0
    assert any("zero rows" in w.lower() for w in result.warnings)
    assert result.checked_row_count == 0


# ---------------------------------------------------------------------------
# Test 5 — All-null column → READY_WITH_WARNINGS
# ---------------------------------------------------------------------------


def test_all_null_column_is_ready_with_warnings():
    """An all-null column must produce a warning, not a blocking issue."""
    df = pd.DataFrame({"revenue": [100.0, 200.0, 300.0], "notes": [None, None, None]})
    meta = DatasetMetadata("ds-null-col", "NullCol", "pandas", 3, 2, [
        ColumnMetadata("revenue", "revenue", "float64"),
        ColumnMetadata("notes", "notes", "object"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical, attach=False)

    result = assess_readiness(canonical, profile)

    assert result.status == ReadinessStatus.READY_WITH_WARNINGS
    assert len(result.blocking_issues) == 0
    assert any("notes" in w and "null" in w.lower() for w in result.warnings)
    # Must not drop or modify the null column
    assert "notes" in canonical.data.columns
    assert canonical.data["notes"].isna().all()


# ---------------------------------------------------------------------------
# Test 6 — Disambiguated headers (name / name.1) → READY
# ---------------------------------------------------------------------------


def test_disambiguated_headers_are_valid():
    """Pandas-disambiguated duplicate headers (name / name.1) must be accepted as READY."""
    df = pd.DataFrame({"name": ["Alice", "Bob"], "name.1": ["Smith", "Jones"]})
    meta = DatasetMetadata("ds-dup-hdr", "DupHdr", "pandas", 2, 2, [
        ColumnMetadata("name", "name", "object"),
        ColumnMetadata("name.1", "name.1", "object"),
    ])
    canonical = CanonicalDataset(meta, df)

    result = assess_readiness(canonical)

    assert result.status == ReadinessStatus.READY
    assert len(result.blocking_issues) == 0


# ---------------------------------------------------------------------------
# Test 7 — Metadata column name mismatch → NOT_READY
# ---------------------------------------------------------------------------


def test_metadata_column_name_mismatch_is_not_ready():
    """When metadata schema names do not match DataFrame columns the result is NOT_READY."""
    df = pd.DataFrame({"col_actual": [1, 2, 3]})
    meta = DatasetMetadata("ds-mm", "MM", "pandas", 3, 1, [
        ColumnMetadata("col_WRONG", "col_wrong", "int64"),  # wrong name
    ])
    canonical = CanonicalDataset(meta, df)

    result = assess_readiness(canonical)

    assert result.status == ReadinessStatus.NOT_READY
    assert any("mismatch" in issue.lower() or "name" in issue.lower()
               for issue in result.blocking_issues)
    assert any(c.check_name == "metadata_column_names_match" and not c.passed
               for c in result.checks)


# ---------------------------------------------------------------------------
# Test 8 — Profile dataset_id mismatch → NOT_READY
# ---------------------------------------------------------------------------


def test_profile_dataset_id_mismatch_is_not_ready():
    """A profile with a different dataset_id must produce NOT_READY."""
    canonical = _make_simple_canonical("ds-real", ["sales"], row_count=4)
    wrong_profile = DataProfile(
        profile_id="prof-wrong",
        dataset_id="ds-other",            # wrong dataset_id
        dataset_summary={"row_count": 4},
        column_statistics={"sales": {"is_all_null": False, "null_percentage": 0.0,
                                      "is_constant": False}},
    )

    result = assess_readiness(canonical, wrong_profile)

    assert result.status == ReadinessStatus.NOT_READY
    assert any("ds-other" in issue or "dataset_id" in issue.lower()
               for issue in result.blocking_issues)
    assert any(c.check_name == "profile_dataset_id_matches" and not c.passed
               for c in result.checks)


# ---------------------------------------------------------------------------
# Test 9 — Semantic profile ghost column → NOT_READY
# ---------------------------------------------------------------------------


def test_semantic_profile_ghost_column_is_not_ready():
    """A semantic profile referencing a nonexistent column must produce NOT_READY."""
    canonical = _make_simple_canonical("ds-sem", ["revenue"], row_count=5)

    ghost_sem_profile = DatasetSemanticProfile(
        dataset_id="ds-sem",
        column_evidences={
            "ghost_column": ColumnSemanticEvidence(
                column_name="ghost_column",
                candidate_role=ColumnRole.UNKNOWN,
                confidence=0.0,
                confidence_level="NONE",
            )
        },
    )

    result = assess_readiness(canonical, semantic_profile=ghost_sem_profile)

    assert result.status == ReadinessStatus.NOT_READY
    assert any("ghost_column" in issue for issue in result.blocking_issues)
    assert any(
        c.check_name == "semantic_profile_column_references_valid" and not c.passed
        for c in result.checks
    )


# ---------------------------------------------------------------------------
# Test 10 — High-missingness warning
# ---------------------------------------------------------------------------


def test_high_missingness_column_produces_warning():
    """A column with ≥50% missing values must produce a READY_WITH_WARNINGS result."""
    # 9 of 10 values null → 90% missing
    data = {
        "id": list(range(10)),
        "sparse": [None, None, None, None, None, None, None, None, None, 42.0],
    }
    df = pd.DataFrame(data).astype({"id": "int64", "sparse": "float64"})
    meta = DatasetMetadata("ds-sparse", "Sparse", "pandas", 10, 2, [
        ColumnMetadata("id", "id", "int64"),
        ColumnMetadata("sparse", "sparse", "float64"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical, attach=False)

    result = assess_readiness(canonical, profile)

    assert result.status == ReadinessStatus.READY_WITH_WARNINGS
    assert len(result.blocking_issues) == 0
    assert any("sparse" in w for w in result.warnings)
    assert any("missingness" in w.lower() or "missing" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Test 11 — Constant-column warning
# ---------------------------------------------------------------------------


def test_constant_column_produces_warning():
    """A column with only one distinct value must produce a READY_WITH_WARNINGS result."""
    df = pd.DataFrame({"revenue": [100.0, 200.0, 300.0], "region": ["US", "US", "US"]})
    meta = DatasetMetadata("ds-const", "Const", "pandas", 3, 2, [
        ColumnMetadata("revenue", "revenue", "float64"),
        ColumnMetadata("region", "region", "object"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical, attach=False)

    result = assess_readiness(canonical, profile)

    assert result.status == ReadinessStatus.READY_WITH_WARNINGS
    assert len(result.blocking_issues) == 0
    assert any("region" in w and "constant" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Test 12 — Read-only dataframe invariance
# ---------------------------------------------------------------------------


def test_read_only_dataframe_invariance():
    """Schema validation must not mutate the underlying DataFrame in any way."""
    df = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    df_before = df.copy(deep=True)
    meta = DatasetMetadata("ds-inv", "Inv", "pandas", 3, 2, [
        ColumnMetadata("x", "x", "int64"),
        ColumnMetadata("y", "y", "object"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical, attach=False)
    sem_profile = analyze_semantics(canonical, profile)

    assess_readiness(canonical, profile, sem_profile)

    pd.testing.assert_frame_equal(canonical.data, df_before)
    # Column order must also be unchanged
    assert list(canonical.data.columns) == list(df_before.columns)
    # dtypes must be unchanged
    for col in df_before.columns:
        assert canonical.data[col].dtype == df_before[col].dtype


# ---------------------------------------------------------------------------
# Test 13 — Deterministic repeated validation
# ---------------------------------------------------------------------------


def test_deterministic_repeated_validation():
    """Repeated validation of the same inputs must produce identical results."""
    from ingestion import CSVLoader
    canonical = CSVLoader().load(FIXTURES_DIR / "baseline.csv")
    profile = profile_dataset(canonical, attach=False)

    r1 = assess_readiness(canonical, profile)
    r2 = assess_readiness(canonical, profile)

    # Normalise timestamps before comparing
    r2.generated_at = r1.generated_at
    assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# Test 14 — JSON serialization
# ---------------------------------------------------------------------------


def test_json_serialization():
    """AnalysisReadiness.to_dict() must produce a json.dumps-safe structure."""
    canonical = _make_simple_canonical("ds-json", ["col_a", "col_b"], row_count=5)
    profile = profile_dataset(canonical, attach=False)
    result = assess_readiness(canonical, profile)

    d = result.to_dict()
    json_str = json.dumps(d)
    assert isinstance(json_str, str)
    assert "status" in d
    assert "blocking_issues" in d
    assert "warnings" in d
    assert "checks" in d
    assert "summary" in d


# ---------------------------------------------------------------------------
# Test 15 — Structured result fields
# ---------------------------------------------------------------------------


def test_structured_result_fields_present():
    """AnalysisReadiness must expose all required fields for downstream consumption."""
    canonical = _make_simple_canonical("ds-fields", ["measure"], row_count=3)
    result = assess_readiness(canonical)

    # All contractual fields must be present
    assert hasattr(result, "dataset_id")
    assert hasattr(result, "status")
    assert hasattr(result, "checks")
    assert hasattr(result, "blocking_issues")
    assert hasattr(result, "warnings")
    assert hasattr(result, "summary")
    assert hasattr(result, "checked_columns")
    assert hasattr(result, "checked_row_count")
    assert hasattr(result, "checked_column_count")
    assert hasattr(result, "generated_at")

    # checks must be a list of ReadinessCheck
    assert isinstance(result.checks, list)
    assert all(isinstance(c, ReadinessCheck) for c in result.checks)

    # status must be a ReadinessStatus
    assert isinstance(result.status, ReadinessStatus)

    # checked_columns must list the DataFrame columns
    assert set(result.checked_columns) == {"measure"}
    assert result.checked_row_count == 3
    assert result.checked_column_count == 1


# ---------------------------------------------------------------------------
# Test 16 — Audit event emitted
# ---------------------------------------------------------------------------


def test_audit_event_emitted():
    """validate() must append a READINESS_CHECKED audit entry to canonical.audit_logs."""
    canonical = _make_simple_canonical("ds-audit", ["sales"], row_count=4)
    initial_log_count = len(canonical.audit_logs)

    result = assess_readiness(canonical)

    assert len(canonical.audit_logs) == initial_log_count + 1
    last_entry = canonical.audit_logs[-1]
    assert last_entry["action"] == "READINESS_CHECKED"
    assert last_entry["details"]["dataset_id"] == "ds-audit"
    assert last_entry["details"]["status"] == result.status.value
    assert "blocking_issue_count" in last_entry["details"]
    assert "warning_count" in last_entry["details"]


# ---------------------------------------------------------------------------
# Test 17 — Multiple simultaneous warnings
# ---------------------------------------------------------------------------


def test_multiple_simultaneous_warnings():
    """All warnings must be captured and reported when multiple observations fire."""
    # Dataset with: zero rows, all-null column (will also be constant by definition)
    df = pd.DataFrame({
        "col_a": pd.Series([], dtype="float64"),
        "col_b": pd.Series([], dtype="object"),
    })
    meta = DatasetMetadata("ds-multi-warn", "MultiWarn", "pandas", 0, 2, [
        ColumnMetadata("col_a", "col_a", "float64"),
        ColumnMetadata("col_b", "col_b", "object"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical, attach=False)

    result = assess_readiness(canonical, profile)

    assert result.status == ReadinessStatus.READY_WITH_WARNINGS
    assert len(result.blocking_issues) == 0
    # Must have the zero-row warning at minimum
    assert any("zero rows" in w.lower() for w in result.warnings)
    # Must have at least one warning
    assert len(result.warnings) >= 1


# ---------------------------------------------------------------------------
# Test 18 — Step 1–4 tests remain green (integration guard)
# ---------------------------------------------------------------------------
# This is verified by running `pytest -v` at the end, not as an individual test.
# A marker test is included as a sanity signal only.

def test_previous_steps_importable():
    """All Step 1–4 symbols must remain importable without errors."""
    from ingestion import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
    from ingestion import CSVLoader, ExcelLoader
    from intelligence import DataProfiler, profile_dataset
    from intelligence import SemanticAnalyzer, analyze_semantics
    from intelligence import ColumnSemanticEvidence, DatasetSemanticProfile


# ---------------------------------------------------------------------------
# Test 19 — Warning != cleaning (the critical distinction)
# ---------------------------------------------------------------------------


def test_warning_is_not_cleaning():
    """
    A column with 95% missing values must produce a warning but must NOT:
        - be dropped
        - have its null values filled
        - have its dtype changed
        - be modified in any way
    """
    data = {
        "revenue": [100.0, 200.0, 300.0, 400.0, 500.0,
                    600.0, 700.0, 800.0, 900.0, 1000.0],
        "sparse_notes": [None, None, None, None, None,
                         None, None, None, None, "last"],
    }
    df = pd.DataFrame(data)
    df_before = df.copy(deep=True)
    meta = DatasetMetadata("ds-no-clean", "NoClean", "pandas", 10, 2, [
        ColumnMetadata("revenue", "revenue", "float64"),
        ColumnMetadata("sparse_notes", "sparse_notes", "object"),
    ])
    canonical = CanonicalDataset(meta, df)
    profile = profile_dataset(canonical, attach=False)

    result = assess_readiness(canonical, profile)

    # 1. Warning must be present for the sparse column
    assert any("sparse_notes" in w for w in result.warnings)

    # 2. Status is READY_WITH_WARNINGS, NOT NOT_READY
    assert result.status == ReadinessStatus.READY_WITH_WARNINGS

    # 3. DataFrame is completely unchanged
    pd.testing.assert_frame_equal(canonical.data, df_before)

    # 4. Sparse column still exists with original nulls intact
    assert "sparse_notes" in canonical.data.columns
    assert canonical.data["sparse_notes"].isna().sum() == 9

    # 5. Column count unchanged
    assert len(canonical.data.columns) == 2


# ---------------------------------------------------------------------------
# Test 20 — Profile row count mismatch → NOT_READY
# ---------------------------------------------------------------------------


def test_profile_row_count_mismatch_is_not_ready():
    """A profile with a stale row count must produce NOT_READY."""
    canonical = _make_simple_canonical("ds-stale", ["sales"], row_count=10)
    stale_profile = DataProfile(
        profile_id="prof-stale",
        dataset_id="ds-stale",           # correct id
        dataset_summary={"row_count": 999},  # wrong row count
        column_statistics={"sales": {"is_all_null": False, "null_percentage": 0.0,
                                      "is_constant": False}},
    )

    result = assess_readiness(canonical, stale_profile)

    assert result.status == ReadinessStatus.NOT_READY
    assert any("row count" in issue.lower() or "stale" in issue.lower()
               for issue in result.blocking_issues)
    assert any(c.check_name == "profile_row_count_matches" and not c.passed
               for c in result.checks)


# ---------------------------------------------------------------------------
# Test 21 — Profile ghost column reference → NOT_READY
# ---------------------------------------------------------------------------


def test_profile_ghost_column_reference_is_not_ready():
    """A profile referencing a column not in the DataFrame must produce NOT_READY."""
    canonical = _make_simple_canonical("ds-pghost", ["actual_col"], row_count=5)
    ghost_profile = DataProfile(
        profile_id="prof-ghost",
        dataset_id="ds-pghost",
        dataset_summary={"row_count": 5},
        column_statistics={
            "actual_col": {"is_all_null": False, "null_percentage": 0.0, "is_constant": False},
            "nonexistent_col": {"is_all_null": False},  # ghost reference
        },
    )

    result = assess_readiness(canonical, ghost_profile)

    assert result.status == ReadinessStatus.NOT_READY
    assert any("nonexistent_col" in issue for issue in result.blocking_issues)
    assert any(c.check_name == "profile_column_references_valid" and not c.passed
               for c in result.checks)


# ---------------------------------------------------------------------------
# Test 22 — Metadata column count mismatch → NOT_READY
# ---------------------------------------------------------------------------


def test_metadata_column_count_mismatch_is_not_ready():
    """When metadata schema has a different column count than the DataFrame, NOT_READY."""
    df = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})
    meta = DatasetMetadata("ds-cnt", "Cnt", "pandas", 2, 1, [
        ColumnMetadata("col_a", "col_a", "int64"),
        # col_b is missing from schema
    ])
    canonical = CanonicalDataset(meta, df)

    result = assess_readiness(canonical)

    assert result.status == ReadinessStatus.NOT_READY
    assert any(c.check_name == "metadata_column_count_matches" and not c.passed
               for c in result.checks)


# ---------------------------------------------------------------------------
# Test 23 — No profile and no semantic profile: still READY if data is clean
# ---------------------------------------------------------------------------


def test_ready_without_profile_or_semantic_profile():
    """A structurally valid dataset must be READY even when no profile/sem profile provided."""
    canonical = _make_simple_canonical("ds-no-prof", ["revenue", "region"], row_count=20)

    result = assess_readiness(canonical)  # no profile, no sem_profile

    assert result.status == ReadinessStatus.READY
    assert len(result.blocking_issues) == 0
    assert len(result.warnings) == 0
    # Informational checks for missing artifacts must still be present
    assert any(c.check_name == "profile_available" for c in result.checks)
    assert any(c.check_name == "semantic_profile_available" for c in result.checks)
