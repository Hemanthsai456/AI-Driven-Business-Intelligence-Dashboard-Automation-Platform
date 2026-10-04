import os
import json
import time
import requests

BASE_URL = "http://localhost:8000"

datasets_to_test = {
    "healthcare": "tests/real_data/healthcare.csv",
    "education": "tests/real_data/education.csv",
    "iot": "tests/real_data/iot.csv",
    "hr": "tests/real_data/hr.csv",
    "logistics": "tests/real_data/logistics.csv",
}

high_level_prompts = [
    "Give me an overview of this dataset.",
    "What are the most important things I should know from this data?",
    "Show me the most useful trends and comparisons.",
]

# Upload datasets and capture upload metadata
uploaded_metadata = {}
for name, filepath in datasets_to_test.items():
    print(f"Uploading {name} ({filepath})...")
    with open(filepath, "rb") as f:
        resp = requests.post(f"{BASE_URL}/api/datasets/upload", files={"file": (os.path.basename(filepath), f, "text/csv")})
    assert resp.status_code in (200, 201), f"Upload failed for {name}: {resp.status_code} - {resp.text}"
    meta = resp.json()
    uploaded_metadata[name] = meta
    print(f"  -> Uploaded as {meta['dataset_id']} ({meta['row_count']} rows, {meta['column_count']} cols)")

# Also fetch semantic profile for each
semantic_profiles = {}
for name, meta in uploaded_metadata.items():
    ds_id = meta["dataset_id"]
    sem_resp = requests.get(f"{BASE_URL}/api/datasets/{ds_id}/semantic-analysis")
    if sem_resp.status_code == 200:
        semantic_profiles[name] = sem_resp.json()

results = []

for name in ["healthcare", "education", "iot"]:
    ds_id = uploaded_metadata[name]["dataset_id"]
    for prompt in high_level_prompts:
        print(f"\n--- Testing [{name}] with prompt: {repr(prompt)} ---")
        t0 = time.time()
        payload = {
            "dataset_id": ds_id,
            "intent": prompt,
            "require_clarification": False,
        }
        resp = requests.post(f"{BASE_URL}/api/orchestrator/pipeline", json=payload, timeout=90)
        dur = round(time.time() - t0, 2)
        code = resp.status_code
        data = resp.json() if code == 200 else {}
        status = data.get("status", f"HTTP_{code}")
        
        spec = data.get("dashboard_spec") or {}
        panels = spec.get("panels") or []
        tiles = spec.get("tiles") or []
        slicers = spec.get("slicers") or []
        headline = spec.get("headline", "")
        mode = spec.get("mode", "focused" if spec else "none")
        winner = spec.get("winner") or {}
        winner_plan = winner.get("plan") or {}
        
        rec = {
            "dataset": name,
            "prompt": prompt,
            "status": status,
            "duration_s": dur,
            "mode": mode,
            "headline": headline,
            "panels": [
                {
                    "panel_id": p.get("panel_id"),
                    "panel_type": p.get("panel_type"),
                    "title": p.get("title"),
                    "x_key": p.get("x_key"),
                    "y_keys": p.get("y_keys"),
                    "data_rows": len(p.get("data") or []),
                }
                for p in panels
            ],
            "tiles": [
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "chart_type": t.get("chart_type"),
                    "size": t.get("size"),
                    "data_rows": len(t.get("data") or []),
                    "x_key": t.get("x_key"),
                    "y_keys": t.get("y_keys"),
                    "generator": t.get("generator"),
                }
                for t in tiles
            ],
            "slicers": [
                {
                    "column": s.get("column"),
                    "control_type": s.get("control_type"),
                    "options_count": len(s.get("options") or []),
                }
                for s in slicers
            ],
            "winner_metric": f"{winner_plan.get('metric', {}).get('aggregation')} of {winner_plan.get('metric', {}).get('column')}",
            "winner_dimensions": [d.get("column") for d in winner_plan.get("dimensions", [])],
        }
        results.append(rec)
        print(f"  Result: status={status}, mode={mode}, panels={len(panels)}, tiles={len(tiles)}, dur={dur}s")
        if tiles:
            for idx, t in enumerate(tiles):
                print(f"    Tile {idx+1}: [{t['chart_type']}] \"{t['title']}\" (rows={t['data_rows']}, x={t['x_key']}, y={t['y_keys']})")

with open("scratch/current_behavior_audit.json", "w") as f:
    json.dump({
        "upload_metadata": uploaded_metadata,
        "semantic_profiles": semantic_profiles,
        "test_results": results
    }, f, indent=2)

print("\nAudit saved to scratch/current_behavior_audit.json")
