# Orchestrator Requirement Conformance & Architectural Cross-Reference

This document establishes the comprehensive traceability and conformance matrix between existing project specifications (`docs/`), system architecture diagrams, and the Orchestrator staged build program (Stages 1–7).

---

## 1. Orchestrator Requirement Conformance Matrix

The following table itemizes every requirement across existing documentation and the Orchestrator specification that governs or interfaces with the Orchestrator.

| Subsystem / Topic | Requirement Summary | Source Document | Section Cited | Stage |
| :--- | :--- | :--- | :--- | :--- |
| **Downstream Execution Contract** | Analytical engines (DuckDB) must operate on format-agnostic `CanonicalDataset.data` (`pd.DataFrame`) without format-specific parsing. | `docs/canonical_data_model.md` | Architectural Objectives (§1) | Stage 4 |
| **Audit Provenance** | System must maintain structured audit logs capturing operational provenance and analytical transformation history. | `docs/canonical_data_model.md` | Architectural Objectives (§4), Serialization | Stage 5, 7 |
| **Semantic Role Semantics** | Columns categorized as `MEASURE` support numerical aggregation (`SUM`, `AVG`, `MIN`, `MAX`, `STDDEV`). Summing/averaging `IDENTIFIER` columns is mathematically invalid. `DATETIME` supports temporal bucketing. | `docs/column_roles.md` | Semantic Role Definitions (§1–4) | Stage 3, 4 |
| **Default Ingestion Role** | Columns default to `ColumnRole.UNKNOWN` upon raw file ingestion until semantic analysis is performed. | `docs/ingestion_loaders.md` | Loaders Architecture (§1, §2) | Stage 1, 4 |
| **Read-Only Invariance** | Downstream profiling, schema validation, and execution must never mutate, clean, fill, transform, or rename the underlying DataFrame. | `docs/profiling_engine.md`, `docs/schema_readiness.md` | Key Principles (§1), Read-Only Guarantee | Stage 4 |
| **Profiling Statistics Hints** | Downstream engines and rankers consume physical statistics (`distinct_count`, `null_percentage`, min/max/mean, top frequent values) for query optimization and stability metrics. | `docs/profiling_engine.md` | Column-Level Statistics (§2) | Stage 3, 7 |
| **Readiness Gate Contract** | Downstream DuckDB engine must NOT proceed if `AnalysisReadiness.status == NOT_READY`. `READY` and `READY_WITH_WARNINGS` permit analytical execution. | `docs/schema_readiness.md` | Downstream DuckDB Contract, Purpose | Stage 4 |
| **Stat Source Priority** | Column stats for validation prefer `profile.column_statistics` ($O(1)$) over `ColumnMetadata`, avoiding raw DataFrame rescanning. | `docs/schema_readiness.md` | Stat Source Priority | Stage 3, 4 |
| **Semantic Evidence & Confidence** | Rule-based engine outputs candidate roles (`candidate_role`), deterministic confidence scores (0.0–1.0), confidence levels (`HIGH`, `MEDIUM`, `LOW`, `NONE`), and explicit evidence string arrays. | `docs/semantic_intelligence.md` | Semantic Role Definitions, Confidence Scoring, Output Contract | Stage 1, 3, 7 |
| **Compact LLM Context** | Downstream AI components receive compact structured physical evidence (column names, candidate roles, confidence levels, key statistics) — raw data rows are NEVER passed. | `docs/semantic_intelligence.md` | Future AI / LLM Preparation | Stage 5 |
| **K-Way Parallel Workers** | Orchestrator invokes up to `MAX_K=3` parallel candidate execution workers. Each worker runs an isolated in-memory DuckDB instance with strict thread limits, memory limits, and interrupt-based timeouts. | Orchestrator Prompt Decisions | Stage 3, Stage 4 | Stage 3, 4 |
| **Query Compiler & Whitelist** | Never accept raw SQL from LLM. Queries are deterministically compiled from `CandidatePlan` using whitelisted aggregations and granularities, quoted identifiers, and parameterized literals. | Orchestrator Prompt Decisions | Stage 4 | Stage 4 |
| **Pass 1a Pre-Dispatch Validator** | Deterministically validates all candidate plans prior to DuckDB dispatch: checks readiness != NOT_READY, verifies column existence, role compatibility with aggregation, DATETIME requirement for granularity, rejection of UNKNOWN roles for automatic KPIs, and warnings on LOW confidence. | Orchestrator Prompt / Architecture Diagram | Pass 1a Specification | Stage 4 |
| **Pass 1b Post-Execution Validator** | Deterministically validates execution result before ranking: checks non-empty result, not all-null, row cap enforcement, and failed-cast rate under threshold. | Orchestrator Prompt / Architecture Diagram | Pass 1b Specification | Stage 4 |
| **Candidate Output Consistency Check** | Verifies that all surviving candidate execution results share identical metric semantics, time basis, scope, units, and output schema before ranking. | Orchestrator Prompt Decisions | Stage 3 | Stage 3, 7 |
| **Pass 2 Post-Execution Validator (Winner Only)** | Validates the winning candidate execution output only: re-checks plan vs. result consistency and chart/visualization suitability (no AI proposal ships unchecked). Failure triggers runner-up cascade. | Orchestrator Prompt Decisions | Stage 3, Stage 7 | Stage 3, 7 |
| **Retry & Reprompt Caps (Project Decisions)** | Project decisions (not spec requirements): initial LLM retry capped at `AI_MAX_RETRIES=1`; DuckDB error re-prompts capped at `PASS1_REPROMPT_MAX`; runner-up cascade capped at `MAX_CASCADE_DEPTH`. | Project Decisions | Stage 3, Stage 5, Stage 7 | Stage 3, 5, 7 |
| **Deterministic Ranker V1 (Project Decisions)** | Zero-LLM scoring: $S = w_1 \cdot \text{evidence} + w_2 \cdot \text{coverage} + w_3 \cdot \text{stability} - w_4 \cdot \text{assumptions}$. Tie threshold `RANK_TIE_EPSILON` is a project decision (configurable hypothesis): ties within epsilon trigger user clarification. | Project Decisions | Stage 3, Stage 7 | Stage 3, 7 |
| **Plan Signature & Deduplication** | Structural signature over (metric, aggregation, grouping, time column/range/granularity, filter/scope, comparison basis, KPI definition) to deduplicate candidates. | Orchestrator Prompt Decisions | Stage 3, Stage 5 | Stage 3, 5 |
| **Ambiguity Engine & UNANSWERABLE** | Pre-check rules detect multiple measures/dates/groupings or missing aggregations. Returns `CLEAR`, `AMBIGUOUS`, or `UNANSWERABLE`. Rejects ungrounded requests where required columns/definitions do not exist (never invent KPIs). | Orchestrator Prompt Decisions | Stage 3, Stage 6 | Stage 3, 6 |
| **Dashboard Specification** | Orchestrator outputs `DashboardSpec` containing canonical spec, `alternate_interpretations`, and complete execution trace. | Orchestrator Prompt Decisions | Stage 3, Stage 7 | Stage 3, 7 |
| **Decision & Explainability Logs** | Structured JSONL decision log records (request, context hash, plans, errors, latency, tokens). Explainability log records ranking rationale and cascade fallbacks. | Orchestrator Prompt Decisions | Stage 5, Stage 7 | Stage 5, 7 |
| **Stage E: Autonomous Insight Discovery** | Deterministic enumeration across 8 insight types, bounded stats summary for agent proposals, Benjamini-Hochberg FDR control ($\alpha=0.05$), diversity selection, and number-grounded narration. | Stage E Specification | `docs/automated_insight_discovery.md` | Stage E |
| **Stage F: Dashboard Generation & Editing** | Deterministic 12-column grid layout (Row 1 KPI strip capped at 4, Row 2 Hero 8-col + Side 4-col, Row 3+ 2/3-col), runtime slicers, in-place chart editing, interactive filter recompilation via DuckDB (`/tile/{id}/query`), and dual-theme tokens. | Dashboard Generation Specification | `docs/dashboard_generation_and_editing.md` | Stage F |
| **Foreign Key & Derived Profiling** | `FOREIGN_KEY` sub-role for repetitive IDs retained as dimensions; `DERIVED` measure detection with arithmetic relationship correlation rejection. | Post-Stage-F Specification | `docs/column_roles.md` | Post-Stage-F |


