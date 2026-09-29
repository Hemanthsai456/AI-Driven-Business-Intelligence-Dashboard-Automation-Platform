"""Deterministic Analytical Execution Engine.

Responsible for:
- SQL compilation
- DuckDB session and connection management
- Deterministic query execution
- Result normalization and sanitization

Zero cognitive orchestration or LLM logic belongs in this package.
"""

from engine.compiler import (
    QueryCompilationError,
    compile_plan_to_sql,
    format_sql_literal,
    quote_identifier,
)
from engine.duckdb_executor import DuckDBExecutor, default_executor
from engine.executor import (
    AnalyticsEngine,
    DuckDBEngine,
    execute_plan,
    get_default_engine,
)
from engine.sanitizer import sanitize_dataframe_to_rows

__all__ = [
    "AnalyticsEngine",
    "DuckDBEngine",
    "DuckDBExecutor",
    "QueryCompilationError",
    "compile_plan_to_sql",
    "default_executor",
    "execute_plan",
    "format_sql_literal",
    "get_default_engine",
    "quote_identifier",
    "sanitize_dataframe_to_rows",
]
