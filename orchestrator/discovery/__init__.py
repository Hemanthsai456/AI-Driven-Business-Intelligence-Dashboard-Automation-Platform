"""Stage E: Insight Discovery Mode package."""

from orchestrator.discovery.schemas import (
    DiscoveredInsight,
    DiscoverySummary,
    InsightCandidate,
    InsightScore,
    InsightType,
    RejectedInsightInfo,
)
from orchestrator.discovery.candidate_generator import enumerate_candidate_insights
from orchestrator.discovery.agent_proposals import generate_agent_proposals, build_bounded_stats_summary
from orchestrator.discovery.scoring import score_and_filter_insights
from orchestrator.discovery.selector import select_diverse_dashboard_insights
from orchestrator.discovery.narration import generate_panel_narration, verify_numbers_grounded
from orchestrator.discovery.engine import (
    classify_intent_mode,
    run_discovery_pipeline,
    GENERIC_DISCOVERY_PROMPTS,
)

__all__ = [
    "InsightType",
    "InsightCandidate",
    "InsightScore",
    "DiscoveredInsight",
    "RejectedInsightInfo",
    "DiscoverySummary",
    "enumerate_candidate_insights",
    "generate_agent_proposals",
    "build_bounded_stats_summary",
    "score_and_filter_insights",
    "select_diverse_dashboard_insights",
    "generate_panel_narration",
    "verify_numbers_grounded",
    "classify_intent_mode",
    "run_discovery_pipeline",
    "GENERIC_DISCOVERY_PROMPTS",
]
