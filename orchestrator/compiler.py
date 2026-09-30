"""Compatibility wrapper for engine.compiler.

Deprecated: Import directly from `engine.compiler` or `engine`.
This module contains NO compiler implementation logic.
"""

from engine.compiler import (
    QueryCompilationError,
    compile_plan_to_sql,
    format_sql_literal,
    quote_identifier,
)

__all__ = [
    "QueryCompilationError",
    "compile_plan_to_sql",
    "format_sql_literal",
    "quote_identifier",
]
