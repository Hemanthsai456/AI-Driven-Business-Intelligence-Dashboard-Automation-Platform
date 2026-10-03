# AI-Driven Business Intelligence & Dashboard Automation Platform

An enterprise-grade, end-to-end platform for automated data ingestion, profiling, semantic understanding, schema readiness validation, deterministic query compilation, multi-provider LLM plan synthesis, DuckDB analytical execution, statistical insight discovery (with Benjamini-Hochberg FDR control), and interactive Power BI-style dashboard automation.

---

## 🏛️ System Architecture

```
                                      ┌──────────────────────────────────────────────┐
                                      │       Next.js 14 Responsive Web App          │
                                      │   Power BI-Style 12-Column Grid Dashboard    │
                                      │  (Recharts / Slicers / Theme Tokens / Cross) │
                                      └──────────────────────┬───────────────────────┘
                                                             │ REST HTTP / JSON
                                                             ▼
                                      ┌──────────────────────────────────────────────┐
                                      │            FastAPI Backend Engine            │
                                      │                 (api/main.py)                │
                                      └──────────────────────┬───────────────────────┘
                                                             │
                  ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
                  ▼                                          ▼                                          ▼
     ┌─────────────────────────┐                ┌─────────────────────────┐                ┌─────────────────────────┐
     │    Ingestion Engine     │                │    Profiling Engine     │                │    Semantic Analyzer    │
     │  CSV / TSV / XLSX /     │                │   Distributions, IQR,   │                │   Role Classification   │
     │  Parquet Loaders        │                │   Null %, Quantiles     │                │   PK / FK / DERIVED     │
     └────────────┬────────────┘                └────────────┬────────────┘                └────────────┬────────────┘
                  │                                          │                                          │
                  └──────────────────────────────────────────┼──────────────────────────────────────────┘
                                                             │ CanonicalDataset & SemanticProfile
                                                             ▼
                                      ┌──────────────────────────────────────────────┐
                                      │         Orchestrator Pipeline Core           │
                                      │          (orchestrator/pipeline.py)          │
                                      └──────────────────────┬───────────────────────┘
                                                             │
                      ┌──────────────────────────────────────┴──────────────────────────────────────┐
                      ▼                                                                             ▼
    ┌───────────────────────────────────┐                                         ┌───────────────────────────────────┐
    │     Focused Mode (User Brief)     │                                         │    Discovery Mode (Generic Brief) │
    │    Ambiguity Engine & Clarify     │                                         │   Candidate Enumerator (8 Types)  │
    │    Multi-Provider LLM Generators  │                                         │   Bounded Stats for Agent Propose │
    │   (Gemini, Groq, Ollama, Local)   │                                         │   Arithmetic Relationship Pruner  │
    └─────────────────┬─────────────────┘                                         └─────────────────┬─────────────────┘
                      │ CandidatePlan                                                               │ Candidates
                      ▼                                                                             ▼
    ┌───────────────────────────────────┐                                         ┌───────────────────────────────────┐
    │   Pass 1a Pre-Dispatch Validator  │                                         │  DuckDB Execution & Pass 1a/1b    │
    │   Query Compiler & DuckDB Engine  │                                         │  Pass 1b Cast/Row Bounds Checks   │
    │   Pass 1b Post-Execution Checks   │                                         └─────────────────┬─────────────────┘
    └─────────────────┬─────────────────┘                                                           │ Executed Candidates
                      │                                                                             ▼
                      │                                                           ┌───────────────────────────────────┐
                      │                                                           │  Statistical Scoring & FDR Gate   │
                      │                                                           │  Strength, Robustness Resampling  │
                      │                                                           │  Benjamini-Hochberg (α = 0.05)    │
                      │                                                           └─────────────────┬─────────────────┘
                      │                                                                             │ FDR-Passed Insights
                      │                                                                             ▼
                      │                                                           ┌───────────────────────────────────┐
                      │                                                           │  Diversity Selection & Narration  │
                      │                                                           │  Grounding Guard (No Hallucinated)│
                      │                                                           └─────────────────┬─────────────────┘
                      │                                                                             │
                      └──────────────────────────────────────┬──────────────────────────────────────┘
                                                             │
                                                             ▼
                                      ┌──────────────────────────────────────────────┐
                                      │       Power BI DashboardSpec                 │
                                      │   Row 1: KPI Context Strip (Max 4 Tiles)     │
                                      │   Row 2: Hero Tile (w=8) + Side Tile (w=4)   │
                                      │   Row 3+: Supporting Grid (w=6 or w=4)       │
                                      │   Runtime Slicers & Dynamic Cross-Filtering  │
                                      │   Endpoint: POST /tile/{id}/query (DuckDB)   │
                                      └──────────────────────────────────────────────┘
```

