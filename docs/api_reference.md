# REST API Reference Manual

**Status:** IMPLEMENTED & AUDITED  
**Base URL:** `http://localhost:8000/api` (Swagger UI at `http://localhost:8000/docs`)  
**Specification Version:** 1.0.0  

---

## 1. System Health & Provider Endpoints

### 1.1 System Health
`GET /api/health`
- **Description**: Verifies API operational status and reports engine capabilities.
- **Response**: `200 OK`
```json
{
  "status": "healthy",
  "service": "DashCrate API",
  "version": "1.0.0",
  "capabilities": [
    "Data Ingestion (CSV, TSV, XLSX, Parquet)",
    "Data Profiling",
    "Rule-Based Semantic Intelligence",
    "Schema Readiness Assessment"
  ]
}
```

### 1.2 Provider Status
`GET /api/providers/status`
- **Description**: Reports availability, configured models, and connectivity status for LLM providers.
- **Response**: `200 OK`
```json
{
  "providers": [
    {
      "provider": "gemini",
      "status": "live",
      "model": "gemini-2.5-flash",
      "is_baseline": true
    },
    {
      "provider": "groq",
      "status": "failed",
      "model": "llama-3.3-70b-versatile",
      "reason": "GROQ_API_KEY not set"
    }
  ]
}
```

---

## 2. Dataset Ingestion & Metadata Endpoints

### 2.1 Upload Dataset
`POST /api/datasets/upload`
- **Content-Type**: `multipart/form-data`
- **Body**: `file` (File stream: `.csv`, `.tsv`, `.xlsx`, `.parquet`, max 100MB)
- **Response**: `201 Created` (`DatasetMetadataResponse`)
- **Errors**: `400 Bad Request` (Invalid file structure), `413 Payload Too Large` (> 100MB).

### 2.2 List Session Datasets
`GET /api/datasets`
- **Response**: `200 OK` (`List[DatasetListItem]`) — List of active session datasets (raw and registered cleaned versions).

### 2.3 Get Dataset Metadata
`GET /api/datasets/{dataset_id}`
- **Response**: `200 OK` (`DatasetMetadataResponse`) — Full metadata including column count, row count, detected types, and semantic roles.

### 2.4 Preview Dataset Rows
`GET /api/datasets/{dataset_id}/preview?limit=50`
- **Query Parameters**: `limit` (int, default: 50)
- **Response**: `200 OK` (`DataPreviewResponse`) — Paginated row objects and column definitions.

### 2.5 Statistical Data Profile
`GET /api/datasets/{dataset_id}/profile`
- **Response**: `200 OK` (`DataProfileResponse`) — Statistical metrics: cardinality, missingness rate, skewness, quantiles, min, max, mean, median.

