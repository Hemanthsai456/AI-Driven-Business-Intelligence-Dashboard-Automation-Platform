"""Robustness across analytical interpretations.

Replaces the V1 stability proxy with perturbation-based robustness testing.

Definition:
For a candidate plan, build a perturbation set at runtime from the ambiguity result
and column roles:
- Alternate compatible MEASURE columns
- Alternate aggregations (SUM/AVG/MEDIAN where valid)
- Adjacent temporal granularities
- Alternate compatible dimensions

Nothing is hardcoded by dataset.
Execute each variant through the existing compiler, executor, and Pass 1.
The candidate's claim is its result ordering over the dimension (top-1 group and full ranking).
Variants use different metrics with different scales, so compare ranks, never raw values.

robustness = mean over valid variants of (0.5 * top1_agreement + 0.5 * spearman_rank_correlation, floored at 0).
Variants that fail execution are excluded and counted in variants_failed.

coverage_of_test = valid_variants / attempted_variants.
If fewer than 2 valid variants exist, robustness = None with status="UNTESTED".
It must never default to 1.0, because untested is not robust.

Determinism:
Column names, dimensions, aggregations, and granularities are processed in strict,
sorted order so that identical inputs (or shuffled column orders) produce identical results.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, Field

from engine.executor import AnalyticsEngine, get_default_engine
from ingestion.models import CanonicalDataset
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.ambiguity import AmbiguityResult, AmbiguityType
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    Granularity,
    MetricSpec,
)
from orchestrator.validator import validate_pass1a, validate_pass1b


TEMPORAL_GRANULARITY_HIERARCHY: List[Granularity] = [
    Granularity.HOUR,
    Granularity.DAY,
    Granularity.WEEK,
    Granularity.MONTH,
    Granularity.QUARTER,
    Granularity.YEAR,
]

VALID_MEASURE_AGGREGATIONS: List[AggregationType] = [
    AggregationType.SUM,
    AggregationType.AVG,
    AggregationType.MEDIAN,
]


class RobustnessEvaluation(BaseModel):
    """Structured evaluation of robustness for a candidate plan."""

    variants_attempted: int = 0
    variants_valid: int = 0
    variants_failed: List[Dict[str, Any]] = Field(default_factory=list)
    variant_details: List[Dict[str, Any]] = Field(default_factory=list)
    coverage_of_test: float = 0.0
    robustness: Optional[float] = None
    status: str = "UNTESTED"  # "TESTED", "UNTESTED", "FAILED"

    model_config = {"frozen": True}


def compute_fractional_ranks(values: Sequence[float]) -> List[float]:
    """Compute 1-based fractional ranks (ties assigned average rank)."""
    n = len(values)
    if n == 0:
        return []
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def compute_spearman_rank_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman's rank correlation coefficient between two numeric sequences."""
    n = len(x)
    if n < 2 or len(y) != n:
        return 0.0

    rx = compute_fractional_ranks(x)
    ry = compute_fractional_ranks(y)

    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n

    cov = sum((rx[k] - mean_rx) * (ry[k] - mean_ry) for k in range(n))
    var_x = sum((rx[k] - mean_rx) ** 2 for k in range(n))
    var_y = sum((ry[k] - mean_ry) ** 2 for k in range(n))

    if var_x <= 1e-12 or var_y <= 1e-12:
        # Constant ranking has zero variance; correlation is undefined / 0.0
        return 0.0

    r = cov / ((var_x * var_y) ** 0.5)
    return max(-1.0, min(1.0, r))


