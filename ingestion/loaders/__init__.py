"""Loaders package providing CSV and XLSX ingestion functionality."""

from pathlib import Path
from typing import Union

from ingestion.exceptions import UnsupportedFileTypeError
from ingestion.loaders.base_loader import BaseLoader
from ingestion.loaders.csv_loader import CSVLoader
from ingestion.loaders.excel_loader import ExcelLoader
from ingestion.models import CanonicalDataset


def load_dataset(file_path: Union[str, Path]) -> CanonicalDataset:
    """Factory function to ingest a CSV or XLSX dataset into a CanonicalDataset based on file extension.

    Raises:
        IngestionFileNotFoundError: If file path does not exist.
        UnsupportedFileTypeError: If file extension is neither .csv nor .xlsx.
        InvalidExcelStructureError: If Excel workbook contains 0 or >1 sheets.
        InvalidFileFormatError: If file is malformed or unreadable.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".csv":
        return CSVLoader().load(path)
    elif ext == ".xlsx":
        return ExcelLoader().load(path)
    else:
        raise UnsupportedFileTypeError(
            f"Unsupported file extension '{ext}' for file '{path.name}'. Supported formats: .csv, .xlsx"
        )


__all__ = ["BaseLoader", "CSVLoader", "ExcelLoader", "load_dataset"]