---

## 🚀 Key Features & Capabilities

### 1. Ingestion & Semantic Profiling (`ingestion/`, `intelligence/`)
- **Format-Agnostic Loaders**: Ingests `.csv`, `.tsv`, `.xlsx`, and `.parquet` with strict validation, schema normalization, and read-only dataset immutability.
- **Statistical Profiler (`intelligence/profiler.py`)**: Computes cardinalities, distinct-to-non-null ratios, missingness rates, skewness, interquartile ranges, and summary statistics.
- **Semantic Classification (`intelligence/semantic_analyzer.py`)**:
  - Classifies columns into `MEASURE`, `DIMENSION`, `DATETIME`, or `IDENTIFIER`.
  - **Foreign Key Sub-Role**: Differentiates `PRIMARY_KEY` (near-unique entity identifiers, ratio $\ge 0.90$) from `FOREIGN_KEY` (repetitive identifiers like `CustomerID`, `ProductID` retained as valid grouping dimensions).
  - **Derived Measure Detection**: Automatically detects algebraic composite measures ($M_3 \approx M_1 \times M_2$, $M_1 + M_2$, or $M_1 / M_2$, e.g., `TotalSales == Quantity * UnitPrice`) with configurable tolerance (`DERIVED_TOLERANCE = 1e-3`) and marks them with the `DERIVED` sub-role.
- **Schema Readiness Gate (`intelligence/schema_validator.py`)**: Evaluates readiness (`READY`, `READY_WITH_WARNINGS`, `NOT_READY`). Blocks analytical execution on corrupted or unviable schemas.

### 2. Autonomous Insight Discovery Mode (`orchestrator/discovery/`)
- **Stage E Insight Discovery**: Automatically triggered on generic briefs (*"dashboard on this data"*, *"explore"*, or empty prompt).
- **Deterministic Candidate Enumeration across 8 Analytical Types**:
  1. `TOTAL_KPI`: Baseline measure totals (SUM for extensive amounts, AVG for rates/prices).
  2. `RANKING`: Top/bottom group concentration share over $k$ categories ($k \ge 3$).
  3. `COMPOSITION`: Proportional distribution and share of total.
  4. `TREND`: Linear regression over temporal intervals ($R^2$, slope, direction).
  5. `PERIOD_CHANGE`: Period-over-period delta and growth percentage.
  6. `DISTRIBUTION_OUTLIERS`: $Z$-score $> 3.0$ extreme outlier detection.
  7. `CORRELATION`: Bivariate Pearson correlation ($|r|$).
  8. `SEGMENT_GAP`: Categorical group disparity via ANOVA $\eta^2$.
- **Arithmetic Pruning**: Correlations between derived composite measures and their constituent factors are automatically pruned with reason `"arithmetic relationship"`.
- **COUNT Insights**: Datasets with or without measures receive `COUNT(*)` ranking and composition candidates across dimensions.
- **Benjamini-Hochberg FDR Control ($\alpha = 0.05$)**: Multiple hypothesis testing control eliminates false discoveries. Validated against a pure noise baseline across 100 seeds with an empirical false discovery rate of exactly **5.0% (5/100)**.
- **Number Grounding Guard**: Guarantees that every statistic emitted in generated narration text matches exact engine calculation results.

