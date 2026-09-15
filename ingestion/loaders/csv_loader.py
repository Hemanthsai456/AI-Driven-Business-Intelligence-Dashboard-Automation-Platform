"""CSV dataset loader implementation."""

from pathlib import Path
from typing import Union
import pandas as pd

from ingestion.exceptions import InvalidFileFormatError
from ingestion.loaders.base_loader import BaseLoader
from ingestion.models import CanonicalDataset, DatasetMetadata


class CSVLoader(BaseLoader):
    """Loader for CSV files."""

    def load(self, file_path: Union[str, Path]) -> CanonicalDataset:
        """Load a CSV file into a CanonicalDataset.

        Raises:
            IngestionFileNotFoundError: If the file does not exist.
            UnsupportedFileTypeError: If the file extension is not '.csv'.
            InvalidFileFormatError: If the CSV file is corrupted or unparseable.
        """
        path = self.validate_file_path(file_path, allowed_extensions=[".csv"])

        try:
            df = pd.read_csv(path)
        except Exception as e:
            raise InvalidFileFormatError(f"Failed to parse CSV file '{path.name}': {e}") from e

        schema = self.extract_column_metadata(df)
        dataset_id = self.generate_dataset_id(path, "csv")

        metadata = DatasetMetadata(
            dataset_id=dataset_id,
            name=path.stem,
            source_type="csv",
            row_count=len(df),
            column_count=len(df.columns),
            schema=schema,
            custom_metadata={"file_name": path.name, "file_size_bytes": path.stat().st_size},
        )

        canonical = CanonicalDataset(metadata=metadata, data=df)
        canonical.add_audit_entry(
            action="INGESTED",
            details={
                "file_path": str(path),
                "source_type": "csv",
                "row_count": len(df),
                "column_count": len(df.columns),
            },
        )

        return canonical
