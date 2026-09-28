# Orchestrator Contracts

This document formally specifies the input/output contracts for all orchestrator
data structures. It is the reference document for implementation in `orchestrator/schemas.py`.

All schemas are Pydantic v2 models. Immutability is enforced via `model_config = {"frozen": True}`.

---

## 1. CandidatePlan

**File:** `orchestrator/schemas.py::CandidatePlan`

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `plan_id` | `str` (UUID) | auto | Unique plan identifier |
| `dataset_id` | `str` | yes | ID of the CanonicalDataset this plan operates on |
| `intent` | `str` | yes | Natural-language analytical request |
| `metric` | `MetricSpec` | yes | Primary metric: `{column, aggregation}` |
| `dimensions` | `List[DimensionSpec]` | default=[] | Grouping dimensions: `[{column, granularity?}]` |
| `filters` | `List[FilterSpec]` | default=[] | Column filter predicates |
| `comparison` | `Optional[ComparisonSpec]` | default=None | Period/segment comparison |
| `visualization` | `VisualizationType` | default=TABLE | Proposed chart type |
| `reasoning` | `PlanReasoning` | yes | LLM interpretation and evidence strings |

### MetricSpec

| Field | Type | Constraint |
| :--- | :--- | :--- |
| `column` | `str` | Must exist in DatasetSemanticProfile |
| `aggregation` | `AggregationType` | Whitelist: SUM, AVG, MIN, MAX, COUNT, COUNT_DISTINCT, STDDEV, MEDIAN |

### DimensionSpec

| Field | Type | Constraint |
| :--- | :--- | :--- |
| `column` | `str` | Must exist in DatasetSemanticProfile |
| `granularity` | `Optional[Granularity]` | Only valid when column has DATETIME role (Pass 1a enforces) |

### Whitelisted Enums

**AggregationType:** SUM, AVG, MIN, MAX, COUNT, COUNT_DISTINCT, STDDEV, MEDIAN
**Granularity:** YEAR, QUARTER, MONTH, WEEK, DAY, HOUR
**VisualizationType:** BAR, LINE, AREA, PIE, SCATTER, TABLE, KPI, HEATMAP

---

## 2. plan_signature() — Deduplication

**File:** `orchestrator/schemas.py::CandidatePlan.plan_signature()`

Returns a SHA-256 hex digest of the structural signature. Two plans are
"materially different" when they differ in:

- `dataset_id`
- `metric.column`
- `metric.aggregation`
- `dimensions[*].column` (sorted)
- `dimensions[*].granularity` (sorted)
- `filters[*].column + operator + value` (sorted)
- `comparison.column + value`
- `comparison` presence/absence

**Visualization and reasoning do NOT affect the signature.**

---

## 3. AmbiguityResult

**File:** `orchestrator/schemas.py::AmbiguityResult`

| Field | Type | Description |
| :--- | :--- | :--- |
| `status` | `AmbiguityStatus` | CLEAR / AMBIGUOUS / UNANSWERABLE |
| `ambiguities` | `List[AmbiguityDetail]` | Non-empty only for AMBIGUOUS or UNANSWERABLE |
| `message` | `Optional[str]` | Human-readable summary |

### AmbiguityStatus semantics

| Status | Meaning |
| :--- | :--- |
| CLEAR | Request is unambiguous; proceed to LLM plan generation |
| AMBIGUOUS | Multiple valid interpretations exist; return `alternatives` to user |
| UNANSWERABLE | Required columns/KPIs do not exist in the dataset; never invent formulas |

### AmbiguityType vocabulary

MULTIPLE_MEASURES, MULTIPLE_DATE_COLUMNS, MULTIPLE_GROUP_BYS,
MISSING_AGGREGATION, MISSING_COLUMN, UNKNOWN_KPI, UNKNOWN_ROLE

---

## 4. LLMContext

**File:** `orchestrator/schemas.py::LLMContext`

The compact structured context sent to the LLM. **Raw data rows are NEVER included.**

| Field | Type | Description |
| :--- | :--- | :--- |
| `dataset_id` | `str` | Dataset identifier |
| `intent` | `str` | Natural-language request |
| `columns` | `List[ColumnContextEntry]` | Request-relevant columns only |
| `context_hash` | `str` | SHA-256 of dataset_id + intent + column names |
| `generated_at` | `str` | ISO 8601 UTC timestamp |

### ColumnContextEntry

Per-column data sent to LLM: `column_name`, `candidate_role`, `confidence`,
`confidence_level`, `evidence` (list of rule strings), `distinct_count`,
`null_percentage`, `dtype`. **No sample values. No raw data rows.**

---

## 5. ExecutionResult

**File:** `orchestrator/schemas.py::ExecutionResult`

DuckDB worker output. Includes failed-cast tracking per C2 binding resolution.

