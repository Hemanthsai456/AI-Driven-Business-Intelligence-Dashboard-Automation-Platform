# AI-Driven Business Intelligence & Dashboard Automation Platform

An automated, end-to-end platform for data ingestion, profiling, cleaning, semantic understanding, analytical planning, KPI/chart generation, and interactive dashboard rendering.

---

## Current Development Stage

**Phase 1 — Ingestion, Profiling & Semantic Intelligence Foundation (Step 4 Complete)**

Currently, the project foundation, ingestion loaders, data profiling engine, and rule-based semantic analyzer have been established:
- **Canonical Data Model**: Format-agnostic dataclasses (`ColumnRole`, `ColumnMetadata`, `DatasetMetadata`, `DataProfile`, `CanonicalDataset`) in `ingestion/models.py`.
- **CSV & XLSX Data Loaders**: `CSVLoader` and `ExcelLoader` in `ingestion/loaders/` transforming CSV and single-worksheet XLSX files into `CanonicalDataset`.
- **Deterministic Data Profiling Engine**: `DataProfiler` in `intelligence/profiler.py` generating read-only statistical profiles, dataset summaries, column metrics, correlation matrices, and non-destructive quality observations.
- **Rule-Based Semantic Intelligence**: `SemanticAnalyzer` in `intelligence/semantic_analyzer.py` classifying preliminary candidate column roles (`MEASURE`, `DIMENSION`, `DATETIME`, `IDENTIFIER`, `UNKNOWN`) with explainable evidence and deterministic confidence scoring.
- **Documentation**: Detailed specifications in [`docs/column_roles.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/column_roles.md), [`docs/canonical_data_model.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/canonical_data_model.md), [`docs/ingestion_loaders.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/ingestion_loaders.md), [`docs/profiling_engine.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/profiling_engine.md), and [`docs/semantic_intelligence.md`](file:///d:/Mini-Project/github%20repo/AI-Driven-Business-Intelligence-Dashboard-Automation-Platform/docs/semantic_intelligence.md).

> **Note:** AI/LLM semantic reasoning, analytical planning, DuckDB query integration, PostgreSQL metadata persistence, and automated dashboard generation will be introduced in subsequent phases after checkpoint reviews.

---

## Installation & Setup

1. **Requirements:**
   Python 3.11+

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Tests:**
   ```bash
   pytest -v
   ```