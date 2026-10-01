"""Stage 4b Verification Tests: Provider degradation, winner regression, cleaning rules, and clarification flow.

Rules (must be at the top of every stage response):
- No hardcoded dataset names, column names, or prompts in runtime code.
- Never write "done", "complete" or "verified" without raw terminal output from this session.
- Don't touch files outside the stage's scope.
- If a test fails, show it and fix the cause, never the test.
- Stop at the end of the stage and wait.
"""

import os
import uuid
import pytest
import pandas as pd
import numpy as np
from typing import List, Optional

from cleaning.cleaner import DataCleaner, clean_dataset
from cleaning.models import CleaningConfig
from engine.executor import get_default_engine
from ingestion.loaders import CSVLoader
from ingestion.models import (
    CanonicalDataset,
    ColumnMetadata,
    ColumnRole,
    DatasetMetadata,
    sanitize_json_value,
)
from intelligence.profiler import profile_dataset
from intelligence.schema_validator import assess_readiness
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.pipeline import run_orchestration_pipeline
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    ScoreBreakdown,
    VisualizationType,
)
from orchestrator.utils import rank_candidates
from providers.adapters.local import RuleBasedBaselineClient
from providers.factory import LLMProviderFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _df_to_canonical(df: pd.DataFrame, dataset_id: Optional[str] = None) -> CanonicalDataset:
    """Build a CanonicalDataset directly from a DataFrame without hitting the filesystem."""
    from ingestion.models import sanitize_json_value
    ds_id = dataset_id or f"ds_test_{uuid.uuid4().hex[:6]}"
    schema: List[ColumnMetadata] = []
    for col in df.columns:
        series = df[col]
        null_cnt = int(series.isna().sum())
        null_pct = float((null_cnt / len(df)) * 100.0) if len(df) > 0 else 0.0
        distinct_cnt = int(series.nunique(dropna=True))
        is_uniq = bool(series.is_unique) if len(df) > 0 else False
        samples = [sanitize_json_value(v) for v in series.dropna().head(5).tolist()]
        schema.append(ColumnMetadata(
            original_name=str(col),
            normalized_name=str(col),
            detected_datatype=str(series.dtype),
            semantic_role=ColumnRole.UNKNOWN,
            null_count=null_cnt,
            null_percentage=round(null_pct, 4),
            distinct_count=distinct_cnt,
            is_unique=is_uniq,
            sample_values=samples,
        ))
    meta = DatasetMetadata(
        dataset_id=ds_id,
        name=ds_id,
        source_type="test",
        row_count=len(df),
        column_count=len(df.columns),
        schema=schema,
    )
    return CanonicalDataset(metadata=meta, data=df)


def _make_candidate(
    plan_id: str,
    dataset_id: str,
    metric_col: str,
    dim_col: str,
    provider: str = "groq",
    supporting_count: int = 1,
    providers_responded: int = 1,
    intent: str = "test intent",
) -> CandidatePlan:
    return CandidatePlan(
        plan_id=plan_id,
        dataset_id=dataset_id,
        intent=intent,
        metric=MetricSpec(column=metric_col, aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column=dim_col, granularity=None)],
        filters=[],
        comparison=None,
        visualization=VisualizationType.BAR,
        generator="llm_direct",
        provider=provider,
        supporting_providers=[provider] if provider != "rule_based_baseline" else [],
        supporting_count=supporting_count,
        providers_responded=providers_responded,
        reasoning=PlanReasoning(
            interpretation=f"Sum of {metric_col} by {dim_col}",
            evidence=["Test evidence"],
        ),
    )


# ---------------------------------------------------------------------------
# 1. Winner Regression: TotalSales-by-StoreID must beat Quantity-by-CustomerID
# ---------------------------------------------------------------------------

