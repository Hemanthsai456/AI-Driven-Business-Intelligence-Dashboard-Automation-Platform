"""Unit tests for Stage 2: Data Cleaning Layer."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ingestion.loaders.csv_loader import CSVLoader
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from cleaning import DataCleaner, clean_dataset, CleaningConfig, CleaningReport

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_cleaning_layer_immutable_original():
    """Verify cleaning NEVER mutates the input CanonicalDataset or its underlying DataFrame."""
    df_raw = pd.DataFrame({
        "revenue": ["$1,000", "$2,000", "$3,000"],
        "region": [" north ", "SOUTH", "north"],
    })
    df_original_copy = df_raw.copy(deep=True)
    meta = DatasetMetadata("ds-immut", "Immut", "pandas", 3, 2, [
        ColumnMetadata("revenue", "revenue", "object", ColumnRole.MEASURE),
        ColumnMetadata("region", "region", "object", ColumnRole.DIMENSION),
    ])
    canonical = CanonicalDataset(meta, df_raw)

    cleaned_dataset, report = clean_dataset(canonical)

    # 1. Original dataframe remains completely untouched
    pd.testing.assert_frame_equal(canonical.data, df_original_copy)

    # 2. Cleaned dataframe is a distinct object and transformed
    assert cleaned_dataset.data is not canonical.data
    assert cleaned_dataset.data["revenue"].dtype == np.float64
    assert cleaned_dataset.data["region"].tolist() == ["North", "South", "North"]
    assert report.total_changes > 0


def test_cleaning_layer_deduplication():
    """Verify duplicate rows are detected and removed."""
    df = pd.DataFrame({
        "id": [1, 1, 2, 3],
        "category": ["A", "A", "B", "C"],
    })
    meta = DatasetMetadata("ds-dup", "Dup", "pandas", 4, 2, [
        ColumnMetadata("id", "id", "int64", ColumnRole.IDENTIFIER),
        ColumnMetadata("category", "category", "object", ColumnRole.DIMENSION),
    ])
    canonical = CanonicalDataset(meta, df)

    cleaned, report = clean_dataset(canonical)

    assert len(cleaned.data) == 3
    assert report.initial_rows == 4
    assert report.final_rows == 3
    assert "deduplicate" in report.changes_by_rule
    assert report.changes_by_rule["deduplicate"] == 1


def test_cleaning_layer_type_coercion():
    """Verify currency, percentages, and mixed dates are coerced to numeric and datetime dtypes."""
    df = pd.DataFrame({
        "price": ["$1,200.50", "€450.00", "($50.00)"],
        "discount": ["10.0%", "5.5%", "20%"],
        "date": ["2024-01-15", "16/01/2024", "Jan 17 2024"],
    })
    meta = DatasetMetadata("ds-coerce", "Coerce", "pandas", 3, 3, [
        ColumnMetadata("price", "price", "object", ColumnRole.MEASURE),
        ColumnMetadata("discount", "discount", "object", ColumnRole.MEASURE),
        ColumnMetadata("date", "date", "object", ColumnRole.DATETIME),
    ])
    canonical = CanonicalDataset(meta, df)

    cleaned, report = clean_dataset(canonical)

    assert cleaned.data["price"].dtype == np.float64
    assert cleaned.data["price"].tolist() == [1200.50, 450.00, -50.00]

    assert cleaned.data["discount"].dtype == np.float64
    assert cleaned.data["discount"].tolist() == [10.0, 5.5, 20.0]

    assert pd.api.types.is_datetime64_any_dtype(cleaned.data["date"])
    assert "coerce_currency" in report.changes_by_rule
    assert "coerce_percentage" in report.changes_by_rule
    assert "coerce_datetime" in report.changes_by_rule


def test_cleaning_layer_normalization():
    """Verify categorical dimensions have whitespace stripped and casing normalized."""
    df = pd.DataFrame({
        "dept": [" electronics ", "ELECTRONICS", "Electronics", " home & garden "],
    })
    meta = DatasetMetadata("ds-norm", "Norm", "pandas", 4, 1, [
        ColumnMetadata("dept", "dept", "object", ColumnRole.DIMENSION),
    ])
    canonical = CanonicalDataset(meta, df)

    cleaned, report = clean_dataset(canonical)

    assert cleaned.data["dept"].tolist() == ["Electronics", "Electronics", "Electronics", "Home & Garden"]
    assert "normalize_category" in report.changes_by_rule


def test_cleaning_layer_null_imputation():
    """Verify measures are imputed with median and dimensions with 'Unknown'."""
    df = pd.DataFrame({
        "sales": [100.0, 200.0, None, 400.0, 500.0],
        "channel": ["Retail", "Online", None, "Retail", "Online"],
    })
    meta = DatasetMetadata("ds-nulls", "Nulls", "pandas", 5, 2, [
        ColumnMetadata("sales", "sales", "float64", ColumnRole.MEASURE),
        ColumnMetadata("channel", "channel", "object", ColumnRole.DIMENSION),
    ])
    canonical = CanonicalDataset(meta, df)

    cleaned, report = clean_dataset(canonical)

    # Median of [100, 200, 400, 500] is 300.0
    assert cleaned.data["sales"].isna().sum() == 0
    assert cleaned.data["sales"][2] == 300.0

    # Dimension null imputed with 'Unknown'
    assert cleaned.data["channel"].isna().sum() == 0
    assert cleaned.data["channel"][2] == "Unknown"

    assert "fill_null_measure" in report.changes_by_rule
    assert "fill_null_dimension" in report.changes_by_rule


def test_cleaning_layer_idempotence():
    """Verify re-running clean_dataset on already cleaned output results in ZERO changes."""
    loader = CSVLoader()
    canonical = loader.load(str(FIXTURES_DIR / "messy_dataset.csv"))

    # Pass 1: Clean raw messy fixture
    cleaned_pass1, report1 = clean_dataset(canonical)
    assert report1.total_changes > 0
    assert len(cleaned_pass1.data) < len(canonical.data)

    # Pass 2: Re-run clean on the cleaned output
    cleaned_pass2, report2 = clean_dataset(cleaned_pass1)

    # Idempotence assertions:
    assert report2.total_changes == 0, f"Expected 0 changes on second pass, got {report2.total_changes}: {report2.changes}"
    assert len(report2.changes) == 0
    pd.testing.assert_frame_equal(cleaned_pass1.data, cleaned_pass2.data)
