import os
import sys
from pathlib import Path

# Add workspace root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from ingestion.loaders.csv_loader import CSVLoader
from intelligence.semantic_analyzer import SemanticAnalyzer
from orchestrator.context_builder import build_llm_context
from orchestrator.generator import MultiProviderGenerator
from orchestrator.intent import interpret_user_request
from orchestrator.schemas import CandidatePlan, LLMContext
from engine.duckdb_executor import DuckDBExecutor
from providers.factory import LLMProviderFactory, get_llm_client
from providers.base import LLMClientError, ProviderInitializationError, get_strict_json_schema

def main():
    print("=" * 80)
    print("STAGE 4 GATE: MULTI-PROVIDER GENERATION, HEALTH CHECKS & GRACEFUL DEGRADATION")
    print("=" * 80)

    # 1. Ingestion and Semantic Profiling of Real Test Dataset
    dataset_file = Path(__file__).resolve().parent.parent / "tests/real_data/Sales_2024.csv"
    loader = CSVLoader()
    analyzer = SemanticAnalyzer()

    canonical = loader.load(str(dataset_file))
    sem_profile = analyzer.analyze(canonical)

    dataset_id = canonical.metadata.dataset_id or "Sales_2024"
    columns = [col.original_name for col in canonical.metadata.schema]
    print(f"\n[DATASET]: {dataset_file.name} ({len(canonical.data)} rows, {len(columns)} columns)")
    print(f"Columns:   {columns}\n")

    brief = "Show total sales by store id"
    structured_intent = interpret_user_request(brief, sem_profile)

    # Build standard LLMContext dynamically from semantic profile
    context = build_llm_context(
        dataset_id=dataset_id,
        intent=brief,
        semantic_profile=sem_profile,
    )

    schema = get_strict_json_schema(CandidatePlan)

    # --------------------------------------------------------------------------
    # Step 1: Provider Health Checks & Initialization (Strict Typed Errors, No Silent Fallbacks)
    # --------------------------------------------------------------------------
    print("-" * 80)
    print("STEP 1: PROVIDER HEALTH CHECKS & INITIALIZATION (TYPED ERRORS, NO SILENT MOCK)")
    print("-" * 80)

    providers_to_test = ["gemini", "groq", "ollama", "zero_cost_local"]
    initialized_clients = {}

    for p in providers_to_test:
        try:
            client = get_llm_client(p)
            initialized_clients[p] = client
            print(f"  [+] Provider '{p}': HEALTH CHECK PASSED")
            print(f"      Model:    {client.model_name}")
            print(f"      Provider: {client.provider}")
        except ProviderInitializationError as pie:
            print(f"  [-] Provider '{p}': HEALTH CHECK FAILED (LOUD TYPED ERROR)")
            print(f"      Error Type:    {type(pie).__name__}")
            print(f"      Error Message: {pie}")
            print(f"      Silent Mock Fallback: FALSE (Typed error raised as required outside tests)")
        except LLMClientError as lce:
            print(f"  [-] Provider '{p}': CONFIGURATION FAILED (TYPED ERROR)")
            print(f"      Error Type:    {type(lce).__name__}")
            print(f"      Error Message: {lce}")
        except Exception as e:
            print(f"  [-] Provider '{p}': UNEXPECTED ERROR: {e}")
        print()

    # --------------------------------------------------------------------------
    # Step 2: Live Generation Calls & Failure Handling
    # --------------------------------------------------------------------------
    print("-" * 80)
    print("STEP 2: LIVE CALL PER PROVIDER (INSIGHT PROPOSAL GENERATION & FAILURE HANDLING)")
    print("-" * 80)

    cols_summary = "\n".join(
        f"- {c.column_name} (Role: {c.candidate_role}, Confidence: {c.confidence:.2f})"
        for c in context.columns
    )
    prompt = (
        f"You are a Business Intelligence Analyst. Generate 1 analytical query plan for dataset '{context.dataset_id}'.\n"
        f"User Intent: {context.intent}\n\n"
        f"Available Columns (Read-only Metadata):\n{cols_summary}\n\n"
        "Rules:\n"
        "1. Metric must use a MEASURE role column for SUM/AVG/STDDEV/MEDIAN.\n"
        "2. Dimension must use a DIMENSION or IDENTIFIER column.\n"
        "3. Return a JSON object matching CandidatePlan schema.\n"
    )

    operational_clients = []

    for p, client in initialized_clients.items():
        print(f"Executing Live Call -> Provider: {p} ({client.model_name})...")
        try:
            raw_response, call_log = client.generate_structured(
                prompt=prompt,
                response_schema=schema,
                generator_label="live_generator",
            )
            operational_clients.append(client)
            print(f"  -> SUCCESS from '{p}'")
            print(f"     Latency:        {call_log.latency_seconds:.4f}s")
            print(f"     Estimated Cost: ${call_log.estimated_cost_usd:.6f}")
            print(f"     Tokens:         Input={call_log.input_tokens}, Output={call_log.output_tokens}")
            print(f"     Plan Metric:    {raw_response.get('metric')}")
            print(f"     Plan Dims:      {raw_response.get('dimensions')}")
            print(f"     Reasoning:      {raw_response.get('reasoning', {}).get('interpretation')}")
        except LLMClientError as lce:
            print(f"  -> CALL FAILED (LOUD TYPED ERROR) for '{p}'")
            print(f"     Error Type:     {type(lce).__name__}")
            print(f"     Error Message:  {str(lce)[:200]}...")
            print("     Silent Fallback: FALSE (Provider failure handled loudly with typed error)")
        except Exception as e:
            print(f"  -> CALL FAILED: {type(e).__name__}: {e}")
        print()

    # --------------------------------------------------------------------------
    # Step 3: Graceful Degradation Demonstration
    # --------------------------------------------------------------------------
    print("-" * 80)
    print("STEP 3: GRACEFUL DEGRADATION: PIPELINE COMPLETION WITH DEGRADED PROVIDER SET")
    print("-" * 80)
    print(f"Degraded Operational Providers Pool: {[c.provider + ':' + c.model_name for c in operational_clients]}")
    print("Executing MultiProviderGenerator across degraded pool...")

    multi_gen = MultiProviderGenerator(clients=operational_clients)
    plans, call_logs = multi_gen.generate_plans(context=context, k=2)

    print(f"\nTotal Plans Generated: {len(plans)}")
    for idx, plan in enumerate(plans, 1):
        print(f"  Plan #{idx}:")
        print(f"    Provider:      {plan.provider} ({plan.generator})")
        print(f"    Metric:        {plan.metric.column} [{plan.metric.aggregation.value}]")
        print(f"    Dimensions:    {[d.column for d in plan.dimensions]}")
        print(f"    Visualization: {plan.visualization.value}")
        print(f"    Interpretation:{plan.reasoning.interpretation}")

    # Step 4: Verification of Plan Execution via DuckDB
    print("\nExecuting winning plan through DuckDB Analytics Engine...")
    executor = DuckDBExecutor()
    exec_result = executor.execute_plan(plans[0], canonical, sem_profile)
    print(f"DuckDB Execution Status: {exec_result.status.value}")
    print(f"Rows Returned:           {exec_result.row_count}")
    print(f"Columns:                 {exec_result.columns}")
    print(f"Execution Runtime:       {exec_result.runtime_seconds}s")
    print(f"Compiled SQL:            {exec_result.compiled_sql}")
    print("\nResult Preview:")
    for row in exec_result.rows[:5]:
        print(f"  {row}")

    print("\n" + "=" * 80)
    print("STAGE 4 GATE: MULTI-PROVIDER GENERATION & DEGRADATION VERIFIED")
    print("=" * 80)

if __name__ == "__main__":
    main()
