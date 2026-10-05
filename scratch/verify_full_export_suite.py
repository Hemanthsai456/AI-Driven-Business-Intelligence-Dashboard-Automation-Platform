import os
import json
from tests.test_focused_multi_tile_dashboard import _load_real_dataset
from orchestrator.pipeline import run_orchestration_pipeline

datasets = ["education.csv", "healthcare.csv", "hr.csv"]

for ds in datasets:
    canonical, profile, sem_profile, readiness = _load_real_dataset(ds)
    res = run_orchestration_pipeline(
        intent=f"Executive dashboard for {ds}",
        dataset=canonical,
        semantic_profile=sem_profile,
        readiness=readiness,
        data_profile=profile,
        require_clarification=False,
    )
    if res.dashboard_spec:
        print(f"Dataset: {ds} | Tiles: {len(res.dashboard_spec.tiles)}")
        for t in res.dashboard_spec.tiles:
            print(f"  - Tile: {t.title} | Type: {t.chart_type} | Dims: {t.dimensions} | Metrics: {t.metrics} | Data rows: {len(t.data) if t.data else 0}")
print("Verification complete.")
