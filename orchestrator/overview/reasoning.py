"""Generalized Analytical Reasoning and Candidate Diversity Engine for Autonomous Overview (Step 7).

Principles:
- Zero column-name dictionaries or domain-specific hardcoded mappings.
- Evidence-grounded inference of dataset grain, entity representation, and aggregation suitability.
- Multi-perspective candidate generation across diverse analytical families.
- Diversity-aware selection to ensure complementary dashboard perspectives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import uuid4

import numpy as np
import pandas as pd

from engine.compiler import compile_plan_to_sql
from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.profiler import DataProfile
from intelligence.semantic_analyzer import (
    ColumnSemanticEvidence,
    DatasetSemanticProfile,
)
from orchestrator.insights.schemas import (
    EvidenceGroundedInsight,
    InsightEvidence,
    InsightType,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DashboardTile,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    MetricSpec,
    PlanReasoning,
    RankedCandidate,
    ScoreBreakdown,
    TileEvidence,
    TileSize,
    VisualizationType,
)


class DatasetGrainType(str, Enum):
    """Inferred grain representing what one row in the dataset represents."""

    ENTITY = "ENTITY"  # 1 row = 1 individual entity/subject (e.g. person, item, account)
    TRANSACTION_EVENT = "TRANSACTION_EVENT"  # 1 row = 1 event, transaction, or log entry
    REPEATED_OBSERVATION = "REPEATED_OBSERVATION"  # Repeated measurements or time-series readings
    GROUPED_SUMMARY = "GROUPED_SUMMARY"  # Pre-aggregated / grouped dataset
    GENERAL_RECORD = "GENERAL_RECORD"  # General tabular records


class AggregationSupportLevel(str, Enum):
    """Degree of analytical support for an aggregation on a measure."""

    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"  # Natural, meaningful primary operation
    REASONABLY_SUPPORTED = "REASONABLY_SUPPORTED"  # Valid secondary perspective
    WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"  # Marginally meaningful; low analytical value
    INAPPROPRIATE = "INAPPROPRIATE"  # Mathematically or conceptually invalid


@dataclass
class AggregationSuitability:
    """Analytical evaluation of a specific aggregation for a measure."""

    aggregation: AggregationType
    score: float  # 0.0 to 1.0
    level: AggregationSupportLevel
    evidence_reasons: List[str] = field(default_factory=list)


@dataclass
class DatasetGrainEvidence:
    """Inferred dataset row grain and entity opportunities based on structural evidence."""

    likely_grain: DatasetGrainType
    entity_columns: List[str]
    primary_entity_col: Optional[str]
    is_unique_entity_grain: bool
    evidence_notes: List[str] = field(default_factory=list)


class AnalyticalFamily(str, Enum):
    """Distinct analytical perspectives supported by the dataset."""

    HEADLINE_KPI = "HEADLINE_KPI"
    TEMPORAL_TREND = "TEMPORAL_TREND"
    GROUPED_BREAKDOWN = "GROUPED_BREAKDOWN"
    ENTITY_COUNT = "ENTITY_COUNT"
    COMPOSITION = "COMPOSITION"
    RELATIONSHIP = "RELATIONSHIP"
    OUTLIER = "OUTLIER"
    RECORD_SAMPLE = "RECORD_SAMPLE"


@dataclass
class AnalyticalCandidate:
    """A fully formed analytical candidate evaluated across evidence dimensions."""

    candidate_id: str
    family: AnalyticalFamily
    plan: CandidatePlan
    chart_type: str
    primary_measure: Optional[str]
    primary_dimension: Optional[str]
    aggregation: Optional[AggregationType]
    title: str
    narration: str
    base_score: float
    evidence: TileEvidence
    default_size: TileSize
    execution_result: Optional[ExecutionResult] = None
    compiled_sql: Optional[str] = None


# ===========================================================================
# 1. Dataset Grain & Entity Inference
# ===========================================================================


def infer_dataset_grain(
    dataset: CanonicalDataset,
    semantic_profile: Optional[DatasetSemanticProfile],
    data_profile: Optional[DataProfile],
    identifiers: List[str],
    datetimes: List[str],
    measures: List[str],
) -> DatasetGrainEvidence:
    """Infer what one row in the dataset represents from structural evidence.

    Uses zero column names or domain keywords. Derives grain from:
    - Presence, uniqueness, and repetition of identifier columns
    - Temporal distribution and repetition of timestamps per entity
    - Cardinality ratios and row count
    """
    df = dataset.data
    total_rows = len(df) if df is not None else 0
    if total_rows == 0:
        return DatasetGrainEvidence(
            likely_grain=DatasetGrainType.GENERAL_RECORD,
            entity_columns=[],
            primary_entity_col=None,
            is_unique_entity_grain=False,
            evidence_notes=["Empty dataset; default grain assigned."],
        )

    entity_cols: List[str] = list(identifiers)
    evidence_notes: List[str] = []

    # Check for candidate entity columns if identifiers list is empty
    if not entity_cols:
        for col in df.columns:
            if col in measures or col in datetimes:
                continue
            nunique = df[col].nunique(dropna=True)
            u_ratio = nunique / total_rows
            is_obj = not pd.api.types.is_numeric_dtype(df[col])
            # High cardinality non-measure column
            if u_ratio >= 0.85 and (is_obj or u_ratio == 1.0):
                entity_cols.append(col)

    primary_entity = entity_cols[0] if entity_cols else None
    is_unique_entity_grain = False

    if primary_entity is not None:
        u_ratio = df[primary_entity].nunique(dropna=True) / max(total_rows, 1)
        if u_ratio >= 0.95:
            # Each row corresponds to a distinct entity ID
            # Check if there is a datetime column indicating registration or time progression
            if datetimes and len(datetimes) >= 1:
                dt_col = datetimes[0]
                dt_nunique = df[dt_col].nunique(dropna=True)
                if dt_nunique > 1:
                    evidence_notes.append(
                        f"Unique entity identifier '{primary_entity}' (uniqueness {u_ratio:.1%}) with distinct timestamps."
                    )
            else:
                evidence_notes.append(
                    f"Entity-level grain: '{primary_entity}' is unique across all rows ({u_ratio:.1%})."
                )

            likely_grain = DatasetGrainType.ENTITY
            is_unique_entity_grain = True
        else:
            # Repeated entity IDs across rows -> Events or transactions per entity
            evidence_notes.append(
                f"Repeated entity identifier '{primary_entity}' (cardinality ratio {u_ratio:.1%}) indicates multi-event/transaction grain."
            )
            likely_grain = DatasetGrainType.TRANSACTION_EVENT
            is_unique_entity_grain = False
    elif datetimes and len(datetimes) >= 1 and total_rows >= 10:
        # Datetime present with no explicit entity ID
        dt_col = datetimes[0]
        dt_nunique = df[dt_col].nunique(dropna=True)
        if dt_nunique / total_rows >= 0.70:
            likely_grain = DatasetGrainType.REPEATED_OBSERVATION
            evidence_notes.append("Time-series observation grain: sequential datetime records detected.")
        else:
            likely_grain = DatasetGrainType.TRANSACTION_EVENT
            evidence_notes.append("Event log grain: timestamps present with categorical groupings.")
    elif total_rows <= 15 and len(measures) >= 2:
        likely_grain = DatasetGrainType.GROUPED_SUMMARY
        evidence_notes.append(f"Low row count ({total_rows}) with multiple measures suggests summary table.")
    else:
        likely_grain = DatasetGrainType.GENERAL_RECORD
        evidence_notes.append("General record grain: no dominant unique entity or timestamp pattern.")

    return DatasetGrainEvidence(
        likely_grain=likely_grain,
        entity_columns=entity_cols,
        primary_entity_col=primary_entity,
        is_unique_entity_grain=is_unique_entity_grain,
        evidence_notes=evidence_notes,
    )


# ===========================================================================
# 2. Generalized Measure Aggregation Inference (No Column Name Lookups!)
# ===========================================================================


def evaluate_measure_aggregations(
    measure: str,
    df: pd.DataFrame,
    grain: DatasetGrainEvidence,
    semantic_profile: Optional[DatasetSemanticProfile] = None,
) -> Dict[AggregationType, AggregationSuitability]:
    """Evaluate plausible aggregations (SUM, AVG, MEDIAN, MIN, MAX) for a numeric measure.

    Guarantees:
    - Zero column-name dictionaries or domain-specific lookups.
    - Derived purely from:
      1. Value behavior (range bounds, discrete vs continuous, floating-point traits, negatives)
      2. Dataset row grain (individual entity vs transaction/event vs observation)
      3. Semantic profile evidence if already available (roles, confidence, notes)
    """
    results: Dict[AggregationType, AggregationSuitability] = {}

    if measure == "*":
        # Record count
        results[AggregationType.COUNT] = AggregationSuitability(
            aggregation=AggregationType.COUNT,
            score=0.98,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Universal dataset record count."],
        )
        return results

    if measure not in df.columns:
        return results

    s = pd.to_numeric(df[measure], errors="coerce").dropna()
    n = len(s)
    if n == 0:
        for agg in (AggregationType.AVG, AggregationType.SUM, AggregationType.MEDIAN, AggregationType.MIN, AggregationType.MAX):
            results[agg] = AggregationSuitability(
                aggregation=agg,
                score=0.20,
                level=AggregationSupportLevel.WEAKLY_SUPPORTED,
                evidence_reasons=["Measure contains zero non-null numeric values."],
            )
        return results

    min_val = float(s.min())
    max_val = float(s.max())
    mean_val = float(s.mean())
    nunique_val = int(s.nunique())
    val_range = max_val - min_val

    # Check floating-point vs discrete integer
    has_fractional = bool((s % 1 != 0).any())
    is_float_type = pd.api.types.is_float_dtype(df[measure]) or has_fractional

    # Extract existing semantic profiling category if present
    ev = semantic_profile.get_evidence(measure) if semantic_profile else None
    ev_agg_cat = (ev.aggregation_category or "").upper() if ev else ""
    ev_default = (ev.aggregation_default or "").upper() if ev else ""

    # -----------------------------------------------------------------------
    # Evidence 1: Bounded Range [0, 1] (Probability / Ratio / Rate)
    # -----------------------------------------------------------------------
    is_bounded_0_1 = (min_val >= 0.0) and (max_val <= 1.0) and (is_float_type or nunique_val > 2)

    # -----------------------------------------------------------------------
    # Evidence 2: Bounded Range [0, 100] (Percentage / Index / Standard Score)
    # -----------------------------------------------------------------------
    is_bounded_0_100 = (
        (min_val >= 0.0)
        and (max_val <= 100.0)
        and (is_float_type or nunique_val > 5)
        and (val_range <= 100.0)
    )

    # -----------------------------------------------------------------------
    # Evidence 3: Small Discrete Scale (e.g. Likert scale, 1-5 rating, 0-10 grade)
    # -----------------------------------------------------------------------
    is_discrete_scale = (
        (min_val >= 0.0)
        and (max_val <= 10.0)
        and (nunique_val <= 11)
        and (not has_fractional or nunique_val <= 21)
    )

    # -----------------------------------------------------------------------
    # Evidence 4: Negative Values Present
    # -----------------------------------------------------------------------
    has_negatives = min_val < 0.0

    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # Determine Suitability per Aggregation
    # -----------------------------------------------------------------------

    # Signal 1: Explicit Semantic Profiling Evidence
    if ev_agg_cat in ("ADDITIVE", "COUNT") or ev_default == "SUM":
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.96,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=[
                f"Semantic evidence indicates additive quantity ({ev_agg_cat or 'additive'}); summation across records is the primary aggregate."
            ],
        )
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.86,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Per-record average provides meaningful expected quantity."],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.78,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Median provides robust typical transaction/quantity value."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.75,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum observed amount."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.50,
            level=AggregationSupportLevel.WEAKLY_SUPPORTED,
            evidence_reasons=["Minimum observed amount."],
        )
        return results

    if ev_agg_cat in ("INTENSIVE", "SCORE", "RATE", "DURATION") or ev_default == "AVG":
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.96,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=[
                f"Semantic evidence indicates intensive measurement ({ev_agg_cat or 'intensive'}); average is the primary aggregate."
            ],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.91,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Median provides robust central tendency."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.78,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Minimum captures lowest observed rate/score."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.78,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum captures peak observed rate/score."],
        )
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.18,
            level=AggregationSupportLevel.INAPPROPRIATE,
            evidence_reasons=[
                f"Summing intensive {ev_agg_cat or 'rate'} across records is analytically misleading."
            ],
        )
        return results

    # Signal 2: Bounded Ratio / Probability [0, 1]
    if is_bounded_0_1:
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.96,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=[
                f"Values bounded in [0, 1] (range {min_val:.2f} - {max_val:.2f}) represent a rate, ratio, or probability where mean is authoritative."
            ],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.91,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Median provides a robust central tendency for bounded ratios."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.75,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Minimum establishes lower bound of observed rates."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.75,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum establishes upper bound of observed rates."],
        )
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.15,
            level=AggregationSupportLevel.INAPPROPRIATE,
            evidence_reasons=[
                "Summing bounded ratios across rows is non-additive and yields uninterpretable numbers exceeding 1.0."
            ],
        )
        return results

    # Signal 3: Small Discrete Rating / Scale (1-5, 0-10)
    if is_discrete_scale:
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.95,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=[
                f"Small discrete scale ({min_val:.0f} - {max_val:.0f}) represents an evaluation score or rating scale best characterized by central tendency."
            ],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.90,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Median reflects typical ordinal rating without outlier distortion."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.70,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Minimum rating indicates lower performance floor."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.70,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum rating indicates ceiling achievement."],
        )
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.18,
            level=AggregationSupportLevel.INAPPROPRIATE,
            evidence_reasons=[
                "Summing ordinal rating values across records is analytically meaningless."
            ],
        )
        return results

    # Signal 4: Bounded Percentage / Index [0, 100]
    if is_bounded_0_100:
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.95,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=[
                f"Values bounded in [0, 100] indicate percentage or standardized index; average reflects overall performance level."
            ],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.90,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Median provides robust index distribution center."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.75,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Minimum boundary of observed index."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.75,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum boundary of observed index."],
        )
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.18,
            level=AggregationSupportLevel.INAPPROPRIATE,
            evidence_reasons=[
                "Summing percentage/index values across entities yields uninterpretable accumulated numbers."
            ],
        )
        return results

    # Signal 5: Entity Grain — Individual Entity Observation / Descriptive Measure
    if grain.likely_grain == DatasetGrainType.ENTITY and grain.is_unique_entity_grain:
        if is_float_type:
            results[AggregationType.AVG] = AggregationSuitability(
                aggregation=AggregationType.AVG,
                score=0.95,
                level=AggregationSupportLevel.STRONGLY_SUPPORTED,
                evidence_reasons=[
                    f"Entity-level continuous attribute ({min_val:.1f} - {max_val:.1f}) describes individual entity observations; average is the most informative aggregate."
                ],
            )
            results[AggregationType.MEDIAN] = AggregationSuitability(
                aggregation=AggregationType.MEDIAN,
                score=0.90,
                level=AggregationSupportLevel.STRONGLY_SUPPORTED,
                evidence_reasons=["Median provides robust per-entity distribution midpoint."],
            )
            results[AggregationType.MIN] = AggregationSuitability(
                aggregation=AggregationType.MIN,
                score=0.80,
                level=AggregationSupportLevel.REASONABLY_SUPPORTED,
                evidence_reasons=["Minimum captures lowest observed entity value."],
            )
            results[AggregationType.MAX] = AggregationSuitability(
                aggregation=AggregationType.MAX,
                score=0.80,
                level=AggregationSupportLevel.REASONABLY_SUPPORTED,
                evidence_reasons=["Maximum captures peak observed entity value."],
            )
            results[AggregationType.SUM] = AggregationSuitability(
                aggregation=AggregationType.SUM,
                score=0.25,
                level=AggregationSupportLevel.WEAKLY_SUPPORTED,
                evidence_reasons=[
                    "Summing individual entity descriptive states across records is analytically uninformative."
                ],
            )
            return results

        # Discrete integer on entity grain (e.g. items owned, dependents, years)
        if min_val >= 0:
            results[AggregationType.SUM] = AggregationSuitability(
                aggregation=AggregationType.SUM,
                score=0.88,
                level=AggregationSupportLevel.STRONGLY_SUPPORTED,
                evidence_reasons=["Discrete entity quantity accumulates to population total."],
            )
            results[AggregationType.AVG] = AggregationSuitability(
                aggregation=AggregationType.AVG,
                score=0.86,
                level=AggregationSupportLevel.STRONGLY_SUPPORTED,
                evidence_reasons=["Per-entity average provides expected individual allocation."],
            )
            results[AggregationType.MEDIAN] = AggregationSuitability(
                aggregation=AggregationType.MEDIAN,
                score=0.80,
                level=AggregationSupportLevel.REASONABLY_SUPPORTED,
                evidence_reasons=["Median provides central per-entity baseline."],
            )
            results[AggregationType.MAX] = AggregationSuitability(
                aggregation=AggregationType.MAX,
                score=0.75,
                level=AggregationSupportLevel.REASONABLY_SUPPORTED,
                evidence_reasons=["Maximum captures highest single entity holding."],
            )
            results[AggregationType.MIN] = AggregationSuitability(
                aggregation=AggregationType.MIN,
                score=0.60,
                level=AggregationSupportLevel.WEAKLY_SUPPORTED,
                evidence_reasons=["Minimum observed entity value."],
            )
            return results

    # Signal 6: Transaction / Event Grain (Accumulating Quantities Across Rows)
    if grain.likely_grain in (DatasetGrainType.TRANSACTION_EVENT, DatasetGrainType.REPEATED_OBSERVATION):
        if min_val >= 0:
            results[AggregationType.SUM] = AggregationSuitability(
                aggregation=AggregationType.SUM,
                score=0.95,
                level=AggregationSupportLevel.STRONGLY_SUPPORTED,
                evidence_reasons=["Transaction/event grain; additive quantities accumulate to meaningful dataset total."],
            )
            results[AggregationType.AVG] = AggregationSuitability(
                aggregation=AggregationType.AVG,
                score=0.86,
                level=AggregationSupportLevel.STRONGLY_SUPPORTED,
                evidence_reasons=["Average transaction / event magnitude."],
            )
            results[AggregationType.MEDIAN] = AggregationSuitability(
                aggregation=AggregationType.MEDIAN,
                score=0.78,
                level=AggregationSupportLevel.REASONABLY_SUPPORTED,
                evidence_reasons=["Median transaction size."],
            )
            results[AggregationType.MAX] = AggregationSuitability(
                aggregation=AggregationType.MAX,
                score=0.75,
                level=AggregationSupportLevel.REASONABLY_SUPPORTED,
                evidence_reasons=["Peak transaction / event magnitude."],
            )
            results[AggregationType.MIN] = AggregationSuitability(
                aggregation=AggregationType.MIN,
                score=0.50,
                level=AggregationSupportLevel.WEAKLY_SUPPORTED,
                evidence_reasons=["Minimum transaction baseline."],
            )
            return results

    # Signal 7: General / Unfamiliar Dataset (Ambiguous Grain & Measure)
    if has_negatives:
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.90,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Distribution contains negative values; average captures central balance."],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.85,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Median represents typical observation."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.80,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Minimum captures lowest negative extreme."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.80,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum captures peak positive extreme."],
        )
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.55,
            level=AggregationSupportLevel.WEAKLY_SUPPORTED,
            evidence_reasons=["Net sum across negative and positive observations."],
        )
    elif is_float_type:
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.90,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Continuous numeric distribution; mean provides foundational central tendency."],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.85,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Median provides robust central tendency."],
        )
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.70,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Plausible additive total across dataset."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.75,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Peak observed value."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.65,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Minimum observed value."],
        )
    else:
        results[AggregationType.SUM] = AggregationSuitability(
            aggregation=AggregationType.SUM,
            score=0.88,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Discrete integer values support additive accumulation across records."],
        )
        results[AggregationType.AVG] = AggregationSuitability(
            aggregation=AggregationType.AVG,
            score=0.85,
            level=AggregationSupportLevel.STRONGLY_SUPPORTED,
            evidence_reasons=["Per-record average rate."],
        )
        results[AggregationType.MEDIAN] = AggregationSuitability(
            aggregation=AggregationType.MEDIAN,
            score=0.78,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Median integer value."],
        )
        results[AggregationType.MAX] = AggregationSuitability(
            aggregation=AggregationType.MAX,
            score=0.72,
            level=AggregationSupportLevel.REASONABLY_SUPPORTED,
            evidence_reasons=["Maximum integer value."],
        )
        results[AggregationType.MIN] = AggregationSuitability(
            aggregation=AggregationType.MIN,
            score=0.55,
            level=AggregationSupportLevel.WEAKLY_SUPPORTED,
            evidence_reasons=["Minimum integer value."],
        )

    return results


# ===========================================================================
# 3. Entity Counting Opportunities
# ===========================================================================


def infer_counting_candidates(
    dataset_id: str,
    df: pd.DataFrame,
    grain: DatasetGrainEvidence,
    dimensions: List[str],
) -> List[AnalyticalCandidate]:
    """Generate entity counting candidates based on available identifier and grain evidence."""
    candidates: List[AnalyticalCandidate] = []
    total_rows = len(df) if df is not None else 0
    if total_rows == 0:
        return candidates

    # Foundational Dataset Record / Entity Count
    # In conformance with platform architecture, identifiers are never placed in metric columns
    ent_title = "Total Records"
    if grain.primary_entity_col:
        clean_ent = re.sub(r"([a-z])([A-Z])", r"\1 \2", grain.primary_entity_col).replace("_", " ").title()
        for pfx in ("Id ", "No ", "Code "):
            if clean_ent.startswith(pfx):
                clean_ent = clean_ent[len(pfx):].strip()
        if grain.is_unique_entity_grain:
            ent_title = f"Total {clean_ent} Count"

    rec_plan = CandidatePlan(
        dataset_id=dataset_id,
        intent=ent_title,
        metric=MetricSpec(column="*", aggregation=AggregationType.COUNT),
        dimensions=[],
        reasoning=PlanReasoning(
            interpretation=f"Total record count across the dataset ({total_rows:,} records).",
            evidence=["universal_record_count"],
        ),
    )
    candidates.append(
        AnalyticalCandidate(
            candidate_id=f"cand_kpi_records_{uuid4().hex[:6]}",
            family=AnalyticalFamily.HEADLINE_KPI,
            plan=rec_plan,
            chart_type="kpi",
            primary_measure="*",
            primary_dimension=None,
            aggregation=AggregationType.COUNT,
            title=ent_title,
            narration=f"Foundational scope metric: {total_rows:,} total records in dataset.",
            base_score=0.92,
            evidence=TileEvidence(strength=1.0, robustness=1.0, score=0.92, n=total_rows),
            default_size=TileSize(w=3, h=2),
        )
    )

    return candidates


# ===========================================================================
# 4. Diversity Selection Algorithm
# ===========================================================================


def calculate_candidate_similarity(c1: AnalyticalCandidate, c2: AnalyticalCandidate) -> float:
    """Compute similarity (0.0 to 1.0) between two analytical candidates for redundancy penalty."""
    sim = 0.0

    # Family overlap
    if c1.family == c2.family:
        sim += 0.35

    # Measure overlap
    if c1.primary_measure and c2.primary_measure and c1.primary_measure == c2.primary_measure:
        sim += 0.35
        # If both measure AND aggregation are identical
        if c1.aggregation == c2.aggregation:
            sim += 0.15

    # Dimension overlap
    if c1.primary_dimension and c2.primary_dimension and c1.primary_dimension == c2.primary_dimension:
        sim += 0.30

    return min(sim, 1.0)


def select_diversified_candidates(
    candidates: List[AnalyticalCandidate],
    target_count: int = 4,
    diversity_penalty_weight: float = 0.45,
) -> List[AnalyticalCandidate]:
    """Greedy diversity selection using maximal marginal relevance (MMR).

    Balances candidate quality with coverage of complementary analytical perspectives.
    """
    if not candidates:
        return []

    if len(candidates) <= target_count:
        return sorted(candidates, key=lambda c: c.base_score, reverse=True)

    selected: List[AnalyticalCandidate] = []
    remaining = list(candidates)

    # Pick the absolute best candidate first
    best_initial = max(remaining, key=lambda c: c.base_score)
    selected.append(best_initial)
    remaining.remove(best_initial)

    while len(selected) < target_count and remaining:
        best_candidate: Optional[AnalyticalCandidate] = None
        best_marginal_utility = -float("inf")

        for cand in remaining:
            # Maximum similarity with any already selected candidate
            max_sim = max(calculate_candidate_similarity(cand, sel) for sel in selected)
            marginal_utility = cand.base_score - (diversity_penalty_weight * max_sim)

            if marginal_utility > best_marginal_utility:
                best_marginal_utility = marginal_utility
                best_candidate = cand

        if best_candidate is not None:
            selected.append(best_candidate)
            remaining.remove(best_candidate)
        else:
            break

    return selected
