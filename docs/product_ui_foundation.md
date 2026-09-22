# Phase 1 Product UI/UX Foundation Specification

## Architecture Overview

Phase 1 establishes a decoupled frontend and backend REST API architecture:

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
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Ingestion     Profiling    Semantic
                                  Engine
```

---

## Technical Stack

- **Frontend**: Next.js 14 App Router, React 18, TypeScript, Tailwind CSS, Lucide React icons.
- **Backend API**: FastAPI, Uvicorn, Pydantic V2, Python 3.11.
- **Python Intelligence Engine**: Locked baseline (`ingestion/` loaders, `intelligence/` profiler, semantic analyzer, and schema validator).

---

## REST API Specification

### 1. Health Check
`GET /api/health`
- **Response**: `200 OK`
- Returns system status and active engine capabilities.

### 2. Dataset Upload & Ingestion
`POST /api/datasets/upload`
- **Content-Type**: `multipart/form-data`
- **Body**: `file` (.csv, .xlsx)
- **Behavior**: Delegates file stream to `CSVLoader` or `ExcelLoader`, runs `profile_dataset()`, `analyze_semantics()`, and `assess_readiness()`. Saves dataset record to session store.
- **Response**: `201 Created` with structured `DatasetMetadataResponse`.

### 3. List Active Session Datasets
`GET /api/datasets`
- **Response**: `200 OK` list of loaded dataset summaries.

### 4. Get Dataset Metadata
`GET /api/datasets/{dataset_id}`
- **Response**: `200 OK` dataset metadata schema.

### 5. Interactive Data Preview
`GET /api/datasets/{dataset_id}/preview?limit=50`
- **Response**: `200 OK` with limited preview rows (first 50 rows) for fast table rendering.

### 6. Data Profile
`GET /api/datasets/{dataset_id}/profile`
- **Response**: `200 OK` full `DataProfile` JSON dictionary.

### 7. Semantic Intelligence
`GET /api/datasets/{dataset_id}/semantic-analysis`
- **Response**: `200 OK` full `DatasetSemanticProfile` JSON dictionary.

### 8. Schema Integrity & Readiness
`GET /api/datasets/{dataset_id}/readiness`
- **Response**: `200 OK` `AnalysisReadiness` assessment object.

---

## Local Startup Instructions

### Terminal 1: Start Backend API
```powershell
# From workspace root:
python -m uvicorn api.main:app --reload --port 8000
```
Backend API interactive documentation available at: `http://localhost:8000/docs`

### Terminal 2: Start Next.js Frontend
```powershell
# From workspace root:
cd frontend
npm run dev
```
Open browser at: `http://localhost:3000`

---

## Development-Stage Limitations

1. **In-Memory Session Store**: Datasets uploaded during a dev session are stored in server memory (`api/store.py`).
2. **50MB Upload Limit**: File uploads are capped at 50MB for local development safety.
3. **No Authentication / RBAC**: Auth is intentionally deferred to future iterations per spec.
