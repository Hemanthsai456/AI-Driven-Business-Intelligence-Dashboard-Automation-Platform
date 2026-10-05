"""Intent interpretation stage in the 6-step cognitive loop.

Analyzes raw user requests against semantic metadata to produce a structured,
validated StructuredIntent contract.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from intelligence.semantic_analyzer import ColumnRole, DatasetSemanticProfile
from orchestrator.schemas import (
    AggregationType,
    FilterSpec,
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


def _stem_word(w: str) -> Set[str]:
    """Generate basic morphological variants / stems for a token."""
    res = {w}
    if w.endswith("ies") and len(w) > 4:
        res.add(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        res.add(w[:-2])
    if w.endswith("s") and len(w) > 3:
        res.add(w[:-1])
    if w.endswith("y") and len(w) > 3:
        res.add(w[:-1] + "ies")
    if w.endswith("ing") and len(w) > 4:
        res.add(w[:-3])
        res.add(w[:-3] + "e")
    if w.endswith("ed") and len(w) > 3:
        res.add(w[:-2])
        res.add(w[:-1])
    return res


def _match_column_score(
    col_name: str,
    req_lower: str,
    tokens: Set[str],
) -> float:
    """Compute deterministic matching score for a column against user query."""
    col_raw_lower = col_name.lower()
    col_norm = _normalize_name(col_name)

    # 1. Exact raw column name match (e.g. "employee_compensation" in "average employee_compensation by...")
    if col_raw_lower in req_lower:
        return 1.0

    # 2. Exact normalized space-separated name match (e.g. "employee compensation" in query)
    if col_norm in req_lower:
        return 0.95

    # 3. Token-level matching
    col_toks = set(re.findall(r"\b[a-z0-9]+\b", col_norm))
    if not col_toks:
        return 0.0

    if col_toks.issubset(tokens):
        return 0.90

    agg_words = {"total", "sum", "avg", "average", "count", "min", "max", "mean", "median", "stddev"}
    id_suffixes = {"id", "code", "key", "num", "number", "tag", "token", "identifier", "ref", "reference"}
    substantive = {t for t in col_toks if t not in agg_words}
    if len(substantive) > 1:
        non_id = {t for t in substantive if t not in id_suffixes}
        if non_id:
            substantive = non_id
    if not substantive:
        return 0.0

    match_count = 0
    for stok in substantive:
        stok_stems = _stem_word(stok)
        if stok in tokens or any(qtok in stok_stems or _stem_word(qtok) & stok_stems for qtok in tokens):
            match_count += 1

    if match_count == len(substantive):
        return 0.85
    elif match_count > 0:
        return 0.40 * (match_count / len(substantive))

    return 0.0


def _parse_literal_value(val_str: str) -> Any:
    """Safely parse a literal string into int, float, bool, or trimmed string."""
    clean = val_str.strip().strip("'\"").rstrip("?,;.")
    if clean.lower() == "true":
        return True
    if clean.lower() == "false":
        return False
    if clean.lower() in ("null", "none"):
        return None
    try:
        if "." in clean:
            return float(clean)
        return int(clean)
    except ValueError:
        return clean


def _extract_ranking_and_limits(req_text: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """Extract ranking ordering and row limits from natural language query.

    Returns:
        (order_by, order_direction, limit)
    """
    req_lower = req_text.lower()
    order_by: Optional[str] = None
    order_dir: Optional[str] = None
    limit: Optional[int] = None

    # Top N / Bottom N patterns
    top_n_match = re.search(r"\b(?:top|highest|best|first)\s+(\d+)\b", req_lower)
    if top_n_match:
        limit = int(top_n_match.group(1))
        order_dir = "DESC"
        order_by = "metric"

    bot_n_match = re.search(r"\b(?:bottom|lowest|worst|last|least)\s+(\d+)\b", req_lower)
    if bot_n_match:
        limit = int(bot_n_match.group(1))
        order_dir = "ASC"
        order_by = "metric"

    # Single-rank superlatives ("which X has the highest Y", "what is the best X")
    if not limit:
        if re.search(r"\b(?:highest|maximum|max|greatest|most|best|top)\b", req_lower):
            order_dir = "DESC"
            order_by = "metric"
            if re.search(r"\bwhich\b|\bwhat\b|\bfind the\b", req_lower):
                limit = 1
        elif re.search(r"\b(?:lowest|minimum|min|least|worst|bottom)\b", req_lower):
            order_dir = "ASC"
            order_by = "metric"
            if re.search(r"\bwhich\b|\bwhat\b|\bfind the\b", req_lower):
                limit = 1

    return order_by, order_dir, limit


def _extract_filters(
    req_text: str,
    semantic_profile: DatasetSemanticProfile,
) -> Tuple[List[FilterSpec], Set[str]]:
    """Extract column filter constraints dynamically from user query.

    Returns:
        (list of FilterSpec, set of resolved token words consumed by filters)
    """
    filters: List[FilterSpec] = []
    consumed_tokens: Set[str] = set()

    all_cols = list(semantic_profile.column_evidences.keys())
    if not all_cols:
        return filters, consumed_tokens

    # Regex patterns for various filter syntaxes
    # 1. Standard Comparison Operators: col (=|!=|<>|<=|>=|<|>) val
    comp_patterns = [
        # where col = 'val' or col = 123
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s*(==|=|!=|<>|<=|>=|<|>)\s*('?[^'\s,;]+'?|\"[^\"\s,;]+\")",
        # col between val1 and val2
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+between\s+('?[^'\s]+'?|\"[^\"\s]+\"|\d+(?:\.\d+)?)\s+and\s+('?[^'\s]+'?|\"[^\"\s]+\"|\d+(?:\.\d+)?)\b",
        # col is [not] null
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+is\s+(not\s+null|null)\b",
        # col is [not] 'val'
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+is\s+(not\s+equal\s+to\s+|not\s+)?('?[A-Za-z0-9_\-\.]+?'?|\"[A-Za-z0-9_\-\.]+\")\b",
        # col in (val1, val2, ...)
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+in\s*\(([^)]+)\)",
        # col like / contains 'val'
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:like|contains|containing)\s+('?[^'\s,;]+'?|\"[^\"\s,;]+\")",
        # Natural language relational comparisons:
        # col (greater than / above / over / at least / exceeding / more than) val
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:greater\s+than\s+or\s+equal\s+to|at\s+least|above\s+or\s+equal\s+to|>=)\s*('?[^'\s,;]+'?|\"[^\"\s,;]+\"|\d+(?:\.\d+)?)",
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:greater\s+than|above|over|exceeding|more\s+than|>)\s*('?[^'\s,;]+'?|\"[^\"\s,;]+\"|\d+(?:\.\d+)?)",
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:less\s+than\s+or\s+equal\s+to|at\s+most|below\s+or\s+equal\s+to|<=)\s*('?[^'\s,;]+'?|\"[^\"\s,;]+\"|\d+(?:\.\d+)?)",
        r"(?:where\s+|with\s+|for\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:less\s+than|below|under|fewer\s+than|<)\s*('?[^'\s,;]+'?|\"[^\"\s,;]+\"|\d+(?:\.\d+)?)",
    ]

    # Pre-extract 'where' or 'filter by' clauses if present
    clause_match = re.search(r"\b(?:where|filter by|filtered by)\s+(.+)$", req_text, re.IGNORECASE)
    if clause_match:
        # Mark all words in the where clause as filter tokens
        consumed_tokens.update(_tokenize(clause_match.group(0)))
        search_texts = [clause_match.group(1)]
    else:
        search_texts = [req_text]

    for stext in search_texts:
        # Quoted string pattern supporting doubled quotes: 'val' or 'it''s ok'
        val_pattern = r"(?:'([^']*(?:''[^']*)*)'|\"([^\"]*)\"|([^\s,;]+))"

        # Between check
        for m in re.finditer(r"\b([A-Za-z0-9_\-\s]+?)\s+between\s+('?[^'\s]+'?|\"[^\"\s]+\"|\d+(?:\.\d+)?)\s+and\s+('?[^'\s]+'?|\"[^\"\s]+\"|\d+(?:\.\d+)?)\b", stext, re.IGNORECASE):
            raw_col, v1_str, v2_str = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            best_col = None
            best_score = 0.0
            for c in all_cols:
                score = _match_column_score(c, raw_col.lower(), _tokenize(raw_col))
                if score > best_score and score >= 0.70:
                    best_score = score
                    best_col = c
            if best_col:
                val1 = _parse_literal_value(v1_str)
                val2 = _parse_literal_value(v2_str)
                filters.append(FilterSpec(column=best_col, operator="BETWEEN", value=[val1, val2]))
                consumed_tokens.update(_tokenize(m.group(0)))

        # IN list check
        for m in re.finditer(r"\b([A-Za-z0-9_\-\s]+?)\s+in\s*\(([^)]+)\)", stext, re.IGNORECASE):
            raw_col, list_str = m.group(1).strip(), m.group(2).strip()
            best_col = None
            best_score = 0.0
            for c in all_cols:
                score = _match_column_score(c, raw_col.lower(), _tokenize(raw_col))
                if score > best_score and score >= 0.70:
                    best_score = score
                    best_col = c
            if best_col:
                items = [_parse_literal_value(x) for x in list_str.split(",") if x.strip()]
                filters.append(FilterSpec(column=best_col, operator="IN", value=items))
                consumed_tokens.update(_tokenize(m.group(0)))

        # IS NULL / IS NOT NULL check
        for m in re.finditer(r"\b([A-Za-z0-9_\-\s]+?)\s+is\s+(not\s+null|null)\b", stext, re.IGNORECASE):
            raw_col, null_op = m.group(1).strip(), m.group(2).strip().upper()
            best_col = None
            best_score = 0.0
            for c in all_cols:
                score = _match_column_score(c, raw_col.lower(), _tokenize(raw_col))
                if score > best_score and score >= 0.70:
                    best_score = score
                    best_col = c
            if best_col:
                op = "IS NOT NULL" if "NOT" in null_op else "IS NULL"
                filters.append(FilterSpec(column=best_col, operator=op, value=None))
                consumed_tokens.update(_tokenize(m.group(0)))

        val_pattern_any = r"(?:'([^']*(?:''[^']*)*)'|\"([^\"]*)\"|([^\s,;?]+))"
        val_pattern_num = r"(?:'([^']*(?:''[^']*)*)'|\"([^\"]*)\"|(\d+(?:\.\d+)?))"

        # Relational comparison checks (>=, <=, >, <, =, !=)
        relational_regexes = [
            (rf"\b([A-Za-z0-9_\-\s]+?)\s*(>=|greater\s+than\s+or\s+equal\s+to|at\s+least|above\s+or\s+equal\s+to)\s*{val_pattern_num}", ">="),
            (rf"\b([A-Za-z0-9_\-\s]+?)\s*(<=|less\s+than\s+or\s+equal\s+to|at\s+most|below\s+or\s+equal\s+to)\s*{val_pattern_num}", "<="),
            (rf"\b([A-Za-z0-9_\-\s]+?)\s*(>|greater\s+than|above|over|exceeding|more\s+than)\s*{val_pattern_num}", ">"),
            (rf"\b([A-Za-z0-9_\-\s]+?)\s*(<|less\s+than|below|under|fewer\s+than)\s*{val_pattern_num}", "<"),
            (rf"\b([A-Za-z0-9_\-\s]+?)\s*(!=|<>|is\s+not|not\s+equal\s+to)\s*{val_pattern_any}", "!="),
            (rf"\b([A-Za-z0-9_\-\s]+?)\s*(==|=|is|equals|equal\s+to|:)\s*{val_pattern_any}", "="),
            (rf"\b([A-Za-z0-9_\-\s]+?)\s+(like|contains|containing)\s*{val_pattern_any}", "LIKE"),
        ]

        invalid_vals = {
            "the", "a", "an", "what", "which", "how", "why", "who", "where", "when",
            "show", "give", "find", "display", "tell", "avg", "average", "mean", "sum",
            "total", "count", "by", "in", "and", "or", "of", "for", "with", "is", "are", "?"
        }

        is_explicit_clause = bool(clause_match)

        for pattern, op in relational_regexes:
            for m in re.finditer(pattern, stext, re.IGNORECASE):
                raw_col = m.group(1).strip()
                matched_op_str = m.group(2).strip().lower()
                matched_val = next((g for g in m.groups()[2:] if g is not None), "").strip()

                val_clean_lower = matched_val.strip("'\"").rstrip("?,;.").lower()
                if not val_clean_lower or val_clean_lower in invalid_vals:
                    continue

                if matched_op_str == "is" and not is_explicit_clause and not (matched_val.startswith("'") or matched_val.startswith('"')):
                    continue

                raw_col_clean = re.sub(r"^(?:where|with|for|and|or|having|filter by)\s+", "", raw_col, flags=re.IGNORECASE).strip()
                if re.match(r"^(?:what|which|how|why|show|give|display|find|tell)\b", raw_col_clean, re.IGNORECASE):
                    continue

                best_col = None
                best_score = 0.0
                for c in all_cols:
                    score = _match_column_score(c, raw_col_clean.lower(), _tokenize(raw_col_clean))
                    if score > best_score and score >= 0.70:
                        best_score = score
                        best_col = c
                if best_col and not any(f.column == best_col for f in filters):
                    val = _parse_literal_value(matched_val)
                    filters.append(FilterSpec(column=best_col, operator=op, value=val))
                    consumed_tokens.update(_tokenize(m.group(0)))

    return filters, consumed_tokens


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
    - analytical_goal: 'trend', 'aggregation', 'distribution', 'comparison', 'ranking'
    - detected_filter_specs: Validated filter specifications extracted from natural language
    - order_by, order_direction, limit: Extracted ranking/ordering specifications
    - unresolved_terms: Tokens in request not matched to semantic columns, filters, or keywords
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

    # 1. Extract dynamic filters first so their tokens are accounted for
    filter_specs, filter_tokens = _extract_filters(cleaned_request, semantic_profile)

    # 2. Extract ranking, superlatives, and row limits
    order_by, order_dir, limit = _extract_ranking_and_limits(cleaned_request)

    # 3. Partition columns from semantic profile
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

    # 4. Match requested metrics
    matched_metrics: List[Tuple[str, float]] = []
    for col, ev in measures.items():
        score = _match_column_score(col, req_lower, tokens)
        if score > 0.0:
            # Combine match score with semantic confidence
            combined = score * float(ev.confidence)
            matched_metrics.append((col, combined))

    # Sort matched metrics by score descending
    matched_metrics.sort(key=lambda x: x[1], reverse=True)
    metric_cols = [m[0] for m in matched_metrics]

    # 5. Match requested dimensions (excluding columns used exclusively as filters)
    filter_col_names = {f.column for f in filter_specs}
    matched_dims: List[Tuple[str, float]] = []
    for col, ev in dimensions.items():
        score = _match_column_score(col, req_lower, tokens)
        col_norm = _normalize_name(col)
        has_group_phrase = bool(
            re.search(r"\b(?:by|per|across|each|every|group(?:ed)?\s+by|split\s+by|breakdown\s+by)\s+" + re.escape(col_norm), req_lower)
        ) or any(
            re.search(r"\b(?:by|per|across|each|every|group(?:ed)?\s+by|split\s+by|breakdown\s+by)\s+[a-z0-9_\-\s]*?\b" + re.escape(part), req_lower)
            for part in col_norm.split()
        )
        if score >= 0.70 or (score > 0.0 and (has_group_phrase or len(dimensions) == 1)):
            if col in filter_col_names and not has_group_phrase:
                continue
            combined = score * float(ev.confidence)
            matched_dims.append((col, combined))

    if not matched_dims:
        for col, ev in identifiers.items():
            score = _match_column_score(col, req_lower, tokens)
            col_norm = _normalize_name(col)
            has_group_phrase = bool(
                re.search(r"\b(?:by|per|across|each|every|group(?:ed)?\s+by|split\s+by|breakdown\s+by)\s+" + re.escape(col_norm), req_lower)
            ) or any(
                re.search(r"\b(?:by|per|across|each|every|group(?:ed)?\s+by|split\s+by|breakdown\s+by)\s+[a-z0-9_\-\s]*?\b" + re.escape(part), req_lower)
                for part in col_norm.split()
                if part not in {"id", "code", "key", "num", "number", "tag", "token", "ref"}
            )
            if score >= 0.70 and has_group_phrase and col not in metric_cols:
                if col in filter_col_names and not has_group_phrase:
                    continue
                matched_dims.append((col, score * float(ev.confidence)))

    matched_dims.sort(key=lambda x: x[1], reverse=True)
    dim_cols = [d[0] for d in matched_dims]

    # 6. Match temporal scope - only if date column is named or query has explicit temporal trigger
    temporal_triggers = {"trend", "over", "time", "timeline", "history", "monthly", "daily", "yearly", "quarterly", "month", "year", "day", "date", "period", "annual"}
    has_temporal_trigger = bool(tokens & temporal_triggers)
    matched_dates: List[Tuple[str, float]] = []
    for col, ev in datetimes.items():
        score = _match_column_score(col, req_lower, tokens)
        if score >= 0.70 or (score > 0.0 and has_temporal_trigger):
            matched_dates.append((col, score * float(ev.confidence)))

    matched_dates.sort(key=lambda x: x[1], reverse=True)
    date_cols = [d[0] for d in matched_dates]

    # 7. Entity count questions (e.g. "count of customers", "how many students", "number of transactions")
    count_triggers = {"count", "how many", "number of", "total number", "records", "rows"}
    is_count_request = any(ct in req_lower for ct in count_triggers)
    if is_count_request:
        if not metric_cols or metric_cols == ["*"]:
            for col in list(identifiers.keys()) + list(dimensions.keys()) + list(measures.keys()):
                if _match_column_score(col, req_lower, tokens) > 0.0:
                    metric_cols = [col]
                    if col in dim_cols:
                        dim_cols.remove(col)
                    break
        if not metric_cols:
            metric_cols = ["*"]

    # 8. Detect temporal keywords and granularity
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

    # 9. Determine analytical goal
    trend_kws = {"trend", "over", "time", "timeline", "history", "monthly", "daily", "yearly", "quarterly"}
    comp_kws = {"compare", "comparison", "versus", "vs", "growth", "difference", "change"}
    dist_kws = {"distribution", "breakdown", "by", "categorize", "category", "share", "proportion"}
    rank_kws = {"top", "bottom", "highest", "lowest", "best", "worst", "rank", "ranking", "most", "least"}

    analytical_goal: Optional[str] = None
    if tokens & rank_kws or order_dir is not None:
        analytical_goal = "ranking"
    elif tokens & trend_kws:
        analytical_goal = "trend"
    elif tokens & comp_kws:
        analytical_goal = "comparison"
    elif tokens & dist_kws:
        analytical_goal = "distribution"
    elif metric_cols or dim_cols or is_count_request:
        analytical_goal = "aggregation"

    # 10. Visual preferences
    vis_keywords = {
        "bar": "bar",
        "line": "line",
        "pie": "pie",
        "donut": "donut",
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

    # 11. Comparison requirements
    comparison_req: Optional[str] = None
    if "previous year" in req_lower or "yoy" in req_lower:
        comparison_req = "year_over_year"
    elif "previous month" in req_lower or "mom" in req_lower:
        comparison_req = "month_over_month"

    # 12. Unresolved terms
    all_known_columns = set()
    for c in semantic_profile.column_evidences.keys():
        all_known_columns.update(_stem_word(c.lower()))
        for sub in re.findall(r"\b[a-z0-9]+\b", _normalize_name(c)):
            all_known_columns.update(_stem_word(sub))

    stopwords = {
        "show", "me", "the", "a", "an", "of", "for", "by", "in", "and", "or", "to",
        "give", "get", "what", "is", "are", "was", "were", "total", "average", "avg", "mean", "sum", "count",
        "median", "mode", "stddev", "stdev", "variance", "min", "max", "all", "top", "bottom", "per", "data",
        "report", "with", "over", "time", "numbers", "stats", "calculate", "calc", "find", "compute", "display",
        "plot", "list", "across", "between", "analyze", "analysis", "each", "every", "group", "grouped",
        "grouping", "compare", "comparison", "versus", "vs", "breakdown", "split", "looks", "look", "like", "tell",
        "explain", "describe", "see", "view", "chart", "graph", "highest", "lowest", "best", "worst",
        "which", "unit", "units", "more", "less", "where", "filter", "filtered", "having", "than", "equal",
        "equals", "at", "least", "most", "above", "below", "exceeding", "from", "how", "many", "much",
        "enrolled", "registered", "occurred", "happened", "observed", "measured", "recorded", "active",
        "completed", "current", "status", "has", "have", "had", "does", "do", "did", "can", "will",
        "would", "should", "taken", "placed", "differ", "differing", "difference", "value", "values",
        "score", "scores", "reading", "readings", "amount", "amounts", "rate", "rates", "level", "levels",
        "measure", "measures", "metric", "metrics", "number", "records", "rows", "column", "columns"
    }
    unresolved: List[str] = []
    for tok in tokens:
        tok_stems = _stem_word(tok)
        if (
            tok not in stopwords
            and tok not in granularity_keywords
            and tok not in vis_keywords
            and tok not in trend_kws
            and tok not in filter_tokens
            and not (tok_stems & all_known_columns)
            and not tok.isdigit()
        ):
            unresolved.append(tok)

    # 13. Compute confidence
    total_meaningful_tokens = len(tokens - stopwords)
    if total_meaningful_tokens > 0:
        matched_count = total_meaningful_tokens - len(unresolved)
        confidence = round(max(0.1, min(1.0, matched_count / total_meaningful_tokens)), 2)
    else:
        confidence = 0.85 if metric_cols or dim_cols else 0.5

    return StructuredIntent(
        original_request=cleaned_request,
        analytical_goal=analytical_goal,
        requested_metrics=metric_cols,
        requested_dimensions=dim_cols,
        temporal_scope=date_cols[0] if date_cols else None,
        grouping_granularity=detected_granularity,
        comparison_requirements=comparison_req,
        requested_visual_preferences=requested_visual,
        filters=[f.model_dump() for f in filter_specs],
        detected_filter_specs=filter_specs,
        order_by=order_by,
        order_direction=order_dir,
        limit=limit,
        unresolved_terms=unresolved,
        confidence=confidence,
    )
