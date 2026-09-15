"""Unit tests for the canonical dataset and metadata models."""

import json
import numpy as np
import pandas as pd
import pytest
from ingestion.models import (
    ColumnRole,
    ColumnMetadata,
    DatasetMetadata,
    DataProfile,
    CanonicalDataset,
    sanitize_json_value,
)


def test_column_role_enum():
    """Verify that all required ColumnRole enum values exist and match expected strings."""
    assert ColumnRole.MEASURE.value == "MEASURE"
    assert ColumnRole.DIMENSION.value == "DIMENSION"
    assert ColumnRole.DATETIME.value == "DATETIME"
    assert ColumnRole.IDENTIFIER.value == "IDENTIFIER"
    assert ColumnRole.UNKNOWN.value == "UNKNOWN"
    assert set(ColumnRole) == {
        ColumnRole.MEASURE,
        ColumnRole.DIMENSION,
        ColumnRole.DATETIME,
        ColumnRole.IDENTIFIER,
        ColumnRole.UNKNOWN,
    }


def test_column_metadata_instantiation_and_serialization():
    """Verify ColumnMetadata initialization, default values, and serialization to dict."""
    col = ColumnMetadata(
        original_name="Customer ID",
        normalized_name="customer_id",
        detected_datatype="int64",
        semantic_role=ColumnRole.IDENTIFIER,
        null_count=0,
        null_percentage=0.0,
        distinct_count=100,
        is_unique=True,
        sample_values=[101, 102, 103],
    )

    assert col.original_name == "Customer ID"
    assert col.normalized_name == "customer_id"
    assert col.semantic_role == ColumnRole.IDENTIFIER
    assert col.is_unique is True
    assert len(col.sample_values) == 3

    d = col.to_dict()
    assert d["original_name"] == "Customer ID"
    assert d["semantic_role"] == "IDENTIFIER"
    assert d["sample_values"] == [101, 102, 103]


def test_column_metadata_json_serialization_numpy_pandas():
    """Verify json.dumps(column_metadata.to_dict()) works with NumPy and Pandas scalars."""
    col = ColumnMetadata(
        original_name="Mixed Col",
        normalized_name="mixed_col",
        detected_datatype="object",
        semantic_role=ColumnRole.MEASURE,
        sample_values=[
            np.int64(42),
            np.float64(3.14159),
            pd.Timestamp("2026-09-15 10:00:00"),
            pd.NA,
            np.nan,
        ],
    )

    d = col.to_dict()
    # Check primitive type sanitization
    assert d["sample_values"] == [42, 3.14159, "2026-09-15T10:00:00", None, None]

    # Must serialize cleanly without TypeError
    json_str = json.dumps(d)
    assert isinstance(json_str, str)


def test_dataset_metadata_lookup_and_serialization():
    """Verify DatasetMetadata creation, column lookup, and serialization."""
    col1 = ColumnMetadata(
        original_name="order_id",
        normalized_name="order_id",
        detected_datatype="int64",
        semantic_role=ColumnRole.IDENTIFIER,
    )
    col2 = ColumnMetadata(
        original_name="Sales Amount",
        normalized_name="sales_amount",
        detected_datatype="float64",
        semantic_role=ColumnRole.MEASURE,
    )

    meta = DatasetMetadata(
        dataset_id="ds-001",
        name="Sales Data",
        source_type="csv",
        row_count=500,
        column_count=2,
        schema=[col1, col2],
        custom_metadata={
            "imported_by": "unit_test",
            "timestamp": pd.Timestamp("2026-09-15 11:00:00"),
            "max_batch_size": np.int64(1000),
        },
    )

    assert meta.row_count == 500
    assert meta.column_count == 2
    assert meta.get_column("order_id") == col1
    assert meta.get_column("Sales Amount") == col2
    assert meta.get_column("non_existent") is None

    d = meta.to_dict()
    assert d["dataset_id"] == "ds-001"
    assert len(d["schema"]) == 2
    assert d["schema"][1]["semantic_role"] == "MEASURE"
    assert d["custom_metadata"]["max_batch_size"] == 1000

    # Test JSON serialization of complete dataset metadata
    json_str = json.dumps(d)
    assert isinstance(json_str, str)


