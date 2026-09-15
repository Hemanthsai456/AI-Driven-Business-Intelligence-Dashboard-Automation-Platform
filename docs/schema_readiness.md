# Schema Validation & Analysis-Readiness Specification

## Overview

Step 4.2 introduces a deterministic, read-only **Schema Validation and Analysis-Readiness** layer that sits between the existing semantic intelligence output and the future DuckDB analytical engine.

```
CanonicalDataset
      +
DataProfile          ← validated if provided
      +
DatasetSemanticProfile  ← validated if provided
      ↓
SchemaValidator
      ↓
AnalysisReadiness  →  DuckDB Analytical Engine (Step 5+)
```

This layer does NOT clean, transform, normalize, or repair data.
It validates structural consistency and produces a structured readiness assessment.

---

## Purpose

Before downstream analytical components consume a dataset, the system must establish:

- **Structural integrity** — the DataFrame, its metadata, and any intelligence artifacts are mutually consistent.
- **Analysis readiness** — whether the dataset meets the minimum structural contract required for safe analytical execution.
- **Observations** — data-quality signals that analysts or the LLM layer should be aware of, without triggering any automatic data modification.

This is fundamentally different from data quality assessment (Phase 3) and data cleaning (Phase 3).

---

## Components

### `ReadinessStatus` (Enum)

| Value | Meaning |
|:--|:--|
| `READY` | All blocking checks pass. No observations. Safe to proceed to analytics. |
| `READY_WITH_WARNINGS` | Structurally valid. One or more data-quality observations are present. Downstream components may proceed but should be aware of the warnings. No data has been modified. |
| `NOT_READY` | One or more blocking structural issues prevent safe analytical execution. Downstream components must not proceed. |

### `ReadinessCheck` (dataclass)

A single evaluated check result:

| Field | Type | Description |
|:--|:--|:--|
| `check_name` | str | Machine-readable identifier (e.g., `metadata_column_names_match`) |
| `passed` | bool | True if the condition was satisfied |
| `message` | str | Human-readable explanation |
| `is_blocking` | bool | True if a failing check contributes to `NOT_READY` |

### `AnalysisReadiness` (dataclass)

The single unified result model. Designed for downstream consumption by the DuckDB analytical engine, LLM reasoning layer, and dashboard generation pipeline.

| Field | Type | Description |
|:--|:--|:--|
| `dataset_id` | str | Dataset identifier |
| `status` | ReadinessStatus | Overall readiness classification |
| `checks` | List[ReadinessCheck] | All checks evaluated, in order |
| `blocking_issues` | List[str] | Human-readable blocking issue descriptions |
| `warnings` | List[str] | Human-readable observation descriptions |
| `summary` | str | One-sentence overall summary |
| `checked_columns` | List[str] | Column names at validation time |
| `checked_row_count` | int | Row count at validation time |
| `checked_column_count` | int | Column count at validation time |
| `generated_at` | str | UTC ISO-8601 timestamp |

`to_dict()` produces a fully JSON-safe dictionary using the project's `sanitize_json_value` utility.

### `SchemaValidator` (class)

```python
validator = SchemaValidator()
readiness = validator.validate(canonical, profile=profile, semantic_profile=sem_profile)
```

### `assess_readiness()` (convenience function)

```python
from intelligence import assess_readiness

readiness = assess_readiness(canonical, profile, sem_profile)
```

---

## Validation Logic

### Checks Performed

#### Blocking Checks (→ `NOT_READY` if any fail)

| Check Name | Validates |
|:--|:--|
| `dataframe_exists` | `canonical.data` is a valid `pd.DataFrame` |
| `column_count_nonzero` | DataFrame has at least one column |
| `metadata_column_count_matches` | `len(metadata.schema) == len(df.columns)` |
| `metadata_column_names_match` | `{col.original_name} == set(df.columns)` |
| `unique_column_references` | All DataFrame column names are unique references |
| `profile_dataset_id_matches` | `profile.dataset_id == canonical.metadata.dataset_id` |
| `profile_row_count_matches` | `profile.dataset_summary["row_count"] == len(df)` |
| `profile_column_references_valid` | All `profile.column_statistics` keys exist in `df.columns` |
| `semantic_profile_column_references_valid` | All `semantic_profile.column_evidences` keys exist in `df.columns` |

