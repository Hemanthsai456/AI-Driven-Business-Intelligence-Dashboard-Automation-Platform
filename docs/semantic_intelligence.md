# Rule-Based Semantic Intelligence Specification

## Overview

The **Semantic Intelligence Foundation** (Step 4) in the **AI-Driven Business Intelligence & Dashboard Automation Platform** provides a deterministic, explainable rule engine that analyzes column physical dtypes, cardinality metrics, profile statistics, and naming patterns to assign preliminary candidate semantic roles (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, `UNKNOWN`).

```
+-------------------+      +-------------------+      +-------------------------+
|  CanonicalDataset | ---> | SemanticAnalyzer  | ---> | DatasetSemanticProfile  |
|   + DataProfile   |      |   (Rule Engine)   |      |  (Candidate Roles & Ev) |
+-------------------+      +-------------------+      +-------------------------+
                                                                   |
                                                                   v
                                                      [ Future AI / LLM Layer ]
```

---

## Key Principles & Scope Boundaries

1. **AI for Reasoning, Code for Execution**: This step establishes structured physical evidence using deterministic code. No LLM calls are made at this stage.
2. **Explainable Output**: Every candidate classification produces an explicit `evidence` array detailing the specific signals evaluated (e.g., `"numeric key/code pattern (id token overrides numeric dtype)"`).
3. **Read-Only Invariance**: Semantic analysis never mutates the underlying `pandas.DataFrame`, converts column dtypes, or renames headers.
4. **Candidate Classifications**: Roles represent candidate hypothesis classifications. Ambiguous columns return `ColumnRole.UNKNOWN` with low confidence rather than creating false certainty.

---

## Semantic Role Definitions & Evidence Signals

### 1. MEASURE
- **Definition**: Quantitative fields that can meaningfully participate in numerical aggregations (`SUM`, `AVG`, `MIN`, `MAX`).
- **Evidence Signals**: Numeric dtypes (`int64`, `float64`), non-unique distribution, high distinct count, measure naming tokens (`amount`, `revenue`, `sales`, `price`, `cost`, `qty`, `count`, `total`).
- **Disambiguation**: Low-cardinality numerics (e.g., status codes 1-4) or numeric keys (`customer_id`) are distinguished from true measures.

### 2. DIMENSION
- **Definition**: Categorical fields used for grouping, filtering, slicing, or segmenting.
- **Evidence Signals**: Text/object/categorical dtypes, boolean dtypes, repeated categorical values, moderate cardinality, dimension naming tokens (`category`, `type`, `status`, `city`, `dept`).

### 3. DATETIME
- **Definition**: Temporal date or timestamp information.
- **Evidence Signals**: Native `datetime64` dtypes ($\rightarrow$ HIGH confidence), date naming tokens (`date`, `time`, `timestamp`, `created_at`) on string columns ($\rightarrow$ MEDIUM candidate confidence without type conversion).

### 4. IDENTIFIER
- **Definition**: Keys or unique identifiers used to distinguish entities or records.
- **Evidence Signals**: Uniqueness ratio $\approx 1.0$, identifier naming tokens (`id`, `_id`, `code`, `key`, `uuid`), surrogate key patterns.
- **Conflict Resolution**: Unique ratio $\approx 1.0$ + `_id` suffix overrides numeric dtype (e.g., `customer_id` is classified as `IDENTIFIER`, not `MEASURE`).

### 5. UNKNOWN
- **Definition**: Default state when evidence is insufficient, contradictory, or unclassified (e.g., 100% all-null columns, constant columns, ambiguous integer years).

---

## Confidence Scoring

Confidence scores are deterministically assigned based on evidence signal alignment:

| Category | Score Range | Description |
| :--- | :--- | :--- |
| `HIGH` | 0.85 – 0.95 | Multiple strong, non-conflicting physical and naming signals agree. |
| `MEDIUM` | 0.60 – 0.84 | Plausible candidate role with partial naming or physical evidence. |
| `LOW` | 0.30 – 0.59 | Weak or conflicting evidence (e.g., constant columns, ambiguous codes). |
| `NONE` | 0.00 | 100% missing / empty columns. |

---

## Output Contract & Explainability

```json
{
  "dataset_id": "ds_sales_data",
  "generated_at": "2026-09-15T11:48:00Z",
  "column_evidences": {
    "total_sales": {
      "column_name": "total_sales",
      "candidate_role": "MEASURE",
      "confidence": 0.92,
      "confidence_level": "HIGH",
      "evidence": [
        "numeric datatype (float64)",
        "distinct count: 482",
        "non-unique numeric distribution",
        "measure naming indicator: 'total_sales'"
      ]
    },
    "customer_id": {
      "column_name": "customer_id",
      "candidate_role": "IDENTIFIER",
      "confidence": 0.90,
      "confidence_level": "HIGH",
      "evidence": [
        "high uniqueness ratio (500/500 = 1.00)",
        "identifier naming pattern ('customer_id')",
        "numeric key/code pattern (id token overrides numeric dtype)"
      ]
    }
  }
}
```

---

## Future AI / LLM Preparation

The `DatasetSemanticProfile` provides structured physical evidence that will be passed to downstream AI agents in future phases:
- LLM agents inspect column names, data dtypes, physical statistics, rule-based candidate roles, confidence levels, and explicit evidence statements.
- **V1 Scope Note :** Role refinement or role reassignment by the LLM is explicitly **out of scope for V1**. The candidate roles and confidence scores produced by `DatasetSemanticProfile` serve as the frozen, authoritative, read-only semantic context for intent interpretation and query compilation.