def test_winner_regression_sales_by_store():
    """Verify that for 'total sales by store' on Sales_2024.csv, TotalSales-by-StoreID wins.

    Regression: in a prior run, tests/run_stage4_gate.py bypassed the ranker by
    executing plans[0] directly. The ranker's own output MUST choose TotalSales/StoreID.
    """
    csv_path = "tests/real_data/Sales_2024.csv"
    if not os.path.exists(csv_path):
        pytest.skip(f"{csv_path} not found; skipping regression test")

    raw_ds = CSVLoader().load(csv_path)
    cleaned_ds, report = clean_dataset(raw_ds)
    profile = profile_dataset(cleaned_ds)
    semantic_profile = analyze_semantics(cleaned_ds, profile=profile)

    ds_id = cleaned_ds.metadata.dataset_id

    # Find actual column names from the dataset (case-insensitive lookup)
    col_lower = {c.lower(): c for c in cleaned_ds.data.columns}
    total_sales_col = col_lower.get("totalsales") or col_lower.get("total_sales") or col_lower.get("sales")
    store_col = col_lower.get("storeid") or col_lower.get("store_id") or col_lower.get("store")
    qty_col = col_lower.get("quantity") or col_lower.get("qty")
    cust_col = col_lower.get("customerid") or col_lower.get("customer_id") or col_lower.get("customer")

    if not all([total_sales_col, store_col, qty_col, cust_col]):
        pytest.skip(f"Required columns not found in dataset. Available: {list(cleaned_ds.data.columns)}")

    plan_groq = CandidatePlan(
        plan_id="plan_groq_sales_store",
        dataset_id=ds_id,
        intent="total sales by store",
        metric=MetricSpec(column=total_sales_col, aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column=store_col, granularity=None)],
        filters=[],
        comparison=None,
        visualization=VisualizationType.BAR,
        generator="llm_direct",
        provider="groq",
        supporting_providers=["groq"],
        supporting_count=1,
        providers_responded=3,
        reasoning=PlanReasoning(
            interpretation=f"Total {total_sales_col} grouped by {store_col}",
            evidence=[f"{total_sales_col} is primary currency measure", f"{store_col} is store dimension"],
        ),
    )

    plan_local = CandidatePlan(
        plan_id="plan_baseline_qty_cust",
        dataset_id=ds_id,
        intent="total sales by store",
        metric=MetricSpec(column=qty_col, aggregation=AggregationType.SUM),
        dimensions=[DimensionSpec(column=cust_col, granularity=None)],
        filters=[],
        comparison=None,
        visualization=VisualizationType.BAR,
        generator="rule_based_baseline",
        provider="rule_based_baseline",
        supporting_providers=[],
        supporting_count=0,
        providers_responded=3,
        reasoning=PlanReasoning(
            interpretation=f"{qty_col} grouped by {cust_col}",
            evidence=["Fallback heuristic"],
        ),
    )

    engine = get_default_engine()
    exec_groq = engine.execute(plan_groq, cleaned_ds, semantic_profile)
    exec_local = engine.execute(plan_local, cleaned_ds, semantic_profile)

    assert exec_groq.status == ExecutionStatus.SUCCESS, f"Groq plan failed: {exec_groq}"
    assert exec_local.status == ExecutionStatus.SUCCESS, f"Local plan failed: {exec_local}"

    candidates = [(plan_groq, exec_groq), (plan_local, exec_local)]
    intent_tokens = "total sales by store".split()

    ranked, is_tie = rank_candidates(
        candidates=candidates,
        semantic_evidences=semantic_profile.column_evidences,
        intent_tokens=intent_tokens,
    )

    print("\n=== Ranker Output ===")
    for plan, exec_res, score, rank in ranked:
        print(
            f"  Rank {rank}: {plan.metric.aggregation.value}({plan.metric.column})"
            f" by {plan.dimensions[0].column} | provider={plan.provider}"
            f" | evidence={score.evidence:.4f} coverage={score.coverage:.4f}"
            f" stability={score.stability:.4f} agreement={score.agreement:.4f}"
            f" total={score.total:.4f}"
        )

    winner_plan, winner_exec, winner_score, winner_rank = ranked[0]
    runner_up_plan, _, runner_up_score, _ = ranked[1]

    # Idempotence assertion – shown verbatim:
    assert winner_plan.plan_id == "plan_groq_sales_store", (
        f"ASSERTION: winner_plan.plan_id == 'plan_groq_sales_store'\n"
        f"Got: winner_plan.plan_id = '{winner_plan.plan_id}'\n"
        f"winner metric col = '{winner_plan.metric.column}'\n"
        f"winner dim col = '{winner_plan.dimensions[0].column}'\n"
        f"winner score total = {winner_score.total:.4f}\n"
        f"runner-up score total = {runner_up_score.total:.4f}"
    )
    assert winner_plan.metric.column == total_sales_col
    assert winner_plan.dimensions[0].column == store_col
    assert winner_score.total > runner_up_score.total
    assert winner_score.coverage > runner_up_score.coverage
    print(f"\n✓ Winner: {winner_plan.metric.aggregation.value}({winner_plan.metric.column}) by {winner_plan.dimensions[0].column}")
    print(f"  total={winner_score.total:.4f} > runner-up total={runner_up_score.total:.4f}")


