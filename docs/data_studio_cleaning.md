# Data Studio & Cleaning Pipeline Specification

**Status:** IMPLEMENTED & AUDITED  
**Audience:** Data Engineers, Analytics Engineers, Frontend Developers  

---

## 1. Overview of Data Studio

**Data Studio** (`/data-studio`) is an interactive, analytical workbench providing data analysts with complete visibility and deterministic control over dataset quality, profiling, transformations, and exploratory analysis.

The Data Studio is organized into **five dedicated tabs**:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   DATA STUDIO                                   │
├───────────────┬───────────────┬─────────────────┬───────────────┬───────────────┤
│ 1. Overview   │ 2. Quality    │ 3. Profiling    │ 4. Cleaning   │ 5. EDA        │
└───────────────┴───────────────┴─────────────────┴───────────────┴───────────────┘
```

1. **Overview Tab (`OverviewTab.tsx`)**: High-level dataset summary, file format details, row/column counts, memory usage, semantic role breakdowns (Measures, Dimensions, Datetimes, Identifiers), and paginated data preview.
2. **Quality Tab (`QualityTab.tsx`)**: Global quality health score (0–100%), metric gauges for Completeness, Uniqueness, Consistency, and Validity, plus actionable issue cards categorized by severity (Critical, Warning, Info).
3. **Profiling Tab (`ProfilingTab.tsx`)**: Deep column-by-column statistical profiling: data types, distinct count, null count/percentage, min/max/mean/median, quantiles (Q25, Q75), IQR, skewness, and frequent values.
4. **Cleaning Tab (`CleaningTab.tsx`)**: Interactive transformation workbench featuring automated recommendations, user-guided column transformations, multi-valued cell handling, structural operations, pre-registration summary, registration, and CSV/XLSX export.
5. **EDA Tab (`EDATab.tsx`)**: Automated exploratory data analysis generating numeric distribution histograms, categorical bar charts, correlation heatmaps, chronological time series, and manual ad-hoc bivariate/multivariate queries.

---

## 2. Ingestion & Canonical Representation

Data Studio operates on the immutable **`CanonicalDataset`** representation produced by the ingestion engine (`ingestion/`):
- Supported formats: `.csv`, `.tsv`, `.xlsx`, and `.parquet` (up to 100MB).
- Strict non-mutating invariant: the uploaded dataset's underlying `DataFrame` is never modified in place.
- All column metadata is extracted and typed into `ColumnMetadata` with inferred physical dtypes (`int64`, `float64`, `string`, `datetime64`, `bool`).

---

## 3. Data Quality Assessment Framework

The quality engine (`intelligence/quality_assessor.py`) evaluates tabular health across four dimensions:

$$\text{Quality Score} = w_1 \cdot \text{Completeness} + w_2 \cdot \text{Uniqueness} + w_3 \cdot \text{Consistency} + w_4 \cdot \text{Validity}$$

Where:
- **Completeness**: Ratio of non-null cells across the dataset:
  $$\text{Completeness} = 1.0 - \frac{\sum \text{null\_count}}{\text{total\_cells}}$$
- **Uniqueness**: Assessment of full-row duplicate rate and primary key identifier uniqueness:
  $$\text{Uniqueness} = 1.0 - \frac{\text{duplicate\_rows}}{\text{total\_rows}}$$
- **Consistency**: Evaluates mixed data types in string columns, irregular dates, and pattern divergence.
- **Validity**: Evaluates negative values in non-negative domains, outliers beyond $3\sigma$, and structural anomalies.

---

## 4. Automated Cleaning & Transformation Lifecycle

Cleaning follows an explicit four-step audit-grade lifecycle:

```
┌────────────────────────────────┐
│ 1. Recommendation Planning     │  (Automated detection of issues)
└───────────────┬────────────────┘
                │
┌───────────────▼────────────────┐
│ 2. Interactive User Selection  │  (Select rules, choose variants, configure values)
└───────────────┬────────────────┘
                │
┌───────────────▼────────────────┐
│ 3. Dry-Run Preview             │  (Sample cell-level diffs, row/col count predictions)
└───────────────┬────────────────┘
                │