def extract_group_ranking(
    plan: CandidatePlan,
    result: ExecutionResult,
) -> Tuple[Optional[Any], Dict[Any, float], List[Any]]:
    """Extract (top1_group, group_to_metric_map, sorted_groups) from execution output.

    Sorts descending by metric value; uses group key string representation as secondary
    sort key for strict determinism on metric ties.
    """
    if not result.rows or not plan.dimensions:
        return None, {}, []

    # Identify dimension columns in output
    dim_cols: List[str] = []
    for d in plan.dimensions:
        gran_alias = (
            f"{d.column}_{d.granularity.value.lower()}"
            if d.granularity is not None
            else d.column
        )
        if gran_alias in result.columns:
            dim_cols.append(gran_alias)
        elif d.column in result.columns:
            dim_cols.append(d.column)

    if not dim_cols:
        return None, {}, []

    # Identify metric column in output (non-dimension column)
    metric_cols = [c for c in result.columns if c not in dim_cols]
    if not metric_cols:
        return None, {}, []
    metric_col = metric_cols[0]

    group_map: Dict[Any, float] = {}
    for row in result.rows:
        if len(dim_cols) == 1:
            raw_key = row.get(dim_cols[0])
            key = str(raw_key) if raw_key is not None else "__null__"
        else:
            key = tuple(str(row.get(c)) for c in dim_cols)

        val = row.get(metric_col)
        try:
            metric_val = float(val) if val is not None else float("-inf")
        except (ValueError, TypeError):
            metric_val = float("-inf")

        group_map[key] = metric_val

    if not group_map:
        return None, {}, []

    # Sort descending by metric value, secondary ascending by key string
    sorted_groups = sorted(
        group_map.keys(),
        key=lambda g: (-group_map[g], str(g)),
    )
    top1 = sorted_groups[0]
    return top1, group_map, sorted_groups