| Field | Type | Description |
| :--- | :--- | :--- |
| `plan_id` | `str` | Matching CandidatePlan.plan_id |
| `status` | `ExecutionStatus` | SUCCESS / TIMEOUT / MEMORY_EXCEEDED / SYNTAX_ERROR / RUNTIME_ERROR |
| `rows` | `List[Dict]` | Result rows (empty on failure) |
| `columns` | `List[str]` | Output column names |
| `row_count` | `int` | Total result row count |
| `compiled_sql` | `Optional[str]` | Compiled DuckDB SQL for audit |
| `failed_cast_count` | `int` | Count of TRY_CAST(col AS TIMESTAMP) NULLs |
| `failed_cast_rate` | `float` | failed_cast_count / total_rows_examined |
| `warnings` | `List[str]` | Non-fatal warnings including cast failure summaries |
| `error_message` | `Optional[str]` | Error detail on failure |
| `runtime_seconds` | `float` | Worker execution time |

### Pass 1b failure triggers

| Condition | Threshold |
| :--- | :--- |
| Empty result | row_count == 0 |
| All-null metrics | All metric column values are NULL |
| Row cap exceeded | row_count > RESULT_ROW_CAP (config default: 50,000) |
| High failed-cast rate | failed_cast_rate > FAILED_CAST_RATE_THRESHOLD (config default: 0.50) |

---

## 6. Validation Results

### Pass1aResult — Pre-Dispatch (Before DuckDB)

Checks (in order):
1. Dataset readiness != NOT_READY (C3 gate)
2. Metric column exists in DatasetSemanticProfile
3. Dimension columns exist in DatasetSemanticProfile
4. Role/aggregation compatibility (MEASURE for SUM/AVG/etc., IDENTIFIER rejected)
5. DATETIME required for any Granularity
6. UNKNOWN role rejected for automatic KPI metrics (produces FAILED, not warning)
7. LOW confidence on metric column produces WARNING (not rejection)
8. Plan structural validity (required fields present)

### Pass1bResult — Post-Execution (Before Ranking)

Checks (in order):
1. Non-empty result (row_count > 0)
2. Not all-null across metric values
3. Row count <= RESULT_ROW_CAP
4. failed_cast_rate <= FAILED_CAST_RATE_THRESHOLD
5. No unrecoverable DuckDB errors (TIMEOUT, MEMORY_EXCEEDED counted)

### Pass2Result — Winner Only

Checks:
1. Plan-vs-result consistency (metric column in output columns)
2. Visualization suitability (KPI requires single value, LINE requires time dimension, etc.)
3. Failure triggers runner-up cascade (capped at MAX_CASCADE_DEPTH)

### CandidateConsistencyCheck

Verifies surviving Pass-1 candidates share:
- Same metric column semantics
- Same temporal granularity (time basis)
- Same output column schema

---

## 7. RankedCandidate

| Field | Type | Description |
| :--- | :--- | :--- |
| `plan` | `CandidatePlan` | The candidate plan |
| `execution_result` | `ExecutionResult` | DuckDB worker output |
| `pass1a` | `Pass1aResult` | Pre-dispatch validation outcome |
| `pass1b` | `Pass1bResult` | Post-execution validation outcome |
| `score_breakdown` | `ScoreBreakdown` | Ranker V1 component scores |
| `rank` | `int` | 1-based rank (1 = winner) |
| `is_winner` | `bool` | True for the plan selected for Pass 2 |

---

## 8. DashboardSpec

Final orchestrator output.

| Field | Type | Description |
| :--- | :--- | :--- |
| `spec_id` | `str` (UUID) | Unique specification identifier |
| `dataset_id` | `str` | Source dataset |
| `intent` | `str` | Original natural-language request |
| `winner` | `RankedCandidate` | Winning candidate (passed Pass 2) |
| `alternate_interpretations` | `List[AlternateInterpretation]` | Runner-up candidates |
| `trace` | `OrchestratorTrace` | Full execution audit trail |
| `created_at` | `str` | ISO 8601 UTC timestamp |
| `is_tie` | `bool` | True when clarification was triggered due to tie |

---

## 9. OrchestratorTrace (Full Audit Trail)

| Field | Type | Description |
| :--- | :--- | :--- |
| `request_id` | `str` (UUID) | Unique request identifier |
| `dataset_id` | `str` | Dataset |
| `intent` | `str` | Request |
| `context_hash` | `str` | SHA-256 of LLMContext inputs |
| `generated_at` | `str` | ISO 8601 UTC |
| `ambiguity_result` | `Optional[AmbiguityResult]` | Ambiguity pre-check result |
| `llm_call_count` | `int` | Total LLM API calls made |
| `llm_token_usage` | `int` | Total tokens consumed |
| `llm_latency_seconds` | `float` | Total LLM time |
| `plans_generated` | `int` | Plans returned by LLM |
| `plans_passed_pass1a` | `int` | Plans passing pre-dispatch validation |
| `plans_passed_pass1b` | `int` | Plans passing post-execution validation |
| `reprompt_count` | `int` | Number of DuckDB error re-prompts |
| `cascade_depth` | `int` | Number of runner-up cascade steps |
| `ranker_weights` | `Optional[RankerWeights]` | Weights used for this ranking |
| `pass2_result` | `Optional[Pass2Result]` | Pass 2 winner validation outcome |
| `consistency_check` | `Optional[CandidateConsistencyCheck]` | Consistency check result |
| `total_runtime_seconds` | `float` | End-to-end wall time |
