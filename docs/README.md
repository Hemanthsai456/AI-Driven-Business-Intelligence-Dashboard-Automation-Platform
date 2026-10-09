# Platform Documentation Index

Welcome to the technical documentation for the **AI-Driven Business Intelligence & Dashboard Automation Platform**. This index serves as the central directory mapping the repository's architecture, data processing pipelines, analytical reasoning engines, API contracts, and development guides.

---

## 🧭 Documentation Map by Component & Workflow

### 1. Architecture & System Design
High-level system topology, component responsibilities, layer boundaries, and dataset lifecycle management.

| Document | Description |
| :--- | :--- |
| [`docs/system_architecture.md`](system_architecture.md) | **Core System Architecture**: End-to-end architecture, cognitive vs. deterministic separation, dataset lifecycle, session management, and data-flow diagrams. |
| [`docs/architecture_boundaries.md`](architecture_boundaries.md) | **Cognitive Loop & Boundaries**: Strict decoupling between `orchestrator/`, `engine/`, and `providers/`, including the 6-step cognitive loop for user intent. |
| [`docs/canonical_data_model.md`](canonical_data_model.md) | **Canonical Data Model**: Specifications for `CanonicalDataset`, `DatasetMetadata`, `ColumnMetadata`, and immutability guarantees. |

---

### 2. Ingestion, Profiling & Schema Readiness
Raw file loading, statistical profiling, semantic inference, and readiness gates.

| Document | Description |
| :--- | :--- |
| [`docs/ingestion_loaders.md`](ingestion_loaders.md) | **Ingestion Loaders**: Multi-format file ingestion architecture supporting `.csv`, `.tsv`, `.xlsx`, and `.parquet` files up to 100MB. |
| [`docs/profiling_engine.md`](profiling_engine.md) | **Statistical Profiling Engine**: Algorithms for computing cardinality, missingness, distributions, quantiles, and IQR metrics. |
| [`docs/semantic_intelligence.md`](semantic_intelligence.md) | **Semantic Analyzer**: Rule-based classification for `MEASURE`, `DIMENSION`, `DATETIME`, and `IDENTIFIER` roles. |
| [`docs/column_roles.md`](column_roles.md) | **Column Semantic Roles & Sub-Roles**: Detailed rules for `PRIMARY_KEY`, `FOREIGN_KEY`, and `DERIVED` algebraic composite measures. |
| [`docs/schema_readiness.md`](schema_readiness.md) | **Schema Readiness Gates**: Structural evaluation (`READY`, `READY_WITH_WARNINGS`, `NOT_READY`) blocking execution on invalid schemas. |
| [`docs/semantic_validation_report.md`](semantic_validation_report.md) | **Semantic Analyzer Empirical Report**: Empirical validation across retail, e-commerce, and financial datasets. |

---

### 3. Data Studio & Data Cleaning Engine
Interactive data quality assessment, user-guided cleaning, structural transforms, multi-valued cell handling, and dataset registration.

| Document | Description |
| :--- | :--- |
| [`docs/data_studio_cleaning.md`](data_studio_cleaning.md) | **Data Studio & Cleaning Pipeline**: Comprehensive guide covering the 5-tab Data Studio (Overview, Quality, Profiling, Cleaning, EDA), automated recommendations, preview vs. apply lifecycle, structural row/col operations, semantic role overrides, multi-valued cells, pre-registration summary, registration of cleaned datasets, and file downloads. |
| [`docs/eda_engine.md`](eda_engine.md) | **Exploratory Data Analysis (EDA) Engine**: Deterministic EDA engine (`intelligence/eda.py`) generating automated distributions, correlation matrices, time-series trends, factual observations, manual ad-hoc slicing, and theme-aware visualizations. |

---

### 4. Analytical Reasoning & Autonomous Dashboards
Unsupervised insight discovery, generalized analytical reasoning, Power BI-style dashboard layouts, and dynamic cross-filtering.

