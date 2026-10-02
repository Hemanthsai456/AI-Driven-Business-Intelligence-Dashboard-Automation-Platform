"""Run Stage A Robustness Evaluation on 3 real data files with analytical briefs."""

import os
import pandas as pd

from cleaning.cleaner import clean_dataset
from engine.executor import get_default_engine
from ingestion.loaders.csv_loader import CSVLoader
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.ambiguity import assess_ambiguity
from orchestrator.config import (
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RANK_W5_AGREEMENT,
)
from orchestrator.intent import interpret_user_request
from orchestrator.interpretation import generate_interpretations
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    RankerWeights,
    VisualizationType,
)
from orchestrator.utils import rank_candidates
from orchestrator.validator import validate_pass1a, validate_pass1b


def run_brief_on_file(csv_path: str, brief: str):
    print(f"\n{'='*80}")
    print(f"Dataset File: {csv_path}")
    print(f"Analytical Brief: \"{brief}\"")
    print(f"{'='*80}")

    raw_ds = CSVLoader().load(csv_path)
    cleaned_ds, _ = clean_dataset(raw_ds)
    profile = profile_dataset(cleaned_ds)
    semantic_profile = analyze_semantics(cleaned_ds, profile=profile)

    structured_intent = interpret_user_request(brief, semantic_profile)
    ambiguity = assess_ambiguity(structured_intent, semantic_profile)

    print(f"Ambiguity Status: {ambiguity.status.value} (is_blocking={ambiguity.is_blocking})")
    if ambiguity.ambiguities:
        for a in ambiguity.ambiguities:
            print(f"  - [{a.type.value}] {a.field}: {a.alternatives}")

    interps = generate_interpretations(structured_intent, semantic_profile, ambiguity=ambiguity, k=3)
    if not interps:
        # Fallback interpretation from structured intent
        interps = generate_interpretations(structured_intent, semantic_profile, k=3)

    engine = get_default_engine()
    candidates = []

    for idx, interp in enumerate(interps, start=1):
        dims = [
            DimensionSpec(column=col, granularity=interp.granularity)
            for col in interp.dimension_columns
        ]
        plan = CandidatePlan(
            plan_id=f"plan_{idx}",
            dataset_id=cleaned_ds.metadata.dataset_id,
            intent=brief,
            metric=MetricSpec(column=interp.metric_column, aggregation=interp.aggregation),
            dimensions=dims,
            filters=interp.filter_specs,
            visualization=interp.visualization,
            generator="interpretation_generator",
            provider="deterministic",
            supporting_count=1,
            providers_responded=1,
            reasoning=PlanReasoning(
                interpretation=interp.intent_summary,
                evidence=interp.evidence,
            ),
        )

        p1a = validate_pass1a(plan, semantic_profile)
        if not p1a.passed:
            continue

        exec_res = engine.execute(plan, cleaned_ds, semantic_profile)
        p1b = validate_pass1b(plan, exec_res)
        if not p1b.passed:
            continue

        candidates.append((plan, exec_res))

    if not candidates:
        print("No valid candidates generated.")
        return

    weights = RankerWeights(
        w1_evidence=RANK_W1_EVIDENCE,
        w2_coverage=RANK_W2_COVERAGE,
        w3_stability=RANK_W3_STABILITY,
        w4_assumptions=RANK_W4_ASSUMPTIONS,
        w5_agreement=RANK_W5_AGREEMENT,
    )

    ranked, is_tie = rank_candidates(
        candidates=candidates,
        semantic_evidences=semantic_profile.column_evidences,
        intent_tokens=brief.lower().split(),
        weights=weights,
        dataset=cleaned_ds,
        semantic_profile=semantic_profile,
        ambiguity_result=ambiguity,
    )

    print("\n--- Candidate Ranking & Robustness Summary ---")
    for plan, exec_res, score, rank in ranked:
        dim_str = ", ".join(d.column for d in plan.dimensions) or "(none)"
        print(f"\n[Rank {rank}] Plan ID: {plan.plan_id}")
        print(f"  Metric: {plan.metric.aggregation.value}({plan.metric.column}) by {dim_str}")
        print(f"  Score Total: {score.total:.4f} (Evidence: {score.evidence:.4f}, Coverage: {score.coverage:.4f}, "
              f"Stability/Robustness: {score.stability if score.stability is not None else 'UNTESTED'}, "
              f"Assumptions: {score.assumptions:.4f}, Cast Penalty: {score.failed_cast_penalty:.4f})")
        print(f"  Robustness Status: {score.stability_status} | Coverage of Test: {score.coverage_of_test:.2f} "
              f"({score.variants_valid}/{score.variants_attempted} valid variants)")

        if score.variants_failed:
            print("  Variants Failed:")
            for vf in score.variants_failed:
                print(f"    - {vf['description']} [{vf['stage']}]: {vf['reason']}")

        if score.variant_details:
            print("  Variant Table:")
            df_var = pd.DataFrame(score.variant_details)
            print(df_var.to_string(index=False))


if __name__ == "__main__":
    runs = [
        ("tests/real_data/Sales_2024.csv", "Store sales performance"),
        ("tests/real_data/Sales_2025.csv", "Sales volume by product in 2025"),
        ("tests/real_data/Products.csv", "Average unit price across product categories"),
    ]
    for path, brief in runs:
        run_brief_on_file(path, brief)
