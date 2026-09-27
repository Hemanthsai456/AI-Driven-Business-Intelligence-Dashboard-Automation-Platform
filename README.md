# AI-Driven Business Intelligence & Dashboard Automation Platform

An automated, end-to-end platform for data ingestion, profiling, semantic understanding, schema readiness assessment, and interactive web-based business intelligence analysis.

---

## Architecture & System Overview

```
                      Browser User
                           │
                           ▼
                 Next.js 14 / React 18
                      TypeScript
                           │
                     HTTP REST API
                           │
                           ▼
                    FastAPI Backend
                           │
                           ▼
                 Existing Python Engine
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      Ingestion        Profiling        Semantic
       Engine           Engine           Engine
```

---

## Current Capabilities (Phase 1 Complete)

- **Production Next.js Web Frontend** (`frontend/`): Next.js 14 App Router, React 18, TypeScript, Tailwind CSS interface featuring drag-and-drop file uploader, dataset overview metrics, data preview table, interactive column profiling inspector, and semantic evidence inspector.
- **FastAPI HTTP REST API** (`api/`): Clean backend service wrapping Python engine loaders/analyzers (`/api/datasets/upload`, `/api/datasets/{id}/preview`, `/api/datasets/{id}/profile`, `/api/datasets/{id}/semantic-analysis`, `/api/datasets/{id}/readiness`).
- **Canonical Data Model** (`ingestion/models.py`): Format-agnostic dataclasses (`ColumnRole`, `ColumnMetadata`, `DatasetMetadata`, `DataProfile`, `CanonicalDataset`).
- **CSV, TSV, XLSX & Parquet Ingestion Loaders** (`ingestion/loaders/`): Format-agnostic `CSVLoader`, `TSVLoader`, `ExcelLoader`, and `ParquetLoader` with encoding detection and header disambiguation.
- **Data Profiling Engine** (`intelligence/profiler.py`): Deterministic statistical profiler generating distributions, missingness metrics, distinct counts, quantiles, and quality observations.
- **Rule-Based Semantic Intelligence** (`intelligence/semantic_analyzer.py`): Preliminary candidate column role classification (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, `UNKNOWN`) with explainable evidence rules and confidence scores.
- **Schema Validation & Readiness** (`intelligence/schema_validator.py`): Structural integrity validator producing `AnalysisReadiness` assessments for downstream analytical execution.

---

## Installation Commands

### 1. Backend Dependency Installation (Python)
From the project root directory:
```powershell
pip install -r requirements.txt
```
*(Dependencies: `pandas`, `openpyxl`, `pyarrow`, `pytest`, `fastapi`, `uvicorn`, `python-multipart`, `httpx`)*

### 2. Frontend Dependency Installation (Next.js / Node.js)
Navigate into the `frontend` folder and run `npm install`:
```powershell
cd frontend
npm install
```
*(Dependencies: `next`, `react`, `react-dom`, `typescript`, `tailwindcss`, `lucide-react`)*

---

## How to Run the Project

### Step 1: Run the Backend API Server
Open Terminal 1 in the project root directory:
```powershell
python -m uvicorn api.main:app --reload --port 8000
```
- **Backend API Base**: `http://localhost:8000`
- **Interactive Swagger Documentation**: `http://localhost:8000/docs`

### Step 2: Run the Web Frontend
Open Terminal 2 in the project root directory:
```powershell
cd frontend
npm run dev
```
- **Web Interface URL**: `http://localhost:3000`

---

## How to Run Tests

To run all 82 unit and API integration tests:
```powershell
python -m pytest tests/ -v
```

---

## Documentation

- [`docs/product_ui_foundation.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/product_ui_foundation.md): Product UI & REST API specification.
- [`docs/schema_readiness.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/schema_readiness.md): Schema validation & readiness specification.
- [`docs/semantic_intelligence.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/semantic_intelligence.md): Semantic intelligence engine documentation.
- [`docs/profiling_engine.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/profiling_engine.md): Data profiling engine documentation.
- [`docs/ingestion_loaders.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/ingestion_loaders.md): Ingestion loaders specification.