Profile and semantic profile checks are only run when those artifacts are provided.

#### Informational Checks (never affect status)

| Check Name | What It Reports |
|:--|:--|
| `profile_available` | Whether a DataProfile was provided |
| `semantic_profile_available` | Whether a DatasetSemanticProfile was provided |

> A missing profile or semantic profile does **not** degrade status. Different downstream operations have different requirements. The informational check appears in `checks` so callers know what was available without the validator making assumptions about future operations.

#### Warning Checks (→ `READY_WITH_WARNINGS` if any fire)

| Check Name | Condition |
|:--|:--|
| `zero_row_warning` | `len(df) == 0` |
| `all_null_column:<col>` | Column is 100% null |
| `high_missingness:<col>` | `null_percentage >= 50.0` (and not all-null) |
| `constant_column:<col>` | Column has exactly 1 distinct non-null value |

**Warning checks never trigger any data modification.**

#### Warning threshold

The `HIGH_MISSINGNESS_THRESHOLD` is `50.0` (percent). This is documented as a heuristic. The threshold can be changed per-instance:

```python
validator = SchemaValidator()
validator.HIGH_MISSINGNESS_THRESHOLD = 30.0  # stricter threshold
```

---

## Blocking Issues vs Warnings

This distinction is critical.

**Blocking issues** indicate structural problems that would cause downstream analytical execution to produce incorrect results or crash:

- The DataFrame is missing
- Column metadata is inconsistent with the actual DataFrame
- An attached profile or semantic profile belongs to a different dataset or references columns that don't exist

**Warnings** are data-quality observations. They are surfaced so that analysts (or the future LLM layer) are aware of potential analytical limitations. They do **not** trigger any automatic action:

| Observation | What is NOT done |
|:--|:--|
| 95% null column | Values are not filled. Column is not dropped. |
| Constant column | Column is not removed. |
| Zero rows | Rows are not populated. |
| Duplicate rows (reported by profiler) | Rows are not deduplicated. |

---

## Why This Is NOT Data Cleaning

Phase 3 of the project architecture contains a dedicated data-quality assessment and cleaning pipeline. The schema validation layer is explicitly excluded from that responsibility.

Any data mutation based on warnings would:
1. Violate the read-only invariant of Steps 1–4
2. Silently alter analyst-visible data without explicit instructions
3. Undermine the explainability/audit trail

The correct architecture is: **Observe → Report → Let the pipeline decide**.

---

## Stat Source Priority

Warning checks prefer existing intelligence artifacts over raw DataFrame scans:

1. **Profile column statistics** (`profile.column_statistics[col]`) — preferred. Already computed in Step 3.
2. **ColumnMetadata fields** (`null_percentage`, `distinct_count`) — fallback when no profile is provided. Populated by ingestion loaders in Step 2.
3. **Raw DataFrame scan** — NOT performed by this layer.

This ensures `O(1)` lookup per column for warning checks.

---

## Dataset Consistency

The current architecture does not include a hash/checksum mechanism for dataset fingerprinting. Lightweight mismatch detection is performed via:

- `profile.dataset_id` vs `canonical.metadata.dataset_id`
- `profile.dataset_summary["row_count"]` vs `len(canonical.data)`
- Profile/semantic profile column reference set vs `df.columns`

If a more robust fingerprinting mechanism is added in a future step, `SchemaValidator` can be extended to use it without changing the public contract.

---

## Downstream DuckDB Contract

After `AnalysisReadiness.status == READY` or `READY_WITH_WARNINGS`, the downstream DuckDB engine can safely:

- Register `canonical.data` as a DuckDB relation
- Trust that all column names in `checked_columns` exist in the DataFrame
- Trust that `checked_row_count` and `checked_column_count` reflect the actual structure
- Use `profile.column_statistics` for query optimisation hints
- Use `semantic_profile.column_evidences` for analytical role assignment