### 2.6 Semantic Role Profile
`GET /api/datasets/{dataset_id}/semantic-analysis` (Alias: `/api/datasets/{dataset_id}/semantics`)
- **Response**: `200 OK` (`SemanticProfileResponse`) — Inferred roles (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`), sub-roles (`PRIMARY_KEY`, `FOREIGN_KEY`, `DERIVED`), and confidence scores.

### 2.7 Schema Readiness Assessment
`GET /api/datasets/{dataset_id}/readiness`
- **Response**: `200 OK` (`AnalysisReadinessResponse`) — Assessment status (`READY`, `READY_WITH_WARNINGS`, `NOT_READY`) and gate checks.

### 2.8 Quality Assessment
`GET /api/datasets/{dataset_id}/quality-assessment` (Alias: `/api/datasets/{dataset_id}/quality`)
- **Response**: `200 OK` (`QualityAssessment`) — Overall quality health score (0–100%) and metrics for completeness, uniqueness, consistency, and validity.

### 2.9 Download Dataset
`GET /api/datasets/{dataset_id}/download?format=csv`
- **Query Parameters**: `format` (`csv` or `xlsx`, default: `csv`)
- **Response**: `200 OK` (Stream with `Content-Disposition: attachment; filename="<name>"`).

---

## 3. Data Studio & Cleaning Endpoints

### 3.1 Get Cleaning Recommendations
`GET /api/datasets/{dataset_id}/cleaning`
- **Response**: `200 OK` (`CleaningReport`) — List of recommended cleaning actions across missing values, duplicates, outliers, and data types.

### 3.2 Get Cleaning Plan
`GET /api/datasets/{dataset_id}/cleaning-plan`
- **Response**: `200 OK` (`CleaningPlan`) — Structured execution plan detailing proposed operations and default parameters.

### 3.3 Get Cleaned Dataset Summary
`GET /api/datasets/{dataset_id}/cleaning-summary` (Alias: `/api/datasets/{dataset_id}/cleaning/summary`)
- **Response**: `200 OK` (`CleanedDatasetSummaryResponse`) — Authoritative summary of the current cleaned state: row/col count delta, null reductions, duplicates removed, and applied operations audit log.

### 3.4 Preview Custom Column Transformation
`POST /api/datasets/{dataset_id}/cleaning/column-transform/preview`
- **Body**: `ColumnTransformPreviewRequest` (`column_name`, `operation`, `parameters`)
- **Response**: `200 OK` (`ColumnTransformPreviewResponse`) — Cell diffs showing before and after sample values.

### 3.5 Multi-Valued Cell Detection & Operations
- `GET /api/datasets/{dataset_id}/cleaning/multivalue/candidates`: Detects columns containing delimited values.
- `POST /api/datasets/{dataset_id}/cleaning/multivalue/preview`: Non-mutating preview of `SPLIT_COLUMNS` or `EXPAND_ROWS`.
- `POST /api/datasets/{dataset_id}/cleaning/multivalue/apply`: Applies multi-valued cell handling to in-memory draft.

### 3.6 Structural Cleaning Operations
- `GET /api/datasets/{dataset_id}/cleaning/structural/recommendations`: Structural suggestions (constant columns, high missingness).
- `POST /api/datasets/{dataset_id}/cleaning/structural/drop-columns/preview` & `/apply`: Drop one or more columns.
- `POST /api/datasets/{dataset_id}/cleaning/structural/filter-rows/preview` & `/apply`: Filter rows using structured conditions (`==`, `!=`, `<`, `>`, `contains`, etc.).
- `POST /api/datasets/{dataset_id}/cleaning/structural/duplicates/preview` & `/apply`: Deduplicate rows (`keep='first'` or `'last'`).
- `POST /api/datasets/{dataset_id}/cleaning/structural/semantic-role/preview` & `/apply`: Override semantic roles with physical dtype validation.

### 3.7 Cleaning Batch Preview & Apply
- `POST /api/datasets/{dataset_id}/cleaning/preview`: Preview batch of selected recommendations.
- `POST /api/datasets/{dataset_id}/cleaning/apply`: Apply selected transformations to in-memory draft.

### 3.8 Register Cleaned Dataset
`POST /api/datasets/{dataset_id}/cleaned/register`
- **Response**: `200 OK` (`RegisterCleanedDatasetResponse`)
- **Behavior**: Promotes in-memory cleaned draft into an independent, first-class `CanonicalDataset` (`ds_<stem>_cleaned_<uuid>`) with independent profiling, semantics, and readiness, leaving raw dataset untouched.

---

## 4. Exploratory Data Analysis (EDA) Endpoints

### 4.1 Automated EDA Summary
`GET /api/datasets/{dataset_id}/eda`
- **Response**: `200 OK` (`EDASummary`)
- **Payload**: Compact dataset profile, 10-bin numeric histograms with skewness, categorical top 10 frequencies, Pearson correlation matrix, temporal analysis, and factual observations.

### 4.2 Manual Ad-Hoc Slicing & Exploration
`POST /api/datasets/{dataset_id}/eda/explore`
- **Body**: `EDAExploreRequest` (`column_x`, `column_y`, `aggregation`, `sample_limit`)
- **Response**: `200 OK` (`EDAExploreResult`) — Formatted chart coordinates (scatter, line, or grouped bar) with deterministic sampling if row count $> 1,000$.

---

## 5. Autonomous Overview & Dashboard Endpoints

### 5.1 Generate Autonomous Overview Dashboard
`POST /api/overview` (Alias: `/api/overview-dashboard`)
- **Body**: `OverviewDashboardRequest` (`dataset_id`, `use_llm`)
- **Response**: `200 OK` (`OrchestratorPipelineResponse`)
- **Payload**: Full `DashboardSpec` with 12-column grid layout (Row 1 KPI strip, Row 2 Hero + Side, Row 3+ supporting grid), runtime slicers, and statistical evidence badges.

### 5.2 Dynamic Tile Query Recompilation
`POST /api/dashboard/{spec_id}/tile/{tile_id}/query`
- **Body**: `TileQueryRequest` (`filters: [{column, operator, values}]`)
- **Response**: `200 OK` (`TileQueryResponse`)
- **Payload**: Recomputed data rows, row count, execution status, and compiled SQL with injected runtime filters.

---

## 6. Dataset Chat & Natural Language Query Endpoints

### 6.1 Conversational Dataset Chat Turn
`POST /api/chat` (Alias: `/api/dataset-chat`)
- **Body**: `ChatRequest` (`dataset_id`, `message`, `conversation_id`, `use_llm`)
- **Response**: `200 OK` (`ChatResponse`)
- **Payload**: Assistant explanation, intent type, compiled DuckDB SQL, tabular data rows, chart configuration, grounding verification, and follow-up prompt suggestions.

### 6.2 Clear Conversation History
`POST /api/chat/conversation/{dataset_id}/{conversation_id}/clear`
- **Response**: `200 OK` (`{status: "SUCCESS", cleared: true, conversation_id: "..."}`)
- **Behavior**: Resets multi-turn thread memory for the specified conversation.

---

## 7. Orchestrator Pipeline Endpoints (Focused Mode)

### 7.1 Run Orchestration Pipeline
`POST /api/orchestrator/pipeline` (Alias: `/pipeline`)
- **Body**: `OrchestratorPipelineRequest` (`dataset_id`, `intent`, `mode`, `k`, `require_clarification`)
- **Response**: `200 OK` (`OrchestratorPipelineResponse`)

### 7.2 Resolve Ambiguity / Pipeline Clarification
`POST /api/orchestrator/pipeline/resolve` (Alias: `/pipeline/resolve`)
- **Body**: `ResolvePipelineRequest` (`run_id`, `selected_plan_id`)
- **Response**: `200 OK` (`OrchestratorPipelineResponse`)
