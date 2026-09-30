"""Compatibility wrapper for engine execution.

Deprecated: Import directly from `engine.executor` or `engine.duckdb_executor`.
This module contains NO DuckDB connection management and NO execution implementation logic.
"""

from engine import (
    AnalyticsEngine,
    DuckDBEngine,
    DuckDBExecutor,
    default_executor,
    execute_plan,
    get_default_engine,
)

__all__ = [
    "AnalyticsEngine",
    "DuckDBEngine",
    "DuckDBExecutor",
    "default_executor",
    "execute_plan",
    "get_default_engine",
]