# ---------------------------------------------------------------------------
# 2. Cleaning Defaults – no imputation of measures by default
# ---------------------------------------------------------------------------

def test_cleaning_defaults_no_impute_measures():
    """Verify measures are NOT imputed by default; nulls are reported; imputation is opt-in via config.
    
    NOTE: All Category values are unique to prevent the deduplication rule from
    collapsing rows (which would reduce the null count before null handling runs).
    """
    df = pd.DataFrame({
        "Revenue": [100.0, np.nan, 300.0, np.nan, 500.0],
        "Category": ["A", "B", "C", "D", "E"],  # all unique – no row deduplication
    })
    raw_ds = _df_to_canonical(df, "test_null_measures")

    # Default config: impute_measures=False
    cleaner_default = DataCleaner(CleaningConfig(impute_measures=False))
    res_default = cleaner_default.clean(raw_ds)

    # Assertion (shown verbatim):
    assert res_default.dataset.data["Revenue"].isna().sum() == 2, (
        "ASSERTION: res_default.dataset.data['Revenue'].isna().sum() == 2\n"
        f"Got: {res_default.dataset.data['Revenue'].isna().sum()}"
    )
    reported_change = next((c for c in res_default.report.changes if c.rule == "report_null_measure"), None)
    assert reported_change is not None, (
        "ASSERTION: reported_change is not None\n"
        f"Got changes rules: {[c.rule for c in res_default.report.changes]}"
    )
    assert reported_change.count == 2
    assert reported_change.details["imputed"] is False

    print(f"\n✓ Default: Revenue nulls remain={res_default.dataset.data['Revenue'].isna().sum()}, reported_change.count={reported_change.count}")

    # Opt-in config: impute_measures=True
    cleaner_optin = DataCleaner(CleaningConfig(impute_measures=True))
    res_optin = cleaner_optin.clean(raw_ds)
    assert res_optin.dataset.data["Revenue"].isna().sum() == 0, (
        "ASSERTION: res_optin.dataset.data['Revenue'].isna().sum() == 0\n"
        f"Got: {res_optin.dataset.data['Revenue'].isna().sum()}"
    )
    filled_change = next((c for c in res_optin.report.changes if c.rule == "fill_null_measure"), None)
    assert filled_change is not None, (
        "ASSERTION: filled_change is not None\n"
        f"Got changes rules: {[c.rule for c in res_optin.report.changes]}"
    )
    assert filled_change.count == 2
    print(f"✓ Opt-in: Revenue nulls after impute={res_optin.dataset.data['Revenue'].isna().sum()}, filled_change.count={filled_change.count}")


