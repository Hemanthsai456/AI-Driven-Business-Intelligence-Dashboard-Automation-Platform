"""Safe analytical query compiler targeting DuckDB.

Converts structured CandidatePlan instances into deterministic, injection-safe SQL queries.
Accepts NO raw SQL strings from outside. All identifiers are safely quoted, all filter literals
are typed and escaped, and all aggregations/granularities are strictly whitelisted.

Architecture references:
- orchestrator_conformance.md §1 (Safe Query Compilation, DuckDB Isolation)
- ranker_v1_spec.md §Pass 1a
"""

from __future__ import annotations

import re
from typing import Any, List, Optional
from orchestrator.config import RESULT_ROW_CAP
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    FilterSpec,
    Granularity,
)


class QueryCompilationError(ValueError):
    """Raised when plan structure cannot be safely compiled into SQL."""


def quote_identifier(identifier: str) -> str:
    """Safely quote a SQL identifier (table, view, or column name).

    Escapes internal double quotes by doubling them. Rejects null bytes or
    unreasonable identifier structures.
    """
    if not identifier or not isinstance(identifier, str):
        raise QueryCompilationError("Identifier must be a non-empty string.")
    if "\x00" in identifier:
        raise QueryCompilationError("Identifier contains invalid null byte.")
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def format_sql_literal(value: Any) -> str:
    """Format a Python value as a safe DuckDB SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        # Ensure finite numeric values
        s = str(value)
        if s in ("nan", "inf", "-inf"):
            return "NULL"
        return s
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "(NULL)"
        formatted_items = [format_sql_literal(item) for item in value]
        return f"({', '.join(formatted_items)})"
    # String or anything else
    val_str = str(value)
    if "\x00" in val_str:
        raise QueryCompilationError("Filter literal contains invalid null byte.")
    escaped = val_str.replace("'", "''")
    return f"'{escaped}'"


def _compile_aggregation(agg: AggregationType, column_name: str) -> str:
    """Compile aggregation function into safe DuckDB expression."""
    quoted_col = quote_identifier(column_name)
    if agg == AggregationType.SUM:
        return f"SUM({quoted_col})"
    elif agg == AggregationType.AVG:
        return f"AVG({quoted_col})"
    elif agg == AggregationType.MIN:
        return f"MIN({quoted_col})"
    elif agg == AggregationType.MAX:
        return f"MAX({quoted_col})"
    elif agg == AggregationType.COUNT:
        return f"COUNT({quoted_col})"
    elif agg == AggregationType.COUNT_DISTINCT:
        return f"COUNT(DISTINCT {quoted_col})"
    elif agg == AggregationType.STDDEV:
        return f"STDDEV_SAMP({quoted_col})"
    elif agg == AggregationType.MEDIAN:
        return f"MEDIAN({quoted_col})"
    else:
        raise QueryCompilationError(f"Unsupported aggregation type: {agg}")


def _compile_granularity(granularity: Granularity, column_name: str) -> str:
    """Compile temporal granularity into DuckDB DATE_TRUNC expression."""
    quoted_col = quote_identifier(column_name)
    gran_lower = granularity.value.lower()
    allowed_parts = {"year", "quarter", "month", "week", "day", "hour"}
    if gran_lower not in allowed_parts:
        raise QueryCompilationError(f"Unsupported temporal granularity: {granularity}")
    return f"DATE_TRUNC('{gran_lower}', {quoted_col})"


def _compile_filter(filter_spec: FilterSpec) -> str:
    """Compile a single FilterSpec predicate safely."""
    op = filter_spec.operator.strip().upper()
    col = quote_identifier(filter_spec.column)
    val = filter_spec.value

    if op in ("IS NULL", "IS NOT NULL"):
        return f"{col} {op}"

    if op in ("=", "!=", "<>", "<", "<=", ">", ">="):
        return f"{col} {op} {format_sql_literal(val)}"

    if op == "IN":
        if isinstance(val, (list, tuple, set)):
            return f"{col} IN {format_sql_literal(val)}"
        else:
            return f"{col} IN ({format_sql_literal(val)})"

    if op == "NOT IN":
        if isinstance(val, (list, tuple, set)):
            return f"{col} NOT IN {format_sql_literal(val)}"
        else:
            return f"{col} NOT IN ({format_sql_literal(val)})"

    if op in ("LIKE", "ILIKE"):
        return f"{col} {op} {format_sql_literal(val)}"

    raise QueryCompilationError(f"Unsupported or unsafe filter operator: {filter_spec.operator}")


def compile_plan_to_sql(
    plan: CandidatePlan,
    source_view: str = "source_data",
    row_limit: Optional[int] = None,
) -> str:
    """Compile CandidatePlan into an executable DuckDB SQL query string.

    Args:
        plan: The structured CandidatePlan to compile.
        source_view: Name of the registered DuckDB view (defaults to 'source_data').
        row_limit: Max rows to return (defaults to RESULT_ROW_CAP + 1 for overflow detection).

    Returns:
        Formatted, injection-safe SQL query string.
    """
    select_items: List[str] = []
    group_indices: List[int] = []

    # 1. Dimensions
    col_idx = 1
    for dim in plan.dimensions:
        if dim.granularity is not None:
            expr = _compile_granularity(dim.granularity, dim.column)
            alias = f"{dim.column}_{dim.granularity.value.lower()}"
            select_items.append(f"{expr} AS {quote_identifier(alias)}")
        else:
            select_items.append(quote_identifier(dim.column))
        group_indices.append(col_idx)
        col_idx += 1

    # 2. Metric
    metric_expr = _compile_aggregation(plan.metric.aggregation, plan.metric.column)
    metric_alias = f"{plan.metric.aggregation.value.lower()}_{plan.metric.column}"
    select_items.append(f"{metric_expr} AS {quote_identifier(metric_alias)}")
    metric_col_idx = col_idx

    # SELECT & FROM
    from_clause = f"FROM {quote_identifier(source_view)}"
    select_clause = f"SELECT\n  " + ",\n  ".join(select_items)

    # WHERE (Filters)
    where_clause = ""
    if plan.filters:
        predicates = [_compile_filter(f) for f in plan.filters]
        where_clause = "\nWHERE " + "\n  AND ".join(predicates)

    # GROUP BY
    group_clause = ""
    if group_indices:
        group_clause = f"\nGROUP BY {', '.join(str(i) for i in group_indices)}"

    # ORDER BY
    # If dimensions exist, order by first dimension ASC (temporal / categorical ordering)
    # If no dimensions, ordering is moot for scalar aggregate
    order_clause = ""
    if group_indices:
        order_clause = f"\nORDER BY 1 ASC"

    # LIMIT
    effective_limit = row_limit if row_limit is not None else (RESULT_ROW_CAP + 1)
    limit_clause = f"\nLIMIT {int(effective_limit)}"

    sql = f"{select_clause}\n{from_clause}{where_clause}{group_clause}{order_clause}{limit_clause};"
    return sql