---

## 2. Conflicts Between Docs, Architecture Diagrams, and Prompt Decisions

During analysis of `docs/`, `README.md`, and the prompt instructions, the following explicit conflicts and specification gaps were identified:

### Conflict 1: Architectural Diagram Omission of Orchestration Layer
- **Existing Documentation (`README.md` § Architecture & System Overview, `docs/product_ui_foundation.md` § Architecture Overview):**
  The system architecture diagram depicts a simple synchronous request-response stack:
  `Browser User` $\rightarrow$ `Next.js 14` $\rightarrow$ `FastAPI Backend` $\rightarrow$ `Existing Python Engine (Ingestion, Profiling, Semantic Engine)`.
- **Prompt Decisions (Stages 3–7):**
  Introduces an asynchronous K-way Orchestrator layer containing DuckDB isolated workers, Query Compiler, Pass 1/Pass 2 Validators, LLM Interpretation Generator, Ambiguity Classifier, and Deterministic Ranker V1.
- **Resolution Required:**
  The system architecture diagram must be updated in later documentation to include the Orchestrator, Worker Pool, DuckDB instances, and LLM context boundary between FastAPI and downstream execution.

### Conflict 2: Omission of Phase 2 (Relationship Detection) and Phase 3 (Cleaning)
- **Existing Documentation (`docs/schema_readiness.md` § Architectural Boundary):**
  Line 289 explicitly reserves:
  - "Relationship Detection: Phase 2 — NOT HERE"
  - "Cleaning: Phase 3 — NOT HERE"
  - "DuckDB Analytics: Next stage — NOT HERE"