### 3. Stage F: Power BI-Style Interactive Dashboard (`frontend/`, `orchestrator/discovery/tiles.py`)
- **12-Column Deterministic Grid Geometry**:
  - **Row 1: KPI Context Strip**: Up to 4 context tiles (`w=3, h=2`) titled by measure semantics (*"Total Sales"*, *"Average Unit Price"*, never *"Total AVG"*), without p-values or strength badges.
  - **Row 2: Hero Tile + Side Tile**: Highest-scoring trend or ranking tile (`w=8, h=4`) paired with side composition tile (`w=4, h=4`).
  - **Row 3+: Supporting Grid**: Remaining visual insights placed in balanced 2- or 3-column layouts (`w=6` or `w=4`, `h=3`).
- **Deterministic Chart Mapping**:
  - `CORRELATION` $\to$ `scatter`
  - `SEGMENT_GAP` and `RANKING` $\to$ `bar`
  - `COMPOSITION` $\to$ `donut` ($\le 6$ slices) or `stacked` ($> 6$ slices)
  - `TREND` $\to$ `line`
  - `DISTRIBUTION` $\to$ `histogram`
- **Interactive Runtime Slicers**:
  - `date_range` slider for datetime columns.
  - `multi_select` checkboxes for low-cardinality dimensions ($\le 12$ distinct values).
- **Dynamic Tile Cross-Filtering**:
  - Backend endpoint `POST /api/dashboard/{spec_id}/tile/{tile_id}/query` dynamically recompiles candidate plans into parameterized DuckDB SQL with injected filter conditions and returns updated rows in real time.
