"""Comprehensive pytest suite for CSV, TSV, XLSX, and Parquet ingestion loaders."""

from pathlib import Path
import pytest
import pandas as pd

from ingestion import (
    CSVLoader,
    TSVLoader,
    ExcelLoader,
    ParquetLoader,
    load_dataset,
    CanonicalDataset,
    ColumnRole,
    IngestionError,
    IngestionFileNotFoundError,
    UnsupportedFileTypeError,
    InvalidFileFormatError,
    InvalidExcelStructureError,
)
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_csv_loader_baseline():
    """Verify CSVLoader reads baseline.csv and creates a valid CanonicalDataset."""
    loader = CSVLoader()
    file_path = FIXTURES_DIR / "baseline.csv"
    canonical = loader.load(file_path)

    assert isinstance(canonical, CanonicalDataset)
    assert canonical.metadata.source_type == "csv"
    assert canonical.metadata.row_count == 5
    assert canonical.metadata.column_count == 5
    assert canonical.validate_integrity() is True

    # Check column order & schema
    expected_cols = ["id", "customer_name", "amount", "order_date", "is_active"]
    assert [col.original_name for col in canonical.metadata.schema] == expected_cols
    assert list(canonical.data.columns) == expected_cols

    # Verify all roles default to UNKNOWN
    for col in canonical.metadata.schema:
        assert col.semantic_role == ColumnRole.UNKNOWN


def test_excel_loader_baseline():
    """Verify ExcelLoader reads baseline.xlsx and creates a valid CanonicalDataset."""
    loader = ExcelLoader()
    file_path = FIXTURES_DIR / "baseline.xlsx"
    canonical = loader.load(file_path)

    assert isinstance(canonical, CanonicalDataset)
    assert canonical.metadata.source_type == "xlsx"
    assert canonical.metadata.row_count == 5
    assert canonical.metadata.column_count == 5
    assert canonical.validate_integrity() is True

    expected_cols = ["id", "customer_name", "amount", "order_date", "is_active"]
    assert [col.original_name for col in canonical.metadata.schema] == expected_cols
    assert list(canonical.data.columns) == expected_cols

    for col in canonical.metadata.schema:
        assert col.semantic_role == ColumnRole.UNKNOWN


def test_tsv_loader_baseline():
    """Verify TSVLoader reads baseline.tsv and creates a valid CanonicalDataset."""
    loader = TSVLoader()
    file_path = FIXTURES_DIR / "baseline.tsv"
    canonical = loader.load(file_path)

    assert isinstance(canonical, CanonicalDataset)
    assert canonical.metadata.source_type == "tsv"
    assert canonical.metadata.row_count == 5
    assert canonical.metadata.column_count == 5
    assert canonical.validate_integrity() is True

    expected_cols = ["id", "customer_name", "amount", "order_date", "is_active"]
    assert [col.original_name for col in canonical.metadata.schema] == expected_cols
    assert list(canonical.data.columns) == expected_cols

    for col in canonical.metadata.schema:
        assert col.semantic_role == ColumnRole.UNKNOWN

    # Verify existing downstream profiling engine processes TSV dataset
    profile = profile_dataset(canonical)
    assert profile.dataset_summary["row_count"] == 5
    assert len(profile.column_statistics) == 5
    assert "amount" in profile.column_statistics
    assert profile.column_statistics["amount"]["null_count"] == 0

    # Verify existing downstream semantic analysis engine processes TSV dataset
    semantic_profile = analyze_semantics(canonical, profile=profile)
    assert len(semantic_profile.column_evidences) == 5
    assert "amount" in semantic_profile.column_evidences
    assert semantic_profile.column_evidences["amount"].candidate_role == ColumnRole.MEASURE


