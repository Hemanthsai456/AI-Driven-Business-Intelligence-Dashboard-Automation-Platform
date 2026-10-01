import sys
from pathlib import Path

# Add workspace root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.loaders.csv_loader import CSVLoader
from intelligence.semantic_analyzer import SemanticAnalyzer
from orchestrator.intent import interpret_user_request
from orchestrator.ambiguity import assess_ambiguity

def main():
    loader = CSVLoader()
    analyzer = SemanticAnalyzer()

    test_cases = [
        # Real File 1: Sales_2024.csv
        (
            "tests/real_data/Sales_2024.csv",
            "Brief 1 (Clear / Specific)",
            "Show total sales by store id",
        ),
        (
            "tests/real_data/Sales_2024.csv",
            "Brief 2 (Vague / Ambiguous)",
            "Show top performance numbers over time",
        ),
        # Real File 2: Products.csv
        (
            "tests/real_data/Products.csv",
            "Brief 3 (Clear / Specific)",
            "Calculate average unit price by category",
        ),
        (
            "tests/real_data/Products.csv",
            "Brief 4 (Vague / Ambiguous)",
            "Show unit price across segments",
        ),
        # Real File 3: Customers.csv
        (
            "tests/real_data/Customers.csv",
            "Brief 5 (Clear / Specific)",
            "Count total customers by region and segment",
        ),
        (
            "tests/real_data/Customers.csv",
            "Brief 6 (Vague / Ambiguous)",
            "Show recent customer activity",
        ),
    ]

    print("=" * 80)
    print("STAGE 3 GATE: INTENT INTERPRETATION & AMBIGUITY PRE-CHECK ACROSS 6 BRIEFS")
    print("=" * 80)

    for i, (file_rel, label, brief) in enumerate(test_cases, 1):
        file_path = Path(__file__).resolve().parent.parent / file_rel
        canonical = loader.load(str(file_path))
        sem_profile = analyzer.analyze(canonical)

        structured_intent = interpret_user_request(brief, sem_profile)
        ambiguity_res = assess_ambiguity(structured_intent, sem_profile)

        print("-" * 80)
        print(f"CASE {i}: {label}")
        print(f"Dataset:            {file_path.name}")
        print(f"Columns:            {[col.original_name for col in canonical.metadata.schema]}")
        print(f"Free-Text Brief:    \"{brief}\"")
        print("-" * 80)
        print("1. STRUCTURED INTENT INTERPRETATION:")
        print(f"   Analytical Goal:       {structured_intent.analytical_goal}")
        print(f"   Requested Metrics:     {structured_intent.requested_metrics}")
        print(f"   Requested Dimensions:  {structured_intent.requested_dimensions}")
        print(f"   Temporal Scope:        {structured_intent.temporal_scope}")
        print(f"   Grouping Granularity:  {structured_intent.grouping_granularity}")
        print(f"   Visual Preferences:    {structured_intent.requested_visual_preferences}")
        print(f"   Unresolved Terms:      {structured_intent.unresolved_terms}")
        print(f"   Confidence Score:      {structured_intent.confidence:.2f}")
        print()
        print("2. AMBIGUITY PRE-CHECK ASSESSMENT:")
        print(f"   Status:                {ambiguity_res.status.value}")
        print(f"   Is Blocking:           {ambiguity_res.is_blocking}")
        print(f"   Ambiguities Detected:  {len(ambiguity_res.ambiguities)}")
        if ambiguity_res.ambiguities:
            for idx, a in enumerate(ambiguity_res.ambiguities, 1):
                amb_type = a.category or (a.type.value if hasattr(a.type, 'value') else str(a.type))
                print(f"   [{idx}] Type:              {amb_type}")
                print(f"       Field / Context:   {a.field}")
                print(f"       Candidate Columns: {a.alternatives}")
                print(f"       Blocking Action:   {'BLOCKING (requires clarification)' if a.is_blocking else 'NON-BLOCKING (item-level / parallel branch)'}")
        else:
            print("   [Clean request: 0 ambiguities detected, passes directly to planning]")
        print()

    print("=" * 80)
    print("STAGE 3 GATE: COMPLETED EXECUTION ACROSS ALL 6 BRIEFS")
    print("=" * 80)

if __name__ == "__main__":
    main()