The DuckDB layer must not proceed if `status == NOT_READY`.

---

## Read-Only Guarantee

`SchemaValidator.validate()` is completely read-only with respect to `canonical.data`:

- No `rename()`, `drop()`, `fillna()`, `astype()`, `sort_values()`, or equivalent
- No DataFrame copy is created
- The only mutation is `canonical.add_audit_entry()`, which appends to `canonical.audit_logs` — consistent with the audit-trail pattern established in Steps 2, 3, and 4

Tests verify this guarantee with `pd.testing.assert_frame_equal()` before and after validation.

---

## Audit Trail

After each validation run, the following entry is appended to `canonical.audit_logs`:

```json
{
    "timestamp": "2026-09-15T14:30:00Z",
    "action": "READINESS_CHECKED",
    "details": {
        "dataset_id": "ds_sales_2026",
        "status": "READY",
        "blocking_issue_count": 0,
        "warning_count": 0
    }
}
```

---

## Example Output

```json
{
    "dataset_id": "ds_sales_2026",
    "status": "READY_WITH_WARNINGS",
    "generated_at": "2026-09-15T14:30:00.123456+00:00",
    "summary": "Dataset 'ds_sales_2026' is structurally valid with 1 observation(s). Review warnings before analytical execution. No data has been modified.",
    "blocking_issues": [],
    "warnings": [
        "Column 'notes' has high missingness (78.0%). This is an observation only — no data has been modified."
    ],
    "checked_columns": ["order_id", "revenue", "region", "notes"],
    "checked_row_count": 5000,
    "checked_column_count": 4,
    "checks": [
        {"check_name": "dataframe_exists", "passed": true, "message": "DataFrame is present and valid.", "is_blocking": true},
        {"check_name": "column_count_nonzero", "passed": true, "message": "Dataset has 4 column(s).", "is_blocking": true},
        {"check_name": "metadata_column_count_matches", "passed": true, "message": "Metadata schema column count (4) matches DataFrame column count (4).", "is_blocking": true},
        {"check_name": "metadata_column_names_match", "passed": true, "message": "All metadata column names match DataFrame column names.", "is_blocking": true},
        {"check_name": "unique_column_references", "passed": true, "message": "All DataFrame column names are unique references.", "is_blocking": true},
        {"check_name": "profile_dataset_id_matches", "passed": true, "message": "DataProfile dataset_id matches ('ds_sales_2026').", "is_blocking": true},
        {"check_name": "profile_row_count_matches", "passed": true, "message": "DataProfile row count (5000) matches DataFrame row count (5000).", "is_blocking": true},
        {"check_name": "profile_column_references_valid", "passed": true, "message": "All DataProfile column references exist in the DataFrame.", "is_blocking": true},
        {"check_name": "profile_available", "passed": true, "message": "DataProfile is available.", "is_blocking": false},
        {"check_name": "semantic_profile_available", "passed": false, "message": "DatasetSemanticProfile is not provided. Semantic role evidence will be absent for operations that depend on it.", "is_blocking": false},
        {"check_name": "zero_row_warning", "passed": true, "message": "Dataset has 5000 row(s).", "is_blocking": false},
        {"check_name": "high_missingness:notes", "passed": false, "message": "Column 'notes' has 78.0% missing values.", "is_blocking": false}
    ]
}
```

---

## Architectural Boundary (After Step 4.2)

| Layer | Responsibility |
|:--|:--|
| **Ingestion** | Load source files; build CanonicalDataset |
| **Profiling** | Compute physical/statistical profile |
| **Semantic Intelligence** | Generate deterministic semantic evidence |
| **Schema / Readiness** | Validate consistency; assess downstream readiness |
| **Cleaning** | Phase 3 — NOT HERE |
| **Relationship Detection** | Phase 2 — NOT HERE |
| **DuckDB Analytics** | Next stage — NOT HERE |
| **LLM** | Later stage — NOT HERE |
