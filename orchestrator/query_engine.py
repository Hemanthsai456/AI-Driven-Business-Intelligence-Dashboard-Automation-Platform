"""Generalized Natural Language to SQL Analytical Query Engine.

Derives analytical meaning from the actual runtime dataset context, semantic roles,
aggregation categories, and profiles. Converts natural language queries to structured
analytical plans, validates with Pass 1a, compiles to safe DuckDB SQL via compiler.py,
executes in isolated in-memory DuckDB, validates with Pass 1b, and returns execution
results with complete SQL provenance and semantic evidence.

Architecture:
User Question
      ↓
Natural Language Interpretation (orchestrator.intent)
      ↓
Active Ambiguity Gate (orchestrator.ambiguity)
      ↓
Discrete Semantic Interpretation (orchestrator.interpretation)
      ↓
Structured CandidatePlan (orchestrator.schemas)
      ↓
Pre-Dispatch Validation Pass 1a (orchestrator.validator)
      ↓
Authoritative SQL Compiler (engine.compiler)
      ↓
Sandboxed In-Memory DuckDB (engine.duckdb_executor)
      ↓
Post-Execution Validation Pass 1b (orchestrator.validator)
      ↓
AnalyticalQueryResult (Result + SQL + Evidence + Provenance)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from engine.compiler import compile_plan_to_sql
from engine.duckdb_executor import DuckDBExecutor
from ingestion.models import CanonicalDataset
from intelligence.schema_validator import AnalysisReadiness, ReadinessCheck, ReadinessStatus
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.ambiguity import AmbiguityResult, assess_ambiguity, is_blocking_ambiguity
from orchestrator.intent import interpret_user_request
from orchestrator.interpretation import generate_interpretations
from orchestrator.schemas import (
    AggregationType,
    AmbiguityStatus,
    AnalyticalQueryResult,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    ExecutionStatus,
    FilterSpec,
    Granularity,
    MetricSpec,
    Pass1aResult,
    Pass1bResult,
    PlanReasoning,
    StructuredIntent,
    ValidationIssue,
    ValidationStatus,
    VisualizationType,
)
from orchestrator.validator import validate_pass1a, validate_pass1b


class AnalyticalQueryEngine:
    """Domain-agnostic analytical query engine executing natural language requests."""

    def __init__(self, executor: Optional[DuckDBExecutor] = None) -> None:
        self.executor = executor or DuckDBExecutor()

    def execute_query(
        self,
        question: str,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        readiness: Optional[AnalysisReadiness] = None,
        row_limit: Optional[int] = None,
    ) -> AnalyticalQueryResult:
        """Execute a natural-language query against a dataset and semantic profile.

        Args:
            question: Natural language analytical query.
            dataset: CanonicalDataset containing the data.
            semantic_profile: Runtime DatasetSemanticProfile (authoritative semantic roles & aggregation categories).
            readiness: Optional AnalysisReadiness assessment.
            row_limit: Optional explicit row limit.

        Returns:
            AnalyticalQueryResult containing plan, compiled SQL, DuckDB rows, validation status, and evidence.
        """
        start_time = time.perf_counter()
        q_clean = (question or "").strip()

        if not q_clean:
            return AnalyticalQueryResult(
                question="",
                ambiguity_status=AmbiguityStatus.UNANSWERABLE,
                validation_status="FAILED",
                validation_issues=[
                    ValidationIssue(
                        check="non_empty_question",
                        status=ValidationStatus.FAILED,
                        message="Query question is empty.",
                    )
                ],
                error_message="Analytical query is empty.",
            )

        # 1. Natural language intent interpretation
        structured = interpret_user_request(q_clean, semantic_profile)

        # 2. Active Ambiguity Gate
        ambiguity = assess_ambiguity(structured, semantic_profile)
        if is_blocking_ambiguity(ambiguity):
            elapsed = time.perf_counter() - start_time
            return AnalyticalQueryResult(
                question=q_clean,
                structured_intent=structured,
                ambiguity_status=ambiguity.status,
                ambiguity_details=ambiguity.ambiguities,
                validation_status="FAILED",
                confidence=structured.confidence,
                runtime_seconds=round(elapsed, 4),
                error_message=ambiguity.message or "Request is ambiguous or unanswerable without clarification.",
            )

        # 3. Discrete Semantic Interpretation Generation
        interpretations = generate_interpretations(
            structured,
            semantic_profile,
            ambiguity=ambiguity,
            k=1,
        )

        if not interpretations:
            elapsed = time.perf_counter() - start_time
            return AnalyticalQueryResult(
                question=q_clean,
                structured_intent=structured,
                ambiguity_status=AmbiguityStatus.UNANSWERABLE,
                validation_status="FAILED",
                confidence=0.0,
                runtime_seconds=round(elapsed, 4),
                error_message="Could not generate a valid semantic interpretation for this request.",
            )

        interp = interpretations[0]

        # 4. Construct Structured CandidatePlan
        dims: List[DimensionSpec] = []
        for d in interp.dimension_columns:
            ev_d = semantic_profile.get_evidence(d)
            gran = interp.granularity if (ev_d and ev_d.candidate_role == ColumnRole.DATETIME) else None
            dims.append(DimensionSpec(column=d, granularity=gran))

        metric_col = interp.metric_column
        metric_agg = interp.aggregation

        plan = CandidatePlan(
            plan_id=str(uuid4()),
            dataset_id=dataset.metadata.dataset_id,
            intent=q_clean,
            metric=MetricSpec(column=metric_col, aggregation=metric_agg),
            dimensions=dims,
            filters=interp.filter_specs,
            order_by=interp.order_by,
            order_direction=interp.order_direction,
            limit=interp.limit,
            visualization=interp.visualization,
            generator="analytical_query_engine",
            provider="deterministic_engine",
            reasoning=PlanReasoning(
                interpretation=interp.intent_summary,
                evidence=interp.evidence,
            ),
        )

        # 5. Pre-Dispatch Validation (Pass 1a)
        effective_readiness = readiness or AnalysisReadiness(
            dataset_id=dataset.metadata.dataset_id,
            status=ReadinessStatus.READY,
            checks=[ReadinessCheck(check_name="ok", passed=True, message="Dataset ready", is_blocking=True)],
        )
        pass1a = validate_pass1a(plan, semantic_profile, readiness=effective_readiness)
        if not pass1a.passed:
            elapsed = time.perf_counter() - start_time
            return AnalyticalQueryResult(
                question=q_clean,
                plan=plan,
                structured_intent=structured,
                validation_status="FAILED",
                validation_issues=pass1a.issues,
                ambiguity_status=ambiguity.status,
                ambiguity_details=ambiguity.ambiguities,
                confidence=structured.confidence,
                evidence=interp.evidence,
                runtime_seconds=round(elapsed, 4),
                error_message="Pass 1a pre-dispatch validation failed.",
            )

        # 6. Authoritative SQL Compilation
        try:
            compiled_sql = compile_plan_to_sql(plan, source_view="source_data", row_limit=row_limit)
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            return AnalyticalQueryResult(
                question=q_clean,
                plan=plan,
                structured_intent=structured,
                validation_status="FAILED",
                validation_issues=[
                    ValidationIssue(
                        check="sql_compilation",
                        status=ValidationStatus.FAILED,
                        message=f"SQL compilation error: {str(e)}",
                    )
                ],
                ambiguity_status=ambiguity.status,
                confidence=structured.confidence,
                evidence=interp.evidence,
                runtime_seconds=round(elapsed, 4),
                error_message=f"SQL compilation error: {str(e)}",
            )

        # 7. Sandboxed DuckDB Execution
        exec_result = self.executor.execute_plan(
            plan=plan,
            dataset=dataset,
            semantic_profile=semantic_profile,
            custom_sql=compiled_sql,
        )

        # 8. Post-Execution Validation (Pass 1b)
        pass1b = validate_pass1b(plan, exec_result)
        combined_issues = pass1a.issues + pass1b.issues

        status_val = "PASSED"
        if not pass1b.passed:
            status_val = "FAILED"
        elif any(i.status == ValidationStatus.WARNING for i in combined_issues):
            status_val = "WARNING"

        elapsed = time.perf_counter() - start_time

        return AnalyticalQueryResult(
            question=q_clean,
            plan=plan,
            structured_intent=structured,
            compiled_sql=compiled_sql,
            rows=exec_result.rows,
            columns=exec_result.columns,
            row_count=exec_result.row_count,
            validation_status=status_val,
            validation_issues=combined_issues,
            ambiguity_status=ambiguity.status,
            ambiguity_details=ambiguity.ambiguities,
            confidence=structured.confidence,
            evidence=interp.evidence,
            runtime_seconds=round(elapsed, 4),
            error_message=exec_result.error_message if exec_result.status != ExecutionStatus.SUCCESS else None,
        )


default_query_engine = AnalyticalQueryEngine()


def execute_analytical_query(
    question: str,
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    readiness: Optional[AnalysisReadiness] = None,
    row_limit: Optional[int] = None,
) -> AnalyticalQueryResult:
    """Convenience function to execute a natural-language analytical query."""
    return default_query_engine.execute_query(
        question=question,
        dataset=dataset,
        semantic_profile=semantic_profile,
        readiness=readiness,
        row_limit=row_limit,
    )
