# AI-Driven Business Intelligence & Dashboard Automation Platform

An end-to-end, multi-agentic platform for automated data ingestion, profiling, semantic understanding, schema readiness validation, deterministic query compilation, multi-provider LLM plan synthesis, DuckDB analytical execution, and interactive business intelligence dashboard generation.

---

## 🏛️ System Architecture

```
                                  ┌─────────────────────────────┐
                                  │   Next.js 14 Web Frontend   │
                                  │  React 18 / Tailwind / App  │
                                  └──────────────┬──────────────┘
                                                 │ HTTP REST API
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │       FastAPI Backend       │
                                  │       (api/main.py)         │
                                  └──────────────┬──────────────┘
                                                 │
            ┌────────────────────────────────────┼────────────────────────────────────┐
            ▼                                    ▼                                    ▼
  ┌───────────────────┐                ┌───────────────────┐                ┌───────────────────┐
  │ Ingestion Engine  │                │ Profiling Engine  │                │ Semantic Analyzer │
  │ CSV / TSV / XLSX  │                │ Distribution, IQR │                │ Roles, Confidence │
  │ Parquet Loaders   │                │ Null % & Quantiles│                │ Explain Evidence  │
  └─────────┬─────────┘                └─────────┬─────────┘                └─────────┬─────────┘
            │                                    │                                    │
            └────────────────────────────────────┼────────────────────────────────────┘
                                                 │
                                                 ▼
                                ┌─────────────────────────────────┐
                                │      Orchestrator Pipeline      │
                                │    (orchestrator/pipeline.py)   │
                                └────────────────┬────────────────┘
                                                 │
         ┌───────────────────────────────────────┼───────────────────────────────────────┐
         ▼                                       ▼                                       ▼
┌───────────────────┐                  ┌───────────────────┐                   ┌───────────────────┐
│ Ambiguity Engine  │                  │ LLM Context Builder│                  │ Multi-Agent Gens  │
│ CLEAR / AMBIGUOUS │                  │ Compact Read-Only │                   │ Gemini / Groq /   │
│ / UNANSWERABLE    │                  │ Metadata Context  │                   │ Ollama (Parallel) │
└───────────────────┘                  └───────────────────┘                   └─────────┬─────────┘
                                                                                         │ CandidatePlans
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │ Pass 1a Validator │
                                                                               │ Pre-Dispatch Gate │
                                                                               └─────────┬─────────┘
                                                                                         │
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │  Query Compiler   │
                                                                               │ Deterministic SQL │
                                                                               └─────────┬─────────┘
                                                                                         │
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │  DuckDB Executor  │
                                                                               │ Isolated Workers  │
                                                                               └─────────┬─────────┘
                                                                                         │ ExecutionResult
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │ Pass 1b Validator │
                                                                               │ Post-Exec Cast/Row│
                                                                               └─────────┬─────────┘
                                                                                         │
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │   Ranker V1 &     │
                                                                               │ Multi-Agreement   │
                                                                               └─────────┬─────────┘
                                                                                         │ Ranked Winner
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │ Pass 2 & Cascade  │
                                                                               │ Winner Validation │
                                                                               └─────────┬─────────┘
                                                                                         │
                                                                                         ▼
                                                                               ┌───────────────────┐
                                                                               │   DashboardSpec   │
                                                                               │ Emission & Trace  │
                                                                               └───────────────────┘
```

---

## 🚀 Key Features & Capabilities

### 1. Ingestion & Canonical Modeling (`ingestion/`)
- **Format-Agnostic Loaders**: Native `CSVLoader`, `TSVLoader`, `ExcelLoader` (`.xlsx`), and `ParquetLoader` (`.parquet`).
- **Canonical Representation**: Uniform `CanonicalDataset` model preserving data frame immutability across analytical steps.
- **Robust Error Handling**: Strict file signature validation, corruption detection, and clear exception hierarchies.

### 2. Deterministic Profiling & Semantic Intelligence (`intelligence/`)
- **Statistical Profiler (`intelligence/profiler.py`)**: Computes distinct counts, missingness rates, skewness, interquartile ranges, and summary statistics.
- **Rule-Based Semantic Classifier (`intelligence/semantic_analyzer.py`)**: Classifies columns into `MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, or `UNKNOWN` roles with transparent evidence strings and confidence scores (0.0–1.0).
- **Schema Readiness Gate (`intelligence/schema_validator.py`)**: Emits `AnalysisReadiness` reports (`READY`, `READY_WITH_WARNINGS`, `NOT_READY`). Analytical execution is blocked if critical criteria fail.

### 3. Multi-Agentic Multi-Provider Orchestrator (`orchestrator/`)
- **Multi-Provider LLM Clients (`orchestrator/llm.py`)**:
  - **Google Gemini**: Uses official `google-genai` SDK with strict JSON schema response mode.
  - **Groq Cloud**: OpenAI-compatible ultra-fast inference with json_object mode.
  - **Local Ollama**: Self-hosted local daemon (`http://localhost:11434`) without requiring external API keys.
