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
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from orchestrator.schemas import (
        AggregationType,
        CandidatePlan,
        DimensionSpec,
        FilterSpec,
        Granularity,
    )

DEFAULT_ROW_LIMIT: int = 50_000


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
        s = str(value)
        if s in ("nan", "inf", "-inf"):
            return "NULL"
        return s
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "(NULL)"
        formatted_items = [format_sql_literal(item) for item in value]
        return f"({', '.join(formatted_items)})"
    val_str = str(value)
    if "\x00" in val_str:
        raise QueryCompilationError("Filter literal contains invalid null byte.")
    escaped = val_str.replace("'", "''")
    return f"'{escaped}'"


def _compile_aggregation(agg: Any, column_name: str) -> str:
    """Compile aggregation function into safe DuckDB expression."""
    quoted_col = "*" if column_name == "*" else quote_identifier(column_name)
    val = (agg.value if hasattr(agg, "value") else str(agg)).upper()
    if val == "SUM":
        return f"SUM({quoted_col})"
    elif val == "AVG":
        return f"AVG({quoted_col})"
    elif val == "MIN":
        return f"MIN({quoted_col})"
    elif val == "MAX":
        return f"MAX({quoted_col})"
    elif val == "COUNT":
        return f"COUNT({quoted_col})"
    elif val == "COUNT_DISTINCT":
        return f"COUNT(DISTINCT {quoted_col})"
    elif val == "STDDEV":
        return f"STDDEV_SAMP({quoted_col})"
    elif val == "MEDIAN":
        return f"MEDIAN({quoted_col})"
    else:
        raise QueryCompilationError(f"Unsupported aggregation type: {agg}")


def _compile_granularity(granularity: Any, column_name: str) -> str:
    """Compile temporal granularity into DuckDB DATE_TRUNC expression."""
    quoted_col = quote_identifier(column_name)
    val = granularity.value if hasattr(granularity, "value") else str(granularity)
    gran_lower = val.lower()
    allowed_parts = {"year", "quarter", "month", "week", "day", "hour"}
    if gran_lower not in allowed_parts:
        raise QueryCompilationError(f"Unsupported temporal granularity: {granularity}")
    return f"DATE_TRUNC('{gran_lower}', {quoted_col})"


def _compile_filter(filter_spec: Any) -> str:
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

    if op == "BETWEEN":
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return f"{col} BETWEEN {format_sql_literal(val[0])} AND {format_sql_literal(val[1])}"
        raise QueryCompilationError(f"BETWEEN filter requires a list/tuple of at least 2 values, got: {val}")

    raise QueryCompilationError(f"Unsupported or unsafe filter operator: {filter_spec.operator}")


def compile_plan_to_sql(
    plan: CandidatePlan,
    source_view: str = "source_data",
    row_limit: Optional[int] = None,
) -> str:
    """Compile CandidatePlan into an executable DuckDB SQL query string."""
    select_items: List[str] = []
    group_indices: List[int] = []

    # 1. Dimensions
    col_idx = 1
    for dim in plan.dimensions:
        if dim.granularity is not None:
            expr = _compile_granularity(dim.granularity, dim.column)
            gran_val = dim.granularity.value if hasattr(dim.granularity, "value") else str(dim.granularity)
            alias = f"{dim.column}_{gran_val.lower()}"
            select_items.append(f"{expr} AS {quote_identifier(alias)}")
        else:
            select_items.append(quote_identifier(dim.column))
        group_indices.append(col_idx)
        col_idx += 1

    # 2. Metric
    metric_agg = plan.metric.aggregation
    if metric_agg is None:
        metric_col_name = plan.metric.column
        metric_expr = quote_identifier(metric_col_name)
        metric_alias = metric_col_name
        select_items.append(f"{metric_expr} AS {quote_identifier(metric_alias)}")
    else:
        agg_str = metric_agg.value if hasattr(metric_agg, "value") else str(metric_agg)
        metric_expr = _compile_aggregation(metric_agg, plan.metric.column)
        metric_col_name = "records" if plan.metric.column == "*" else plan.metric.column
        metric_alias = f"{agg_str.lower()}_{metric_col_name}"
        select_items.append(f"{metric_expr} AS {quote_identifier(metric_alias)}")

    # SELECT & FROM
    from_clause = f"FROM {quote_identifier(source_view)}"
    select_clause = f"SELECT\n  " + ",\n  ".join(select_items)

    # WHERE (Filters)
    where_clause = ""
    if plan.filters:
        predicates = [_compile_filter(f) for f in plan.filters]
        where_clause = "\nWHERE " + "\n  AND ".join(predicates)

    # GROUP BY (only when an aggregation function is applied)
    group_clause = ""
    if group_indices and metric_agg is not None:
        group_clause = f"\nGROUP BY {', '.join(str(i) for i in group_indices)}"

    # ORDER BY
    order_clause = ""
    order_dir = (getattr(plan, "order_direction", None) or "ASC").strip().upper()
    if order_dir not in ("ASC", "DESC"):
        order_dir = "ASC"

    order_target = getattr(plan, "order_by", None)
    metric_idx = len(plan.dimensions) + 1

    if order_target == "metric" or (getattr(plan, "order_direction", None) and order_target != "dimension"):
        order_clause = f"\nORDER BY {metric_idx} {order_dir}"
    elif group_indices:
        order_clause = f"\nORDER BY 1 {order_dir}"

    # LIMIT
    plan_limit = getattr(plan, "limit", None)
    if plan_limit is not None and plan_limit > 0:
        effective_limit = plan_limit
    elif row_limit is not None:
        effective_limit = row_limit
    else:
        effective_limit = DEFAULT_ROW_LIMIT + 1
    limit_clause = f"\nLIMIT {int(effective_limit)}"

    sql = f"{select_clause}\n{from_clause}{where_clause}{group_clause}{order_clause}{limit_clause};"
    return sql