- **Prompt Decisions (Stages 1–7):**
  The Orchestrator Staged Build directly jumps to DuckDB analytical query execution (Stage 4) and LLM Orchestration without implementing multi-table relationship detection or data cleaning pipelines.
- **Resolution / Status:**
  The Orchestrator operates strictly on single-table `CanonicalDataset` objects under the read-only invariant. Data cleaning is intentionally bypassed, relying on `AnalysisReadiness` warnings rather than data modification.

### Conflict 3: Readiness Gate Contract vs. Pass 1 Plan Validation
- **Existing Documentation (`docs/schema_readiness.md` § Downstream DuckDB Contract):**
  Specifies: *"The DuckDB layer must not proceed if status == NOT_READY."*
- **Prompt Decisions (Stage 4):**
  Defines Pass 1 validator solely based on plan structural validity: column existence, role compatibility with aggregation, `DATETIME` for granularity, `UNKNOWN` rejection for KPIs. It does not explicitly mention verifying `AnalysisReadiness.status`.
- **Resolution / Flag:**
  To uphold the safety contract in `docs/schema_readiness.md`, the Orchestrator must enforce that a dataset with `AnalysisReadiness.status == NOT_READY` cannot have queries executed in DuckDB. Pass 1 or the Orchestrator pipeline must explicitly check readiness prior to worker dispatch.

### Conflict 4: Location of Column Semantic Roles (`ColumnMetadata` vs. `DatasetSemanticProfile`)
- **Existing Documentation (`docs/canonical_data_model.md`, `docs/semantic_intelligence.md`):**
  In `CanonicalDataset`, each column in `metadata.schema` has a `semantic_role` field that defaults to `ColumnRole.UNKNOWN`. `SemanticAnalyzer.analyze()` produces an external artifact `DatasetSemanticProfile` with `column_evidences[col].candidate_role` and `confidence`. It does NOT mutate `CanonicalDataset.metadata.schema` unless `apply_roles=True` is explicitly passed.
- **Prompt Decisions (Stage 1 & Stage 4):**
  Stage 1 freezes `schemas/semantic_profile_v1.schema.json` based on the serialized `DatasetSemanticProfile` (using `candidate_role`). Stage 4 requires Pass 1 validator to verify "aggregation compatible with role, UNKNOWN role rejected for automatic KPIs, LOW confidence -> warning".
- **Resolution / Flag:**
  Pass 1 validator and the context builder cannot rely solely on `CanonicalDataset.metadata.schema.semantic_role` (which is `UNKNOWN` if `apply_roles` was false). The Orchestrator must ingest the `DatasetSemanticProfile` as the authoritative source of candidate roles and confidence scores.

