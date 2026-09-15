# Data Profiling Engine Specification

## Overview

The **Data Profiling Engine** in the **AI-Driven Business Intelligence & Dashboard Automation Platform** executes deterministic, read-only statistical and physical analysis on a `CanonicalDataset`.

```
+-------------------+      +-------------------+      +-------------------+
|  CanonicalDataset | ---> |   DataProfiler    | ---> |    DataProfile    |
| (DataFrame + Meta)|      | (Read-Only Engine)|      | (Stats & Issues)  |
+-------------------+      +-------------------+      +-------------------+
```

---

## Key Principles & Scope Boundaries

1. **Read-Only Invariance**: Profiling never modifies, cleans, fills, transforms, or renames the underlying `CanonicalDataset.data` DataFrame.
2. **Deterministic Output**: Execution on the same `CanonicalDataset` produces identical profile metrics. Sample lists and top frequent value rankings enforce explicit, deterministic sorting rules.
3. **No Premature Semantic Reasoning**: Profiling reports physical observations (e.g., `"high_missingness"`, `"constant_column"`), but **does NOT** assign semantic roles (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`). Semantic classification is deferred to Step 4 (Semantic Intelligence).
4. **No AI/LLM Involvement**: Calculated entirely using deterministic Python/Pandas/NumPy logic.

---

## Profiling Calculations

### 1. Dataset-Level Summary (`dataset_summary`)
- `row_count`: Total rows.
- `column_count`: Total columns.
- `duplicate_row_count` & `duplicate_row_percentage`: Rows with identical values across all columns.
- `total_cells`: `row_count * column_count`.
- `overall_missing_count` & `overall_missing_percentage`: Aggregate null counts across all cells.

### 2. Column-Level Statistics (`column_statistics`)
- **Universal Metrics**: `total_count`, `non_null_count`, `null_count`, `null_percentage`, `distinct_count`, `is_unique`, `is_constant`, `is_all_null`, `observations`.
- **Numeric Columns** (`int`, `float`): `min`, `max`, `mean`, `median`, `std`, `q25`, `q75`, `zero_count`, `negative_count`, `infinite_count`.
- **Categorical / Text Columns**: `empty_string_count`, `most_frequent_values` (top 10 values sorted by count descending, then value string ascending).
- **Datetime Columns**: `min_datetime`, `max_datetime`, `distinct_dates_count`.
- **Boolean Columns**: `true_count`, `false_count`.

### 3. Pearson Correlation Matrix (`correlation_matrix`)
Calculates pairwise numerical Pearson correlation coefficients across columns with numeric data types when $\ge 2$ numeric columns and $\ge 2$ rows exist.

### 4. Data Quality Observations (`quality_issues`)
Non-destructive flags identifying data quality characteristics:
- `duplicate_rows`: Dataset contains duplicate records.
- `all_null_column`: Column contains 100% missing values.
- `high_missingness`: Column contains $\ge 50\%$ missing values.
- `constant_column`: Column contains only 1 distinct non-null value.

---

## Edge Case Resilience

- **Empty / 0-row Datasets**: Safely returns 0 counts and `None` statistics without crashing.
- **Single-value or All-Null Columns**: Sets boolean flags (`is_constant=True`, `is_all_null=True`) and skips invalid statistical calculations.
- **Infinity Values**: Counts `inf` / `-inf` separately in float columns.
- **Fault-Tolerant Execution**: Column calculation exceptions are caught per column to prevent a single bad column from crashing the entire profiling run.
