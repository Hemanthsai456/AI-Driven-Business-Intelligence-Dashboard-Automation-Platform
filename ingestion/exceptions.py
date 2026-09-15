"""Custom exception hierarchy for data ingestion operations."""


class IngestionError(Exception):
    """Base exception for all ingestion failures."""

    pass


class IngestionFileNotFoundError(IngestionError):
    """Raised when the specified file path does not exist on disk."""

    pass


class UnsupportedFileTypeError(IngestionError):
    """Raised when the input file extension is not supported by the ingestion pipeline."""

    pass


class InvalidFileFormatError(IngestionError):
    """Raised when a file cannot be parsed or read due to corruption or formatting errors."""

    pass


class InvalidExcelStructureError(IngestionError):
    """Raised when an Excel file violates structural assumptions (e.g., multi-sheet workbooks in V1)."""

    pass
