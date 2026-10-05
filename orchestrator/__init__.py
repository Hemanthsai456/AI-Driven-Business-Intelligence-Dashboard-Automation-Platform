"""Orchestrator package for AI-driven dashboard query planning and execution.

This package provides schemas, configuration, and cognitive coordination for the
6-step cognitive loop that interprets user requests, gates ambiguity, generates
interpretations, plans K-way candidates, coordinates deterministic engine execution,
ranks candidates, and produces DashboardSpec outputs.
"""

from orchestrator.ambiguity import (
    assess_ambiguity,
    is_blocking_ambiguity,
)
from orchestrator.compiler import (
    QueryCompilationError,
    compile_plan_to_sql,
    format_sql_literal,
    quote_identifier,
)
from orchestrator.context_builder import (
    build_llm_context,
    sanitize_text,
)
from orchestrator.executor import (
    AnalyticsEngine,
    DuckDBEngine,
    DuckDBExecutor,
    default_executor,
    execute_plan,
    get_default_engine,
)
from orchestrator.generator import (
    ExternalAgentGenerator,
    MultiProviderGenerator,
    PlanGenerationCoordinator,
    PlanGenerator,
)
from orchestrator.intent import (
    interpret_user_request,
)
from orchestrator.interpretation import (
    generate_interpretations,
)
from orchestrator.llm import (
    GeminiClient,
    GroqClient,
    LLMClient,
    LLMClientError,
    LLMProviderFactory,
    MockLLMClient,
    OllamaClient,
    get_llm_client,
    get_multi_provider_clients,
)
from orchestrator.insights import (
    AnalyticalInsightDiscoverer,
    EvidenceGroundedInsight,
    InsightEngine,
    InsightEvidence,
    InsightGenerationResult,
    InsightNarrator,
    InsightRanker,
    InsightRejectionInfo,
    InsightType,
    InsightValidator,
    generate_grounded_insights,
)
from orchestrator.query_engine import (
    AnalyticalQueryEngine,
    default_query_engine,
    execute_analytical_query,
)
from orchestrator.schemas import (
    AggregationType,
    AmbiguityDetail,
    AmbiguityResult,
    AmbiguityStatus,
    AmbiguityType,
    AnalyticalQueryResult,
    CandidateConsistencyCheck,
    CandidatePlan,
    DashboardSpec,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    FilterSpec,
    GeneratorCallLog,
    Granularity,
    LLMContext,
    MetricSpec,
    OrchestratorTrace,
    Pass1aResult,
    Pass1bResult,
    Pass2Result,
    PassResult,
    RankedCandidate,
    RankerWeights,
    ScoreBreakdown,
    SemanticInterpretation,
    StructuredIntent,
    ValidationIssue,
    ValidationStatus,
    VisualizationType,
    PanelType,
    DashboardPanel,
)
from orchestrator.panels import (
    build_dashboard_panels,
    generate_headline_insight,
    select_main_chart_panel,
    build_robustness_heatmap_panel,
    build_alternates_panel,
    build_table_panel,
)
from orchestrator.utils import (
    check_candidate_output_consistency,
    compute_score,
    rank_candidates,
)
from orchestrator.robustness import (
    RobustnessEvaluation,
    evaluate_robustness,
    generate_perturbations,
)
from orchestrator.validator import (
    validate_pass1a,
    validate_pass1b,
    validate_pass2,
)
from orchestrator.winner import (
    WinnerSelectionError,
    select_winner,
)
from orchestrator.logger import (
    emit_decision_log,
    emit_explainability_log,
    save_candidate_artifact,
)
from orchestrator.pipeline import (
    OrchestrationPipelineResult,
    run_orchestration_pipeline,
)
from orchestrator.run_store import (
    PlanNotFoundError,
    RunExpiredError,
    RunNotFoundError,
    RunResolveError,
    RunStore,
    StoredRun,
    default_run_store,
    resolve_pipeline_run,
)

__all__ = [
    # Cognitive Loop
    "interpret_user_request",
    "assess_ambiguity",
    "is_blocking_ambiguity",
    "generate_interpretations",
    "StructuredIntent",
    "SemanticInterpretation",
    # Analytical Query Engine
    "AnalyticalQueryEngine",
    "default_query_engine",
    "execute_analytical_query",
    "AnalyticalQueryResult",
    # Compiler
    "compile_plan_to_sql",
    "quote_identifier",
    "format_sql_literal",
    "QueryCompilationError",
    # Executor / Engine
    "AnalyticsEngine",
    "DuckDBEngine",
    "DuckDBExecutor",
    "default_executor",
    "execute_plan",
    "get_default_engine",
    # Context
    "build_llm_context",
    "sanitize_text",
    # Generators
    "PlanGenerator",
    "MultiProviderGenerator",
    "ExternalAgentGenerator",
    "PlanGenerationCoordinator",
    # LLM
    "LLMClient",
    "LLMClientError",
    "LLMProviderFactory",
    "get_llm_client",
    "get_multi_provider_clients",
    "GeminiClient",
    "GroqClient",
    "OllamaClient",
    "MockLLMClient",
    # Schemas
    "AggregationType",
    "Granularity",
    "VisualizationType",
    "AmbiguityStatus",
    "AmbiguityType",
    "ValidationStatus",
    "ExecutionStatus",
    "MetricSpec",
    "DimensionSpec",
    "FilterSpec",
    "CandidatePlan",
    "AmbiguityDetail",
    "AmbiguityResult",
    "LLMContext",
    "ExecutionResult",
    "Pass1aResult",
    "Pass1bResult",
    "Pass2Result",
    "PassResult",
    "ValidationIssue",
    "RankerWeights",
    "ScoreBreakdown",
    "RankedCandidate",
    "CandidateConsistencyCheck",
    "OrchestratorTrace",
    "DashboardSpec",
    "PanelType",
    "DashboardPanel",
    "build_dashboard_panels",
    "generate_headline_insight",
    "select_main_chart_panel",
    "build_robustness_heatmap_panel",
    "build_alternates_panel",
    "build_table_panel",
    "GeneratorCallLog",
    # Validation & Ranking
    "validate_pass1a",
    "validate_pass1b",
    "validate_pass2",
    "check_candidate_output_consistency",
    "rank_candidates",
    "compute_score",
    "RobustnessEvaluation",
    "evaluate_robustness",
    "generate_perturbations",
    "select_winner",
    "WinnerSelectionError",
    # Logging & Pipeline
    "save_candidate_artifact",
    "emit_decision_log",
    "emit_explainability_log",
    "run_orchestration_pipeline",
    "OrchestrationPipelineResult",
    "resolve_pipeline_run",
    "RunStore",
    "StoredRun",
    "RunResolveError",
    "RunNotFoundError",
    "RunExpiredError",
    "PlanNotFoundError",
    "default_run_store",
    # Step 6: Evidence-Grounded AI Insights
    "InsightType",
    "InsightEvidence",
    "EvidenceGroundedInsight",
    "InsightRejectionInfo",
    "InsightGenerationResult",
    "AnalyticalInsightDiscoverer",
    "InsightValidator",
    "InsightNarrator",
    "InsightRanker",
    "InsightEngine",
    "generate_grounded_insights",
]