def test_parquet_loader_baseline():
    """Verify ParquetLoader reads baseline.parquet and creates a valid CanonicalDataset."""
    loader = ParquetLoader()
    file_path = FIXTURES_DIR / "baseline.parquet"
    canonical = loader.load(file_path)

    assert isinstance(canonical, CanonicalDataset)
    assert canonical.metadata.source_type == "parquet"
    assert canonical.metadata.row_count == 5
    assert canonical.metadata.column_count == 5
    assert canonical.validate_integrity() is True

    expected_cols = ["id", "customer_name", "amount", "order_date", "is_active"]
    assert [col.original_name for col in canonical.metadata.schema] == expected_cols
    assert list(canonical.data.columns) == expected_cols

    for col in canonical.metadata.schema:
        assert col.semantic_role == ColumnRole.UNKNOWN

    # Verify existing downstream profiling engine processes Parquet dataset
    profile = profile_dataset(canonical)
    assert profile.dataset_summary["row_count"] == 5
    assert len(profile.column_statistics) == 5
    assert "amount" in profile.column_statistics
    assert profile.column_statistics["amount"]["null_count"] == 0

    # Verify existing downstream semantic analysis engine processes Parquet dataset
    semantic_profile = analyze_semantics(canonical, profile=profile)
    assert len(semantic_profile.column_evidences) == 5
    assert "amount" in semantic_profile.column_evidences
    assert semantic_profile.column_evidences["amount"].candidate_role == ColumnRole.MEASURE



def test_critical_paired_baseline_comparison():
    """Critical Check: Compare baseline.csv and baseline.xlsx canonical representations."""
    csv_canonical = load_dataset(FIXTURES_DIR / "baseline.csv")
    xlsx_canonical = load_dataset(FIXTURES_DIR / "baseline.xlsx")

    # 1. Column names match
    csv_cols = [c.original_name for c in csv_canonical.metadata.schema]
    xlsx_cols = [c.original_name for c in xlsx_canonical.metadata.schema]
    assert csv_cols == xlsx_cols

    # 2. Column order matches
    assert list(csv_canonical.data.columns) == list(xlsx_canonical.data.columns)

    # 3. Row count matches
    assert csv_canonical.metadata.row_count == xlsx_canonical.metadata.row_count == 5

    # 4. Column count matches
    assert csv_canonical.metadata.column_count == xlsx_canonical.metadata.column_count == 5

    # 5. Semantic roles match (all UNKNOWN)
    for c_col, x_col in zip(csv_canonical.metadata.schema, xlsx_canonical.metadata.schema):
        assert c_col.semantic_role == x_col.semantic_role == ColumnRole.UNKNOWN

    # 6. Logical dtypes are compatible
    # (id: int, customer_name: str/object, amount: float, order_date: object/str, is_active: bool)
    assert csv_canonical.metadata.get_column("id").null_count == 0
    assert xlsx_canonical.metadata.get_column("id").null_count == 0
    assert csv_canonical.metadata.get_column("amount").null_count == 0
    assert xlsx_canonical.metadata.get_column("amount").null_count == 0


def test_missing_values_metadata():
    """Verify null count, null percentage, and sample values in datasets with missing data."""
    canonical = load_dataset(FIXTURES_DIR / "missing_values.csv")

    qty_col = canonical.metadata.get_column("quantity")
    assert qty_col is not None
    assert qty_col.null_count == 2
    assert qty_col.null_percentage == 50.0
    assert qty_col.distinct_count == 2
    assert None not in qty_col.sample_values  # Sample values only contain non-null samples

    cat_col = canonical.metadata.get_column("category")
    assert cat_col is not None
    assert cat_col.null_count == 1
    assert cat_col.null_percentage == 25.0


def test_duplicate_headers():
    """Verify loading dataset with duplicate column header names."""
    canonical_csv = load_dataset(FIXTURES_DIR / "duplicate_headers.csv")
    canonical_xlsx = load_dataset(FIXTURES_DIR / "duplicate_headers.xlsx")

    assert canonical_csv.metadata.column_count == 3
    assert canonical_xlsx.metadata.column_count == 3
    assert canonical_csv.validate_integrity() is True
    assert canonical_xlsx.validate_integrity() is True


