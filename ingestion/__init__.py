"""Ingestion package for data loading, schema extraction, and canonical dataset construction."""

from ingestion.exceptions import (
    IngestionError,
    IngestionFileNotFoundError,
    InvalidExcelStructureError,
    InvalidFileFormatError,
    UnsupportedFileTypeError,
)
from ingestion.loaders import CSVLoader, ExcelLoader, ParquetLoader, TSVLoader, load_dataset
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DataProfile,
    DatasetMetadata,
    sanitize_json_value,
)

__all__ = [
    "IngestionError",
    "IngestionFileNotFoundError",
    "UnsupportedFileTypeError",
    "InvalidFileFormatError",
    "InvalidExcelStructureError",
    "CSVLoader",
    "TSVLoader",
    "ExcelLoader",
    "ParquetLoader",
    "load_dataset",
    "ColumnRole",
    "ColumnMetadata",
    "DatasetMetadata",
    "DataProfile",
    "CanonicalDataset",
    "sanitize_json_value",
]
