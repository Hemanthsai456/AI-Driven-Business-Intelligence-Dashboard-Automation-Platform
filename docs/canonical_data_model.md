# Canonical Data Model Architecture

## Overview

The Canonical Data Model provides a unified, source-agnostic internal representation for datasets processed by **DashCrate** (AI-Driven Business Intelligence & Dashboard Automation Platform).

Regardless of whether incoming data originates from CSV files, TSV files, Excel spreadsheets (`.xlsx`), Parquet files, SQL databases, or API responses, the ingestion pipeline standardizes the data into this canonical structure before downstream profiling, transformation, semantic inference, or dashboard generation take place.

---

## Architectural Objectives

1. **Format Independence:** Eliminates file-format specific logic from downstream analytical engines (DuckDB), profiling components, and AI orchestrators.
2. **Metadata Enrichment:** Retains complete physical schema details (data types, null counts, distinct values) alongside semantic role classifications (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, `UNKNOWN`).
3. **Consistent Tabular Access:** Stores the underlying dataset in a high-performance, standardized `pandas.DataFrame` format for uniform query and analytical execution.
4. **Auditability & Explainability:** Includes structured audit logs to track operational provenance and transformation history for compliance and explainability.
5. **Extensibility:** Provides dedicated slots for data profiling metrics (`DataProfile`) without coupling profile computation to basic dataset representation.

---

## Core Components

The canonical model is defined using standard Python dataclasses in `ingestion/models.py`:

```
+-------------------------------------------------------------+
|                      CanonicalDataset                       |
+-------------------------------------------------------------+
|  - metadata: DatasetMetadata                                |
|  - data: pandas.DataFrame                                   |
|  - profile: Optional[DataProfile]                           |
|  - audit_logs: List[Dict[str, Any]]                         |
+-------------------------------------------------------------+
         |                                |
         v                                v
+------------------+             +--------------------+
| DatasetMetadata  |             |    DataProfile     |
+------------------+             +--------------------+
| - dataset_id     |             | - profile_id       |
| - name           |             | - column_stats     |
| - source_type    |             | - quality_issues   |
| - row_count      |             | - correlations     |
| - column_count   |             +--------------------+
| - schema: List   |
+------------------+
         |
         v
+------------------+
|  ColumnMetadata  |
+------------------+
| - original_name  |
| - normalized_name|
| - datatype       |
| - semantic_role  |  --> (ColumnRole Enum)
| - null_count     |
| - null_pct       |
| - distinct_count |
| - sample_values  |
+------------------+
```

### 1. `ColumnMetadata`
Holds physical metrics and semantic attributes for each column. Standardizes physical column names (`original_name` vs `normalized_name`) and stores a safe sample of values.

### 2. `DatasetMetadata`
Maintains dataset-level information including row count, column count, source format (`csv`, `tsv`, `xlsx`, `parquet`), creation timestamps, and full schema listing. Capped at 100MB per dataset.

### 3. `DataProfile`
A reserved placeholder object designed to receive comprehensive statistical profiles, distributions, correlation matrices, and data quality scores produced during profiling.

### 4. `CanonicalDataset`
The primary container combining metadata, tabular dataframe, profiling container, and audit trails. Provides validation methods (`validate_integrity()`) to enforce synchronization between metadata metrics and the underlying dataframe.

---

## Serialization & Persistence

All metadata and profile dataclasses implement `.to_dict()` helpers, making the canonical model easily serializable to JSON for storage in PostgreSQL, API communication, or state persistence across execution phases.