# ---------------------------------------------------------------------------
# 3. Cleaning – category normalization on low-cardinality dims only
# ---------------------------------------------------------------------------

def test_cleaning_category_normalization_low_cardinality_only():
    """Category normalization maps case/whitespace variants to most frequent original spelling.

    Free text columns (avg_len >= 40 or cardinality_ratio > 0.4) are left untouched.
    """
    df = pd.DataFrame({
        "Region": ["North", "north ", "North", " North", "South"],
        "Notes": [
            "Great service and prompt response from the support team today",
            "great service and prompt response from the support team today",
            "The delivery was slightly delayed but product arrived in good condition",
            "Completely satisfied with the user experience and checkout flow",
            "Item broke during shipping and refund was requested immediately",
        ],
    })
    raw_ds = _df_to_canonical(df, "test_category_norm")
    cleaner = DataCleaner(CleaningConfig(normalize_categories=True))
    res = cleaner.clean(raw_ds)

    cleaned_regions = res.dataset.data["Region"].tolist()
    print(f"\n✓ Cleaned regions: {cleaned_regions}")

    # "north " and " North" should be mapped to "North" (the most frequent raw spelling)
    assert cleaned_regions == ["North", "North", "North", "North", "South"], (
        f"ASSERTION: cleaned_regions == ['North', 'North', 'North', 'North', 'South']\n"
        f"Got: {cleaned_regions}"
    )

    # Free text is untouched (high cardinality)
    orig_notes = df["Notes"].tolist()
    cleaned_notes = res.dataset.data["Notes"].tolist()
    assert cleaned_notes == orig_notes, (
        "ASSERTION: free-text Notes column is unchanged after normalization\n"
        f"Expected: {orig_notes}\nGot: {cleaned_notes}"
    )
    print("✓ Free-text Notes column unchanged")


# ---------------------------------------------------------------------------
# 4. Cleaning – ambiguous date detection
# ---------------------------------------------------------------------------

def test_cleaning_ambiguous_date_detection():
    """Ambiguous day/month strings must be detected and logged without silent guessing."""
    df = pd.DataFrame({
        "TransactionDate": ["03/04/2024", "04/05/2024", "05/06/2024"],
        "Amount": [10.0, 20.0, 30.0],
    })
    raw_ds = _df_to_canonical(df, "test_ambig_dates")
    cleaner = DataCleaner(CleaningConfig(coerce_types=True))
    res = cleaner.clean(raw_ds)

    ambig_change = next((c for c in res.report.changes if c.rule == "ambiguous_date_detected"), None)
    print(f"\n✓ Changes found: {[c.rule for c in res.report.changes]}")

    assert ambig_change is not None, (
        "ASSERTION: ambig_change is not None (a 'ambiguous_date_detected' change must be reported)\n"
        f"Got changes: {[(c.rule, c.column) for c in res.report.changes]}"
    )
    assert ambig_change.count > 0
    assert "Ambiguous" in ambig_change.details["warning"], (
        f"ASSERTION: 'Ambiguous' in ambig_change.details['warning']\n"
        f"Got: {ambig_change.details.get('warning')}"
    )
    print(f"✓ ambiguous_date_detected count={ambig_change.count}, sample={ambig_change.details.get('sample_values')}")


# ---------------------------------------------------------------------------
# 5. Pipeline – NEEDS_CLARIFICATION returned on tie
# ---------------------------------------------------------------------------

