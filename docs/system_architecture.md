# System Architecture & Technical Design

**Status:** IMPLEMENTED & AUDITED  
**Audience:** Software Engineers, Data Architects, Machine Learning Engineers  

---

## 1. High-Level Architectural Overview

The **AI-Driven Business Intelligence & Dashboard Automation Platform** is architected as a decoupled, multi-tier system separating user interaction, cognitive reasoning, deterministic analytical computation, and stateful dataset session management.

```mermaid
flowchart TD
    subgraph UI ["Presentation Layer (Next.js 14 App Router)"]
        Nav["App Shell & Navigation"]
        DataStudioView["Data Studio (Overview, Quality, Profiling, Cleaning, EDA)"]
        DashboardView["Autonomous Overview Dashboard (12-Col Grid, Slicers)"]
        ChatView["Dataset Chat & Evidence Inspector"]
        AnalysisView["Focused Natural-Language Analysis Workspace"]
    end

    subgraph API ["API & Session Management Layer (FastAPI)"]
        RESTRouter["FastAPI Application (api/main.py)"]
        SessionStore["In-Memory Dataset Session Store (api/store.py)"]
        Record["DatasetSessionRecord (Raw Dataset, Cleaned Dataset, Overrides, Contexts)"]
    end

    subgraph Intelligence ["Data Intelligence & Profiling Engine"]
        Loaders["Format Loaders (CSV, TSV, XLSX, Parquet)"]
        Profiler["Statistical Profiler (Distributions, Cardinality, Missingness)"]
        Semantics["Semantic Analyzer (Roles: MEASURE, DIMENSION, DATETIME, PK, FK, DERIVED)"]
        Readiness["Schema Readiness Validator (READY, WARNINGS, NOT_READY)"]
        EDA["Deterministic EDA Engine (Distributions, Correlations, Trends)"]
    end

    subgraph Cleaning ["Data Cleaning & Transformation Engine"]
        Planner["Cleaning Recommendation Planner"]
        Executor["Transform Executor (Batch, Overrides, Previews)"]
        Structural["Structural Ops (Drop Cols, Filter Rows, Deduplicate, Semantic Overrides)"]
        MultiValued["Multi-Valued Cell Engine (Keep, Split, Expand)"]
        Summary["Pre-Registration Audit Summary"]
    end

    subgraph Cognitive ["Cognitive & Planning Orchestrator"]
        Ambiguity["Ambiguity Detector & Active Gate"]
        AutonomousOverview["Autonomous Overview Planner (Grain & Aggregation Reasoning)"]
        InsightDiscovery["Stage E Insight Discovery (8 Families, FDR Gate)"]
        DatasetChatEngine["Conversational Chat Engine (Intent Dispatch, Follow-ups)"]
        Ranker["Ranker V1 (Evidence, Coverage, Stability, Assumptions, Agreement)"]
    end

    subgraph Execution ["Deterministic Execution Engine"]
        Compiler["Query Compiler (Plan / Filters -> DuckDB SQL)"]
        DuckDB["DuckDB Worker Engine (PRAGMAs, Row Bounds, Sanitization)"]
    end

    subgraph Providers ["LLM Provider Abstraction Layer"]
        Factory["Provider Factory (providers/factory.py)"]
        GeminiAdapter["Google Gemini Adapter"]
        GroqAdapter["Groq Cloud Adapter"]
        OllamaAdapter["Local Ollama Adapter"]
        MockAdapter["Deterministic Mock Adapter"]
    end

    UI -->|HTTP REST JSON| RESTRouter
    RESTRouter <--> SessionStore
    SessionStore --- Record

    RESTRouter --> Loaders
    Loaders --> Profiler --> Semantics --> Readiness
    RESTRouter --> Cleaning
    RESTRouter --> EDA

    RESTRouter --> Cognitive
    Cognitive --> Providers
    Cognitive --> Compiler
    Compiler --> DuckDB
    DuckDB --> Cognitive
    Cleaning -.->|Register Cleaned Dataset| SessionStore
```

---

## 2. Core Architectural Principles & Boundaries

The architecture maintains four strict isolation boundaries to guarantee reliability, auditability, and safety:

### 2.1 Deterministic vs. Cognitive Separation
- **No Hallucinated Numbers**: LLM providers never compute aggregations, averages, totals, or p-values. LLMs are restricted strictly to proposing semantic plan targets, formulating structured hypotheses, or generating narrative commentary.
- **Engine Ownership of Math**: All computations, filter evaluations, group-by queries, statistical tests (ANOVA, Pearson correlations, Benjamini-Hochberg FDR adjustments), and chart coordinates are computed deterministically by **DuckDB** and scientific Python libraries (`numpy`, `scipy`).
- **Number Grounding Guard**: Generated narrative text is verified by an automated grounding guard to ensure that every emitted numeric token matches exact engine execution output.

### 2.2 Cognitive Layer Independence from Databases
- The cognitive orchestrator (`orchestrator/`) contains **zero imports of `duckdb`**.
- All SQL construction, session creation, PRAGMA configuration, query parameterization, and output sanitization belong exclusively to `engine/`.
- Communication between the orchestrator and execution layer occurs solely via typed contracts (`CandidatePlan`, `FilterSpec`, `ExecutionResult`).

### 2.3 Provider-Agnostic LLM Layer
- The system interacts with language models through the abstract `LLMClient` interface (`providers/base.py`).
- Implementations exist for **Google Gemini**, **Groq Cloud**, **Local Ollama**, and **Deterministic Mock**.
- Switching providers requires modifying a single environment variable (`PROVIDER=gemini|groq|ollama`) without altering pipeline code.
- If no external LLM credentials exist, the platform gracefully falls back to deterministic rule-based algorithms.