┌───────────────▼────────────────┐
│ 4. Execution & Registration    │  (Apply to deep copy, review summary, register new dataset)
└────────────────────────────────┘
```

### 4.1 Supported Transformation Operations (`cleaning/executor.py`)

The transformation engine supports targeted operations on individual columns or entire datasets:

| Operation Key | Category | Behavior |
| :--- | :--- | :--- |
| `REMOVE_DUPLICATES` | Structural | Removes identical rows, resetting dataframe index. |
| `NORMALIZE_EMPTY_STRINGS` | Value Normalization | Converts `""`, `"   "`, `"N/A"`, `"null"`, `"None"` to actual `NaN`. |
| `TRIM_WHITESPACE` | Value Normalization | Strips leading and trailing whitespace from string columns. |
| `IMPUTE_MEDIAN` | Missing Value Handling | Fills numeric missing values using column median (robust to outliers). |
| `IMPUTE_MEAN` | Missing Value Handling | Fills numeric missing values using column mean. |
| `IMPUTE_MODE` | Missing Value Handling | Fills categorical missing values using the most frequent value. |
| `IMPUTE_UNKNOWN` | Missing Value Handling | Fills categorical missing values with `"Unknown"`. |
| `IMPUTE_SPECIFIC_VALUE` | Missing Value Handling | Fills missing cells with user-provided constant value. |
| `CONVERT_NUMERIC` | Type Conversion | Strips currency symbols (`$`, `€`, `£`, `₹`) and commas, converting to float. |
| `CONVERT_INTEGER` | Type Conversion | Coerces numeric column to nullable integer (`Int64`). |
| `CONVERT_FLOAT` | Type Conversion | Coerces numeric column to standard float. |
| `CONVERT_DATETIME` | Type Conversion | Parses string column to datetime with ISO format standardisation. |
| `NORMALIZE_BOOLEAN` | Type Conversion | Standardizes `"yes"/"no"`, `"true"/"false"`, `"1"/"0"` to boolean. |
| `LEAVE_UNCHANGED` | User Override | Explicitly retains column in original state. |

---

## 5. Structural Row and Column Operations (`cleaning/structural.py`)

Data Studio provides full deterministic control over dataset structure:

### 5.1 Column Dropping
- Supports single or multi-column removal.
- Prevents dropping all columns (at least 1 column must remain).
- Provides preview showing dropped columns and remaining schema.

### 5.2 Condition-Based Row Filtering
Allows removing rows based on structured conditions:
- **Supported Operators**: `equals` (`==`), `not equals` (`!=`), `greater than` (`>`), `less than` (`<`), `greater than or equal` (`>=`), `less than or equal` (`<=`), `contains`, `missing`, `not_missing`.
- **Compound Logic**: Multiple conditions combined with `AND` (all match) or `OR` (any match).
- **Preview**: Emits preview showing matched row count, percentage of rows to be dropped, and sample removed rows.

### 5.3 Duplicate Row Removal
- Configurable retention strategy: `keep='first'` or `keep='last'`.
- Deduplication over all columns or over specific user-selected subset of key columns.

### 5.4 Semantic Role Overrides
- Users can override inferred semantic roles: `MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, or `UNKNOWN`.
- **Physical Dtype Validation**: The engine enforces safety rules preventing incompatible assignments (e.g., non-numeric string column cannot be assigned `MEASURE`).

---

## 6. Multi-Valued Cell Detection & Handling (`cleaning/multivalue.py`)

Columns containing packed lists (e.g., `"Python;SQL;Java"`, `"10,20,30"`, `"Red|Green|Blue"`) hinder analytical grouping and aggregations.

### 6.1 Detection Heuristic
- Detects delimiters: `,` (comma), `;` (semicolon), `|` (pipe), `/` (slash), `:` (colon).
- **Thousands Separator Guard**: Avoids false positives on formatted financial numbers (e.g., `"1,250.50"` or `"1,000,000"`) via regex `^\s*[-+]?[\$€£¥₹]?\s*\d{1,3}(,\d{3})+(\.\d+)?`.
- Classifies confidence (`HIGH`, `MEDIUM`, `LOW`) based on affected row percentage and average values per row.

### 6.2 Available Handling Strategies
1. **KEEP AS IS**: Leaves column untouched.
2. **SPLIT INTO COLUMNS**: Splits values into multiple new columns (e.g., `Skills_1`, `Skills_2`) using collision-safe naming.
3. **EXPAND INTO ROWS (Unnest)**: Explodes delimited values into distinct rows, duplicating context columns. Generates clear warnings about row count inflation.

---

## 7. Cleaned Dataset Summary Before Registration

To prevent blind registrations, Data Studio displays an authoritative **Cleaned Dataset Summary** card before the user commits to registering the cleaned dataset:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CURRENT CLEANED DATASET SUMMARY                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  Original Shape:   1,000 rows × 12 columns                                  │
│  Current Shape:      942 rows × 11 columns                                  │
│  Rows Removed:        58 rows (5.8%)                                        │
│  Columns Dropped:      1 column                                             │
│  Nulls Imputed:      134 values                                             │
│  Duplicates Removed:  12 rows                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  Applied Operations Log (Audit Trail):                                      │
│  • [Structural] Dropped column 'InternalNotes'                              │
│  • [Deduplication] Removed 12 duplicate rows                                │
│  • [Imputation] Imputed median (42.5) for column 'Age' (14 missing)         │
│  • [Type Cast] Converted 'OrderDate' to ISO Datetime                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  [ Register Cleaned Dataset ]               [ Download CSV ]  [ Download XLSX ]│
└─────────────────────────────────────────────────────────────────────────────┘
```

The summary card reflects the **actual current cleaned state**, derived directly from the in-memory cleaned DataFrame and recorded operations.

---

## 8. Cleaned Dataset Registration Lifecycle

When the user clicks **Register Cleaned Dataset** (`POST /api/datasets/{dataset_id}/cleaned/register`):

1. **Distinct Identity Generation**: A collision-safe dataset ID is created:
   `ds_{base_stem}_cleaned_{uuid_hex_6}` (e.g., `ds_sales_data_cleaned_3f8a1b`).
2. **Derivation Metadata**: The new dataset records provenance links to its parent:
   `source_dataset_id`, `derivation: "cleaning"`, and `operations_applied`.
3. **Independent Profiling & Validation**: The registered cleaned dataset passes through:
   - Full statistical profiling (`profile_dataset`).
   - Semantic role analysis (`analyze_semantics`).
   - Schema readiness validation (`assess_readiness`).
   - Re-application of any existing user semantic role overrides.
4. **First-Class Storage**: Stored in `session_store` as an independent `DatasetSessionRecord`.
5. **Raw Dataset Preservation**: The original raw dataset remains pristine and unmutated in the store. Users can switch between raw and cleaned versions anywhere in the application.

---

## 9. Dataset Downloads

Users can export either the raw or cleaned dataset at any time via:
- `GET /api/datasets/{dataset_id}/download?format=csv`
- `GET /api/datasets/{dataset_id}/download?format=xlsx`

Downloads stream directly with correct MIME types (`text/csv` or `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) and filename headers.