### Conflict 5: Role of LLM in Semantic Role Inference vs. Plan Generation
- **Existing Documentation (`docs/semantic_intelligence.md` § Future AI / LLM Preparation):**
  Lines 105–106 state: *"LLM agents inspect column names, data dtypes, physical statistics, rule-based candidate roles... The LLM can validate or refine candidate roles using domain context."*
- **Prompt Decisions (Stages 3, 5, 7):**
  The LLM is NOT used to refine semantic roles in the profile. Instead, candidate semantic roles and physical evidence are passed as read-only context to the LLM to generate analytical `CandidatePlan`s. All role validation, scoring, and candidate ranking are strictly deterministic (zero LLM in Ranker V1).
- **Resolution / Flag:**
  Role classification remains 100% deterministic (rule-based). The LLM's sole responsibility is translating natural language intent into structured `CandidatePlan` specifications adhering to the provided semantic roles.

### Conflict 6: Audit Logging Destination (`CanonicalDataset.audit_logs` vs. Orchestrator Decision Logs)
- **Existing Documentation (`docs/canonical_data_model.md` § Core Components, `docs/schema_readiness.md` § Audit Trail):**
  Specifies in-memory audit logs stored within `CanonicalDataset.audit_logs` (e.g. `INGESTED`, `READINESS_CHECKED`).
- **Prompt Decisions (Stage 5, Stage 7):**
  Specifies standalone persistent logging: a JSONL decision log (`request`, `context_hash`, `plans`, `errors`, `latency`, `tokens`) and an explainability log (`ranking_rationale`, `fallbacks`), plus `DashboardSpec.trace`.
- **Resolution / Flag:**
  `CanonicalDataset.audit_logs` tracks dataset lifecycle events, while Orchestrator decision logs and explainability logs are separate execution artifacts persisted independently of the dataset model.

### Conflict 7: Git Tracking Conflict with `frontend/lib`
- **Existing Repository Configuration (`.gitignore` line 27):**
  Contains `lib/` under the generic Python ignore section.
- **Impact:**
  Git ignores `frontend/lib/api.ts` and `frontend/lib/types.ts`. Consequently, `git ls-files frontend/lib` returns empty, conflicting with the prompt rule: *"Confirm .gitignore covers .env and that `git ls-files frontend/lib` lists api.ts and types.ts."*
- **Resolution / Flag:**
  `.gitignore` line 27 (`lib/`) must be restricted to `/lib/` or overridden with `!frontend/lib/` so that frontend library TypeScript files are tracked. Note: As Stage 0 is strictly read-only ("No code"), this conflict is flagged here and will be resolved when allowed.

---

## 3. Conformance Summary & Gate Status

- **Stage 0 Goal:** Complete documentary cross-reference and conflict enumeration without code modifications.
- **Current State:** Baseline test suite verified (89 passing unit/API tests). No locked layers modified.
- **Readiness for Stage 1:** Frozen schemas and contract tests can proceed immediately upon approval.

---

## 4. Architecture Diagram (`Archotecture.drawio.png`) Verification & Binding Resolutions

This section cross-references the official system architecture diagram ([`docs/references/Archotecture.drawio.png`](references/Archotecture.drawio.png)) with existing documentation (`docs/`) and the Orchestrator specifications, citing exact text, diagram blocks, and section numbers.

### 4.1 Verification Matrix: Diagram vs. Specifications

#### 1. Retry Caps, Epsilon, and Cascade Depth (Project Decisions)
- **Architecture Diagram Text:**
  - Red loop arrow: `"Pass 1 Failure: Error-Informed Re-Prompt Loop (DuckDB Execution Error Logs)"` routed back to `"AI Orchestrator"`.
  - Condition diamond: `"All Candidates Failed? (|S| = 0)"`.
  - Cascade arrow: `"Runner-Up Candidate Rollback Cascade (Evaluate Next Candidate)"` routed back to `"Robustness Ranker (Deterministic / Zero LLM Cost)"`.
  - Decision diamond: `"Score Differential < ε (Tie Threshold)?"`.
- **Existing Documentation (`docs/`):**
  - No retry caps, re-prompt limits, cascade limits, or tie thresholds exist in `docs/canonical_data_model.md`, `docs/schema_readiness.md`, or `docs/semantic_intelligence.md`.
