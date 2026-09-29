"""Compatibility wrapper for engine execution.

Deprecated: Import directly from `engine.executor` or `engine.duckdb_executor`.
This module contains NO DuckDB connection management and NO execution implementation logic.
"""

from engine.duckdb_executor import DuckDBExecutor, default_executor
from engine.executor import AnalyticsEngine, DuckDBEngine, execute_plan, get_default_engine

__all__ = [
    "AnalyticsEngine",
    "DuckDBEngine",
    "DuckDBExecutor",
    "default_executor",
    "execute_plan",
    "get_default_engine",
]