- **Single Robustness Floor (`ROBUSTNESS_FLOOR = 0.35`)**: Single configuration source of truth in `orchestrator/config.py`. Triggers an amber **"Low stability"** warning badge on headline insights if robustness $< 0.35$.
- **Design System**: Rich dual-mode light/dark themes with Warm Beige, Deep Charcoal, and Burnt Orange design tokens. Zero hardcoded colors.

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11 & 3.13)
- Node.js 18+ & npm
- (Optional) [Ollama](https://ollama.ai/) for local offline LLM inference

### 2. Backend Setup
From the repository root:
```powershell
# Create and activate virtual environment (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# (macOS/Linux: source .venv/bin/activate)

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup
```powershell
cd frontend
npm install
cd ..
```

### 4. Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```

Configure your desired LLM provider (optional for local/discovery baseline):
```ini
PROVIDER=gemini

# Google Gemini API (https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Groq Cloud API (https://console.groq.com/keys)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Ollama Local Daemon (offline, no API key needed)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
```

---

## 🚀 Running the Platform

### Terminal 1: Backend API Server
```powershell
python -m uvicorn api.main:app --port 8000
```
- API Base: `http://localhost:8000`
- Swagger Interactive API Docs: `http://localhost:8000/docs`

### Terminal 2: Next.js Web Frontend
```powershell
cd frontend
npm run dev
```
- Web Application: `http://localhost:3000`

---

## 🧪 Comprehensive Test Suite

The test suite runs **327 collected test items** with **NO `--ignore` flags**:

```powershell
# Run the complete test suite
pytest -vv
```

### Summary Output:
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
rootdir: AI-Driven-Business-Intelligence-Dashboard-Automation-Platform
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.13.0
collected 327 items

tests\test_api.py ............                                           [  3%]
tests\test_architecture_conformance.py .......................           [ 10%]
tests\test_canonical_model.py .........                                  [ 13%]
tests\test_chart_mapping.py ......                                       [ 15%]
tests\test_chart_svg_marks.py .                                          [ 15%]
tests\test_cleaning_layer.py ......                                      [ 17%]
tests\test_dashboard_panels_stage_c.py ........                          [ 19%]
tests\test_headline_robustness.py ...                                    [ 20%]
tests\test_ingestion_loaders.py ...............                          [ 25%]
tests\test_insight_discovery_stage_e.py .......                          [ 27%]
tests\test_inspect.py .                                                  [ 27%]
tests\test_llm_live.py sss                                               [ 28%]
tests\test_locator.py .                                                  [ 29%]
tests\test_narration_bands.py .....                                      [ 30%]
tests\test_noise_gate_100_seeds.py .                                     [ 30%]
tests\test_orchestrator_schemas.py ..................................... [ 42%]
..................                                                       [ 47%]
tests\test_orchestrator_stage4.py ....................                   [ 53%]
tests\test_orchestrator_stage5.py ..........                             [ 56%]
tests\test_orchestrator_stage6.py ......................                 [ 63%]
tests\test_orchestrator_stage7.py ........                               [ 66%]
tests\test_pass2_and_cascade.py ........                                 [ 68%]
tests\test_profiling_engine.py .........                                 [ 71%]
tests\test_result_and_clarification.py .                                 [ 71%]
tests\test_robustness_stage_a.py ......                                  [ 73%]
tests\test_run.py .                                                      [ 73%]
tests\test_schema_readiness.py .......................                   [ 80%]
tests\test_semantic_analyzer.py ................................         [ 90%]
tests\test_semantic_profile_v1_contract.py ........                      [ 92%]
tests\test_stage4b_fixes.py .........                                    [ 95%]
tests\test_tie_clarification_stage_b.py ..........                       [ 98%]
tests\test_tile_query_backend_stage_f.py ....                            [100%]

================= 324 passed, 3 skipped in 261.35s (0:04:21) ==================
```

---

## 📚 Technical Documentation Directory

| Document | Description |
| :--- | :--- |
| [`docs/stage_e_insight_discovery.md`](docs/stage_e_insight_discovery.md) | Stage E Insight Discovery Mode, candidate enumeration, Benjamini-Hochberg FDR control, and grounding guard |
| [`docs/stage_f_power_bi_dashboard.md`](docs/stage_f_power_bi_dashboard.md) | Stage F Power BI 12-column grid layout, runtime slicers, DuckDB dynamic tile recompilation, and browser testing |
| [`docs/column_roles.md`](docs/column_roles.md) | Semantic column roles, `PRIMARY_KEY` / `FOREIGN_KEY` sub-roles, and `DERIVED` measure detection |
| [`docs/ranker_v1_spec.md`](docs/ranker_v1_spec.md) | Deterministic Ranker V1 mathematical specification and multi-provider agreement scoring |
| [`docs/multi_agent_generator.md`](docs/multi_agent_generator.md) | Multi-provider LLM integration, parallel dispatch, and agent sandboxing |
| [`docs/orchestrator_contracts.md`](docs/orchestrator_contracts.md) | Complete schemas, validation contracts, and DashboardSpec data models |
| [`docs/orchestrator_conformance.md`](docs/orchestrator_conformance.md) | Traceability matrix between design requirements and staged implementation |
| [`docs/canonical_data_model.md`](docs/canonical_data_model.md) | Canonical dataset representations and immutability invariants |
| [`docs/schema_readiness.md`](docs/schema_readiness.md) | Data readiness gates and structural integrity rules |
| [`docs/semantic_intelligence.md`](docs/semantic_intelligence.md) | Rule-based semantic classification engine and confidence scoring |
| [`docs/profiling_engine.md`](docs/profiling_engine.md) | Statistical profiling engine algorithms |
| [`docs/ingestion_loaders.md`](docs/ingestion_loaders.md) | Multi-format file ingestion architecture |
| [`docs/product_ui_foundation.md`](docs/product_ui_foundation.md) | UI foundation, component hierarchy, and design tokens |
| [`docs/known_issues.md`](docs/known_issues.md) | Known issues, tracking log, and resolution histories |