- **Orchestrator Project Decisions (Not Spec Requirements):**
  - `AI_MAX_RETRIES = 1`: Project decision default capping initial LLM JSON/schema generation attempts.
  - `PASS1_REPROMPT_MAX`: Project decision default capping the DuckDB error-informed re-prompt loop.
  - `MAX_CASCADE_DEPTH`: Project decision default capping the runner-up candidate rollback cascade.
  - `RANK_TIE_EPSILON`: Project decision default threshold where score differentials trigger user clarification.
- **Mismatch / Verification Flag:**
  - **PROJECT DECISIONS CLARIFICATION:** The diagram visually specifies the loops and tie branch but does NOT define numerical bounding limits. These caps (`AI_MAX_RETRIES=1`, `PASS1_REPROMPT_MAX`, `MAX_CASCADE_DEPTH`, `RANK_TIE_EPSILON`) are **project decisions** (configurable hypotheses/operational defaults), not pre-existing spec requirements. Without them, the loop `"Pass 1 Failure: Error-Informed Re-Prompt Loop"` would risk indefinite execution.

#### 2. Pass 1a / Pass 1b / Pass 2 Validation Semantics
- **Architecture Diagram Text:**
  - In `AI Orchestrator`: `"Enforces API JSON Schema + Candidate Homogenization Checks"`.
  - Worker Pool: `"Analytical Engine (DuckDB - K-Way Parallel)"` with 3 workers labeled `"Candidate Execution Plan 1..3 (DuckDB Worker)"` and subtitle `"Thread Isolation | Per-Worker Memory Caps | Timeout Bounds"`.
  - Pass 1 block: `"Validation Layer — Pass 1 (Per-Candidate)"` with `"Deterministic Schema, Query, & Evidence Checks"`.
  - Filter: `"Surviving Candidates Set S"`.
  - Ranker: `"Robustness Ranker (Deterministic / Zero LLM Cost)"`.
  - Pass 2 block: `"Validation Layer — Pass 2 (AI Proposal Validation)"` with `"Validates Winner Only (No AI Proposal Ships Unchecked)"`.
  - Decision diamond: `"Winner Passed Pass 2?"`
    - **Yes** $\rightarrow$ `"Dashboard Specification Object (Canonical Spec + alternate_interpretations Field & Full Trace History)"`.
    - **No** $\rightarrow$ `"Runner-Up Candidate Rollback Cascade (Evaluate Next Candidate)"` back to Ranker.
- **Existing Documentation (`docs/schema_readiness.md`):**
  - Section 3.4 & 4.1 define only `SchemaValidator` for dataset structural integrity prior to analytical loading.
- **Split Validation Semantics (Matching the Architecture Diagram):**
  - **Pass 1a (Before Dispatch):** Pre-execution deterministic validation. Verifies:
    1. Dataset readiness check (`AnalysisReadiness.status != NOT_READY`).
    2. Column existence in `DatasetSemanticProfile`.
    3. Semantic role and aggregation compatibility (e.g. `MEASURE` for `SUM`/`AVG`, reject `IDENTIFIER`).
    4. Granularity requires `DATETIME` role.
    5. Structural syntax correctness of `CandidatePlan`.
  - **Pass 1b (After Execution / Pre-Ranking):** Post-execution deterministic validation on worker output. Verifies:
    1. Non-empty tabular result.
    2. Result is not all-null across metric values.
    3. Row cap enforcement (result length within allowed limits).
    4. Failed-cast rate under threshold for string timestamps.
    5. DuckDB execution errors (syntax/interrupt/memory) caught and routed to error-informed re-prompt loop (capped by `PASS1_REPROMPT_MAX`).
  - **Candidate Output Consistency Check:** Verifies surviving candidates share identical metric semantics, time basis, scope, units, and output schema.
  - **Pass 2 (Winner Only):** Validates winning candidate exclusively:
    1. Re-checks plan vs. result consistency.
    2. Validates chart/visualization choice against result dimensions and cardinality.
    3. Failure initiates runner-up rollback cascade (capped by `MAX_CASCADE_DEPTH`). Defined formally in `docs/ranker_v1_spec.md`.

#### 3. Relationship-Detection Scope
- **Architecture Diagram Text:**
  - Third top block: `"Data Intelligence Engine"` with description `"Profiling, Quality, Semantic Graphs & Relationship Extraction"`.