### 2.4 Non-Mutating Data Immutability
- Input raw datasets represented as `CanonicalDataset` are **strictly immutable**.
- All cleaning operations (normalization, imputation, structural drops, row filters, multi-value unnesting) operate exclusively on explicit deep copies.
- Registering a cleaned dataset creates an independent first-class dataset entity with its own distinct dataset ID (`ds_<stem>_cleaned_<uuid>`), preserving the raw dataset in its pristine original state.

---

## 3. Dataset Lifecycle & Session Management

Dataset state is tracked in an in-memory session registry (`api/store.py`):

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant API as FastAPI (api/main.py)
    participant Ingest as Ingestion & Profiling
    participant Store as Session Store (api/store.py)
    participant Clean as Cleaning Layer
    participant Engine as DuckDB Engine

    User->>API: POST /api/datasets/upload (File)
    API->>Ingest: Parse format, compute Profile, Semantics, Readiness
    Ingest-->>API: CanonicalDataset + Metadata
    API->>Store: Save DatasetSessionRecord (dataset_id: "ds_sales_raw")
    API-->>User: 201 Created (DatasetMetadataResponse)

    User->>API: POST /api/datasets/{id}/cleaning/apply (Transformations)
    API->>Clean: Execute cleaning rules on deep copy
    Clean-->>API: Cleaned DataFrame + CleaningReport
    API->>Store: Update record.cleaned_dataset (In-Memory Draft)
    API-->>User: 200 OK (Summary & Diff Preview)

    User->>API: POST /api/datasets/{id}/cleaned/register
    API->>Ingest: Extract schema, profile & analyze cleaned dataset
    API->>Store: Register new record (dataset_id: "ds_sales_cleaned_a1b2c3")
    API-->>User: 200 OK (Cleaned dataset registered as first-class entity)

    User->>API: POST /api/overview or /api/chat (Select Cleaned or Raw ID)
    API->>Engine: Compile & execute SQL against selected dataset
    Engine-->>API: Validated Rows & Aggregates
    API-->>User: Render Dashboard Tiles / Chat Response
```

### 3.1 `DatasetSessionRecord` Responsibilities
Each uploaded dataset is stored in a `DatasetSessionRecord` containing:
- `dataset`: The immutable raw `CanonicalDataset`.
- `profile`: Statistical profile metrics (cardinalities, null rates, quantiles).
- `semantic_profile`: Inferred column roles (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`).
- `readiness`: Schema viability assessment (`READY`, `READY_WITH_WARNINGS`, `NOT_READY`).
- `cleaned_dataset`: In-memory cleaned dataset draft prior to or following registration.
- `applied_operations`: Authoritative audit log of transformations applied to this dataset.
- `user_semantic_role_overrides`: User-specified role modifications overriding automated inference.
- `conversations`: Active conversational multi-turn context threads keyed by `conversation_id`.

---

## 4. Analytical Execution Layer (`engine/`)

The analytical engine guarantees safe, isolated, and high-performance SQL execution on tabular data:

1. **In-Memory DuckDB Instances**: Each query executes in an isolated or shared in-memory DuckDB environment.
2. **Schema Sanitization**: Column names containing special characters or spaces are escaped into safe SQL identifiers.
3. **Parameter Injection Prevention**: Slicer and dynamic cross-filtering clauses pass through strict type checking, operator whitelisting, and parameter validation.
4. **NaN and Infinity Sanitization**: Output records are sanitized to prevent IEEE floating-point invalid values (`NaN`, `Infinity`, `-Infinity`) from breaking downstream JSON serialization.
5. **Execution Bounds**: Queries execute with strict row limit bounds and timeout controls to prevent memory exhaustion on large datasets.

---

## 5. Frontend Presentation Layer (`frontend/`)

Built with **Next.js 14 App Router**, **React 18**, and **TypeScript**:

- **App Shell & TopBar**: Provides persistent workspace navigation, quick dataset switching (toggle between raw and cleaned versions), and light/dark theme toggling.
- **Data Studio (`/data-studio`)**: 5-tab workspace designed for data analysts:
  - *Overview*: High-level metadata, dimension/measure counts, data preview table.
  - *Quality*: Comprehensive data quality health score, missingness indicators, and integrity alerts.
  - *Profiling*: Column-by-column statistical metrics, quantiles, distinct ratios, and min/max/median values.
  - *Cleaning*: Interactive recommendation review, custom transformations, structural row/column operations, multi-valued cell handling, pre-registration summary, registration, and CSV/XLSX export.
  - *EDA*: Automated histograms, categorical frequencies, correlation matrix, chronological trends, observations, and manual bivariate/multivariate ad-hoc queries.
- **Autonomous Overview Dashboard (`/`)**: 12-column responsive grid featuring KPI context strips, hero visuals, side composition donuts, supporting charts, interactive slicers (`date_range`, `multi_select`), and dynamic tile cross-filtering.
- **Dataset Chat & Evidence Inspector**: Multi-turn conversational interface with natural language querying, execution timing, row count indicators, and deep SQL provenance inspection.
- **Centralized Theme Tokens (`frontend/lib/theme.ts`, `frontend/lib/chartTheme.ts`)**: Enterprise warm-palette design system with complete light and dark mode support for UI elements and SVG chart marks.