def test_pipeline_needs_clarification_on_tie():
    """On a tie between two candidates, pipeline returns status='NEEDS_CLARIFICATION' with options."""
    df = pd.DataFrame({
        "Region": ["East", "West", "East", "West", "East"],
        "Category": ["Electronics", "Furniture", "Electronics", "Books", "Furniture"],
        "Sales": [100.0, 200.0, 150.0, 80.0, 300.0],
    })
    raw_ds = _df_to_canonical(df, "test_tie_pipeline")
    cleaned_ds, _ = clean_dataset(raw_ds)
    profile = profile_dataset(cleaned_ds)
    semantic_profile = analyze_semantics(cleaned_ds, profile=profile)
    readiness = assess_readiness(cleaned_ds, profile=profile, semantic_profile=semantic_profile)
    ds_id = cleaned_ds.metadata.dataset_id

    c1 = _make_candidate("plan_tie_1", ds_id, "Sales", "Region",
                         intent="Sales by Region and Category")
    c2 = _make_candidate("plan_tie_2", ds_id, "Sales", "Category",
                         intent="Sales by Region and Category")

    class MockTieGenerator:
        def generate_plans(self, context, k=2, interpretations=None):
            return [c1, c2], []

    res = run_orchestration_pipeline(
        dataset=cleaned_ds,
        semantic_profile=semantic_profile,
        readiness=readiness,
        intent="Sales by Region and Category",
        generator=MockTieGenerator(),
        require_clarification=True,
    )

    print(f"\n✓ Pipeline status: {res.status}")
    print(f"  clarification_options: {[opt.get('plan_id') for opt in (res.clarification_options or [])]}")

    assert res.status == "NEEDS_CLARIFICATION", (
        f"ASSERTION: res.status == 'NEEDS_CLARIFICATION'\nGot: {res.status}\n{res.message}"
    )
    assert res.clarification_options is not None
    assert len(res.clarification_options) >= 2
    option_ids = [opt["plan_id"] for opt in res.clarification_options]
    assert "plan_tie_1" in option_ids, f"plan_tie_1 missing from options: {option_ids}"
    assert "plan_tie_2" in option_ids, f"plan_tie_2 missing from options: {option_ids}"


# ---------------------------------------------------------------------------
# 6. Pipeline – follow-up with chosen_plan_id resolves correctly
# ---------------------------------------------------------------------------

def test_pipeline_clarification_followup_resolution():
    """Follow-up call with chosen_plan_id executes the chosen candidate as winner."""
    df = pd.DataFrame({
        "Region": ["East", "West", "East", "West"],
        "Category": ["Electronics", "Furniture", "Books", "Clothing"],
        "Sales": [100.0, 200.0, 150.0, 80.0],
    })
    raw_ds = _df_to_canonical(df, "test_followup_pipeline")
    cleaned_ds, _ = clean_dataset(raw_ds)
    profile = profile_dataset(cleaned_ds)
    semantic_profile = analyze_semantics(cleaned_ds, profile=profile)
    readiness = assess_readiness(cleaned_ds, profile=profile, semantic_profile=semantic_profile)
    ds_id = cleaned_ds.metadata.dataset_id

    c1 = _make_candidate("plan_follow_1", ds_id, "Sales", "Region",
                         intent="Sales analysis", providers_responded=1)
    c2 = _make_candidate("plan_follow_2", ds_id, "Sales", "Category",
                         intent="Sales analysis", providers_responded=1)

    # User chose plan_follow_2 (Category)
    res = run_orchestration_pipeline(
        dataset=cleaned_ds,
        semantic_profile=semantic_profile,
        readiness=readiness,
        intent="Sales analysis",
        require_clarification=True,
        chosen_plan_id="plan_follow_2",
        existing_candidates=[c1, c2],
    )

    print(f"\n✓ Follow-up pipeline status: {res.status}")
    if res.dashboard_spec:
        winner = res.dashboard_spec.winner.plan
        print(f"  Winner: plan_id={winner.plan_id}, dim={winner.dimensions[0].column}")

    assert res.status == "SUCCESS", (
        f"ASSERTION: res.status == 'SUCCESS'\nGot: {res.status}\n{res.message}"
    )
    assert res.dashboard_spec is not None
    assert res.dashboard_spec.winner.plan.plan_id == "plan_follow_2", (
        f"ASSERTION: winner.plan_id == 'plan_follow_2'\n"
        f"Got: {res.dashboard_spec.winner.plan.plan_id}"
    )
    assert res.dashboard_spec.winner.plan.dimensions[0].column == "Category"


