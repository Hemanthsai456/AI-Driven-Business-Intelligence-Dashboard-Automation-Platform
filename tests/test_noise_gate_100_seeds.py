"""Noise gate test across 100 seeds.

Evaluates false discovery rate under pure independent Gaussian noise and uniform categories.
Assures FDR control suppresses spurious visual insights across random seeds.
"""

import numpy as np
import pandas as pd
import pytest

from ingestion.models import CanonicalDataset, ColumnMetadata, DatasetMetadata
from intelligence.schema_validator import assess_readiness
from intelligence.semantic_analyzer import ColumnRole, ColumnSemanticEvidence, DatasetSemanticProfile
from orchestrator.discovery.engine import run_discovery_pipeline
from orchestrator.discovery.schemas import InsightType


def _create_mock_dataset(df: pd.DataFrame, dataset_id: str = "mock_ds"):
    col_metadata = []
    col_evidences = {}

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            role = ColumnRole.MEASURE
            dtype_str = "FLOAT"
        else:
            role = ColumnRole.DIMENSION
            dtype_str = "VARCHAR"

        col_metadata.append(
            ColumnMetadata(
                original_name=col,
                normalized_name=col.lower(),
                detected_datatype=dtype_str,
                semantic_role=role,
                null_count=int(df[col].isna().sum()),
                null_percentage=float(df[col].isna().sum() / len(df) * 100),
                distinct_count=int(df[col].nunique()),
                is_unique=bool(df[col].nunique() == len(df)),
                sample_values=list(df[col].head(3)),
            )
        )

        col_evidences[col] = ColumnSemanticEvidence(
            column_name=col,
            candidate_role=role,
            confidence=0.95,
            confidence_level="HIGH",
            evidence=[f"Synthetic evidence for {role.value}"],
        )

    metadata = DatasetMetadata(
        dataset_id=dataset_id,
        name=f"{dataset_id}.csv",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=col_metadata,
    )

    dataset = CanonicalDataset(data=df.copy(), metadata=metadata)
    sem_profile = DatasetSemanticProfile(dataset_id=dataset_id, column_evidences=col_evidences)
    readiness = assess_readiness(dataset)
    return dataset, sem_profile, readiness


def test_noise_gate_100_seeds():
    """Run 100 seeds with pure noise and measure exact false discovery count."""
    total_runs = 100
    false_discovery_runs = 0
    seeds_with_false_discoveries = []

    for seed in range(total_runs):
        rng = np.random.RandomState(seed + 2000)
        n = 100
        # Independent Gaussian noise
        m1 = rng.normal(100.0, 15.0, size=n)
        m2 = rng.normal(50.0, 10.0, size=n)
        # Uniform independent categories
        cat1 = rng.choice(["North", "South", "East", "West"], size=n)
        cat2 = rng.choice(["Tier1", "Tier2", "Tier3"], size=n)

        df = pd.DataFrame({
            "noise_m1": m1,
            "noise_m2": m2,
            "noise_cat1": cat1,
            "noise_cat2": cat2,
        })

        dataset, sem_profile, readiness = _create_mock_dataset(df, f"noise_100_ds_{seed}")

        spec, rejected, summary = run_discovery_pipeline(
            dataset=dataset,
            semantic_profile=sem_profile,
            readiness=readiness,
            intent="dashboard on this data",
            fdr_alpha=0.05,
            strength_floor=0.08,
            robustness_floor=0.35,
        )

        # Non-KPI visual insights
        non_kpi_panels = [
            p
            for p in spec.panels
            if p.metadata.get("insight_type")
            in (
                InsightType.RANKING.value,
                InsightType.TREND.value,
                InsightType.CORRELATION.value,
                InsightType.SEGMENT_GAP.value,
                InsightType.COMPOSITION.value,
                InsightType.DISTRIBUTION_OUTLIERS.value,
            )
        ]

        if len(non_kpi_panels) > 0:
            false_discovery_runs += 1
            seeds_with_false_discoveries.append((seed, [p.metadata.get("insight_type") for p in non_kpi_panels]))

    print(
        f"\n[NOISE GATE AT 100 SEEDS]: exact false-discovery count = {false_discovery_runs}/{total_runs} "
        f"(rate: {false_discovery_runs / total_runs:.1%})"
    )
    if seeds_with_false_discoveries:
        print(f"Seeds with false discoveries: {seeds_with_false_discoveries}")

    # Standard nominal FDR control bound: at alpha=0.05, expected false discoveries <= 5
    assert false_discovery_runs <= 5, f"False discovery count too high: {false_discovery_runs}/{total_runs}"
