import requests, json

BASE_URL = 'http://localhost:8000'
with open('scratch/current_behavior_audit.json') as f:
    audit_data = json.load(f)

discovery_results = []
for ds_name in ['healthcare', 'education', 'iot']:
    ds_id = audit_data['upload_metadata'][ds_name]['dataset_id']
    resp = requests.post(f'{BASE_URL}/api/orchestrator/pipeline', json={
        'dataset_id': ds_id,
        'intent': 'overview',
        'require_clarification': False
    })
    data = resp.json()
    status = data.get('status')
    spec = data.get('dashboard_spec') or {}
    panels = spec.get('panels') or []
    tiles = spec.get('tiles') or []
    slicers = spec.get('slicers') or []
    headline = spec.get('headline')
    mode = spec.get('mode')
    summary = spec.get('discovery_summary') or {}
    
    print(f"=== {ds_name.upper()} [intent: 'overview'] ===")
    print(f"Status: {status} | Mode: {mode} | Panels: {len(panels)} | Tiles: {len(tiles)} | Slicers: {len(slicers)}")
    print(f"Headline: {headline}")
    print(f"Discovery Summary: {summary}")
    print("Tiles breakdown:")
    for idx, t in enumerate(tiles):
        print(f"  {idx+1}. [{t.get('chart_type')}] {t.get('title')} | w={t.get('size', {}).get('w')}, h={t.get('size', {}).get('h')} | rows={len(t.get('data') or [])} | x={t.get('x_key')}, y={t.get('y_keys')}")
    print()

    discovery_results.append({
        "dataset": ds_name,
        "status": status,
        "mode": mode,
        "panels_count": len(panels),
        "tiles_count": len(tiles),
        "slicers_count": len(slicers),
        "headline": headline,
        "summary": summary,
        "tiles": tiles,
        "slicers": slicers,
    })

with open("scratch/discovery_audit_results.json", "w") as f:
    json.dump(discovery_results, f, indent=2)
