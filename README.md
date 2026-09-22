# AI-Driven Business Intelligence & Dashboard Automation Platform

An automated, end-to-end platform for data ingestion, profiling, cleaning, semantic understanding, analytical planning, KPI/chart generation, and interactive dashboard rendering.

---

## Current Development Stage

**Phase 1 — Product UI/UX Foundation & Intelligence Engine (Complete)**

Currently, the production web interface, REST API, ingestion loaders, data profiling engine, rule-based semantic analyzer, and schema readiness engine are established:
- **Product Frontend**: Next.js 14 / React 18 / TypeScript interface in `frontend/` featuring drag-and-drop file uploader, dataset overview KPIs, data preview table, interactive column profiling inspector, and semantic rule-evidence inspector.
- **Backend HTTP REST API**: FastAPI application in `api/` wrapping existing Python intelligence engine functions (`/api/datasets/upload`, `/api/datasets/{id}/profile`, `/api/datasets/{id}/semantic-analysis`, `/api/datasets/{id}/preview`, `/api/datasets/{id}/readiness`).
- **Canonical Data Model**: Format-agnostic dataclasses (`ColumnRole`, `ColumnMetadata`, `DatasetMetadata`, `DataProfile`, `CanonicalDataset`) in `ingestion/models.py`.
- **CSV & XLSX Data Loaders**: `CSVLoader` and `ExcelLoader` in `ingestion/loaders/` transforming CSV and single-worksheet XLSX files into `CanonicalDataset`.
- **Deterministic Data Profiling Engine**: `DataProfiler` in `intelligence/profiler.py` generating statistical profiles, dataset summaries, column metrics, correlation matrices, and quality observations.
- **Rule-Based Semantic Intelligence**: `SemanticAnalyzer` in `intelligence/semantic_analyzer.py` classifying candidate column roles (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, `UNKNOWN`) with explainable evidence rules and confidence scoring.
- **Schema & Analysis Readiness**: `SchemaValidator` in `intelligence/schema_validator.py` verifying dataset structural integrity prior to analytical execution.
- **Documentation**: Detailed specifications in `docs/product_ui_foundation.md`, `docs/schema_readiness.md`, `docs/semantic_intelligence.md`, `docs/profiling_engine.md`, and `docs/ingestion_loaders.md`.

---

## Local Development & Startup

### 1. Install Backend Dependencies & Run Pytest Suite
```powershell
pip install -r requirements.txt
python -m pytest tests/ -v
```

### 2. Start Backend API Server
```powershell
python -m uvicorn api.main:app --reload --port 8000
```

### 3. Start Next.js Web Frontend
```powershell
cd frontend
npm install
npm run dev
```

Open browser at `http://localhost:3000`.