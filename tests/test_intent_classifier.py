"""Unit tests for classify_intent_mode -- structural-signal intent classifier.

Tests are fully deterministic and do NOT require a live LLM, database, or
external service.  A lightweight synthetic DatasetSemanticProfile is built
inline so the function signature is satisfied; the classifier must NOT use it
for routing logic.

Coverage:
    DISCOVERY -- broad / overview / exploratory prompts
    FOCUSED   -- specific analytical queries with aggregation + grouping/filter
    EDGE      -- single-word, empty, ambiguous, multi-signal prompts
"""

from __future__ import annotations

import pytest

from intelligence.semantic_analyzer import ColumnSemanticEvidence, DatasetSemanticProfile
from ingestion.models import ColumnRole
from orchestrator.discovery import classify_intent_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(cols=None):
    """Build a minimal DatasetSemanticProfile for testing.

    The new classifier does NOT use column names for routing, so any schema
    works.  We provide a generic one to satisfy the function signature.
    """
    cols = cols or {
        "id": ColumnRole.IDENTIFIER,
        "value": ColumnRole.MEASURE,
        "category": ColumnRole.DIMENSION,
    }
    evidences = {
        col: ColumnSemanticEvidence(
            column_name=col,
            candidate_role=role,
            confidence=0.9,
            confidence_level="HIGH",
            evidence=["synthetic"],
        )
        for col, role in cols.items()
    }
    return DatasetSemanticProfile(dataset_id="test_ds", column_evidences=evidences)


PROFILE = _make_profile()


# ---------------------------------------------------------------------------
# DISCOVERY cases -- must route to "discovery"
# ---------------------------------------------------------------------------

DISCOVERY_PROMPTS = [
    # Empty / blank
    "",
    "   ",
    # Single words / ultra-short
    "dashboard",
    "insights",
    "data",
    # Classic overview phrasing
    "Give me an overview of this dataset.",
    "Give me an overview of my data.",
    "overview",
    "Overview of this data",
    "data overview",
    # Broad natural-language exploration
    "What are the most important things I should know from this data?",
    "What are the key insights in this data?",
    "Show me the most useful trends and comparisons.",
    "Analyze this dataset.",
    "What can you tell me about this data?",
    "What does this data show?",
    "Explore the data.",
    "Explore this data",
    "Describe the dataset.",
    "Explain the patterns in this data.",
    "Summarize this dataset.",
    "Build me a useful dashboard.",
    "Build a dashboard for this data.",
    "Generate a dashboard for this dataset.",
    "Create a dashboard on this data.",
    "Make a dashboard from this data.",
    "Give me a dashboard.",
    # Topic-scoped -- still exploratory (no aggregation verb + grouping)
    "Key insights",
    "Top insights",
    "All metrics",
    "Everything in this dataset",
    "What should I know about this?",
    "Tell me about this dataset.",
    "Quick look at this data",
    "High level summary",
    "High-level view",
    "At a glance",
    "Snapshot of the data",
    # Broad slice without an aggregation verb -- still exploratory
    "Show me data by region",
    "Break it down by category",
    "Data across departments",
    "Filter by active status",
]


@pytest.mark.parametrize("prompt", DISCOVERY_PROMPTS)
def test_discovery_routing(prompt):
    mode, _ = classify_intent_mode(prompt, PROFILE)
    assert mode == "discovery", f"Expected 'discovery' for: {prompt!r}"


# ---------------------------------------------------------------------------
# FOCUSED cases -- must route to "focused"
# ---------------------------------------------------------------------------

FOCUSED_PROMPTS = [
    # Aggregation + grouping
    "Total amount by customer_name",
    "Average salary by department",
    "Count of orders by region",
    "Sum of revenue per category",
    "How many records per month?",
    "What is the average score by grade?",
    "Total sales across each region",
    "Maximum temperature by sensor",
    "Minimum delivery time per route",
    # Aggregation + filter
    "Total revenue where status is active",
    "Count of patients where age is above 65",
    "Average cost for the top 10 items",
    "Sum of hours for the highest earners",
    # Aggregation + comparison
    "Compare average salary between male and female employees",
    "Average score vs department",
    "Total revenue compared to last year",
    # Single-metric questions (aggregation, no slice)
    "What is the total revenue?",
    "How many rows are there?",
    "What is the mean value?",
    "Calculate the median delivery time",
    "Compute the percentage of late orders",
]


@pytest.mark.parametrize("prompt", FOCUSED_PROMPTS)
def test_focused_routing(prompt):
    mode, _ = classify_intent_mode(prompt, PROFILE)
    assert mode == "focused", f"Expected 'focused' for: {prompt!r}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_none_intent_is_discovery():
    mode, topic = classify_intent_mode(None, PROFILE)
    assert mode == "discovery"
    assert topic is None


def test_empty_string_is_discovery():
    mode, _ = classify_intent_mode("", PROFILE)
    assert mode == "discovery"


def test_whitespace_only_is_discovery():
    mode, _ = classify_intent_mode("   \t\n  ", PROFILE)
    assert mode == "discovery"


def test_single_word_no_signal_is_discovery():
    """A single unrecognised word carries no structural signals -> discovery."""
    mode, _ = classify_intent_mode("abcxyz", PROFILE)
    assert mode == "discovery"


def test_aggregation_plus_grouping_is_focused():
    mode, _ = classify_intent_mode("sum of sales by region", PROFILE)
    assert mode == "focused"


def test_grouping_without_aggregation_is_discovery():
    """'Show data by region' has grouping but no aggregation verb -> discovery."""
    mode, _ = classify_intent_mode("show data by region", PROFILE)
    assert mode == "discovery"


