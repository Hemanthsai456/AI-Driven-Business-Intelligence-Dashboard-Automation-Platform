"""Orchestrator package for AI-driven dashboard query planning and execution.

This package provides schemas, configuration, and logic for the K-way
parallel orchestrator that translates natural-language analytical requests
into DuckDB query plans, validates them, ranks results, and produces
DashboardSpec outputs.
"""

from orchestrator.ambiguity import (
    assess_ambiguity,
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
    DuckDBExecutor,
    default_executor,
    execute_plan,
)
from orchestrator.generator import (
    ExternalAgentGenerator,
    LLMDirectGenerator,
    MockAgent,
    PlanGenerationCoordinator,
    PlanGenerator,
)
from orchestrator.llm import (
    GeminiClient,
    LLMClient,
    LLMClientError,
    MockLLMClient,
)
from orchestrator.schemas import (
    AggregationType,
    AmbiguityDetail,
    AmbiguityResult,
    AmbiguityStatus,
    AmbiguityType,
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
    RankedCandidate,
    RankerWeights,
    ScoreBreakdown,
    ValidationIssue,
    ValidationStatus,
    VisualizationType,
)
from orchestrator.utils import (
    check_candidate_output_consistency,
    compute_score,
    rank_candidates,
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

__all__ = [
    # Compiler
    "compile_plan_to_sql",
    "quote_identifier",
    "format_sql_literal",
    "QueryCompilationError",
    # Executor
    "DuckDBExecutor",
    "default_executor",
    "execute_plan",
    # Validator
    "validate_pass1a",
    "validate_pass1b",
    "validate_pass2",
    # Winner Selection
    "select_winner",
    "WinnerSelectionError",
    # Ambiguity
    "assess_ambiguity",
    # Context Builder
    "build_llm_context",
    "sanitize_text",
    # LLM Clients
    "LLMClient",
    "GeminiClient",
    "MockLLMClient",
    "LLMClientError",
    # Plan Generators
    "PlanGenerator",
    "LLMDirectGenerator",
    "ExternalAgentGenerator",
    "MockAgent",
    "PlanGenerationCoordinator",
    # Schemas
    "AggregationType",
    "Granularity",
    "VisualizationType",
    "ValidationStatus",
    "ExecutionStatus",
    "AmbiguityStatus",
    "AmbiguityType",
    "MetricSpec",
    "DimensionSpec",
    "FilterSpec",
    "CandidatePlan",
    "ExecutionResult",
    "ValidationIssue",
    "Pass1aResult",
    "Pass1bResult",
    "Pass2Result",
    "RankedCandidate",
    "DashboardSpec",
    "CandidateConsistencyCheck",
    "ScoreBreakdown",
    "RankerWeights",
    "LLMContext",
    "AmbiguityResult",
    "AmbiguityDetail",
    "GeneratorCallLog",
    "OrchestratorTrace",
    # Utils
    "compute_score",
    "rank_candidates",
    "check_candidate_output_consistency",
]
