# Known Issues Log

This document tracks all identified issues, edge cases, anomalies, and deferred items discovered across execution stages, annotated with severity.

| Issue ID | Stage Discovered | Component | Description | Severity | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KI-001** | Stage 0 | Tooling / Git | `.gitignore` previously contained `lib/`, ignoring `frontend/lib/api.ts` and `types.ts`. Resolved by anchoring `/lib/` and adding `!frontend/lib/`. | LOW | RESOLVED |
| **KI-002** | Stage 0 | API Store | `datetime.utcnow()` deprecation warnings in `api/store.py`. Resolved using `datetime.now(timezone.utc)`. | LOW | RESOLVED |
| **KI-003** | Stage 0 | Ingestion Docs | Documentation references indicated 50MB and CSV/XLSX only, while backend had expanded to TSV/Parquet and 100MB limit. Resolved in docs. | LOW | RESOLVED |
| **KI-004** | Stage 2 | Test Fixtures | `tests/real_data/` directory was initially empty at first Stage 2 attempt (OneDrive sync delay). Files present at second attempt: Calendar.csv, Customers.csv, Products.csv, Sales_2024.csv, Sales_2025.csv, Stores.csv. | MEDIUM | RESOLVED |
| **KI-005** | Stage 2 | Semantic Analyzer | `Calendar.csv::Year` classified as UNKNOWN (conf=0.30) instead of DIMENSION. Root cause: constant-column guard fires before calendar-component name-token rule. Year is a valid temporal dimension even when constant in a single-year calendar dataset. | MEDIUM | RESOLVED |
| **KI-006** | Stage 8 | Orchestrator Schemas | `RankerWeights.w5_agreement` lacked a default value, causing Pydantic validation errors when initialized with 4-weight configs. Resolved by adding `default=0.0`. | MEDIUM | RESOLVED |
| **KI-007** | Stage 8 | Environment Dependencies | `jsonschema` and `pyarrow` were missing from the local virtual environment / `requirements.txt`. Resolved by adding `jsonschema>=4.20.0`, `pyarrow>=14.0.0`, and `python-dotenv>=1.0.0` to `requirements.txt`. | HIGH | RESOLVED |
| **KI-008** | Stage 8 | Orchestrator Generators | `LLMDirectGenerator` and `MockAgent` were omitted during the multi-provider generator overhaul in commit `b5032e0`, breaking unit test imports. Resolved by restoring both classes in `orchestrator/generator.py` alongside `MultiProviderGenerator`. | HIGH | RESOLVED |
| **KI-009** | Stage F | Frontend / Recharts | Recharts `ResponsiveContainer` collapsed to 0px height inside dynamic grid cells lacking explicit min-height. Resolved by applying `min-h-[220px]` class. | HIGH | RESOLVED |
| **KI-010** | Stage F | Frontend Page | `canRun` state prevented executing generic brief / auto-dashboard when intent prompt input was empty. Resolved by adding `|| isAutoDashboard` to condition. | HIGH | RESOLVED |
| **KI-011** | Stage F | API / Security | String representation of list filter values (`str(['Value'])`) triggered false-positive SQL injection detection due to Python list quotes. Resolved by checking individual string items. | HIGH | RESOLVED |
| **KI-012** | Stage F | Discovery / DuckDB | Compiler and direct DuckDB calculations attempted `SUM(*)` on wildcard count metrics. Resolved by branching to `COUNT(*)` when metric is wildcard or count. | MEDIUM | RESOLVED |