def test_column_lookup_behavior():
    """Verify DatasetMetadata.get_column() lookup semantics.

    Intended behavior:
    1. Returns column metadata matching original_name if matched.
    2. Returns column metadata matching normalized_name if matched.
    3. Returns None if name matches neither original_name nor normalized_name.
    """
    col = ColumnMetadata(
        original_name="Customer Order # ($)",
        normalized_name="customer_order_num",
        detected_datatype="string",
        semantic_role=ColumnRole.IDENTIFIER,
    )
    meta = DatasetMetadata(
        dataset_id="ds-lookup",
        name="Lookup Test",
        source_type="xlsx",
        row_count=1,
        column_count=1,
        schema=[col],
    )

    # 1. Lookup by exact original column name
    assert meta.get_column("Customer Order # ($)") == col

    # 2. Lookup by normalized column name
    assert meta.get_column("customer_order_num") == col

    # 3. Lookup by nonexistent column name returns None
    assert meta.get_column("non_existent_column") is None


def test_data_profile_placeholder():
    """Verify DataProfile instantiation and placeholder statistics serialization."""
    profile = DataProfile(
        profile_id="prof-100",
        dataset_id="ds-001",
        column_statistics={"sales_amount": {"min": np.float64(10.0), "max": np.float64(500.0)}},
        quality_issues=[],
    )

    assert profile.profile_id == "prof-100"
    assert "sales_amount" in profile.column_statistics

    d = profile.to_dict()
    assert d["profile_id"] == "prof-100"
    json_str = json.dumps(d)
    assert isinstance(json_str, str)


def test_canonical_dataset_integration():
    """Verify CanonicalDataset with DataFrame, audit logging, and integrity check."""
    df = pd.DataFrame(
        {
            "customer_id": [1, 2, 3],
            "revenue": [100.5, 200.0, 150.75],
        }
    )

    col1 = ColumnMetadata("customer_id", "customer_id", "int64", ColumnRole.IDENTIFIER)
    col2 = ColumnMetadata("revenue", "revenue", "float64", ColumnRole.MEASURE)

    meta = DatasetMetadata(
        dataset_id="ds-test",
        name="Test Dataset",
        source_type="pandas",
        row_count=3,
        column_count=2,
        schema=[col1, col2],
    )

    canonical = CanonicalDataset(metadata=meta, data=df)

    assert canonical.validate_integrity() is True
    assert canonical.data.shape == (3, 2)
    assert canonical.profile is None

    # Test audit logging
    canonical.add_audit_entry("CREATED", {"source": "unit_test"})
    assert len(canonical.audit_logs) == 1
    assert canonical.audit_logs[0]["action"] == "CREATED"


def test_canonical_dataset_summary_serialization():
    """Verify CanonicalDataset.to_dict() produces a JSON-safe summary without row contents."""
    df = pd.DataFrame(
        {
            "customer_id": [101, 102, 103],
            "revenue": [100.5, 200.0, 150.75],
        }
    )

    col1 = ColumnMetadata("customer_id", "customer_id", "int64", ColumnRole.IDENTIFIER)
    col2 = ColumnMetadata("revenue", "revenue", "float64", ColumnRole.MEASURE)

    meta = DatasetMetadata(
        dataset_id="ds-summary",
        name="Summary Test",
        source_type="csv",
        row_count=3,
        column_count=2,
        schema=[col1, col2],
    )

    canonical = CanonicalDataset(metadata=meta, data=df)
    canonical.add_audit_entry("INGESTED", {"row_count": np.int64(3)})

    summary_dict = canonical.to_dict()

    # 1. Summary dictionary contains dataset metadata, summary, profile, audit logs
    assert "metadata" in summary_dict
    assert "dataframe_summary" in summary_dict
    assert summary_dict["dataframe_summary"]["row_count"] == 3
    assert summary_dict["dataframe_summary"]["column_count"] == 2
    assert summary_dict["dataframe_summary"]["columns"] == ["customer_id", "revenue"]
    assert summary_dict["is_integrity_valid"] is True

    # 2. Verify JSON serialization succeeds
    json_str = json.dumps(summary_dict)
    assert isinstance(json_str, str)

    # 3. Verify raw DataFrame row contents ([101, 102, 103], [100.5, ...]) are NOT present
    assert "101" not in json_str
    assert "100.5" not in json_str


def test_canonical_dataset_integrity_failure():
    """Verify validate_integrity returns False when metadata and DataFrame shapes mismatch."""
    df = pd.DataFrame({"a": [1, 2]})
    col = ColumnMetadata("a", "a", "int64", ColumnRole.UNKNOWN)
    meta = DatasetMetadata(
        dataset_id="ds-mismatch",
        name="Mismatch Dataset",
        source_type="csv",
        row_count=10,  # Mismatch (df has 2 rows)
        column_count=1,
        schema=[col],
    )

    canonical = CanonicalDataset(metadata=meta, data=df)
    assert canonical.validate_integrity() is False