def test_classifier_does_not_use_column_names():
    """Domain-agnosticity: routing must be identical across two different schemas."""
    profile_a = _make_profile({"salary": ColumnRole.MEASURE, "dept": ColumnRole.DIMENSION})
    profile_b = _make_profile({"temperature": ColumnRole.MEASURE, "sensor_id": ColumnRole.IDENTIFIER})
    intent = "Give me an overview of this dataset."
    mode_a, _ = classify_intent_mode(intent, profile_a)
    mode_b, _ = classify_intent_mode(intent, profile_b)
    assert mode_a == mode_b == "discovery"


def test_discovery_anchor_beats_aggregation_word():
    """An anchor phrase beats an incidental aggregation word in the same string.

    'Summarize the total revenue trends' -- 'summarize' is a discovery anchor
    so the result must still be DISCOVERY even though 'total' is present.
    """
    mode, _ = classify_intent_mode("Summarize the total revenue trends", PROFILE)
    assert mode == "discovery"


def test_overview_anchor_takes_priority():
    """'overview' anchor wins even when aggregation + grouping words also appear."""
    mode, _ = classify_intent_mode(
        "Give me an overview of how the average salary compares by department",
        PROFILE,
    )
    assert mode == "discovery"


def test_case_insensitivity():
    """Routing must be case-insensitive."""
    cases = [
        ("GIVE ME AN OVERVIEW", "discovery"),
        ("TOTAL AMOUNT BY CUSTOMER", "focused"),
        ("Average Score By Grade", "focused"),
        ("Analyze This Dataset", "discovery"),
    ]
    for prompt, expected in cases:
        mode, _ = classify_intent_mode(prompt, PROFILE)
        assert mode == expected, f"{prompt!r}: expected {expected!r}, got {mode!r}"


def test_punctuation_tolerance():
    """Commas and question marks must not break routing."""
    mode, _ = classify_intent_mode(
        "What is the total revenue, broken down by department?",
        PROFILE,
    )
    assert mode == "focused"


# ---------------------------------------------------------------------------
# Adversarial regression tests -- cases found during checkpoint validation
# ---------------------------------------------------------------------------

# FOCUSED: rhetorical question starters + aggregation + grouping
ADVERSARIAL_FOCUSED = [
    "What are the total sales by region?",
    "What are the average marks by department?",
    "What are the maximum temperatures by device?",
    "Show me what revenue is by region",
    "Show me what salary looks like by department",
    "What are the total orders by month?",
    "Tell me the average salary by department",
    "Explain the average temperature by device",
    "Describe total revenue by region",
    "What is the total revenue by region?",
    "Show me the average delivery time by destination",
    "Compare average salary across departments",
    # Boundary: implicit aggregation nouns + grouping
    "What are the trends in sales by region?",
    "Show me the trends in revenue by month",
    "Explain the distribution of salary by department",
]


@pytest.mark.parametrize("prompt", ADVERSARIAL_FOCUSED)
def test_adversarial_focused(prompt):
    """Adversarial focused cases must not be misclassified as discovery."""
    mode, _ = classify_intent_mode(prompt, PROFILE)
    assert mode == "focused", f"Expected 'focused' for adversarial prompt: {prompt!r}"


# DISCOVERY: broad importance queries and exploration phrases
ADVERSARIAL_DISCOVERY = [
    "What are the most important things I should know from this data?",
    "What are the key insights in this dataset?",
    "Show me what matters in this data",
    "Tell me what is important in this dataset",
    "Explain this dataset",
    "Describe the important patterns in this data",
    "What can you tell me about this dataset?",
    "Give me an overview of this dataset",
    "Build a useful dashboard from this data",
    "Explore this dataset",
]


@pytest.mark.parametrize("prompt", ADVERSARIAL_DISCOVERY)
def test_adversarial_discovery(prompt):
    """Adversarial discovery cases must not be misclassified as focused."""
    mode, _ = classify_intent_mode(prompt, PROFILE)
    assert mode == "discovery", f"Expected 'discovery' for adversarial prompt: {prompt!r}"


def test_strong_anchor_beats_agg_and_filter():
    """'most important' is a strong anchor and must win over 'most' filter + 'what are the' agg."""
    mode, _ = classify_intent_mode(
        "What are the most important things I should know from this data?",
        PROFILE,
    )
    assert mode == "discovery"


def test_show_me_what_plus_grouping_is_focused():
    """'Show me what X is by Y' contains an implicit retrieval request + grouping -> focused."""
    mode, _ = classify_intent_mode("Show me what revenue is by region", PROFILE)
    assert mode == "focused"


def test_analytical_noun_plus_grouping_is_focused():
    """Analytical dimensional nouns (trends, distribution) + grouping -> focused."""
    assert classify_intent_mode("What are the trends in sales by region?", PROFILE)[0] == "focused"
    assert classify_intent_mode("Explain the distribution of salary by department", PROFILE)[0] == "focused"
    assert classify_intent_mode("Show me the trends in revenue by month", PROFILE)[0] == "focused"


def test_explain_without_slice_is_discovery():
    """'explain' alone (no grouping) must remain discovery."""
    mode, _ = classify_intent_mode("Explain this dataset", PROFILE)
    assert mode == "discovery"


def test_describe_without_slice_is_discovery():
    """'describe' alone (no grouping) must remain discovery."""
    mode, _ = classify_intent_mode("Describe the important patterns in this data", PROFILE)
    assert mode == "discovery"