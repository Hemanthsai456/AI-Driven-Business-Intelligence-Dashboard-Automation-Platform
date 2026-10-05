"""DuckDB sandboxed executor with isolated in-memory worker instances.

Architecture guarantees:
1. Sandboxed Worker Isolation: Each execution uses an independent, in-memory DuckDB instance.
2. Read-only: Never mutates CanonicalDataset.data.
3. C2 Binding Resolution: DATETIME string columns are TRY_CAST in the DuckDB view.
   Failed cast counts and rates are computed and returned in ExecutionResult.
4. Resource Bounds: Isolated in-memory instance, threads=1, memory_limit=256MB, timeout=30s.
5. Deterministic Sanitization: Delegates all row/null sanitization to engine.sanitizer.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import duckdb
import pandas as pd

from ingestion.models import CanonicalDataset
from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from engine.compiler import compile_plan_to_sql, quote_identifier
from engine.sanitizer import sanitize_dataframe_to_rows

if TYPE_CHECKING:
    from orchestrator.schemas import (
        CandidatePlan,
        ExecutionResult,
        ExecutionStatus,
    )

DEFAULT_DUCKDB_THREAD_LIMIT: int = 1
DEFAULT_DUCKDB_MEMORY_LIMIT: str = "256MB"
DEFAULT_DUCKDB_TIMEOUT_SECONDS: float = 30.0



class DuckDBExecutor:
    """Executes compiled analytical plans in sandboxed, in-memory DuckDB sessions."""

    def __init__(
        self,
        thread_limit: int = DEFAULT_DUCKDB_THREAD_LIMIT,
        memory_limit: str = DEFAULT_DUCKDB_MEMORY_LIMIT,
        timeout_seconds: float = DEFAULT_DUCKDB_TIMEOUT_SECONDS,
    ):

        self.thread_limit = thread_limit
        self.memory_limit = memory_limit
        self.timeout_seconds = timeout_seconds

    def execute_plan(
        self,
        plan: CandidatePlan,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        custom_sql: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a plan against a dataset within an isolated DuckDB instance.

        Guarantees:
        1. Read-only: Never mutates CanonicalDataset.data.
        2. C2 Binding Resolution: DATETIME string columns are TRY_CAST in the DuckDB view.
           Failed cast counts and rates are computed and returned in ExecutionResult.
        3. Sandboxing: Isolated in-memory instance, threads=1, memory_limit=256MB, timeout=30s.
        """
        from orchestrator.schemas import ExecutionResult, ExecutionStatus

        start_time = time.perf_counter()

        df = dataset.data
        plan_id = plan.plan_id
        warnings: List[str] = []
        total_failed_casts = 0

        # Create isolated in-memory connection
        con = duckdb.connect(":memory:")
        timeout_timer: Optional[threading.Timer] = None

        try:
            # Set resource limits
            con.execute(f"SET threads TO {int(self.thread_limit)};")
            con.execute(f"SET max_memory = '{self.memory_limit}';")

            # Register source dataframe (zero-copy read-only reference)
            con.register("raw_dataframe", df)

            # C2 Implementation: Build TRY_CAST expressions for DATETIME columns in the view
            view_expressions: List[str] = []
            for col in df.columns:
                ev = semantic_profile.get_evidence(col)
                col_quoted = quote_identifier(col)

                # Check if classified as DATETIME and stored as string/object in pandas
                is_datetime_role = ev is not None and ev.candidate_role == ColumnRole.DATETIME
                is_string_dtype = pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col])

                if is_datetime_role and is_string_dtype:
                    # TRY_CAST in view
                    view_expressions.append(f"TRY_CAST({col_quoted} AS TIMESTAMP) AS {col_quoted}")

                    # Measure failed cast count on non-empty values
                    cast_check_query = (
                        f"SELECT COUNT(*) FROM raw_dataframe "
                        f"WHERE {col_quoted} IS NOT NULL "
                        f"  AND TRIM(CAST({col_quoted} AS VARCHAR)) != '' "
                        f"  AND TRY_CAST({col_quoted} AS TIMESTAMP) IS NULL;"
                    )
                    try:
                        failed_count = con.execute(cast_check_query).fetchone()[0]
                    except Exception:
                        failed_count = 0

                    if failed_count > 0:
                        total_failed_casts += failed_count
                        rate = failed_count / max(len(df), 1)
                        warnings.append(
                            f"Column '{col}' had {failed_count} failed datetime casts ({rate:.1%}) via TRY_CAST."
                        )
                else:
                    view_expressions.append(f"{col_quoted} AS {col_quoted}")

            # Create clean DuckDB view
            create_view_sql = f"CREATE VIEW source_data AS SELECT {', '.join(view_expressions)} FROM raw_dataframe;"
            con.execute(create_view_sql)

            # Compile or use provided SQL
            compiled_sql = custom_sql or compile_plan_to_sql(plan, source_view="source_data")

            # Setup timeout interrupt timer
            timed_out = threading.Event()

            def interrupt_worker():
                timed_out.set()
                try:
                    con.interrupt()
                except Exception:
                    pass

            timeout_timer = threading.Timer(self.timeout_seconds, interrupt_worker)
            timeout_timer.start()

            # Execute query
            cursor = con.execute(compiled_sql)
            res_df = cursor.fetchdf()

            # Query succeeded; cancel timer
            if timeout_timer:
                timeout_timer.cancel()

            elapsed = time.perf_counter() - start_time
            if timed_out.is_set() or elapsed >= self.timeout_seconds:
                return ExecutionResult(
                    plan_id=plan_id,
                    status=ExecutionStatus.TIMEOUT,
                    error_message=f"Query execution timed out after {self.timeout_seconds} seconds.",
                    runtime_seconds=round(elapsed, 4),
                )

            total_rows = len(df)
            failed_cast_rate = total_failed_casts / max(total_rows, 1)

            # Sanitize output rows for JSON serialization via deterministic sanitizer
            rows, columns = sanitize_dataframe_to_rows(res_df)

            return ExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.SUCCESS,
                rows=rows,
                columns=columns,
                row_count=len(rows),
                compiled_sql=compiled_sql,
                failed_cast_count=total_failed_casts,
                failed_cast_rate=failed_cast_rate,
                warnings=warnings,
                runtime_seconds=round(elapsed, 4),
            )

        except duckdb.InterruptException:
            elapsed = time.perf_counter() - start_time
            return ExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.TIMEOUT,
                error_message=f"Query execution timed out after {self.timeout_seconds} seconds.",
                runtime_seconds=round(elapsed, 4),
            )
        except duckdb.OutOfMemoryException as e:
            elapsed = time.perf_counter() - start_time
            return ExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.MEMORY_EXCEEDED,
                error_message=f"DuckDB memory limit exceeded: {str(e)}",
                runtime_seconds=round(elapsed, 4),
            )
        except (duckdb.ParserException, duckdb.BinderException) as e:
            elapsed = time.perf_counter() - start_time
            return ExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.SYNTAX_ERROR,
                error_message=f"SQL compilation or binder error: {str(e)}",
                runtime_seconds=round(elapsed, 4),
            )
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            return ExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.RUNTIME_ERROR,
                error_message=f"Execution runtime error: {str(e)}",
                runtime_seconds=round(elapsed, 4),
            )
        finally:
            if timeout_timer:
                timeout_timer.cancel()
            try:
                con.close()
            except Exception:
                pass


default_executor = DuckDBExecutor()
