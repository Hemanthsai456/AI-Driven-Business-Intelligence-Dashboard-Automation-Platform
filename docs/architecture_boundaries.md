# Architectural Boundaries & 6-Step Cognitive Loop Specification

**Document Version:** 1.0  
**Status:** IMPLEMENTED & VERIFIED  
**Architecture Authority:** Senior AI Software Architect & Remediation Audit  
**System Topology:** For the end-to-end platform architecture and data flow, see [System Architecture](system_architecture.md).

---

## 1. Architectural Boundaries Overview

The architecture enforces strict separation of concerns across three decoupled layers:

```
                  +-----------------------------------+
                  |             API / UI              |
                  +-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                       orchestrator/ (Cognitive)                       |
|  - Intent Interpretation (User Request -> StructuredIntent)           |
|  - Ambiguity Detection & Active Gating (Blocking vs Item-level)        |
|  - Discrete Interpretation Generation (StructuredIntent -> Interp[]) |
|  - Planning Coordination (Multi-provider / Agent)                     |
|  - Validation Coordination (Pass 1a / 1b, Pass 2)                    |
|  - Ranker V1 Scoring & Winner Selection                               |
+-----------------------------------------------------------------------+
                |                                       |
                v                                       v
+-------------------------------+       +-------------------------------+
|     engine/ (Deterministic)   |       |    providers/ (Agnostic LLM)  |
| - Safe SQL Compilation        |       | - Abstract LLMClient Contract |
| - DuckDB Session / Workers    |       | - Dynamic Factory & Registry  |
| - Deterministic Query Exec    |       | - Adapters: Gemini, Groq,     |
| - Result Sanitization (NaN/NaT|       |   Ollama, Mock                |
+-------------------------------+       +-------------------------------+
                |
                v
       +-----------------+
       |  DuckDB Engine  |
       +-----------------+
```

### Boundary Guarantees:
1. **Zero Database Coupling in Orchestrator**: `orchestrator/` contains **ZERO** imports of `duckdb`. DuckDB connection management, PRAGMAs, and in-memory execution belong exclusively to `engine/`.
2. **Deterministic Engine Independence**: `engine/` contains **ZERO** LLM logic and does not depend on cognitive or agent layers.
3. **Provider-Agnostic LLM Layer**: The orchestrator depends exclusively on the `LLMClient` abstraction via `providers.factory`. Provider adapters (`gemini`, `groq`, `ollama`, `mock`) are dynamically instantiated based on configuration (`PROVIDER` and `ACTIVE_PROVIDERS`).

---

## 2. The 6-Step Cognitive Loop

```
User Request
     ↓
[1. Intent Interpretation] ─────────────> StructuredIntent
     ↓
[2. Ambiguity Detection & Active Gate]
     ├── Request-Level Blocking? ───────> Early Clarification / Unresolved (Pipeline Halts)
     └── Item-Level Ambiguity / Clear?
              ↓
[3. Discrete Interpretation Gen] ───────> SemanticInterpretation[]
              ↓
[4. Planning × K] ─────────────────────> CandidatePlan[]
              ↓
[5. Validation & Execution Coord]
     ├── Pass 1a Pre-Dispatch Validation (Static Rules)
     ├── Deterministic Engine Execution (Isolated DuckDB Worker)
     └── Pass 1b Post-Execution Validation (Output Invariants)
              ↓
[6. Ranking & Winner Selection]
     ├── Candidate Output Consistency Check
     ├── Ranker V1 Scoring (Evidence, Coverage, Stability, Assumptions, Agreement)
     ├── Pass 2 Winner Validation & Runner-Up Cascade
     └── Final DashboardSpec / Decision Log Emission
```

---

## 3. Ambiguity Handling: Active Gate

Ambiguity detection actively controls pipeline execution flow rather than behaving as a passive observation.

### 3.1 Request-Level Blocking Ambiguity
- **Definition**: The user's query lacks analytical target or references non-existent concepts such that no viable plan can be formulated without guessing (e.g. empty request, or generic *"Show performance / numbers / stats"* when multiple measures exist without qualification).
- **Control Flow**: The Ambiguity Gate **halts pipeline execution immediately**, emitting a structured refusal log and returning `status="AMBIGUOUS"` or `status="UNANSWERABLE"` with a targeted clarification message listing available choices.

### 3.2 Item-Level Ambiguity
- **Definition**: The analytical target is valid, but specific parameters have multiple candidate choices (e.g. multiple date columns `order_date` vs `ship_date` for a temporal trend).
- **Control Flow**: The pipeline **does NOT halt**. The Ambiguity Gate passes the alternative options to Step 3 (Interpretation Generation), which forks distinct, parallel semantic interpretations for each choice.

---

## 4. Structured Intent & Discrete Interpretations

### 4.1 `StructuredIntent` Contract
Captured before any candidate plan generation:
- `original_request`: Exact user text
- `analytical_goal`: `'trend'`, `'aggregation'`, `'distribution'`, `'comparison'`
- `requested_metrics`: Identified measure columns
- `requested_dimensions`: Identified grouping dimensions
- `temporal_scope`: Relevant datetime column
- `grouping_granularity`: `'month'`, `'quarter'`, `'year'`, etc.
- `requested_visual_preferences`: `'bar'`, `'line'`, `'table'`, etc.
- `unresolved_terms`: Tokens unmapped to semantic columns
- `confidence`: Confidence score in [0.0, 1.0]

### 4.2 `SemanticInterpretation` Contract
Bridges between intent and planning:
- `interpretation_id`: UUID
- `intent_summary`: Concise description of interpretation
- `metric_column` & `aggregation`: Selected measure and SQL aggregate function
- `dimension_columns` & `granularity`: Grouping specifications
- `visualization`: Selected visualization type
- `resolved_intent_elements`: Dictionary of resolved mappings
- `referenced_columns`: Full set of columns required
- `assumptions`: Explicit defaults assumed
- `evidence`: Profile-backed evidence strings
- `confidence`: Interpretation confidence score

---

## 5. Deterministic Engine (`engine/`)

### Component Responsibilities:
- `engine/compiler.py`: Compiles structured `CandidatePlan` into safe DuckDB SQL SELECT queries with quoting, typed literal formatting, and whitelisted aggregates. Pure compilation, zero DB connections.
- `engine/sanitizer.py`: Sanitizes query result DataFrames to JSON-serializable row dictionaries: converts `NaN`, `NaT`, `inf`, and `-inf` to `None`, and standardizes timestamps to ISO-8601 strings.
- `engine/duckdb_executor.py`: Creates isolated in-memory DuckDB connections (`:memory:`), enforces worker limits (`threads=1`, `max_memory='256MB'`), injects C2 `TRY_CAST` views for string datetime columns, and arms execution timeout interrupts.
- `engine/executor.py`: Exposes `AnalyticsEngine` abstract base class and `DuckDBEngine` implementation, consumed by `orchestrator/pipeline.py`.

---

## 6. Provider-Agnostic LLM Layer (`providers/`)

### Dynamic Instantiation:
- `PROVIDER=gemini`: Instantiates `GeminiClient`
- `PROVIDER=groq`: Instantiates `GroqClient`
- `PROVIDER=ollama`: Instantiates `OllamaClient`
- `PROVIDER=mock`: Instantiates `MockLLMClient`
- `ACTIVE_PROVIDERS=gemini,groq,ollama`: Controls multi-provider consensus pool in `MultiProviderGenerator`. Optional provider failures are gracefully isolated.
