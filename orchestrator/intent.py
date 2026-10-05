"""Intent interpretation stage in the 6-step cognitive loop.

Analyzes raw user requests against semantic metadata to produce a structured,
validated StructuredIntent contract.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.schemas import (
    AggregationType,
    Granularity,
    LLMContext,
    StructuredIntent,
    VisualizationType,
)


def _tokenize(text: str) -> Set[str]:
    """Tokenize lowercased text into alphanumeric word tokens."""
    return set(re.findall(r"\b[a-z0-9_]+\b", text.lower()))


def _normalize_name(name: str) -> str:
    """Normalize camelCase/PascalCase/snake_case into space-delimited lowercase string."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    spaced = spaced.replace("_", " ").replace("-", " ")
    return spaced.lower()


def interpret_user_request(
    request_text: str,
    semantic_profile: DatasetSemanticProfile,
    context: Optional[LLMContext] = None,
) -> StructuredIntent:
    """Interpret user request text into a validated StructuredIntent.

    Extracts:
    - requested_metrics: Measures mentioned or strongly matching semantic columns
    - requested_dimensions: Categorical/dimension columns mentioned
    - temporal_scope: Date/time columns relevant to requested trend/timeline
    - grouping_granularity: Temporal granularity (month, day, year, etc.)
    - requested_visual_preferences: Explicit chart preferences (bar, line, etc.)
    - comparison_requirements: Period-over-period or baseline comparisons
    - analytical_goal: 'trend', 'aggregation', 'distribution', 'comparison'
    - unresolved_terms: Tokens in request not matched to semantic columns or keywords
    """
    cleaned_request = (request_text or "").strip()
    if not cleaned_request:
        return StructuredIntent(
            original_request="",
            analytical_goal=None,
            confidence=0.0,
            unresolved_terms=[],
        )

    tokens = _tokenize(cleaned_request)
    req_lower = cleaned_request.lower()

    # Partition columns from semantic profile
    measures: Dict[str, Any] = {}
    dimensions: Dict[str, Any] = {}
    datetimes: Dict[str, Any] = {}
    identifiers: Dict[str, Any] = {}

    for col, ev in semantic_profile.column_evidences.items():
        if ev.candidate_role == ColumnRole.MEASURE:
            measures[col] = ev
        elif ev.candidate_role == ColumnRole.DIMENSION:
            dimensions[col] = ev
        elif ev.candidate_role == ColumnRole.DATETIME:
            datetimes[col] = ev
        elif ev.candidate_role == ColumnRole.IDENTIFIER:
            identifiers[col] = ev

    def _stem_word(w: str) -> Set[str]:
        res = {w}
        if w.endswith("ies") and len(w) > 4:
            res.add(w[:-3] + "y")
        if w.endswith("es") and len(w) > 3:
            res.add(w[:-2])
        if w.endswith("s") and len(w) > 3:
            res.add(w[:-1])
        if w.endswith("y") and len(w) > 3:
            res.add(w[:-1] + "ies")
        return res

    def _col_matches(col_name: str) -> bool:
        col_norm = _normalize_name(col_name)
        col_toks = set(re.findall(r"\b[a-z0-9]+\b", col_norm))
        if col_name.lower() in req_lower or col_norm in req_lower:
            return True
        if col_toks and col_toks.issubset(tokens):
            return True

        agg_words = {"total", "sum", "avg", "average", "count", "min", "max", "mean"}
        id_words = {"id", "code", "key", "number", "name", "desc", "description", "val", "value", "amt", "amount", "lpa", "usd", "inr"}
        substantive = {t for t in col_toks if t not in agg_words}
        if not substantive:
            return False

        for stok in substantive:
            stok_stems = _stem_word(stok)
            for qtok in tokens:
                if qtok == stok or _stem_word(qtok) & stok_stems:
                    return True

        return False

    # 1. Match requested metrics
    matched_metrics: List[str] = []
    for col in measures:
        if _col_matches(col):
            matched_metrics.append(col)

    # 2. Match requested dimensions (include identifiers if mentioned in grouping context)
    matched_dims: List[str] = []
    for col in dimensions:
        if _col_matches(col):
            matched_dims.append(col)

    for col in identifiers:
        # Check if identifier is referenced as a dimension (e.g. "by store id", "store id")
        if _col_matches(col) and col not in matched_metrics:
            matched_dims.append(col)

    # 3. Match temporal scope
    matched_dates: List[str] = []
    for col in datetimes:
        if _col_matches(col):
            matched_dates.append(col)

    # If count requested on an entity (e.g. "count customers"), match identifier or dimension to metric
    if "count" in tokens and not matched_metrics:
        for col in list(identifiers.keys()) + list(dimensions.keys()):
            if _col_matches(col):
                matched_metrics.append(col)
                if col in matched_dims:
                    matched_dims.remove(col)
                break

    # 4. Detect temporal keywords and granularity
    granularity_keywords = {
        "monthly": "month",
        "month": "month",
        "daily": "day",
        "day": "day",
        "yearly": "year",
        "annual": "year",
        "annually": "year",
        "year": "year",
        "quarterly": "quarter",
        "quarter": "quarter",
        "weekly": "week",
        "week": "week",
        "hourly": "hour",
        "hour": "hour",
    }
    detected_granularity: Optional[str] = None
    for kw, gran in granularity_keywords.items():
        if kw in tokens:
            detected_granularity = gran
            break

    # 5. Determine analytical goal
    trend_kws = {"trend", "over", "time", "timeline", "history", "monthly", "daily", "yearly"}
    comp_kws = {"compare", "comparison", "versus", "vs", "growth", "difference"}
    dist_kws = {"distribution", "breakdown", "by", "categorize", "category", "share"}

    analytical_goal: Optional[str] = None
    if tokens & trend_kws:
        analytical_goal = "trend"
    elif tokens & comp_kws:
        analytical_goal = "comparison"
    elif tokens & dist_kws:
        analytical_goal = "distribution"
    elif matched_metrics or matched_dims:
        analytical_goal = "aggregation"

    # 6. Visual preferences
    vis_keywords = {
        "bar": "bar",
        "line": "line",
        "pie": "pie",
        "table": "table",
        "kpi": "kpi",
        "scatter": "scatter",
        "area": "area",
    }
    requested_visual: Optional[str] = None
    for kw, vis in vis_keywords.items():
        if kw in tokens:
            requested_visual = vis
            break

    # 7. Comparison requirements
    comparison_req: Optional[str] = None
    if "previous year" in req_lower or "yoy" in req_lower:
        comparison_req = "year_over_year"
    elif "previous month" in req_lower or "mom" in req_lower:
        comparison_req = "month_over_month"

    # 8. Unresolved terms
    all_known_columns = set()
    for c in semantic_profile.column_evidences.keys():
        all_known_columns.update(_stem_word(c.lower()))
        for sub in re.findall(r"\b[a-z0-9]+\b", _normalize_name(c)):
            all_known_columns.update(_stem_word(sub))

    stopwords = {
        "show", "me", "the", "a", "an", "of", "for", "by", "in", "and", "or", "to",
        "give", "get", "what", "is", "are", "total", "average", "avg", "sum", "count",
        "all", "top", "per", "data", "report", "with", "over", "time", "numbers", "stats",
        "calculate", "calc", "find", "compute", "display", "plot", "list", "across", "between",
        "analyze", "analysis", "each", "every", "group", "grouped", "grouping", "compare",
        "comparison", "versus", "vs", "breakdown", "split", "looks", "look", "like", "tell",
        "explain", "describe", "see", "view", "chart", "graph"
    }
    unresolved: List[str] = []
    for tok in tokens:
        tok_stems = _stem_word(tok)
        if (
            tok not in stopwords
            and tok not in granularity_keywords
            and tok not in vis_keywords
            and tok not in trend_kws
            and not (tok_stems & all_known_columns)
        ):
            unresolved.append(tok)

    # 9. Compute confidence
    total_meaningful_tokens = len(tokens - stopwords)
    if total_meaningful_tokens > 0:
        matched_count = total_meaningful_tokens - len(unresolved)
        confidence = round(max(0.1, min(1.0, matched_count / total_meaningful_tokens)), 2)
    else:
        confidence = 0.5

    return StructuredIntent(
        original_request=cleaned_request,
        analytical_goal=analytical_goal,
        requested_metrics=matched_metrics,
        requested_dimensions=matched_dims,
        temporal_scope=matched_dates[0] if matched_dates else None,
        grouping_granularity=detected_granularity,
        comparison_requirements=comparison_req,
        requested_visual_preferences=requested_visual,
        filters=[],
        unresolved_terms=unresolved,
        confidence=confidence,
    )
