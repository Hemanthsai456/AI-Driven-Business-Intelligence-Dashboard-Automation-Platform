import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion import CSVLoader
from intelligence import analyze_semantics, assess_readiness, profile_dataset
from orchestrator.discovery import run_discovery_pipeline, generate_agent_proposals

files = ['Sales_2024.csv', 'Customers.csv']
base_dir = Path('tests/real_data')
loader = CSVLoader()

for fname in files:
    fpath = base_dir / fname
    dataset = loader.load(fpath)
    profiler_res = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profiler_res)
    readiness = assess_readiness(dataset)

    print("=" * 80)
    print(f"DATASET: {fname}")
    print("=" * 80)
    print("PROFILED COLUMN ROLES & SUB-ROLES:")
    for col, ev in sem_profile.column_evidences.items():
        sub_info = f" [sub_role: {ev.sub_role}]" if ev.sub_role else ""
        derived_info = f" (DERIVED: {ev.derived_parts} via {ev.derived_op})" if ev.derived_parts else ""
        print(f"  - {col}: {ev.candidate_role.value}{sub_info}{derived_info}")

    # Run discovery with agent proposals enabled
    spec, rejected, summary = run_discovery_pipeline(
        dataset=dataset,
        semantic_profile=sem_profile,
        readiness=readiness,
        intent="dashboard on this data",
        include_agent_proposals=True,
    )

    print("\nPROVENANCE BREAKDOWN:")
    print(f"  Enumerator Proposed:     {summary.enumerator_proposed}")
    print(f"  Agent Proposed:          {summary.agent_proposed}")
    print(f"  Enumerator FDR Survived: {summary.enumerator_fdr_passed}")
    print(f"  Agent FDR Survived:      {summary.agent_fdr_passed}")
    print(f"  Total FDR Survived:      {summary.candidates_fdr_passed}")
    print(f"  Enumerator Selected:     {summary.enumerator_selected}")
    print(f"  Agent Selected:          {summary.agent_selected}")
    print(f"  Total Selected:          {summary.candidates_selected}")
    if summary.agent_selected == 0:
        print("  Notice: Agents contributed zero selected insights.")

    print("\nTILES (GRID LAYOUT WITH CHART TYPE & PROVENANCE):")
    if hasattr(spec, "tiles") and spec.tiles:
        for idx, t in enumerate(spec.tiles, start=1):
            ev_str = f"Strength={t.evidence.strength:.2f}, Robustness={t.evidence.robustness:.2f}, Score={t.evidence.score:.2f}" if t.evidence else "Context Tile (No Score)"
            print(f"  Tile {idx}: [{t.chart_type.upper()}] '{t.title}' | Grid: w={t.size.w}, h={t.size.h} | Source: {t.generator} | {ev_str}")
    else:
        print("  No tiles generated.")

    print("\nREJECTED CANDIDATES SAMPLE (ARITHMETIC & PRUNED):")
    arithmetic_rejections = [r for r in rejected if "arithmetic" in str(r.get("reason", "")).lower()]
    for r in arithmetic_rejections[:5]:
        print(f"  [ARITHMETIC REJECTION] {r.get('description')}: {r.get('reason')}")
    other_rejections = [r for r in rejected if "arithmetic" not in str(r.get("reason", "")).lower()]
    for r in other_rejections[:5]:
        print(f"  [{r.get('rejection_stage')}] {r.get('description')}: {r.get('reason')}")
    print("\n")
