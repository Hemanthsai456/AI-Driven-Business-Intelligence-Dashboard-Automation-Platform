"""Excel (XLSX) dataset loader implementation."""

from pathlib import Path
from typing import Union
import pandas as pd

from ingestion.exceptions import (
    InvalidExcelStructureError,
    InvalidFileFormatError,
)
from ingestion.loaders.base_loader import BaseLoader
from ingestion.models import CanonicalDataset, DatasetMetadata


class ExcelLoader(BaseLoader):
    """Loader for Excel (.xlsx) files enforcing V1 single-worksheet structure."""

    def load(self, file_path: Union[str, Path]) -> CanonicalDataset:
        """Load a single-worksheet Excel file into a CanonicalDataset.

        Raises:
            IngestionFileNotFoundError: If the file does not exist.
            UnsupportedFileTypeError: If the file extension is not '.xlsx'.
            InvalidExcelStructureError: If the workbook has 0 or >1 worksheets.
            InvalidFileFormatError: If the Excel file is corrupted or unparseable.
        """
        path = self.validate_file_path(file_path, allowed_extensions=[".xlsx"])

        try:
            excel_file = pd.ExcelFile(path)
            sheet_names = excel_file.sheet_names
        except Exception as e:
            raise InvalidFileFormatError(f"Failed to read Excel workbook '{path.name}': {e}") from e

        if not sheet_names:
            raise InvalidExcelStructureError(f"Excel workbook '{path.name}' contains no worksheets.")

        if len(sheet_names) > 1:
            raise InvalidExcelStructureError(
                f"V1 ExcelLoader only supports single-worksheet Excel files. "
                f"Workbook '{path.name}' contains {len(sheet_names)} worksheets: {sheet_names}"
            )

        try:
            df = pd.read_excel(excel_file, sheet_name=0)
        except Exception as e:
            raise InvalidFileFormatError(f"Failed to parse sheet in Excel file '{path.name}': {e}") from e

        schema = self.extract_column_metadata(df)
        dataset_id = self.generate_dataset_id(path, "xlsx")

        metadata = DatasetMetadata(
            dataset_id=dataset_id,
            name=path.stem,
            source_type="xlsx",
            row_count=len(df),
            column_count=len(df.columns),
            schema=schema,
            custom_metadata={
                "file_name": path.name,
                "file_size_bytes": path.stat().st_size,
                "sheet_name": sheet_names[0],
            },
        )

        canonical = CanonicalDataset(metadata=metadata, data=df)
        canonical.add_audit_entry(
            action="INGESTED",
            details={
                "file_path": str(path),
                "source_type": "xlsx",
                "sheet_name": sheet_names[0],
                "row_count": len(df),
                "column_count": len(df.columns),
            },
        )

        return canonical