- **Existing Documentation (`docs/schema_readiness.md`):**
  - Section "Architectural Boundary (After Step 4.2)", line 290 explicitly states: `| **Relationship Detection** | Phase 2 — NOT HERE |`.
- **Mismatch / Verification Flag:**
  - **MISMATCH:** The diagram includes `"Semantic Graphs & Relationship Extraction"` within the upstream Data Intelligence Engine. However, per `docs/schema_readiness.md` and the Orchestrator staged build scope, relationship extraction and multi-table joins are **strictly out of scope for V1**. V1 executes single-dataset analytics over a single `CanonicalDataset`.

#### 4. Confidence Handling
- **Architecture Diagram Text:**
  - In Pass 1: `"Deterministic Schema, Query, & Evidence Checks"`.
  - In Ranker: `"Robustness Ranker (Deterministic / Zero LLM Cost)"`.
  - Decision diamond: `"Score Differential < ε (Tie Threshold)?"` $\rightarrow$ **Yes**: `"Clarification Fallback Prompt (User UI)"`.
- **Existing Documentation (`docs/semantic_intelligence.md`):**
  - Section 4 "Confidence Scoring": defines deterministic confidence levels: `HIGH` (0.85–0.95), `MEDIUM` (0.60–0.84), `LOW` (0.30–0.59), `NONE` (0.00).
  - Section 2.4: `"Ambiguous columns return ColumnRole.UNKNOWN with low confidence rather than creating false certainty."`
- **Orchestrator Specification:**
  - Pass 1: `LOW` confidence produces a plan warning; `UNKNOWN` role is rejected for automatic KPIs.
  - Ranker V1: `evidence = mean role confidence of columns used`.
  - Tie threshold: If score differential $< \epsilon$ (`RANK_TIE_EPSILON`), route to clarification prompt rather than picking arbitrarily.
- **Mismatch / Verification Flag:**
  - **ALIGNMENT:** The diagram's tie threshold check (`Score Differential < ε`) and fallback prompt directly align with Ranker V1's `RANK_TIE_EPSILON` clarification rule.
  - **ALIGNMENT:** Confidence scores from `DatasetSemanticProfile` serve directly as inputs to both Pass 1 evidence checks and the Ranker evidence formula.

---

### 4.2 Binding Architectural Resolutions

The following architectural resolutions are binding across all subsequent build stages (Stage 1 through Stage 7):

1. **Resolution C3 (Readiness Gating Before Pass 1):**
   - In accordance with `docs/schema_readiness.md` (§ Downstream DuckDB Contract, line 212: *"The DuckDB layer must not proceed if status == NOT_READY"*), the Orchestrator **refuses dispatch** if `AnalysisReadiness.status == NOT_READY`.
   - This gate check is evaluated **prior to Pass 1 and prior to DuckDB worker invocation**. Datasets with `NOT_READY` status immediately halt pipeline execution with a structured readiness refusal error.

2. **Resolution C4 (Sole Semantic Role Authority):**
   - `DatasetSemanticProfile` is the **sole authoritative source** for column candidate roles (`candidate_role`) and confidence scores.
   - `apply_roles` remains `False` on the canonical model; `CanonicalDataset.metadata.schema` is never mutated, preserving the fundamental read-only invariance guarantee.

3. **Resolution C5 (LLM Role Refinement Out of Scope for V1):**
   - `docs/semantic_intelligence.md` (§ Future AI / LLM Preparation, lines 102–107) has been formally updated: **Role refinement or role reassignment by the LLM is explicitly out of scope for V1**.
   - Semantic roles and confidence scores produced by the deterministic rule engine are frozen, read-only inputs to the LLM. The LLM's role is restricted to translating natural language intent into structured `CandidatePlan`s conforming to these frozen roles.

4. **Resolution C2 Addition (DataFrame Invariance & Temporal String Casting):**
   - `CanonicalDataset.data` DataFrame is strictly immutable and will **never be mutated or type-coerced**.
   - `DATETIME` columns stored as strings are handled via `TRY_CAST(col AS TIMESTAMP)` dynamically inside the DuckDB view created per worker.
   - Any failed casts (evaluating to `NULL`) are tracked, and failed-cast counts are reported as structured warnings in `ExecutionResult.warnings`.

