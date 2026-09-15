"""Base loader definition and shared utilities for dataset ingestion."""

from abc import ABC, abstractmethod
import hashlib
from pathlib import Path
from typing import Any, List, Union
import pandas as pd

from ingestion.exceptions import (
    IngestionError,
    IngestionFileNotFoundError,
    UnsupportedFileTypeError,
)
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DatasetMetadata,
    sanitize_json_value,
)


class BaseLoader(ABC):
    """Abstract base class for format-specific dataset loaders."""

    @abstractmethod
    def load(self, file_path: Union[str, Path]) -> CanonicalDataset:
        """Load a dataset file into a CanonicalDataset representation."""
        pass

    def validate_file_path(
        self, file_path: Union[str, Path], allowed_extensions: List[str]
    ) -> Path:
        """Validate that file exists and matches allowed extensions.

        Raises:
            IngestionFileNotFoundError: If the file does not exist.
            UnsupportedFileTypeError: If the file extension is not allowed.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise IngestionFileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        allowed = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in allowed_extensions]
        if ext not in allowed:
            raise UnsupportedFileTypeError(
                f"Unsupported file extension '{ext}' for file '{path.name}'. Allowed extensions: {allowed}"
            )

        return path

    def extract_column_metadata(
        self, df: pd.DataFrame, sample_size: int = 5
    ) -> List[ColumnMetadata]:
        """Extract ColumnMetadata for each column in the DataFrame."""
        schema: List[ColumnMetadata] = []
        total_rows = len(df)

        for col in df.columns:
            col_str = str(col)
            series = df[col]
            null_cnt = int(series.isna().sum())
            null_pct = float((null_cnt / total_rows) * 100.0) if total_rows > 0 else 0.0
            distinct_cnt = int(series.nunique(dropna=True))
            is_uniq = bool(series.is_unique) if total_rows > 0 else False

            # Extract non-null sample values safely
            non_null_series = series.dropna()
            samples = non_null_series.head(sample_size).tolist()
            sanitized_samples = [sanitize_json_value(s) for s in samples]

            col_meta = ColumnMetadata(
                original_name=col_str,
                normalized_name=col_str,
                detected_datatype=str(series.dtype),
                semantic_role=ColumnRole.UNKNOWN,
                null_count=null_cnt,
                null_percentage=round(null_pct, 4),
                distinct_count=distinct_cnt,
                is_unique=is_uniq,
                sample_values=sanitized_samples,
            )
            schema.append(col_meta)

        return schema

    def generate_dataset_id(self, file_path: Path, source_type: str) -> str:
        """Generate a deterministic dataset ID based on file path and source type."""
        stem_slug = "".join(c if c.isalnum() else "_" for c in file_path.stem.lower()).strip("_")
        hash_suffix = hashlib.md5(f"{file_path.name}_{file_path.stat().st_size}".encode("utf-8")).hexdigest()[:6]
        return f"ds_{stem_slug}_{hash_suffix}"
