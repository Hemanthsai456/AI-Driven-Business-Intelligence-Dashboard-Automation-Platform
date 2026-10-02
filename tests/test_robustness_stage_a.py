"""Gate tests for Stage A: Robustness across interpretations.

Verifies:
1. Planted group A top under every measure -> robustness ≈ 1.0
2. Planted flip where the top group differs under half the measures -> robustness clearly lower,
   with expected value computed by hand in the test
3. One measure only -> robustness = None, status="UNTESTED"
4. Determinism: same input twice gives identical robustness
5. Column order shuffled gives the same result
6. Trace recording of attempted, valid, failed (with reasons), per-variant top-1 match and Spearman
"""

import pandas as pd
import pytest

from engine.duckdb_executor import DuckDBExecutor
from engine.executor import AnalyticsEngine, DuckDBEngine
from ingestion.models import CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence.semantic_analyzer import ColumnSemanticEvidence, DatasetSemanticProfile
from orchestrator.robustness import (
    RobustnessEvaluation,
    compute_spearman_rank_correlation,
    evaluate_robustness,
    generate_perturbations,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    PlanReasoning,
    VisualizationType,
)


def _make_dataset(df: pd.DataFrame, roles: dict) -> CanonicalDataset:
    col_metadata = []
    for col in df.columns:
        role = roles.get(col, ColumnRole.MEASURE if pd.api.types.is_numeric_dtype(df[col]) else ColumnRole.DIMENSION)
        col_metadata.append(
            ColumnMetadata(
                original_name=col,
                normalized_name=col,
                detected_datatype=str(df[col].dtype),
                semantic_role=role,
                null_count=int(df[col].isnull().sum()),
                null_percentage=float(df[col].isnull().mean()),
                distinct_count=int(df[col].nunique()),
            )
        )
    meta = DatasetMetadata(
        dataset_id="test_synthetic",
        name="test_synthetic",
        source_type="csv",
        row_count=len(df),
        column_count=len(df.columns),
        schema=col_metadata,
    )
    return CanonicalDataset(metadata=meta, data=df)


def _make_semantic_profile(roles: dict) -> DatasetSemanticProfile:
    evidences = {}
    for col, role in roles.items():
        evidences[col] = ColumnSemanticEvidence(
            column_name=col,
            candidate_role=role,
            confidence=0.95,
            confidence_level="HIGH",
            evidence=["synthetic"],
        )
    return DatasetSemanticProfile(dataset_id="test_synthetic", column_evidences=evidences)


def _make_plan(metric_col: str, dim_col: str = "category", agg: AggregationType = AggregationType.SUM) -> CandidatePlan:
    return CandidatePlan(
        plan_id="cand_test",
        dataset_id="test_synthetic",
        intent="Show total metric by category",
        metric=MetricSpec(column=metric_col, aggregation=agg),
        dimensions=[DimensionSpec(column=dim_col)],
        filters=[],
        visualization=VisualizationType.BAR,
        reasoning=PlanReasoning(interpretation="Synthetic test plan", evidence=[]),
    )