def generate_perturbations(
    plan: CandidatePlan,
    semantic_profile: DatasetSemanticProfile,
    ambiguity_result: Optional[AmbiguityResult] = None,
) -> List[Tuple[CandidatePlan, str]]:
    """Build the perturbation set at runtime from ambiguity result and column roles.

    Categories:
    1. Alternate compatible MEASURE columns
    2. Alternate aggregations (SUM/AVG/MEDIAN where valid)
    3. Adjacent temporal granularities
    4. Alternate compatible dimensions

    Determinism: All choices are sorted alphabetically.
    Deduplication: Duplicate plans (by plan_signature) are pruned.
    """
    perturbations: List[Tuple[CandidatePlan, str]] = []
    seen_signatures: Set[str] = {plan.plan_signature()}

    # 1. Alternate compatible MEASURE columns
    compatible_measures: Set[str] = set()
    for col, ev in semantic_profile.column_evidences.items():
        if ev.candidate_role == ColumnRole.MEASURE and col != plan.metric.column:
            compatible_measures.add(col)

    if ambiguity_result:
        for amb in ambiguity_result.ambiguities:
            if amb.type in (AmbiguityType.LEXICAL, AmbiguityType.MULTIPLE_MEASURES):
                for alt in amb.alternatives:
                    ev = semantic_profile.column_evidences.get(alt)
                    if ev and ev.candidate_role == ColumnRole.MEASURE and alt != plan.metric.column:
                        compatible_measures.add(alt)

    for alt_col in sorted(compatible_measures):
        v = plan.model_copy(
            update={"metric": MetricSpec(column=alt_col, aggregation=plan.metric.aggregation)}
        )
        sig = v.plan_signature()
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            perturbations.append((v, f"alternate_measure:{alt_col}"))

    # 2. Alternate aggregations (SUM/AVG/MEDIAN where valid)
    # Generated if ambiguity_result signals aggregation ambiguity or if valid for MEASURE
    has_agg_ambiguity = False
    if ambiguity_result:
        has_agg_ambiguity = any(
            amb.type == AmbiguityType.AGGREGATION for amb in ambiguity_result.ambiguities
        )

    # When aggregation is ambiguous in the intent / ambiguity result:
    if has_agg_ambiguity:
        for alt_agg in sorted(VALID_MEASURE_AGGREGATIONS, key=lambda a: a.value):
            if alt_agg != plan.metric.aggregation:
                v = plan.model_copy(
                    update={"metric": MetricSpec(column=plan.metric.column, aggregation=alt_agg)}
                )
                sig = v.plan_signature()
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    perturbations.append((v, f"alternate_aggregation:{alt_agg.value}"))

    # 3. Adjacent temporal granularities
    for d_idx, dim in enumerate(plan.dimensions):
        if dim.granularity is not None:
            try:
                curr_idx = TEMPORAL_GRANULARITY_HIERARCHY.index(dim.granularity)
            except ValueError:
                curr_idx = -1

            if curr_idx != -1:
                neighbors = []
                if curr_idx - 1 >= 0:
                    neighbors.append(TEMPORAL_GRANULARITY_HIERARCHY[curr_idx - 1])
                if curr_idx + 1 < len(TEMPORAL_GRANULARITY_HIERARCHY):
                    neighbors.append(TEMPORAL_GRANULARITY_HIERARCHY[curr_idx + 1])

                for adj_gran in neighbors:
                    new_dims = list(plan.dimensions)
                    new_dims[d_idx] = DimensionSpec(column=dim.column, granularity=adj_gran)
                    v = plan.model_copy(update={"dimensions": new_dims})
                    sig = v.plan_signature()
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        perturbations.append(
                            (v, f"adjacent_granularity:{dim.column}:{adj_gran.value}")
                        )

    # 4. Alternate compatible dimensions
    if ambiguity_result and plan.dimensions:
        for amb in ambiguity_result.ambiguities:
            if amb.type == AmbiguityType.MULTIPLE_DATE_COLUMNS:
                for alt_col in sorted(amb.alternatives):
                    if alt_col in semantic_profile.column_evidences:
                        current_cols = {d.column for d in plan.dimensions}
                        if alt_col not in current_cols:
                            new_dims = []
                            for d in plan.dimensions:
                                ev = semantic_profile.column_evidences.get(d.column)
                                if ev and ev.candidate_role == ColumnRole.DATETIME:
                                    new_dims.append(
                                        DimensionSpec(column=alt_col, granularity=d.granularity)
                                    )
                                else:
                                    new_dims.append(d)
                            v = plan.model_copy(update={"dimensions": new_dims})
                            sig = v.plan_signature()
                            if sig not in seen_signatures:
                                seen_signatures.add(sig)
                                perturbations.append(
                                    (v, f"alternate_dimension:{alt_col}")
                                )

    # Sort perturbations by description for deterministic evaluation order
    perturbations.sort(key=lambda item: item[1])
    return perturbations


