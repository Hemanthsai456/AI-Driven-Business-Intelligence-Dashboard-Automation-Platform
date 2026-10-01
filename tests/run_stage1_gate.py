import sys
from pathlib import Path

# Add repository root to python search path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.loaders.csv_loader import CSVLoader
from intelligence.semantic_analyzer import SemanticAnalyzer

analyzer = SemanticAnalyzer()
loader = CSVLoader()

files = [
    ("tests/real_data/Calendar.csv", "Real Data 1: Calendar.csv"),
    ("tests/real_data/Customers.csv", "Real Data 2: Customers.csv"),
    ("tests/real_data/Products.csv", "Real Data 3: Products.csv"),
    ("tests/real_data/Sales_2024.csv", "Real Data 4: Sales_2024.csv"),
    ("tests/real_data/Stores.csv", "Real Data 5: Stores.csv"),
    ("tests/fixtures/obfuscated_financial_metrics.csv", "Obfuscated File 1: Financial Metrics (Headers: c1..c5)"),
    ("tests/fixtures/obfuscated_time_series_logs.csv", "Obfuscated File 2: Time Series Logs (Headers: x0..x4)"),
    ("tests/fixtures/obfuscated_customer_survey.csv", "Obfuscated File 3: Customer Survey (Headers: f_a..f_f)"),
]

for file_path, label in files:
    canonical = loader.load(file_path)
    sem_profile = analyzer.analyze(canonical)
    print("=" * 80)
    print(f"FILE: {label} [{file_path}]")
    print("=" * 80)
    print(f"{'Column':<16} | {'Role':<12} | {'Conf':<6} | {'Level':<7} | Primary Evidence")
    print("-" * 80)
    for col_meta in canonical.metadata.schema:
        col = col_meta.original_name
        ev = sem_profile.get_evidence(col)
        role = ev.candidate_role.value if ev else "UNKNOWN"
        conf = f"{ev.confidence:.2f}" if ev else "0.00"
        lvl = ev.confidence_level if ev else "NONE"
        key_ev = [
            e for e in (ev.evidence if ev else [])
            if not e.startswith("cardinality")
            and not e.startswith("uniqueness")
            and not e.startswith("null ratio")
            and not e.startswith("numeric profile")
        ]
        primary_ev = key_ev[0] if key_ev else (ev.evidence[0] if ev and ev.evidence else "No evidence")
        print(f"{col:<16} | {role:<12} | {conf:<6} | {lvl:<7} | {primary_ev}")
    print()
