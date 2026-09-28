# Known Issues Log

This document tracks all identified issues, edge cases, anomalies, and deferred items discovered across execution stages, annotated with severity.

| Issue ID | Stage Discovered | Component | Description | Severity | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KI-001** | Stage 0 | Tooling / Git | `.gitignore` previously contained `lib/`, ignoring `frontend/lib/api.ts` and `types.ts`. Resolved by anchoring `/lib/` and adding `!frontend/lib/`. | LOW | RESOLVED |
| **KI-002** | Stage 0 | API Store | `datetime.utcnow()` deprecation warnings in `api/store.py`. Resolved using `datetime.now(timezone.utc)`. | LOW | RESOLVED |
| **KI-003** | Stage 0 | Ingestion Docs | Documentation references indicated 50MB and CSV/XLSX only, while backend had expanded to TSV/Parquet and 100MB limit. Resolved in docs. | LOW | RESOLVED |
| **KI-004** | Stage 2 | Test Fixtures | `tests/real_data/` directory does not exist / is empty. Halting Stage 2 execution per prompt instruction ('If it is empty, stop and tell me. Do not synthesize data.'). | MEDIUM | OPEN (Awaiting user data) |