- **Parallel Generation (`MultiProviderGenerator`)**: Dispatches queries across multiple models simultaneously, deduplicates via structural `plan_signature`, and evaluates model consensus.
- **Autonomous Reasoning Agent (`ExternalAgentGenerator`)**: Operates inside a read-only sandboxed metadata environment (`AgentMetadataEnvironment`) with strict step limits, token budgets, and failure isolation.
- **Deterministic Ranker V1 (`orchestrator/utils.py`)**: Evaluates candidates across 5 weighted objectives:
  $$\text{Score} = w_1 \cdot \text{evidence} + w_2 \cdot \text{coverage} + w_3 \cdot \text{stability} - w_4 \cdot \text{assumptions} + w_5 \cdot \text{agreement}$$
- **Validation Pipeline**:
  - **Pass 1a (Pre-Dispatch)**: Semantic role compatibility, time dimension checks, and column existence.
  - **DuckDB Isolated Workers**: Safe query compilation with `TRY_CAST` defensive type coercion and refusal guards.
  - **Pass 1b (Post-Execution)**: Cast failure rate thresholds and row count bounds.
  - **Pass 2 (Winner Only)**: Visual suitability checks (KPI single-value check, Line time-dimension requirement, Pie chart cardinality guard) with automated runner-up cascade.

### 4. Modern Enterprise Web UI (`frontend/`)
- **Design System**: Warm Beige, Deep Charcoal, and Burnt Orange aesthetic with persistent dark/light theme support.
- **Views & Workflows**:
  - **Datasets Overview**: Drag-and-drop file ingestion, preview tables, profiling metrics, and semantic role inspector.
  - **Ask AI / Query Console**: Natural language query interface with provider selection, streaming status, and reasoning transparency.
  - **Plan Runner**: Step-by-step validator execution viewer displaying Pass 1a/1b checks, DuckDB execution, and compiled SQL.
  - **Dashboard Viewer**: Real-time rendering of generated `DashboardSpec` widgets (KPI cards, bar charts, line graphs, tables) and alternative interpretation selectors.

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11 & 3.13)
- Node.js 18+ & npm
- (Optional) [Ollama](https://ollama.ai/) for running local LLMs without external API keys

### 2. Backend Installation (Python)
From the project root:
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
# (Linux/macOS) source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Installation (Next.js)
```powershell
cd frontend
npm install
cd ..
```

### 4. Environment Configuration
Copy the template configuration file:
```powershell
cp .env.example .env
```
*(Do NOT run `.env` directly as a shell script; it is loaded automatically by the backend).*

Configure your desired provider and keys in `.env`:
```ini
# Active provider: 'gemini', 'groq', or 'ollama'
PROVIDER=gemini

# Google Gemini (https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Groq Cloud (https://console.groq.com/keys)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Ollama Local LLM (No API key needed!)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
```

---

## 🚀 Running the Platform

### Terminal 1: Backend API Server
```powershell
python -m uvicorn api.main:app --reload --port 8000
```
- API Base: `http://localhost:8000`
- Swagger Interactive Docs: `http://localhost:8000/docs`

### Terminal 2: Next.js Frontend
```powershell
cd frontend
npm run dev
```
- Web Application: `http://localhost:3000`

### (Optional) Terminal 3: Local Ollama Daemon
If using local Ollama:
```powershell
ollama run llama3
```

---

## 🧪 Running Tests

The test suite contains **218 test cases** covering ingestion, profiling, semantic analysis, contracts, DuckDB query compilation, Pass 1/Pass 2 validation, and multi-agent plan generation:

```powershell
# Run all unit and integration tests
python -m pytest tests/ -v

# Run with short summary
python -m pytest tests/ -q
```

---

## 📚 Technical Documentation Directory

| Document | Description |
| :--- | :--- |
| [`docs/multi_agent_generator.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/multi_agent_generator.md) | Multi-provider LLM integration, parallel dispatch, and agent sandboxing |
| [`docs/ranker_v1_spec.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/ranker_v1_spec.md) | Deterministic Ranker V1 mathematical specification and multi-provider agreement |
| [`docs/orchestrator_contracts.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/orchestrator_contracts.md) | Complete schemas, validation contracts, and DashboardSpec data models |
| [`docs/orchestrator_conformance.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/orchestrator_conformance.md) | Traceability matrix between design requirements and staged implementation |
| [`docs/canonical_data_model.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/canonical_data_model.md) | Canonical dataset representations and immutability invariants |
| [`docs/column_roles.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/column_roles.md) | Semantic role definitions (`MEASURE`, `DIMENSION`, `DATETIME`, etc.) |
| [`docs/schema_readiness.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/schema_readiness.md) | Data readiness gates and structural integrity rules |
| [`docs/semantic_intelligence.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/semantic_intelligence.md) | Rule-based semantic classification engine and confidence scoring |
| [`docs/profiling_engine.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/profiling_engine.md) | Statistical profiling engine algorithms |
| [`docs/ingestion_loaders.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/ingestion_loaders.md) | Multi-format file ingestion architecture |
| [`docs/product_ui_foundation.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/product_ui_foundation.md) | UI foundation, component hierarchy, and design tokens |
| [`docs/known_issues.md`](file:///c:/Users/GANDL/OneDrive/Documents/MiniProject/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/known_issues.md) | Known issues, tracking log, and resolution histories |