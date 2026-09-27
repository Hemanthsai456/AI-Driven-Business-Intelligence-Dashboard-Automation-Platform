"""Parquet dataset loader implementation."""

from pathlib import Path
from typing import Union
import pandas as pd

from ingestion.exceptions import InvalidFileFormatError
from ingestion.loaders.base_loader import BaseLoader
from ingestion.models import CanonicalDataset, DatasetMetadata


class ParquetLoader(BaseLoader):
    """Loader for Apache Parquet files."""

    def load(self, file_path: Union[str, Path]) -> CanonicalDataset:
        """Load a Parquet file into a CanonicalDataset.

        Raises:
            IngestionFileNotFoundError: If the file does not exist.
            UnsupportedFileTypeError: If the file extension is not '.parquet'.
            InvalidFileFormatError: If the Parquet file is corrupted or unparseable.
        """
        path = self.validate_file_path(file_path, allowed_extensions=[".parquet"])

        try:
            df = pd.read_parquet(path)
        except Exception as e:
            raise InvalidFileFormatError(f"Failed to parse Parquet file '{path.name}': {e}") from e

        schema = self.extract_column_metadata(df)
        dataset_id = self.generate_dataset_id(path, "parquet")

        metadata = DatasetMetadata(
            dataset_id=dataset_id,
            name=path.stem,
            source_type="parquet",
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
                "source_type": "parquet",
                "row_count": len(df),
                "column_count": len(df.columns),
            },
        )

        return canonical
