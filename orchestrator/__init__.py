"""Orchestrator package for AI-driven dashboard query planning and execution.

This package provides schemas, configuration, and logic for the K-way
parallel orchestrator that translates natural-language analytical requests
into DuckDB query plans, validates them, ranks results, and produces
DashboardSpec outputs.
"""

from orchestrator.compiler import (
    QueryCompilationError,
    compile_plan_to_sql,
    format_sql_literal,
    quote_identifier,
)
from orchestrator.executor import (
    DuckDBExecutor,
    default_executor,
    execute_plan,
)
from orchestrator.schemas import (
    AggregationType,
    CandidateConsistencyCheck,
    CandidatePlan,
    DashboardSpec,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    FilterSpec,
    Granularity,
    MetricSpec,
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
    # Schemas
    "AggregationType",
    "Granularity",
    "VisualizationType",
    "ValidationStatus",
    "ExecutionStatus",
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
    # Utils
    "compute_score",
    "rank_candidates",
    "check_candidate_output_consistency",
]