| Document | Description |
| :--- | :--- |
| [`docs/autonomous_overview.md`](autonomous_overview.md) | **Autonomous Overview Engine**: Generalized analytical reasoning (`orchestrator/overview/`), dataset grain inference, aggregation suitability (additive vs. intensive), candidate diversity ranking, 12-column grid layout, and DuckDB live cross-filtering. |
| [`docs/stage_e_insight_discovery.md`](stage_e_insight_discovery.md) | **Stage E Insight Discovery**: Autonomous candidate enumeration across 8 statistical types, Benjamini-Hochberg FDR control ($\alpha = 0.05$), and numeric grounding guards. |
| [`docs/stage_f_power_bi_dashboard.md`](stage_f_power_bi_dashboard.md) | **Stage F Power BI Dashboard**: 12-column deterministic grid layout, KPI context strip, runtime slicers, and DuckDB tile query re-compilation. |
| [`docs/ranker_v1_spec.md`](ranker_v1_spec.md) | **Ranker V1 Specification**: Mathematical formulation of candidate ranking across evidence, coverage, stability, assumptions, and provider agreement. |

---

### 5. Conversational Interaction & Evidence Grounding
Natural language dataset chat, query compilation, SQL provenance, and evidence verification.

| Document | Description |
| :--- | :--- |
| [`docs/dataset_chat_evidence.md`](dataset_chat_evidence.md) | **Dataset Chat & Evidence Grounding**: Conversational architecture (`orchestrator/chat/`), multi-turn intent routing, NL-to-SQL DuckDB compilation, SQL provenance inspector (`EvidenceInspector.tsx`), and hallucination guards. |

---

### 6. API, Frontend & Development Reference
REST API specification, UI components, configuration, testing, and troubleshooting.

| Document | Description |
| :--- | :--- |
| [`docs/api_reference.md`](api_reference.md) | **REST API Reference**: Complete specification of all backend endpoints in `api/main.py`, covering dataset ingestion, cleaning, EDA, overview, chat, and tile queries. |
| [`docs/product_ui_foundation.md`](product_ui_foundation.md) | **UI Foundation**: Frontend architecture, Next.js 14 layout, responsive design tokens, and theme provider. |
| [`docs/multi_agent_generator.md`](multi_agent_generator.md) | **Multi-Provider LLM Generators**: Configuration and execution across Google Gemini, Groq, local Ollama, and deterministic Mock adapters. |
| [`docs/orchestrator_contracts.md`](orchestrator_contracts.md) | **Orchestrator Schemas & Contracts**: Pydantic models for CandidatePlan, DashboardSpec, ExecutionResult, and Pass 1/Pass 2 validation. |
| [`docs/orchestrator_conformance.md`](orchestrator_conformance.md) | **Requirements Traceability Matrix**: Implementation status and conformance verification across project stages. |
| [`docs/known_issues.md`](known_issues.md) | **Known Issues Log**: Tracking log of resolved defects, edge cases, and current development limitations. |

---

## 🛠️ Typical Developer Reading Paths

### Path A: Understanding the Full Data Lifecycle
1. [`docs/system_architecture.md`](system_architecture.md)
2. [`docs/ingestion_loaders.md`](ingestion_loaders.md) & [`docs/profiling_engine.md`](profiling_engine.md)
3. [`docs/data_studio_cleaning.md`](data_studio_cleaning.md)
4. [`docs/eda_engine.md`](eda_engine.md)

### Path B: Understanding Autonomous Analytics & Dashboards
1. [`docs/system_architecture.md`](system_architecture.md)
2. [`docs/autonomous_overview.md`](autonomous_overview.md)
3. [`docs/stage_e_insight_discovery.md`](stage_e_insight_discovery.md)
4. [`docs/stage_f_power_bi_dashboard.md`](stage_f_power_bi_dashboard.md)

### Path C: Integrating with the API or Building Frontend Views
1. [`docs/api_reference.md`](api_reference.md)
2. [`docs/dataset_chat_evidence.md`](dataset_chat_evidence.md)
3. [`docs/product_ui_foundation.md`](product_ui_foundation.md)
