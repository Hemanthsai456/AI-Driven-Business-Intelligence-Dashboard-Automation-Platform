"""Evidence-Grounded AI Insight Engine Coordinator (Step 6).

Coordinates the full evidence-grounded insight pipeline:
1. Deterministic analytical candidate generation & DuckDB calculation (discovery.py)
2. Deterministic evidence validation (validator.py)
3. Grounded natural language narration & hallucination guard (narrator.py)
4. Full claim validation & causal check (validator.py)
5. Deduplication, scoring, and diversity selection (ranker.py)
"""

from __future__ import annotations

import time
from typing import List, Optional
from uuid import uuid4

from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import CanonicalDataset
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.insights.discovery import AnalyticalInsightDiscoverer
from orchestrator.insights.narrator import InsightNarrator
from orchestrator.insights.ranker import InsightRanker
from orchestrator.insights.schemas import (
    EvidenceGroundedInsight,
    InsightEvidence,
    InsightGenerationResult,
    InsightRejectionInfo,
    InsightType,
)
from orchestrator.insights.validator import InsightValidator
from providers.base import LLMClient


class InsightEngine:
    """End-to-end coordinator for Evidence-Grounded AI Insights."""

    def __init__(
        self,
        executor: Optional[DuckDBExecutor] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.executor = executor or DuckDBExecutor()
        self.discoverer = AnalyticalInsightDiscoverer(self.executor)
        self.validator = InsightValidator()
        self.narrator = InsightNarrator(llm_client)
        self.ranker = InsightRanker()

    def generate_insights(
        self,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        max_insights: int = 8,
        use_llm: bool = True,
    ) -> InsightGenerationResult:
        """Discover, calculate, validate, narrate, and select evidence-grounded insights."""
        start_t = time.perf_counter()
        dataset_id = dataset.metadata.dataset_id if dataset.metadata else "source_data"

        rejections: List[InsightRejectionInfo] = []
        validated_insights: List[EvidenceGroundedInsight] = []

        # 1. Discover and compute candidates
        candidates = self.discoverer.discover_candidates(dataset, semantic_profile)
        total_candidates = len(candidates)

        for itype, evidence in candidates:
            # 2. Validate evidence
            is_valid_ev, ev_reason = self.validator.validate_evidence(
                itype, evidence, dataset, semantic_profile
            )
            if not is_valid_ev:
                rejections.append(
                    InsightRejectionInfo(
                        candidate_id=str(uuid4()),
                        insight_type=itype,
                        metric=evidence.metric_column,
                        dimension=evidence.dimension_column,
                        reason=ev_reason or "Invalid evidence",
                        stage="VALIDATION",
                    )
                )
                continue

            # 3. Narrate (with grounding guard and fallback)
            title, stmt, interp = self.narrator.narrate_insight(itype, evidence, use_llm=use_llm)

            # 4. Construct insight object
            candidate_insight = EvidenceGroundedInsight(
                insight_id=str(uuid4()),
                type=itype,
                title=title,
                statement=stmt,
                interpretation=interp,
                importance=0.5,
                confidence=1.0,
                evidence=evidence,
                warnings=[],
                provenance={
                    "plan_id": evidence.query_or_plan.plan_id if evidence.query_or_plan else None,
                    "compiled_sql": evidence.compiled_sql,
                    "engine": "duckdb",
                    "row_count": evidence.row_count,
                },
            )

            # 5. Full validation check
            is_valid_full, full_reason = self.validator.validate_final_insight(
                candidate_insight, dataset, semantic_profile
            )
            if not is_valid_full:
                rejections.append(
                    InsightRejectionInfo(
                        candidate_id=candidate_insight.insight_id,
                        insight_type=itype,
                        metric=evidence.metric_column,
                        dimension=evidence.dimension_column,
                        reason=full_reason or "Failed final insight validation",
                        stage="VALIDATION",
                    )
                )
                continue

            validated_insights.append(candidate_insight)

        # 6. Rank, deduplicate, and select top diverse insights
        selected_insights = self.ranker.select_top_insights(
            validated_insights, max_insights=max_insights
        )

        elapsed = round(time.perf_counter() - start_t, 4)

        return InsightGenerationResult(
            dataset_id=dataset_id,
            insights=selected_insights,
            rejections=rejections,
            total_candidates_generated=total_candidates,
            total_candidates_executed=total_candidates,
            total_insights_validated=len(validated_insights),
            total_insights_selected=len(selected_insights),
            runtime_seconds=elapsed,
            summary_notice=f"Successfully generated {len(selected_insights)} evidence-grounded insights across {len({i.type for i in selected_insights})} distinct analytical types."
            if selected_insights else "Insufficient statistical variation or sample size to generate conclusive insights.",
        )


def generate_grounded_insights(
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    max_insights: int = 8,
    use_llm: bool = True,
    executor: Optional[DuckDBExecutor] = None,
    llm_client: Optional[LLMClient] = None,
) -> InsightGenerationResult:
    """Convenience helper to discover and return evidence-grounded insights."""
    engine = InsightEngine(executor=executor, llm_client=llm_client)
    return engine.generate_insights(
        dataset=dataset,
        semantic_profile=semantic_profile,
        max_insights=max_insights,
        use_llm=use_llm,
    )
