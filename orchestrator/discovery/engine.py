"""Discovery Engine Coordinator for Stage E.

Integrates the 7 steps:
E1: Deterministic candidate enumeration
E2: Agent proposals via bounded stats summary
E3: Execution & Pass 1 validation via compiler & DuckDB executor
E4: Scoring (strength, robustness, Benjamini-Hochberg FDR control, data quality)
E5: Diversity-aware dashboard selection & layout
E6: Narration & number grounding guard
E7: Panel building & DashboardSpec extension
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
import pandas as pd

from engine.executor import AnalyticsEngine, get_default_engine
from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.profiler import DataProfile
from intelligence.schema_validator import AnalysisReadiness, ReadinessStatus
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.discovery.agent_proposals import generate_agent_proposals
from orchestrator.discovery.candidate_generator import enumerate_candidate_insights
from orchestrator.discovery.narration import generate_panel_narration
from orchestrator.discovery.scoring import score_and_filter_insights
from orchestrator.discovery.schemas import (
    DiscoveredInsight,
    DiscoverySummary,
    InsightCandidate,
    InsightType,
)
from orchestrator.discovery.selector import select_diverse_dashboard_insights
from orchestrator.panels import (
    build_table_panel,
    select_main_chart_panel,
)
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DashboardPanel,
    DashboardSpec,
    ExecutionResult,
    ExecutionStatus,
    MetricSpec,
    OrchestratorTrace,
    PanelType,
    Pass1aResult,
    Pass1bResult,
    PlanReasoning,
    RankedCandidate,
    ScoreBreakdown,
    VisualizationType,
)
from orchestrator.validator import validate_pass1a, validate_pass1b
from providers.base import LLMClient


GENERIC_DISCOVERY_PROMPTS: Set[str] = {
    "",
    "dashboard on this data",
    "dashboard",
    "create dashboard",
    "generate dashboard",
    "build dashboard",
    "explore data",
    "explore this data",
    "analyze data",
    "analyze this data",
    "insights",
    "show insights",
    "discover insights",
    "auto dashboard",
    "give me a dashboard",
    "create a dashboard on this data",
    "generate a dashboard on this data",
    "build a dashboard on this data",
    "overview",
    "data overview",
}


def classify_intent_mode(
    intent: Optional[str],
    semantic_profile: DatasetSemanticProfile,
) -> Tuple[str, Optional[str]]:
    """Determine whether a brief triggers DISCOVERY mode or FOCUSED mode.

    Returns:
        (mode, topic) where mode is "discovery" or "focused"
    """
    if not intent or intent.strip() == "":
        return "discovery", None

    cleaned = intent.strip().lower()
    cleaned_no_punct = re.sub(r"[^\w\s]", "", cleaned)

    if cleaned in GENERIC_DISCOVERY_PROMPTS or cleaned_no_punct in GENERIC_DISCOVERY_PROMPTS:
        return "discovery", None

    # Check for generic patterns
    generic_prefixes = (
        "dashboard on",
        "dashboard for",
        "explore",
        "overview of",
        "insights on",
        "insights for",
        "analyze",
    )

    tokens = cleaned_no_punct.split()
    # Check if brief is very short (1-2 words) naming only a measure/topic
    # e.g. "sales", "revenue", "orders", "customers"
    known_cols = {col.lower(): col for col in semantic_profile.column_evidences.keys()}

    if len(tokens) <= 2:
        for t in tokens:
            if t in known_cols:
                return "discovery", t
        if "dashboard" in tokens or "insights" in tokens:
            return "discovery", None

    # If it starts with a generic exploration prefix and doesn't specify concrete grouping operations
    specific_keywords = {"by", "group by", "top", "bottom", "highest", "lowest", "filter", "where", "compare to"}
    has_specific = any(sk in cleaned for sk in specific_keywords)

    for prefix in generic_prefixes:
        if cleaned.startswith(prefix) and not has_specific:
            topic_candidate = cleaned[len(prefix) :].strip()
            return "discovery", topic_candidate if topic_candidate else None

    return "focused", None


def run_discovery_pipeline(
    *,
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    readiness: AnalysisReadiness,
    intent: Optional[str] = None,
    data_profile: Optional[DataProfile] = None,
    engine: Optional[AnalyticsEngine] = None,
    llm_client: Optional[LLMClient] = None,
    include_agent_proposals: bool = True,
    fdr_alpha: float = 0.05,
    strength_floor: float = 0.08,
    robustness_floor: float = 0.35,
    quality_floor: float = 0.40,
    cap_per_type: int = 8,
    topic: Optional[str] = None,
) -> Tuple[DashboardSpec, List[Dict[str, Any]], DiscoverySummary]:
    """Execute Stage E Insight Discovery Mode.

    Returns:
        (dashboard_spec, rejected_candidates_list, discovery_summary)
    """
    exec_engine = engine or get_default_engine()
    dataset_id = dataset.metadata.dataset_id or "dataset"
    all_rejected: List[Dict[str, Any]] = []

    # E1: Deterministic Candidate Insight Enumeration
    enumerated_candidates = enumerate_candidate_insights(
        dataset=dataset,
        semantic_profile=semantic_profile,
        data_profile=data_profile,
        cap_per_type=cap_per_type,
    )

    # E2: Agent Proposals
    if include_agent_proposals:
        agent_candidates = generate_agent_proposals(
            dataset=dataset,
            semantic_profile=semantic_profile,
            llm_client=llm_client,
            brief=intent,
        )
    else:
        agent_candidates = []

    # Combine candidates (deduplicate by structural signature)
    seen_sigs: Set[str] = set()
    combined_candidates: List[InsightCandidate] = []

    for cand in enumerated_candidates + agent_candidates:
        sig = (
            cand.insight_type.value,
            cand.measure,
            cand.dimension or "",
            cand.secondary_measure or "",
            cand.aggregation.value,
        )
        sig_str = "|".join(sig)
        if sig_str not in seen_sigs:
            seen_sigs.add(sig_str)
            combined_candidates.append(cand)

    # E3: Execute and Validate Candidates through existing compiler, executor, and Pass 1
    executed_candidates: List[Tuple[InsightCandidate, ExecutionResult]] = []

    for cand in combined_candidates:
        desc = (
            f"{cand.insight_type.value}: {cand.aggregation.value}({cand.measure})"
            + (f" by {cand.dimension}" if cand.dimension else "")
            + (f" & {cand.secondary_measure}" if cand.secondary_measure else "")
        )

        # Pass 1a: Pre-dispatch validation
        pass1a_res = validate_pass1a(
            plan=cand.plan,
            semantic_profile=semantic_profile,
            readiness=readiness,
        )
        if not pass1a_res.passed:
            all_rejected.append({
                "candidate_id": cand.candidate_id,
                "insight_type": cand.insight_type.value,
                "description": desc,
                "measure": cand.measure,
                "dimension": cand.dimension,
                "rejection_stage": "PASS1A",
                "reason": f"Pass 1a failure: {'; '.join(i.message for i in pass1a_res.issues)}",
            })
            continue

        # Deterministic execution
        exec_res = exec_engine.execute(
            plan=cand.plan,
            dataset=dataset,
            semantic_profile=semantic_profile,
        )
        if exec_res.status != ExecutionStatus.SUCCESS:
            all_rejected.append({
                "candidate_id": cand.candidate_id,
                "insight_type": cand.insight_type.value,
                "description": desc,
                "measure": cand.measure,
                "dimension": cand.dimension,
                "rejection_stage": "EXECUTION",
                "reason": f"Execution failed: {exec_res.error_message or 'Unknown error'}",
            })
            continue

        # Pass 1b: Post-execution validation
        pass1b_res = validate_pass1b(
            plan=cand.plan,
            exec_result=exec_res,
        )
        if not pass1b_res.passed:
            all_rejected.append({
                "candidate_id": cand.candidate_id,
                "insight_type": cand.insight_type.value,
                "description": desc,
                "measure": cand.measure,
                "dimension": cand.dimension,
                "rejection_stage": "PASS1B",
                "reason": f"Pass 1b failure: {'; '.join(i.message for i in pass1b_res.issues)}",
            })
            continue

        executed_candidates.append((cand, exec_res))

    # E4: Score each insight (strength, robustness, FDR multiple-testing control, quality)
    passed_scored_insights, scoring_rejected = score_and_filter_insights(
        candidate_tuples=executed_candidates,
        dataset=dataset,
        fdr_alpha=fdr_alpha,
        strength_floor=strength_floor,
        robustness_floor=robustness_floor,
        quality_floor=quality_floor,
    )
    all_rejected.extend(scoring_rejected)

    # E5: Dashboard Selection (Greedy diversity-aware selection)
    selected_insights, selection_rejected, selection_notice = select_diverse_dashboard_insights(
        passed_insights=passed_scored_insights,
        topic=topic,
        max_total=8,
        max_per_measure=2,
        max_per_dimension=2,
    )
    all_rejected.extend(selection_rejected)

    # E6: Narration & Hallucination Guard
    narrated_insights: List[DiscoveredInsight] = []
    for item in selected_insights:
        verified_sentence, why_chosen = generate_panel_narration(item)
        narrated_insights.append(
            DiscoveredInsight(
                candidate=item.candidate,
                execution_result=item.execution_result,
                score=item.score,
                narration=verified_sentence,
                why_chosen=why_chosen,
                rank=item.rank,
            )
        )

    # E7: Assemble into DashboardSpec
    dashboard_panels: List[DashboardPanel] = []

    # If < 3 insights pass, create notice panel and set spec headline
    data_supports_more = len(narrated_insights) >= 3
    if not data_supports_more:
        dashboard_panels.append(
            DashboardPanel(
                panel_id=str(uuid4()),
                panel_type=PanelType.INSIGHT,
                title="Data Quality & Significance Notice",
                description="The data doesn't support more insights (fewer than 3 candidates passed statistical significance and quality floors).",
                data=[{"notice": "The data doesn't support more"}],
                metadata={"status": "LOW_INSIGHT_COUNT", "eligible_count": len(narrated_insights)},
            )
        )

    # Build visual panels for selected insights
    for ins in narrated_insights:
        cand = ins.candidate
        res = ins.execution_result
        score = ins.score

        # Use existing select_main_chart_panel for consistency
        panel = select_main_chart_panel(
            plan=cand.plan,
            result=res,
            semantic_profile=semantic_profile,
        )

        # Extend panel metadata with Stage E narration, effect size, robustness, and why_chosen
        meta = dict(panel.metadata)
        meta.update({
            "insight_type": cand.insight_type.value,
            "strength": score.strength,
            "robustness": score.robustness,
            "p_value": score.p_value,
            "fdr_passed": score.fdr_passed,
            "quality": score.quality,
            "score": score.total_score,
            "narration": ins.narration,
            "why_chosen": ins.why_chosen,
            "rank": ins.rank,
        })

        panel_desc = ins.narration or panel.description
        enriched_panel = DashboardPanel(
            panel_id=panel.panel_id,
            panel_type=panel.panel_type,
            title=panel.title,
            description=panel_desc,
            data=panel.data,
            x_key=panel.x_key,
            y_keys=panel.y_keys,
            metadata=meta,
        )
        dashboard_panels.append(enriched_panel)

    # Include raw data table panel if insights exist
    if narrated_insights:
        top_ins = narrated_insights[0]
        table_panel = build_table_panel(
            plan=top_ins.candidate.plan,
            result=top_ins.execution_result,
        )
        dashboard_panels.append(table_panel)

    # Determine Winner
    if narrated_insights:
        winner_insight = narrated_insights[0]
        winner_score_breakdown = ScoreBreakdown(
            evidence=round(winner_insight.score.quality, 3),
            coverage=1.0,
            stability=round(winner_insight.score.robustness, 3),
            assumptions=0.0,
            agreement=1.0,
            total=round(winner_insight.score.total_score, 4),
            stability_status="TESTED",
        )
        winner_ranked = RankedCandidate(
            plan=winner_insight.candidate.plan,
            execution_result=winner_insight.execution_result,
            pass1a=Pass1aResult(plan_id=winner_insight.candidate.plan.plan_id, passed=True),
            pass1b=Pass1bResult(plan_id=winner_insight.candidate.plan.plan_id, passed=True),
            score_breakdown=winner_score_breakdown,
            rank=1,
            is_winner=True,
        )
        headline = winner_insight.narration or f"Discovered {winner_insight.candidate.insight_type.value} on {winner_insight.candidate.measure}"
    else:
        # Fallback dummy plan if 0 insights passed
        first_col = list(dataset.data.columns)[0] if len(dataset.data.columns) > 0 else "col"
        from orchestrator.schemas import MetricSpec
        dummy_plan = CandidatePlan(
            dataset_id=dataset_id,
            intent=intent or "Discovery",
            metric=MetricSpec(column=first_col, aggregation=AggregationType.COUNT),
            dimensions=[],
            reasoning=PlanReasoning(interpretation="No significant insights passed thresholds", evidence=[]),
        )
        dummy_res = ExecutionResult(plan_id=dummy_plan.plan_id, status=ExecutionStatus.SUCCESS)
        winner_ranked = RankedCandidate(
            plan=dummy_plan,
            execution_result=dummy_res,
            pass1a=Pass1aResult(plan_id=dummy_plan.plan_id, passed=True),
            pass1b=Pass1bResult(plan_id=dummy_plan.plan_id, passed=True),
            score_breakdown=ScoreBreakdown(
            evidence=0.0,
            coverage=0.0,
            stability=0.0,
            assumptions=0.0,
            agreement=0.0,
            total=0.0,
            stability_status="UNTESTED",
        ),
            rank=1,
            is_winner=True,
        )
        headline = "The data doesn't support more insights."

    trace = OrchestratorTrace(
        dataset_id=dataset_id,
        intent=intent or "Discovery Mode",
        context_hash="discovery",
        plans_generated=len(combined_candidates),
        plans_passed_pass1a=len(executed_candidates),
        plans_passed_pass1b=len(executed_candidates),
        candidate_records=[
            {
                "candidate_id": ins.candidate.candidate_id,
                "insight_type": ins.candidate.insight_type.value,
                "measure": ins.candidate.measure,
                "dimension": ins.candidate.dimension,
                "score": ins.score.total_score,
                "strength": ins.score.strength,
                "robustness": ins.score.robustness,
                "p_value": ins.score.p_value,
                "rank": ins.rank,
            }
            for ins in narrated_insights
        ],
    )

    from orchestrator.discovery.tiles import build_dashboard_tiles, build_slicer_definitions

    dashboard_tiles = build_dashboard_tiles(
        discovered_insights=narrated_insights,
        winner_ranked=winner_ranked,
        dataset=dataset,
        semantic_profile=semantic_profile,
    )
    slicer_defs = build_slicer_definitions(
        dataset=dataset,
        semantic_profile=semantic_profile,
    )

    enum_proposed = len([c for c in combined_candidates if c.proposed_by == "enumerator"])
    agent_proposed = len([c for c in combined_candidates if c.proposed_by != "enumerator"])
    fdr_passed_count = len(passed_scored_insights)
    enum_fdr_passed = len([ins for ins in passed_scored_insights if ins.candidate.proposed_by == "enumerator"])
    agent_fdr_passed = len([ins for ins in passed_scored_insights if ins.candidate.proposed_by != "enumerator"])
    enum_selected = len([ins for ins in narrated_insights if ins.candidate.proposed_by == "enumerator"])
    agent_selected = len([ins for ins in narrated_insights if ins.candidate.proposed_by != "enumerator"])

    spec = DashboardSpec(
        dataset_id=dataset_id,
        intent=intent or "Discovery Mode",
        headline=headline,
        winner=winner_ranked,
        panels=dashboard_panels,
        tiles=dashboard_tiles,
        slicers=slicer_defs,
        trace=trace,
        mode="discovery",
        rejected_insights=all_rejected,
        discovery_summary={
            "candidates_generated": len(combined_candidates),
            "candidates_executed": len(executed_candidates),
            "candidates_rejected": len(all_rejected),
            "candidates_selected": len(narrated_insights),
            "enumerator_proposed": enum_proposed,
            "agent_proposed": agent_proposed,
            "candidates_fdr_passed": fdr_passed_count,
            "enumerator_fdr_passed": enum_fdr_passed,
            "agent_fdr_passed": agent_fdr_passed,
            "enumerator_selected": enum_selected,
            "agent_selected": agent_selected,
            "fdr_alpha": fdr_alpha,
            "notice": selection_notice,
        },
    )

    summary = DiscoverySummary(
        dataset_id=dataset_id,
        candidates_generated=len(combined_candidates),
        candidates_executed=len(executed_candidates),
        candidates_rejected=len(all_rejected),
        candidates_selected=len(narrated_insights),
        enumerator_proposed=enum_proposed,
        agent_proposed=agent_proposed,
        candidates_fdr_passed=fdr_passed_count,
        enumerator_fdr_passed=enum_fdr_passed,
        agent_fdr_passed=agent_fdr_passed,
        enumerator_selected=enum_selected,
        agent_selected=agent_selected,
        fdr_alpha=fdr_alpha,
        strength_floor=strength_floor,
        robustness_floor=robustness_floor,
        quality_floor=quality_floor,
        data_supports_insights=data_supports_more,
        notice=selection_notice,
    )

    return spec, all_rejected, summary
