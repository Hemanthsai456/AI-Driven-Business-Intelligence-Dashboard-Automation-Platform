# Known Issues Log

This document tracks all identified issues, edge cases, anomalies, and deferred items discovered across execution stages, annotated with severity.

| Issue ID | Stage Discovered | Component | Description | Severity | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KI-001** | Stage 0 | Tooling / Git | `.gitignore` previously contained `lib/`, ignoring `frontend/lib/api.ts` and `types.ts`. Resolved by anchoring `/lib/` and adding `!frontend/lib/`. | LOW | RESOLVED |
| **KI-002** | Stage 0 | API Store | `datetime.utcnow()` deprecation warnings in `api/store.py`. Resolved using `datetime.now(timezone.utc)`. | LOW | RESOLVED |
| **KI-003** | Stage 0 | Ingestion Docs | Documentation references indicated 50MB and CSV/XLSX only, while backend had expanded to TSV/Parquet and 100MB limit. Resolved in docs. | LOW | RESOLVED |
| **KI-004** | Stage 2 | Test Fixtures | `tests/real_data/` directory was initially empty at first Stage 2 attempt (OneDrive sync delay). Files present at second attempt: Calendar.csv, Customers.csv, Products.csv, Sales_2024.csv, Sales_2025.csv, Stores.csv. | MEDIUM | RESOLVED |
| **KI-005** | Stage 2 | Semantic Analyzer | `Calendar.csv::Year` classified as UNKNOWN (conf=0.30) instead of DIMENSION. Root cause: constant-column guard fires before calendar-component name-token rule. Year is a valid temporal dimension even when constant in a single-year calendar dataset. | MEDIUM | OPEN — Fix deferred to Stage 3+ (no HIGH-severity errors found; no fix applied in Stage 2 per spec). |