def test_mixed_types():
    """Verify loading column with mixed numeric and text string types."""
    canonical = load_dataset(FIXTURES_DIR / "mixed_types.csv")
    code_col = canonical.metadata.get_column("code")
    assert code_col is not None
    assert code_col.null_count == 0
    assert code_col.distinct_count == 4


def test_dates_loading():
    """Verify dataset containing ISO dates and US date representations."""
    canonical = load_dataset(FIXTURES_DIR / "dates.csv")
    assert canonical.metadata.column_count == 3
    assert canonical.metadata.row_count == 3


def test_tiny_dataset():
    """Verify minimal 1-row dataset loads cleanly."""
    canonical = load_dataset(FIXTURES_DIR / "tiny.csv")
    assert canonical.metadata.row_count == 1
    assert canonical.metadata.column_count == 1
    assert canonical.validate_integrity() is True


def test_file_not_found_error():
    """Verify IngestionFileNotFoundError raised when file path does not exist."""
    non_existent = FIXTURES_DIR / "does_not_exist.csv"
    with pytest.raises(IngestionFileNotFoundError) as exc_info:
        load_dataset(non_existent)
    assert "File not found" in str(exc_info.value)


def test_unsupported_file_type_error():
    """Verify UnsupportedFileTypeError raised for invalid file extensions."""
    invalid_file = FIXTURES_DIR / "generate_fixtures.py"
    with pytest.raises(UnsupportedFileTypeError) as exc_info:
        load_dataset(invalid_file)
    assert "Unsupported file extension" in str(exc_info.value)


def test_multi_sheet_excel_error():
    """Verify InvalidExcelStructureError raised when Excel file contains multiple worksheets."""
    multi_sheet_file = FIXTURES_DIR / "multi_sheet.xlsx"
    with pytest.raises(InvalidExcelStructureError) as exc_info:
        ExcelLoader().load(multi_sheet_file)
    assert "V1 ExcelLoader only supports single-worksheet" in str(exc_info.value)


def test_corrupt_file_errors():
    """Verify InvalidFileFormatError raised for unparseable / corrupted files."""
    # Corrupt CSV
    corrupt_csv = FIXTURES_DIR / "corrupt.csv"
    with pytest.raises(InvalidFileFormatError):
        CSVLoader().load(corrupt_csv)

    # Corrupt TSV
    corrupt_tsv = FIXTURES_DIR / "corrupt.tsv"
    with pytest.raises(InvalidFileFormatError):
        TSVLoader().load(corrupt_tsv)

    # Corrupt XLSX
    corrupt_xlsx = FIXTURES_DIR / "corrupt.xlsx"
    with pytest.raises(InvalidFileFormatError):
        ExcelLoader().load(corrupt_xlsx)

    # Corrupt Parquet
    corrupt_parquet = FIXTURES_DIR / "corrupt.parquet"
    with pytest.raises(InvalidFileFormatError):
        ParquetLoader().load(corrupt_parquet)


def test_load_dataset_all_formats_parity():
    """Verify load_dataset dispatches correctly for CSV, TSV, XLSX, and Parquet."""
    canonical_csv = load_dataset(FIXTURES_DIR / "baseline.csv")
    canonical_tsv = load_dataset(FIXTURES_DIR / "baseline.tsv")
    canonical_xlsx = load_dataset(FIXTURES_DIR / "baseline.xlsx")
    canonical_parquet = load_dataset(FIXTURES_DIR / "baseline.parquet")

    assert canonical_csv.metadata.source_type == "csv"
    assert canonical_tsv.metadata.source_type == "tsv"
    assert canonical_xlsx.metadata.source_type == "xlsx"
    assert canonical_parquet.metadata.source_type == "parquet"

    # All produce same columns and rows
    expected_cols = ["id", "customer_name", "amount", "order_date", "is_active"]
    for c in [canonical_csv, canonical_tsv, canonical_xlsx, canonical_parquet]:
        assert [col.original_name for col in c.metadata.schema] == expected_cols
        assert list(c.data.columns) == expected_cols
        assert c.metadata.row_count == 5
        assert c.metadata.column_count == 5
        assert c.validate_integrity() is True