# ---------------------------------------------------------------------------
# 7. RuleBasedBaselineClient excluded from consensus
# ---------------------------------------------------------------------------

def test_rule_based_baseline_excluded_from_consensus():
    """RuleBasedBaselineClient is labeled rule_based_baseline and excluded from LLM consensus."""
    client = LLMProviderFactory.create_client("rule_based_baseline")
    assert isinstance(client, RuleBasedBaselineClient), (
        f"ASSERTION: isinstance(client, RuleBasedBaselineClient)\nGot: {type(client)}"
    )
    assert client.provider == "rule_based_baseline", (
        f"ASSERTION: client.provider == 'rule_based_baseline'\nGot: {client.provider}"
    )

    plan, log = client.generate_structured(
        prompt=(
            "Dataset ID: test_ds\n"
            "User Intent: Total sales by store\n"
            "- TotalSales (Role: ColumnRole.MEASURE, Confidence: 0.95)\n"
            "- StoreID (Role: ColumnRole.DIMENSION, Confidence: 0.92)\n"
        ),
        response_schema={},
    )

    print(f"\n✓ RuleBasedBaseline plan:")
    print(f"  provider={plan['provider']}")
    print(f"  supporting_providers={plan['supporting_providers']}")
    print(f"  supporting_count={plan['supporting_count']}")
    print(f"  reasoning interpretation={plan['reasoning']['interpretation']}")

    assert plan["provider"] == "rule_based_baseline", (
        f"ASSERTION: plan['provider'] == 'rule_based_baseline'\nGot: {plan['provider']}"
    )
    assert plan["supporting_providers"] == [], (
        f"ASSERTION: plan['supporting_providers'] == []\nGot: {plan['supporting_providers']}"
    )
    assert plan["supporting_count"] == 0, (
        f"ASSERTION: plan['supporting_count'] == 0\nGot: {plan['supporting_count']}"
    )
    # Verify the label "rule-based baseline" appears in the reasoning
    assert "rule-based baseline" in plan["reasoning"]["interpretation"].lower(), (
        f"ASSERTION: 'rule-based baseline' in reasoning interpretation\n"
        f"Got: {plan['reasoning']['interpretation']}"
    )
    print("✓ Confirmed: rule_based_baseline is excluded from consensus (supporting_count=0, supporting_providers=[])")


# ---------------------------------------------------------------------------
# 8. Factory registers groq_secondary and rule_based_baseline
# ---------------------------------------------------------------------------

def test_factory_registers_groq_secondary(monkeypatch):
    """Verify LLMProviderFactory creates groq_secondary with model openai/gpt-oss-20b."""
    from providers.adapters.groq import GroqClient
    monkeypatch.setenv("GROQ_API_KEY", "test-key-placeholder")
    client = LLMProviderFactory.create_client("groq_secondary")
    assert isinstance(client, GroqClient), f"Expected GroqClient, got {type(client)}"
    assert client.model_name == "openai/gpt-oss-20b", (
        f"ASSERTION: client.model_name == 'openai/gpt-oss-20b'\nGot: {client.model_name}"
    )
    print(f"\n✓ groq_secondary: model={client.model_name}")


def test_factory_backward_compat_zero_cost_local():
    """Verify zero_cost_local still resolves to RuleBasedBaselineClient for backward compat."""
    client = LLMProviderFactory.create_client("zero_cost_local")
    assert isinstance(client, RuleBasedBaselineClient), (
        f"ASSERTION: zero_cost_local creates RuleBasedBaselineClient\nGot: {type(client)}"
    )
    assert client.provider == "rule_based_baseline"
    print(f"\n✓ zero_cost_local backward-compat: provider={client.provider}")