def evaluate_robustness(
    plan: CandidatePlan,
    candidate_result: ExecutionResult,
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    ambiguity_result: Optional[AmbiguityResult] = None,
    engine: Optional[AnalyticsEngine] = None,
) -> RobustnessEvaluation:
    """Evaluate candidate plan robustness across runtime perturbation variants.

    Formula:
        robustness = mean over valid variants of (0.5 * top1_agreement + 0.5 * spearman_rank_correlation, floored at 0)
        coverage_of_test = valid_variants / attempted_variants

    If fewer than 2 valid variants exist:
        robustness = None
        status = "UNTESTED"
    """
    if candidate_result.status != ExecutionStatus.SUCCESS:
        return RobustnessEvaluation(
            variants_attempted=0,
            variants_valid=0,
            variants_failed=[],
            variant_details=[],
            coverage_of_test=0.0,
            robustness=None,
            status="FAILED",
        )

    cand_top1, cand_groups, cand_sorted = extract_group_ranking(plan, candidate_result)
    if len(cand_groups) < 2 or cand_top1 is None:
        # Group ranking requires at least 2 groups over dimension
        return RobustnessEvaluation(
            variants_attempted=0,
            variants_valid=0,
            variants_failed=[],
            variant_details=[],
            coverage_of_test=0.0,
            robustness=None,
            status="UNTESTED",
        )

    perturbations = generate_perturbations(
        plan=plan,
        semantic_profile=semantic_profile,
        ambiguity_result=ambiguity_result,
    )

    attempted_count = len(perturbations)
    if attempted_count == 0:
        return RobustnessEvaluation(
            variants_attempted=0,
            variants_valid=0,
            variants_failed=[],
            variant_details=[],
            coverage_of_test=0.0,
            robustness=None,
            status="UNTESTED",
        )

    exec_engine = engine or get_default_engine()
    valid_scores: List[float] = []
    failed_variants: List[Dict[str, Any]] = []
    variant_details: List[Dict[str, Any]] = []

    for variant_plan, description in perturbations:
        # 1. Pass 1a validation
        pass1a_res = validate_pass1a(variant_plan, semantic_profile)
        if not pass1a_res.passed:
            failed_variants.append(
                {
                    "description": description,
                    "stage": "Pass 1a",
                    "reason": "; ".join(i.message for i in pass1a_res.issues),
                }
            )
            continue

        # 2. Execution
        try:
            var_result = exec_engine.execute(
                plan=variant_plan,
                dataset=dataset,
                semantic_profile=semantic_profile,
            )
        except Exception as e:
            failed_variants.append(
                {
                    "description": description,
                    "stage": "Execution",
                    "reason": str(e),
                }
            )
            continue

        if var_result.status != ExecutionStatus.SUCCESS:
            failed_variants.append(
                {
                    "description": description,
                    "stage": "Execution",
                    "reason": var_result.error_message or "Execution status not SUCCESS",
                }
            )
            continue

        # 3. Pass 1b validation
        pass1b_res = validate_pass1b(variant_plan, var_result)
        if not pass1b_res.passed:
            failed_variants.append(
                {
                    "description": description,
                    "stage": "Pass 1b",
                    "reason": "; ".join(i.message for i in pass1b_res.issues),
                }
            )
            continue

        # 4. Extract variant ranking and compare
        var_top1, var_groups, var_sorted = extract_group_ranking(variant_plan, var_result)
        common_groups = [g for g in cand_sorted if g in var_groups]
        if len(common_groups) < 2 or var_top1 is None:
            failed_variants.append(
                {
                    "description": description,
                    "stage": "Comparison",
                    "reason": f"Insufficient common dimension groups ({len(common_groups)} < 2)",
                }
            )
            continue

        top1_match = 1.0 if cand_top1 == var_top1 else 0.0
        x_vals = [cand_groups[g] for g in common_groups]
        y_vals = [var_groups[g] for g in common_groups]
        spearman = compute_spearman_rank_correlation(x_vals, y_vals)

        # variant score floored at 0
        variant_score = max(0.0, 0.5 * top1_match + 0.5 * spearman)
        valid_scores.append(variant_score)

        variant_details.append(
            {
                "description": description,
                "top1_match": round(top1_match, 4),
                "spearman": round(spearman, 4),
                "score": round(variant_score, 4),
                "group_ranks": {str(g): var_sorted.index(g) + 1 for g in common_groups},
            }
        )

    valid_count = len(valid_scores)
    coverage_of_test = valid_count / attempted_count if attempted_count > 0 else 0.0

    if valid_count < 2:
        return RobustnessEvaluation(
            variants_attempted=attempted_count,
            variants_valid=valid_count,
            variants_failed=failed_variants,
            variant_details=variant_details,
            coverage_of_test=round(coverage_of_test, 4),
            robustness=None,
            status="UNTESTED",
        )

    robustness = sum(valid_scores) / valid_count
    return RobustnessEvaluation(
        variants_attempted=attempted_count,
        variants_valid=valid_count,
        variants_failed=failed_variants,
        variant_details=variant_details,
        coverage_of_test=round(coverage_of_test, 4),
        robustness=round(robustness, 4),
        status="TESTED",
    )
