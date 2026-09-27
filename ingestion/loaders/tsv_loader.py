"""TSV dataset loader implementation."""

from pathlib import Path
from typing import Union
import pandas as pd

from ingestion.exceptions import InvalidFileFormatError
from ingestion.loaders.base_loader import BaseLoader
from ingestion.models import CanonicalDataset, DatasetMetadata


class TSVLoader(BaseLoader):
    """Loader for TSV (tab-separated values) files."""

    def load(self, file_path: Union[str, Path]) -> CanonicalDataset:
        """Load a TSV file into a CanonicalDataset.

        Raises:
            IngestionFileNotFoundError: If the file does not exist.
            UnsupportedFileTypeError: If the file extension is not '.tsv'.
            InvalidFileFormatError: If the TSV file is corrupted or unparseable.
        """
        path = self.validate_file_path(file_path, allowed_extensions=[".tsv"])

        try:
            df = pd.read_csv(path, sep="\t")
        except Exception as e:
            raise InvalidFileFormatError(f"Failed to parse TSV file '{path.name}': {e}") from e

        schema = self.extract_column_metadata(df)
        dataset_id = self.generate_dataset_id(path, "tsv")

        metadata = DatasetMetadata(
            dataset_id=dataset_id,
            name=path.stem,
            source_type="tsv",
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
                "source_type": "tsv",
                "row_count": len(df),
                "column_count": len(df.columns),
            },
        )

        return canonical
