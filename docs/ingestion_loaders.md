# CSV & XLSX Data Ingestion Specification

## Overview

The ingestion layer in the **AI-Driven Business Intelligence & Dashboard Automation Platform** converts raw tabular files (`.csv` and `.xlsx`) into standardized `CanonicalDataset` objects.

```
+---------------+      +-------------------+
|  input.csv    | ---> |     CSVLoader     | ---\
+---------------+      +-------------------+     \
                                                  +--->  CanonicalDataset
+---------------+      +-------------------+     /
|  input.xlsx   | ---> |    ExcelLoader    | ---/
+---------------+      +-------------------+
```

---

## Loaders Architecture

### 1. `CSVLoader`
- **File Validation:** Verifies file existence and `.csv` extension.
- **Data Parsing:** Reads file contents using `pandas.read_csv()`.
- **Metadata Extraction:** Populates column metadata (`original_name`, `normalized_name`, `detected_datatype`, null statistics, distinct count, sample values) and dataset-level metadata (`source_type="csv"`).
- **Default Roles:** All column semantic roles default to `ColumnRole.UNKNOWN`.

### 2. `ExcelLoader`
- **File Validation:** Verifies file existence and `.xlsx` extension.
- **Single-Worksheet Rule (V1):** Inspects the workbook using `pandas.ExcelFile`. If the workbook contains zero or more than one worksheet, `InvalidExcelStructureError` is raised. Multi-sheet merging or guessing is strictly forbidden in V1.
- **Data Parsing:** Reads worksheet 0 via `pandas.read_excel()`.
- **Metadata Extraction:** Produces the identical `CanonicalDataset` structure as `CSVLoader` (`source_type="xlsx"`).

---

## Canonicalization Process

Regardless of the source format:
1. Column order and total row/column counts are strictly preserved.
2. `ColumnMetadata` is computed per column:
   - `original_name` and `normalized_name` are set to the column header string.
   - `detected_datatype` captures the Pandas column dtype.
   - `semantic_role` is set to `ColumnRole.UNKNOWN`.
   - `null_count` and `null_percentage` record missing data metrics.
   - `distinct_count` and `is_unique` record cardinality.
   - `sample_values` extracts up to 5 non-null values sanitized via `sanitize_json_value()`.
3. An audit log entry (`action="INGESTED"`) records the source path, format, and dimensions.

---

## Ingestion Error Handling

Custom exception hierarchy defined in `ingestion/exceptions.py`:

| Exception | Trigger Condition |
| :--- | :--- |
| `IngestionError` | Base exception for all ingestion failures. |
| `IngestionFileNotFoundError` | Raised when the target file does not exist on disk. |
| `UnsupportedFileTypeError` | Raised when file extension is not `.csv` or `.xlsx`. |
| `InvalidFileFormatError` | Raised when CSV/XLSX file is corrupted or unparseable. |
| `InvalidExcelStructureError` | Raised when an Excel workbook has 0 or >1 worksheets. |

---

## Test Fixtures & Strategy

Committed test fixtures in `tests/fixtures/`:
- `baseline.csv` & `baseline.xlsx`: Paired identical logical dataset for cross-format equivalency checks.
- `missing_values.csv` & `missing_values.xlsx`: Datasets containing nulls across numeric, text, and date columns.
- `duplicate_headers.csv` & `duplicate_headers.xlsx`: Header name duplication tests.
- `mixed_types.csv` & `mixed_types.xlsx`: Mixed numeric and text string columns.
- `dates.csv` & `dates.xlsx`: ISO 8601 dates and US date formats.
- `tiny.csv` & `tiny.xlsx`: Minimal 1-row datasets.
- `multi_sheet.xlsx`: Excel workbook with multiple worksheets to test structural enforcement.
- `corrupt.csv` & `corrupt.xlsx`: Unreadable files for error handling tests.
