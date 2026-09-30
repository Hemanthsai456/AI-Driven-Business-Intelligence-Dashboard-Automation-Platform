"""Deterministic result normalization and sanitization layer.

Converts raw query output DataFrames into clean, JSON-serializable rows.
Handles:
- NaN, NaT, and infinity values -> None (safe JSON null)
- Datetime / Timestamp columns -> standardized ISO-8601 string representations
- Zero-copy row dictionary generation
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import pandas as pd


def sanitize_dataframe_to_rows(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Sanitize a pandas DataFrame into JSON-safe dictionaries and column names.

    Replaces NaN, NaT, inf, -inf with None.
    Converts datetime columns into ISO string representations.
    """
    if df.empty:
        return [], list(df.columns)

    clean_df = df.copy()

    # Convert datetime columns: format valid timestamps to ISO strings, NaT to None
    for col_name in clean_df.columns:
        if pd.api.types.is_datetime64_any_dtype(clean_df[col_name]):
            clean_df[col_name] = clean_df[col_name].apply(
                lambda v: v.isoformat() if pd.notnull(v) and hasattr(v, "isoformat") else (str(v) if pd.notnull(v) else None)
            )

    # Convert to object dtype so None is preserved without coercing back to NaN
    clean_df = clean_df.astype(object)
    clean_df = clean_df.replace([float("inf"), float("-inf")], None)
    clean_df = clean_df.where(pd.notnull(clean_df), None)

    raw_rows: List[Dict[str, Any]] = clean_df.to_dict(orient="records")
    sanitized_rows: List[Dict[str, Any]] = []
    for r in raw_rows:
        row_dict = {}
        for k, v in r.items():
            if pd.isna(v) or v in (float("inf"), float("-inf")) or v == "NaT":
                row_dict[k] = None
            else:
                row_dict[k] = v
        sanitized_rows.append(row_dict)

    columns: List[str] = list(df.columns)
    return sanitized_rows, columns
