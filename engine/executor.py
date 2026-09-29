"""Analytics engine interface and concrete DuckDB implementation.

Decouples the cognitive orchestrator from the underlying execution infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ingestion.models import CanonicalDataset
from intelligence.semantic_analyzer import DatasetSemanticProfile
from engine.duckdb_executor import DuckDBExecutor, default_executor

if TYPE_CHECKING:
    from orchestrator.schemas import CandidatePlan, ExecutionResult



class AnalyticsEngine(ABC):
    """Abstract interface for deterministic analytical query execution engines."""

    @abstractmethod
    def execute(
        self,
        plan: CandidatePlan,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        custom_sql: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an analytical plan against a dataset and return structured results."""
        pass


class DuckDBEngine(AnalyticsEngine):
    """AnalyticsEngine implementation backed by isolated DuckDB in-memory workers."""

    def __init__(self, executor: Optional[DuckDBExecutor] = None):
        self._executor = executor or default_executor

    def execute(
        self,
        plan: CandidatePlan,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        custom_sql: Optional[str] = None,
    ) -> ExecutionResult:
        return self._executor.execute_plan(
            plan=plan,
            dataset=dataset,
            semantic_profile=semantic_profile,
            custom_sql=custom_sql,
        )


_DEFAULT_ENGINE = DuckDBEngine()


def get_default_engine() -> AnalyticsEngine:
    """Return the global default deterministic AnalyticsEngine."""
    return _DEFAULT_ENGINE


def execute_plan(
    plan: CandidatePlan,
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    custom_sql: Optional[str] = None,
) -> ExecutionResult:
    """Convenience helper routing to the default deterministic analytics engine."""
    return _DEFAULT_ENGINE.execute(
        plan=plan,
        dataset=dataset,
        semantic_profile=semantic_profile,
        custom_sql=custom_sql,
    )
