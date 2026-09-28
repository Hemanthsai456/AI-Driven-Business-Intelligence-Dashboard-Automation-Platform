"""Compact LLM context builder with sanitization, value truncation, and injection defense.

Guarantees:
1. Compact structured context: Raw data rows are NEVER included.
2. Sanitization: Strips control characters from user intent, column names, and metadata.
3. Truncation: Values and evidence strings are capped to bounded lengths.
4. Safe data encapsulation: Column entries are strictly typed ColumnContextEntry structures.

Architecture references:
- orchestrator_conformance.md §1 ('Compact LLM Context')
- ranker_v1_spec.md §Pass 1a
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from intelligence.profiler import DataProfile
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.schemas import ColumnContextEntry, LLMContext

# Control characters regex: ASCII 0-31 and 127
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_text(text: str, max_len: int = 250) -> str:
    """Strip control characters, normalize whitespace, and truncate to max_len."""
    if not text:
        return ""
    # Strip control chars
    clean = CONTROL_CHAR_RE.sub(" ", str(text))
    # Normalize excessive whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) > max_len:
        clean = clean[:max_len] + "..."
    return clean


def build_llm_context(
    dataset_id: str,
    intent: str,
    semantic_profile: DatasetSemanticProfile,
    data_profile: Optional[DataProfile] = None,
    max_evidence_len: int = 200,
) -> LLMContext:
    """Build a sanitized, compact LLM context from dataset semantic and data profiles.

    Raw data rows are never included. All strings are stripped of control chars
    and truncated.

    Args:
        dataset_id: Identifier of the canonical dataset.
        intent: Natural-language user prompt.
        semantic_profile: Semantic analyzer profile.
        data_profile: Optional profiling engine statistics.
        max_evidence_len: Maximum length for evidence strings.

    Returns:
        LLMContext instance with computed SHA-256 context_hash.
    """
    sanitized_intent = sanitize_text(intent, max_len=1000)
    column_entries: List[ColumnContextEntry] = []

    profile_stats: Dict[str, Any] = {}
    if data_profile is not None:
        profile_stats = getattr(data_profile, "column_statistics", {}) or {}

    for col_name, evidence in semantic_profile.column_evidences.items():
        # Sanitize column name and evidence strings
        safe_col_name = sanitize_text(col_name, max_len=128)
        safe_evidence = [sanitize_text(e, max_len=max_evidence_len) for e in evidence.evidence]

        # Extract summary statistics from data profile if present
        col_stat = profile_stats.get(col_name)
        distinct_count: Optional[int] = None
        null_percentage: Optional[float] = None
        dtype: Optional[str] = None

        if col_stat is not None:
            if hasattr(col_stat, "distinct_count"):
                distinct_count = col_stat.distinct_count
                null_percentage = col_stat.null_percentage
                dtype = col_stat.detected_datatype
            elif isinstance(col_stat, dict):
                distinct_count = col_stat.get("distinct_count")
                null_percentage = col_stat.get("null_percentage")
                dtype = col_stat.get("detected_datatype") or col_stat.get("dtype")

        role_str = (
            evidence.candidate_role.value
            if hasattr(evidence.candidate_role, "value")
            else str(evidence.candidate_role)
        )

        entry = ColumnContextEntry(
            column_name=safe_col_name,
            candidate_role=role_str,
            confidence=round(float(evidence.confidence), 4),
            confidence_level=evidence.confidence_level,
            evidence=safe_evidence,
            distinct_count=distinct_count,
            null_percentage=round(null_percentage, 2) if null_percentage is not None else None,
            dtype=dtype,
        )
        column_entries.append(entry)

    # Deterministic sorting of columns by name
    column_entries.sort(key=lambda c: c.column_name)

    context_hash = LLMContext.compute_hash(
        dataset_id=dataset_id,
        intent=sanitized_intent,
        column_names=[c.column_name for c in column_entries],
    )

    return LLMContext(
        dataset_id=dataset_id,
        intent=sanitized_intent,
        columns=column_entries,
        context_hash=context_hash,
    )
