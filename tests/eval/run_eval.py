"""Synthetic regression harness for ranker and validation logic.

This suite tests ranker/validation logic against scripted candidate sets.
It does not measure real LLM provider behavior.

For empirical multi-provider evaluation using live LLM provider calls,
see tests/eval/run_real_eval.py and tests/eval/real_results.md.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
print(f"[EVAL STARTUP] Environment loaded. GEMINI_API_KEY present: {'GEMINI_API_KEY' in os.environ}, GROQ_API_KEY present: {'GROQ_API_KEY' in os.environ}")

from ingestion.loaders import load_dataset
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import assess_readiness, ReadinessStatus
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.compiler import compile_plan_to_sql
from orchestrator.config import (
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RANK_W5_AGREEMENT,
)
from orchestrator.context_builder import build_llm_context
from orchestrator.executor import execute_plan
from orchestrator.generator import PlanGenerator
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    FilterSpec,
    GeneratorCallLog,
    Granularity,
    LLMContext,
    MetricSpec,
    PlanReasoning,
    RankerWeights,
    VisualizationType,
)
from orchestrator.utils import check_candidate_output_consistency, rank_candidates
from orchestrator.validator import validate_pass1a, validate_pass1b
from orchestrator.winner import select_winner, WinnerSelectionError


def canonical_signature(plan: CandidatePlan) -> str:
    """Format a human-readable canonical signature for a plan."""
    agg = plan.metric.aggregation.value if hasattr(plan.metric.aggregation, "value") else str(plan.metric.aggregation)
    col = plan.metric.column
    base = f"{agg.upper()}({col})"
    
    if plan.dimensions:
        dims = []
        for d in plan.dimensions:
            if d.granularity:
                dims.append(f"{d.column}:{d.granularity.value.lower()}")
            else:
                dims.append(d.column)
        base += " BY " + ", ".join(dims)

    if plan.filters:
        filts = [f"{f.column} {f.operator} {repr(f.value) if isinstance(f.value, str) else f.value}" for f in plan.filters]
        base += " WHERE " + " AND ".join(filts)

    return base


class SyntheticRankerRegressionHarness(PlanGenerator):
    """Synthetic multi-provider harness simulating candidate generation.

    Emits deterministic candidate plans per provider to test ranker, validation,
    consensus aggregation, and disambiguation logic against controlled scenarios.
    Does NOT call real LLM APIs.
    """

    def __init__(self):
        self.providers = ["gemini", "groq", "ollama"]

    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        intent_lower = context.intent.lower()
        dataset_id = context.dataset_id
        logs = []
        for p in self.providers:
            logs.append(
                GeneratorCallLog(
                    model=f"{p}-model",
                    provider=p,
                    generator="llm_direct",
                    steps=1,
                    input_tokens=150,
                    output_tokens=120,
                    latency_seconds=0.05,
                    estimated_cost_usd=0.0001,
                )
            )

        # UNANSWERABLE checks: missing KPI definitions
        unanswerable_keywords = ["churn", "retention", "marketing roi", "acquisition cost", "profit margin", "supplier cost"]
        if any(kw in intent_lower for kw in unanswerable_keywords):
            # No valid plan can be formed with available columns
            return [], logs

        # Check prompt scenarios
        plans_raw: List[CandidatePlan] = []

        # 1. Total revenue by product ID
        if "revenue by product" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="ProductID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Product revenue", evidence=[]),
                    )
                )

        # 2. Monthly sales trend 2024 / 2025
        elif "monthly sales trend" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="Date", granularity=Granularity.MONTH)],
                        visualization=VisualizationType.LINE,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Monthly trend", evidence=[]),
                    )
                )

        # 3. Top customers by total quantity purchased
        elif "top customers" in intent_lower and "quantity" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="Quantity", aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="CustomerID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Customer quantity", evidence=[]),
                    )
                )

        # 4. Average unit price across product categories
        elif "average unit price" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="UnitPrice", aggregation=AggregationType.AVG),
                        dimensions=[DimensionSpec(column="Category")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Category average price", evidence=[]),
                    )
                )

        # 5. Store count by region
        elif "store count" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="StoreID", aggregation=AggregationType.COUNT),
                        dimensions=[DimensionSpec(column="Region")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Stores by region", evidence=[]),
                    )
                )

        # 6. Store sales performance (metric ambiguity)
        elif "store sales performance" in intent_lower:
            # Gemini & Groq pick TotalSales (revenue), Ollama picks Quantity (volume)
            for p, metric_col in [("gemini", "TotalSales"), ("groq", "TotalSales"), ("ollama", "Quantity")]:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column=metric_col, aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="StoreID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Store performance", evidence=[]),
                    )
                )

        # 7. Customer sales aggregation (aggregation ambiguity)
        elif "customer sales aggregation" in intent_lower:
            # Gemini proposes SUM, Groq proposes SUM, Ollama proposes AVG
            for p, agg in [("gemini", AggregationType.SUM), ("groq", AggregationType.SUM), ("ollama", AggregationType.AVG)]:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=agg),
                        dimensions=[DimensionSpec(column="CustomerID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Customer sales", evidence=[]),
                    )
                )

        # 8. Quarterly revenue for 2024
        elif "quarterly revenue" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="Date", granularity=Granularity.QUARTER)],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Quarterly sales", evidence=[]),
                    )
                )

        # 9. Daily sales volume
        elif "daily sales volume" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="Quantity", aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="Date", granularity=Granularity.DAY)],
                        visualization=VisualizationType.LINE,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Daily volume", evidence=[]),
                    )
                )

        # 10. Total sales for Store 101
        elif "store 101" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[],
                        filters=[FilterSpec(column="StoreID", operator="=", value=101)],
                        visualization=VisualizationType.KPI,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Store 101 total", evidence=[]),
                    )
                )

        # 11. Average order value by store
        elif "average order value" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.AVG),
                        dimensions=[DimensionSpec(column="StoreID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Store AOV", evidence=[]),
                    )
                )

        # 12. High value sales over 500 dollars
        elif "over 500" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[],
                        filters=[FilterSpec(column="TotalSales", operator=">", value=500)],
                        visualization=VisualizationType.KPI,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="High value sales", evidence=[]),
                    )
                )

        # 13. Sales volume by product in 2025
        elif "sales volume by product" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="Quantity", aggregation=AggregationType.SUM),
                        dimensions=[DimensionSpec(column="ProductID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Product volume 2025", evidence=[]),
                    )
                )

        # 14. Customer count by region
        elif "customer count by region" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="CustomerID", aggregation=AggregationType.COUNT),
                        dimensions=[DimensionSpec(column="Region")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Customers by region", evidence=[]),
                    )
                )

        # 15. Customer count by segment
        elif "customer count by segment" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="CustomerID", aggregation=AggregationType.COUNT),
                        dimensions=[DimensionSpec(column="Segment")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Customers by segment", evidence=[]),
                    )
                )

        # 17. Overall total revenue across entire year
        elif "overall total revenue" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[],
                        visualization=VisualizationType.KPI,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Total revenue KPI", evidence=[]),
                    )
                )

        # 18. Product count per category
        elif "product count per category" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="ProductID", aggregation=AggregationType.COUNT),
                        dimensions=[DimensionSpec(column="Category")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Products per category", evidence=[]),
                    )
                )

        # 22. Ambiguous metric request: Show ambiguous store performance metric
        # CONSENSUS FAILURE MODE CASE: All 3 models agree on AVG(UnitPrice) instead of SUM(TotalSales)!
        elif "ambiguous store performance" in intent_lower:
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="UnitPrice", aggregation=AggregationType.AVG),
                        dimensions=[DimensionSpec(column="StoreID")],
                        visualization=VisualizationType.BAR,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Consensus error on unit price", evidence=[]),
                    )
                )

        else:
            # Fallback
            for p in self.providers:
                plans_raw.append(
                    CandidatePlan(
                        dataset_id=dataset_id,
                        intent=context.intent,
                        metric=MetricSpec(column="TotalSales", aggregation=AggregationType.SUM),
                        dimensions=[],
                        visualization=VisualizationType.KPI,
                        provider=p,
                        generator="llm_direct",
                        reasoning=PlanReasoning(interpretation="Fallback", evidence=[]),
                    )
                )

        # Deduplicate and aggregate provider supporting count
        unique_plans: Dict[str, CandidatePlan] = {}
        for plan in plans_raw:
            sig = plan.plan_signature()
            if sig not in unique_plans:
                unique_plans[sig] = plan.model_copy(update={
                    "supporting_count": 1,
                    "providers_responded": len(self.providers),
                    "supporting_providers": [plan.provider],
                })
            else:
                curr = unique_plans[sig]
                unique_plans[sig] = curr.model_copy(update={
                    "supporting_count": curr.supporting_count + 1,
                    "supporting_providers": curr.supporting_providers + [plan.provider],
                })

        return list(unique_plans.values()), logs


def run_pipeline_for_prompt(
    item: Dict[str, Any],
    generator: PlanGenerator,
) -> Dict[str, Any]:
    """Execute a single prompt through the full orchestrator pipeline."""
    prompt = item["prompt"]
    dataset_file = item["dataset_id"]
    dataset_path = PROJECT_ROOT / "tests" / "real_data" / dataset_file

    dataset = load_dataset(dataset_path)
    profile = profile_dataset(dataset)
    readiness = assess_readiness(dataset, profile)
    semantic_profile = analyze_semantics(dataset, profile)

    context = build_llm_context(
        dataset_id=dataset.metadata.dataset_id,
        intent=prompt,
        semantic_profile=semantic_profile,
        data_profile=profile,
    )

    candidates, generator_logs = generator.generate_plans(context, k=3)

    if not candidates:
        return {
            "status": "UNANSWERABLE",
            "winning_signature": "UNANSWERABLE",
            "agreement_score": 1.0,
            "supporting_count": 3,
            "providers_responded": 3,
        }

    # Pass 1a + DuckDB execution + Pass 1b
    surviving_candidates: List[Tuple[CandidatePlan, ExecutionResult]] = []
    for cand in candidates:
        p1a = validate_pass1a(plan=cand, semantic_profile=semantic_profile, readiness=readiness)
        if not p1a.passed:
            continue
        exec_res = execute_plan(plan=cand, dataset=dataset, semantic_profile=semantic_profile)
        p1b = validate_pass1b(plan=cand, exec_result=exec_res)
        if not p1b.passed:
            continue
        surviving_candidates.append((cand, exec_res))

    if not surviving_candidates:
        return {
            "status": "UNANSWERABLE",
            "winning_signature": "UNANSWERABLE",
            "agreement_score": 1.0,
            "supporting_count": 3,
            "providers_responded": 3,
        }

    consistency = check_candidate_output_consistency(surviving_candidates)
    weights = RankerWeights(
        w1_evidence=RANK_W1_EVIDENCE,
        w2_coverage=RANK_W2_COVERAGE,
        w3_stability=RANK_W3_STABILITY,
        w4_assumptions=RANK_W4_ASSUMPTIONS,
        w5_agreement=RANK_W5_AGREEMENT,
    )
    ranked, is_tie = rank_candidates(
        candidates=surviving_candidates,
        semantic_evidences=semantic_profile.column_evidences,
        intent_tokens=prompt.lower().split(),
        weights=weights,
    )

    try:
        spec = select_winner(
            ranked=ranked,
            dataset_id=dataset.metadata.dataset_id,
            intent=prompt,
            context_hash=context.context_hash,
            generator_logs=generator_logs,
            ranker_weights=weights,
            consistency_check=consistency,
        )
        winner_plan = spec.winner.plan
        sig_str = canonical_signature(winner_plan)
        agreement = winner_plan.supporting_count / winner_plan.providers_responded if winner_plan.providers_responded > 0 else 0.0

        return {
            "status": "SUCCESS",
            "winning_plan": winner_plan,
            "winning_signature": sig_str,
            "plan_hash": winner_plan.plan_signature(),
            "agreement_score": round(agreement, 2),
            "supporting_count": winner_plan.supporting_count,
            "providers_responded": winner_plan.providers_responded,
        }
    except WinnerSelectionError:
        return {
            "status": "UNANSWERABLE",
            "winning_signature": "UNANSWERABLE",
            "agreement_score": 1.0,
            "supporting_count": 3,
            "providers_responded": 3,
        }


def check_signature_match(actual_sig: str, acceptable: List[str], plan_hash: Optional[str] = None) -> bool:
    """Check if actual signature matches any acceptable signature."""
    for acc in acceptable:
        if acc == actual_sig:
            return True
        if plan_hash and acc == plan_hash:
            return True
        # Normalize whitespace and case-insensitive check
        if acc.lower().strip() == actual_sig.lower().strip():
            return True
    return False


def main():
    prompts_path = PROJECT_ROOT / "tests" / "eval" / "prompts.jsonl"
    results_path = PROJECT_ROOT / "tests" / "eval" / "results.md"

    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = [json.loads(line) for line in f if line.strip()]

    generator = SyntheticRankerRegressionHarness()
    results = []

    print(f"Starting regression run of {len(prompts)} prompts against synthetic candidate harness...")

    for idx, item in enumerate(prompts, 1):
        prompt_text = item["prompt"]
        cat = item["category"]
        acceptable = item["acceptable_signatures"]

        eval_res = run_pipeline_for_prompt(item, generator)
        actual_sig = eval_res["winning_signature"]
        plan_hash = eval_res.get("plan_hash")
        agreement = eval_res["agreement_score"]

        is_passed = check_signature_match(actual_sig, acceptable, plan_hash)
        is_consensus = abs(agreement - 1.0) < 1e-4

        if is_consensus and is_passed:
            consensus_mode = "Consensus on Correct"
        elif is_consensus and not is_passed:
            consensus_mode = "Consensus on WRONG (Risk Triggered)"
        elif not is_consensus and is_passed:
            consensus_mode = "Dissenting / Disambiguated"
        else:
            consensus_mode = "Incorrect Non-Consensus"

        record = {
            "id": idx,
            "prompt": prompt_text,
            "dataset": item["dataset_id"],
            "category": cat,
            "winning_sig": actual_sig,
            "acceptable": acceptable,
            "passed": is_passed,
            "agreement": agreement,
            "is_consensus": is_consensus,
            "consensus_mode": consensus_mode,
        }
        results.append(record)

        mark = "PASS" if is_passed else "FAIL"
        print(f"[{idx:02d}/{len(prompts):02d}] [{mark}] agg={agreement:.2f} ({consensus_mode}): '{prompt_text}' -> {actual_sig}")

    # Metrics
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    accuracy = (passed_count / total) * 100.0 if total > 0 else 0.0

    consensus_total = sum(1 for r in results if r["is_consensus"])
    consensus_correct = sum(1 for r in results if r["is_consensus"] and r["passed"])
    consensus_wrong = sum(1 for r in results if r["is_consensus"] and not r["passed"])
    high_agreement_wrong_rate = (consensus_wrong / consensus_total) if consensus_total > 0 else 0.0

    print("\n" + "=" * 60)
    print(f"SYNTHETIC REGRESSION COMPLETE: {passed_count}/{total} passed ({accuracy:.1f}% accuracy)")
    print(f"Consensus Count (Agreement = 1.0): {consensus_total}/{total}")
    print(f"  - Consensus on Correct Signature: {consensus_correct}")
    print(f"  - Consensus on WRONG Signature:   {consensus_wrong} (Agreement-on-Wrong-Answer Risk)")
    print(f"  - High-Agreement Wrong Rate:      {high_agreement_wrong_rate:.1%} ({consensus_wrong}/{consensus_total})")
    print("=" * 60)

    # Generate Markdown Report
    md = []
    md.append("# Synthetic Ranker & Validation Regression Report\n")
    md.append("> [!NOTE]")
    md.append("> **Harness Scope**: This suite tests ranker/validation logic against scripted candidate sets. It does not measure real LLM provider behavior. For live multi-model evaluation, see [real_results.md](real_results.md).\n")
    md.append(f"**Total Prompts**: {total}  ")
    md.append(f"**Passed**: {passed_count} / {total}  ")
    md.append(f"**Overall Accuracy**: {accuracy:.1f}%  ")
    md.append(f"**High-Agreement Wrong Rate**: {high_agreement_wrong_rate:.1%} ({consensus_wrong}/{consensus_total})\n")

    md.append("## Agreement & Consensus-Failure Analysis (Q3 Risk)\n")
    md.append("| Metric | Count | Percentage |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| Total Consensus Prompts (Agreement = 1.0) | {consensus_total} | {(consensus_total/total)*100:.1f}% |")
    md.append(f"| Consensus on Correct Signature | {consensus_correct} | {(consensus_correct/total)*100:.1f}% |")
    md.append(f"| **Consensus on WRONG Signature** | **{consensus_wrong}** | **{(consensus_wrong/total)*100:.1f}%** |")
    md.append(f"| **High-Agreement Wrong Rate** | **{consensus_wrong}/{consensus_total}** | **{high_agreement_wrong_rate*100:.1f}%** |")
    md.append(f"| Non-Consensus / Dissenting Providers | {total - consensus_total} | {((total - consensus_total)/total)*100:.1f}% |\n")

    md.append("> [!WARNING]")
    md.append(f"> **Agreement-on-Wrong-Answer Risk Detected**: In **{consensus_wrong}** case(s), all 3 providers independently agreed on an incorrect plan signature. High-agreement wrong rate is **{high_agreement_wrong_rate:.1%}**. Because consensus was 100% (agreement = 1.0), the ranker awarded maximum agreement bonus, crowning the erroneous plan as winner without detection. This validates the Q3 architectural limitation.\n")

    md.append("## Per-Prompt Evaluation Details\n")
    md.append("| # | Prompt | Dataset | Category | Agreement | Status | Consensus Analysis | Winning Signature |")
    md.append("| :-: | :--- | :--- | :--- | :-: | :-: | :--- | :--- |")

    for r in results:
        status_badge = "PASS" if r["passed"] else "**FAIL**"
        md.append(
            f"| {r['id']} | {r['prompt']} | `{r['dataset']}` | `{r['category']}` | "
            f"`{r['agreement']:.2f}` | {status_badge} | {r['consensus_mode']} | `{r['winning_sig']}` |"
        )

    md_content = "\n".join(md) + "\n"
    with open(results_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\nMarkdown report generated at: {results_path}")


if __name__ == "__main__":
    main()
