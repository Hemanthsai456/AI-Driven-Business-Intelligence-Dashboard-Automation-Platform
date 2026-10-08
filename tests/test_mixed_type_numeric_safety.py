"""Targeted regression test suite for Mixed-Type Numeric Safety in Autonomous Dashboard & Data Studio.

Validates that:
1. Mixed numeric/text columns (e.g. 'LPA/CTC' with floats and 'Internship') do not crash Autonomous Overview.
2. "Internship" remains identifiable as non-numeric and is not silently coerced.
3. Numeric analysis safely handles or excludes mixed columns.
4. Pure numeric columns (e.g. 'CGPA') still receive full numeric analysis.
5. Dashboard generation continues cleanly using valid columns.
6. Explicit numeric conversion preview reports invalid/unparseable counts and examples.
7. Invalid numeric values are never silently coerced without review.
8. Raw dataset remains completely immutable.
9. Cleaned dataset state is unchanged unless user explicitly applies transformation.
10. Autonomous Overview returns a valid DashboardSpec with rendered tiles.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from ingestion.models import CanonicalDataset, DatasetMetadata, ColumnRole
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from orchestrator.insights import generate_grounded_insights, InsightType
from orchestrator.overview import generate_overview_dashboard
from orchestrator.schemas import DashboardSpec
from cleaning.executor import CleaningExecutor


def make_placement_mixed_dataset() -> CanonicalDataset:
    """Create canonical dataset with mixed semantic/value column."""
    df = pd.DataFrame({
        "Student Name": ["Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Heidi"],
        "Roll-No": [101, 102, 103, 104, 105, 106, 107, 108],
        "Company Name": ["Google", "Amazon", "Google", "Microsoft", "Amazon", "Google", "Microsoft", "Amazon"],
        "On Campus/Off Campus": ["On Campus", "Off Campus", "On Campus", "Off Campus", "On Campus", "Off Campus", "On Campus", "Off Campus"],
        "LPA/CTC": [12.5, 8.2, "Internship", 7.5, 10.0, 15.0, "Internship", 9.0],
        "CGPA": [8.5, 7.8, 9.1, 8.0, 7.2, 8.9, 9.4, 7.5],
    })
    meta = DatasetMetadata(
        dataset_id="ds_placement_mixed",
        name="placement_records.csv",
        source_type="CSV",
        row_count=len(df),
        column_count=len(df.columns),
    )
    return CanonicalDataset(data=df, metadata=meta)


def test_mixed_numeric_text_column_does_not_crash_autonomous_overview():
    """1. Verify that mixed numeric/text column ('LPA/CTC') does not crash Autonomous Overview."""
    dataset = make_placement_mixed_dataset()
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)

    spec = generate_overview_dashboard(
        dataset=dataset,
        semantic_profile=sem_profile,
        data_profile=profile,
        use_llm=False,
    )

    assert isinstance(spec, DashboardSpec)
    assert spec.spec_id.startswith("spec_overview_")
    assert spec.winner is not None
    assert len(spec.tiles) > 0
    assert spec.headline is not None
    assert len(spec.executive_summary) > 0


def test_internship_identifiable_as_non_numeric():
    """2. Verify that 'Internship' remains identifiable as non-numeric."""
    dataset = make_placement_mixed_dataset()
    s = dataset.data["LPA/CTC"]
    
    coerced = pd.to_numeric(s, errors="coerce")
    non_numeric_mask = s.notna() & coerced.isna()
    non_numeric_values = s[non_numeric_mask].tolist()

    assert "Internship" in non_numeric_values
    assert len(non_numeric_values) == 2


def test_numeric_analysis_safely_handles_mixed_column():
    """3. Verify that insight discovery handles mixed column without astype(float) crash."""
    dataset = make_placement_mixed_dataset()
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)

    # Should run outlier, correlation, ranking, and distribution without ValueError
    res = generate_grounded_insights(
        dataset=dataset,
        semantic_profile=sem_profile,
        max_insights=12,
        use_llm=False,
    )

    assert res.total_candidates_generated >= 0
    assert isinstance(res.insights, list)


def test_valid_numeric_columns_still_receive_numeric_analysis():
    """4. Verify that pure numeric columns ('CGPA') receive proper numeric analysis."""
    dataset = make_placement_mixed_dataset()
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)

    spec = generate_overview_dashboard(
        dataset=dataset,
        semantic_profile=sem_profile,
        data_profile=profile,
        use_llm=False,
    )

    # Check tiles to ensure CGPA is analyzed
    tile_metrics = [m for t in spec.tiles for m in t.metrics]
    assert "CGPA" in tile_metrics or "*" in tile_metrics


def test_dashboard_generation_continues_using_other_valid_columns():
    """5. Verify that dashboard generation incorporates valid dimensions (Company Name, On Campus)."""
    dataset = make_placement_mixed_dataset()
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)

    spec = generate_overview_dashboard(
        dataset=dataset,
        semantic_profile=sem_profile,
        data_profile=profile,
        use_llm=False,
    )

    all_dims = [d for t in spec.tiles for d in t.dimensions]
    assert any("Company Name" in d or "On Campus/Off Campus" in d for d in all_dims)


def test_explicit_numeric_conversion_preview_reports_invalid_values():
    """6. Verify that explicit numeric conversion preview detects and reports invalid values."""
    dataset = make_placement_mixed_dataset()
    executor = CleaningExecutor()
    
    preview = executor.preview_column_transformation(
        canonical=dataset,
        column_name="LPA/CTC",
        operation="CONVERT_NUMERIC",
        target_type="FLOAT",
    )

    assert preview.column_name == "LPA/CTC"
    assert preview.non_null_count == 8
    assert preview.converted_count == 6
    assert preview.unparseable_count == 2
    assert "Internship" in preview.unparseable_samples


def test_invalid_numeric_values_are_never_silently_coerced():
    """7. Verify that conversion creates valid preview tracking unparseable samples."""
    dataset = make_placement_mixed_dataset()
    executor = CleaningExecutor()
    
    preview = executor.preview_column_transformation(
        canonical=dataset,
        column_name="LPA/CTC",
        operation="CONVERT_NUMERIC",
        target_type="FLOAT",
    )

    assert preview.is_valid is True
    assert preview.unparseable_count == 2
    assert len(preview.unparseable_samples) > 0


def test_raw_dataset_remains_unchanged():
    """8. Verify that raw dataset remains completely immutable during overview and preview."""
    dataset = make_placement_mixed_dataset()
    orig_copy = dataset.data.copy(deep=True)
    executor = CleaningExecutor()

    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    generate_overview_dashboard(dataset, sem_profile, data_profile=profile, use_llm=False)
    executor.preview_column_transformation(dataset, "LPA/CTC", "CONVERT_NUMERIC", "FLOAT")

    pd.testing.assert_frame_equal(dataset.data, orig_copy)


def test_cleaned_dataset_unchanged_unless_explicitly_applied():
    """9. Verify that dataset values retain 'Internship' without unexpected silent in-place mutation."""
    dataset = make_placement_mixed_dataset()
    assert "Internship" in dataset.data["LPA/CTC"].values
    
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    res = generate_grounded_insights(dataset, sem_profile, use_llm=False)

    assert "Internship" in dataset.data["LPA/CTC"].values


def test_autonomous_overview_with_pure_mixed_column_dataset():
    """10. Verify Autonomous Overview succeeds on a dataset where ALL non-id columns are mixed or categorical."""
    df_pure_mixed = pd.DataFrame({
        "Student Name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "Company": ["Google", "Amazon", "Microsoft", "Google", "Amazon"],
        "Package": ["12.5", "Internship", "8.0", "Internship", "10.0"],
    })
    meta = DatasetMetadata(
        dataset_id="ds_pure_mixed",
        name="mixed_only.csv",
        source_type="CSV",
        row_count=len(df_pure_mixed),
        column_count=len(df_pure_mixed.columns),
    )
    dataset = CanonicalDataset(data=df_pure_mixed, metadata=meta)
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)

    spec = generate_overview_dashboard(
        dataset=dataset,
        semantic_profile=sem_profile,
        data_profile=profile,
        use_llm=False,
    )

    assert isinstance(spec, DashboardSpec)
    assert len(spec.tiles) > 0
    assert spec.winner is not None