class TestStageARobustness:
    """Gate unit tests on synthetic frames with known answers."""

    def test_planted_group_a_top_under_every_measure(self):
        """Planted group A top under every measure -> robustness ≈ 1.0."""
        # 3 groups: A, B, C
        # m1: A=100, B=50, C=10 (ranking: A=1, B=2, C=3)
        # m2: A=500, B=250, C=50 (ranking: A=1, B=2, C=3)
        # m3: A=30, B=20, C=10 (ranking: A=1, B=2, C=3)
        df = pd.DataFrame({
            "category": ["A", "B", "C"],
            "m1": [100.0, 50.0, 10.0],
            "m2": [500.0, 250.0, 50.0],
            "m3": [30.0, 20.0, 10.0],
        })
        roles = {
            "category": ColumnRole.DIMENSION,
            "m1": ColumnRole.MEASURE,
            "m2": ColumnRole.MEASURE,
            "m3": ColumnRole.MEASURE,
        }
        dataset = _make_dataset(df, roles)
        profile = _make_semantic_profile(roles)
        plan = _make_plan("m1")

        engine = DuckDBEngine()
        cand_res = engine.execute(plan, dataset, profile)

        rob = evaluate_robustness(
            plan=plan,
            candidate_result=cand_res,
            dataset=dataset,
            semantic_profile=profile,
            engine=engine,
        )

        assert rob.status == "TESTED"
        assert rob.variants_attempted == 2  # alternate measures: m2, m3
        assert rob.variants_valid == 2
        assert len(rob.variants_failed) == 0
        assert rob.coverage_of_test == 1.0
        # Under both m2 and m3: top1 matches (A), Spearman = 1.0
        # Score = 0.5 * 1.0 + 0.5 * 1.0 = 1.0 for each variant
        assert rob.robustness == pytest.approx(1.0, abs=1e-3)

    def test_planted_flip_top_group_differs_under_half_measures(self):
        """Planted flip where top group differs under half the measures -> robustness clearly lower.

        Hand computation:
        Candidate plan uses m1:
            Category A: 100
            Category B: 50
            Category C: 10
            Candidate ranking: A=1 (val 100), B=2 (val 50), C=3 (val 10).
            Top-1 group: A.

        Variant 1 (m2):
            Category A: 500, Category B: 250, Category C: 50
            Ranking: A=1, B=2, C=3.
            Top-1 match = 1.0 (A == A)
            Spearman = 1.0
            Variant 1 score = 0.5 * 1.0 + 0.5 * 1.0 = 1.0

        Variant 2 (m3) - planted flip:
            Category A: 250, Category B: 500, Category C: 50
            Ranking: B=1, A=2, C=3.
            Top-1 match = 0.0 (B != A)
            Ranks in candidate: A=1, B=2, C=3
            Ranks in variant 2: A=2, B=1, C=3
            d = [1-2, 2-1, 3-3] = [-1, 1, 0]; d^2 = [1, 1, 0]; sum(d^2) = 2
            Spearman = 1 - 6*(2)/(3*(9-1)) = 1 - 12/24 = 0.50
            Variant 2 score = max(0, 0.5 * 0.0 + 0.5 * 0.50) = 0.25

        Hand-computed expected robustness = (1.0 + 0.25) / 2 = 0.625
        """
        df = pd.DataFrame({
            "category": ["A", "B", "C"],
            "m1": [100.0, 50.0, 10.0],
            "m2": [500.0, 250.0, 50.0],
            "m3": [250.0, 500.0, 50.0],  # B is top, ranking partially flipped
        })
        roles = {
            "category": ColumnRole.DIMENSION,
            "m1": ColumnRole.MEASURE,
            "m2": ColumnRole.MEASURE,
            "m3": ColumnRole.MEASURE,
        }
        dataset = _make_dataset(df, roles)
        profile = _make_semantic_profile(roles)
        plan = _make_plan("m1")

        engine = DuckDBEngine()
        cand_res = engine.execute(plan, dataset, profile)

        rob = evaluate_robustness(
            plan=plan,
            candidate_result=cand_res,
            dataset=dataset,
            semantic_profile=profile,
            engine=engine,
        )

        assert rob.status == "TESTED"
        assert rob.variants_attempted == 2
        assert rob.variants_valid == 2
        assert len(rob.variant_details) == 2

        # Check per-variant details
        v1 = next(v for v in rob.variant_details if "m2" in v["description"])
        v2 = next(v for v in rob.variant_details if "m3" in v["description"])

        assert v1["top1_match"] == 1.0
        assert v1["spearman"] == pytest.approx(1.0, abs=1e-3)
        assert v1["score"] == pytest.approx(1.0, abs=1e-3)

        assert v2["top1_match"] == 0.0
        assert v2["spearman"] == pytest.approx(0.50, abs=1e-3)
        assert v2["score"] == pytest.approx(0.25, abs=1e-3)

        # Expected value hand-computed in docstring: (1.0 + 0.25) / 2 = 0.625
        expected_hand_computed = 0.625
        assert rob.robustness == pytest.approx(expected_hand_computed, abs=1e-3)
        assert rob.robustness < 0.90  # clearly lower than 1.0

    def test_one_measure_only_untested(self):
        """One measure only -> robustness = None with status='UNTESTED'. Never defaults to 1.0."""
        df = pd.DataFrame({
            "category": ["A", "B", "C"],
            "m1": [100.0, 50.0, 10.0],
        })
        roles = {
            "category": ColumnRole.DIMENSION,
            "m1": ColumnRole.MEASURE,
        }
        dataset = _make_dataset(df, roles)
        profile = _make_semantic_profile(roles)
        plan = _make_plan("m1")

        engine = DuckDBEngine()
        cand_res = engine.execute(plan, dataset, profile)

        rob = evaluate_robustness(
            plan=plan,
            candidate_result=cand_res,
            dataset=dataset,
            semantic_profile=profile,
            engine=engine,
        )

        assert rob.status == "UNTESTED"
        assert rob.robustness is None
        assert rob.variants_valid < 2
        assert rob.coverage_of_test == 0.0

    def test_determinism_same_input_twice(self):
        """Determinism: same input twice gives identical robustness."""
        df = pd.DataFrame({
            "category": ["A", "B", "C"],
            "m1": [100.0, 50.0, 10.0],
            "m2": [500.0, 250.0, 50.0],
            "m3": [250.0, 500.0, 50.0],
        })
        roles = {
            "category": ColumnRole.DIMENSION,
            "m1": ColumnRole.MEASURE,
            "m2": ColumnRole.MEASURE,
            "m3": ColumnRole.MEASURE,
        }
        dataset = _make_dataset(df, roles)
        profile = _make_semantic_profile(roles)
        plan = _make_plan("m1")

        engine = DuckDBEngine()
        cand_res = engine.execute(plan, dataset, profile)

        rob1 = evaluate_robustness(plan, cand_res, dataset, profile, engine=engine)
        rob2 = evaluate_robustness(plan, cand_res, dataset, profile, engine=engine)

        assert rob1.robustness == rob2.robustness
        assert rob1.coverage_of_test == rob2.coverage_of_test
        assert rob1.variant_details == rob2.variant_details

    def test_determinism_column_order_shuffled(self):
        """Determinism: column order shuffled gives the exact same robustness."""
        df_orig = pd.DataFrame({
            "category": ["A", "B", "C"],
            "m1": [100.0, 50.0, 10.0],
            "m2": [500.0, 250.0, 50.0],
            "m3": [250.0, 500.0, 50.0],
        })
        roles_orig = {
            "category": ColumnRole.DIMENSION,
            "m1": ColumnRole.MEASURE,
            "m2": ColumnRole.MEASURE,
            "m3": ColumnRole.MEASURE,
        }
        dataset_orig = _make_dataset(df_orig, roles_orig)
        profile_orig = _make_semantic_profile(roles_orig)

        # Reverse column order in dataframe and semantic profile
        df_shuffled = df_orig[["m3", "category", "m1", "m2"]]
        roles_shuffled = {
            "m3": ColumnRole.MEASURE,
            "category": ColumnRole.DIMENSION,
            "m1": ColumnRole.MEASURE,
            "m2": ColumnRole.MEASURE,
        }
        dataset_shuffled = _make_dataset(df_shuffled, roles_shuffled)
        profile_shuffled = _make_semantic_profile(roles_shuffled)

        plan = _make_plan("m1")
        engine = DuckDBEngine()

        cand_orig = engine.execute(plan, dataset_orig, profile_orig)
        cand_shuf = engine.execute(plan, dataset_shuffled, profile_shuffled)

        rob_orig = evaluate_robustness(plan, cand_orig, dataset_orig, profile_orig, engine=engine)
        rob_shuf = evaluate_robustness(plan, cand_shuf, dataset_shuffled, profile_shuffled, engine=engine)

        assert rob_orig.robustness == rob_shuf.robustness
        assert rob_orig.variant_details == rob_shuf.variant_details

    def test_spearman_rank_correlation_properties(self):
        """Verify Spearman correlation properties with ties, inversions, and constants."""
        # Perfect correlation
        assert compute_spearman_rank_correlation([1, 2, 3], [10, 20, 30]) == 1.0
        # Perfect inversion
        assert compute_spearman_rank_correlation([1, 2, 3], [30, 20, 10]) == -1.0
        # Ties
        r_tied = compute_spearman_rank_correlation([1, 2, 2, 3], [10, 20, 20, 30])
        assert r_tied == pytest.approx(1.0, abs=1e-3)
        # Constant vector has 0 variance -> returns 0.0 safely
        assert compute_spearman_rank_correlation([1, 1, 1], [10, 20, 30]) == 0.0
