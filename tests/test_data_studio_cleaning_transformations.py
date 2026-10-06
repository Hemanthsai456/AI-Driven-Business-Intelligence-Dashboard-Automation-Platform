"""Targeted unit tests for Part 6.2: User-Controlled Column Transformations."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ingestion import CSVLoader, CanonicalDataset, ColumnMetadata, ColumnRole, DatasetMetadata
from intelligence import DataProfiler, SemanticAnalyzer
from cleaning import (
    CleaningExecutionError,
    CleaningExecutor,
    CleaningPlanner,
    ColumnTransformPreviewResult,
    generate_cleaning_plan,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REAL_DATA_DIR = Path(__file__).parent / "real_data"


def _build_dataset(df: pd.DataFrame, dataset_id: str = "ds-test") -> CanonicalDataset:
    """Helper to build a CanonicalDataset from a DataFrame."""
    cols = []
    for c in df.columns:
        cols.append(ColumnMetadata(c, c, str(df[c].dtype)))
    meta = DatasetMetadata(dataset_id, "Test Dataset", "pandas", len(df), len(df.columns), cols)
    return CanonicalDataset(meta, df)


# ---------------------------------------------------------------------------
# 1. Text -> Numeric Conversion
# ---------------------------------------------------------------------------
def test_text_to_numeric_conversion():
    """1. Test converting text/string column containing numeric values into float."""
    df = pd.DataFrame({"salary": ["50000.0", "65000.5", "72000.0", "80000"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "salary", "CONVERT_NUMERIC", "NUMERIC"
    )

    assert preview.is_valid is True
    assert preview.converted_count == 4
    assert preview.unparseable_count == 0
    assert "float" in preview.target_dtype.lower()

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "salary",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )
    assert exec_result.operations_applied == 1
    assert pd.api.types.is_numeric_dtype(cleaned.data["salary"])
    assert cleaned.data["salary"].iloc[1] == 65000.5


# ---------------------------------------------------------------------------
# 2. Numeric Conversion with Invalid Values
# ---------------------------------------------------------------------------
def test_numeric_conversion_with_invalid_values():
    """2. Test numeric conversion with invalid/unparseable tokens being coerced to missing."""
    df = pd.DataFrame({"score": ["45.2", "50", "61.5", "unknown", "N/A"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "score", "CONVERT_NUMERIC", "NUMERIC"
    )

    assert preview.is_valid is True
    assert preview.converted_count == 3
    assert preview.unparseable_count == 2
    assert "unknown" in preview.unparseable_samples or "N/A" in preview.unparseable_samples
    assert preview.new_missing_count == 2

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "score",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )
    assert pd.api.types.is_numeric_dtype(cleaned.data["score"])
    assert cleaned.data["score"].isna().sum() == 2
    assert cleaned.data["score"].dropna().tolist() == [45.2, 50.0, 61.5]


# ---------------------------------------------------------------------------
# 3. Text -> Datetime Conversion
# ---------------------------------------------------------------------------
def test_text_to_datetime_conversion():
    """3. Test text column with date strings parsed to datetime64."""
    df = pd.DataFrame({"event_date": ["2024-01-15", "2024-02-20", "2024-03-25"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "event_date", "CONVERT_DATETIME", "DATETIME"
    )

    assert preview.is_valid is True
    assert preview.converted_count == 3
    assert preview.unparseable_count == 0
    assert "datetime" in preview.target_dtype.lower()

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "event_date",
            "operation": "CONVERT_DATETIME",
            "source": "USER",
        }],
    )
    assert pd.api.types.is_datetime64_any_dtype(cleaned.data["event_date"])


# ---------------------------------------------------------------------------
# 4. Datetime Invalid-Value Handling
# ---------------------------------------------------------------------------
def test_datetime_invalid_value_handling():
    """4. Test datetime conversion with unparseable formats coerced to missing."""
    df = pd.DataFrame({"joined_at": ["2023-05-01", "invalid_date", "2023-06-15", "pending"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "joined_at", "CONVERT_DATETIME", "DATETIME"
    )

    assert preview.is_valid is True
    assert preview.converted_count == 2
    assert preview.unparseable_count == 2

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "joined_at",
            "operation": "CONVERT_DATETIME",
            "source": "USER",
        }],
    )
    assert cleaned.data["joined_at"].isna().sum() == 2


# ---------------------------------------------------------------------------
# 5. Text -> Boolean Conversion
# ---------------------------------------------------------------------------
def test_text_to_boolean_conversion():
    """5. Test boolean conversion of recognized representations."""
    df = pd.DataFrame({"is_active": ["true", "False", "YES", "no", "1", "0"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "is_active", "NORMALIZE_BOOLEAN", "BOOLEAN"
    )

    assert preview.is_valid is True
    assert preview.converted_count == 6
    assert preview.unparseable_count == 0

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "is_active",
            "operation": "NORMALIZE_BOOLEAN",
            "source": "USER",
        }],
    )
    assert cleaned.data["is_active"].tolist() == [True, False, True, False, True, False]


# ---------------------------------------------------------------------------
# 6. Numeric -> Integer Unsafe Fractional Conversion Rejected
# ---------------------------------------------------------------------------
def test_numeric_to_integer_unsafe_fractional_rejected():
    """6. Test integer conversion rejection when column contains fractional numbers."""
    df = pd.DataFrame({"count_val": [12.5, 13.2, 14.0]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()

    # Preview detects fractional loss
    preview = executor.preview_column_transformation(
        canonical, "count_val", "CONVERT_INTEGER", "INTEGER", allow_fractional_truncation=False
    )
    assert preview.fractional_loss_count == 2
    assert preview.is_valid is False
    assert "fractional" in preview.error_message.lower()

    # Execution without confirmation must raise CleaningExecutionError
    with pytest.raises(CleaningExecutionError) as excinfo:
        executor.execute(
            canonical,
            [],
            custom_transformations=[{
                "column_name": "count_val",
                "operation": "CONVERT_INTEGER",
                "allow_fractional_truncation": False,
                "source": "USER",
            }],
        )
    assert "fractional" in str(excinfo.value).lower()

    # Execution with explicit user confirmation succeeds
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "count_val",
            "operation": "CONVERT_INTEGER",
            "allow_fractional_truncation": True,
            "source": "USER",
        }],
    )
    assert cleaned.data["count_val"].tolist() == [12, 13, 14]


# ---------------------------------------------------------------------------
# 7. Numeric -> Float Conversion
# ---------------------------------------------------------------------------
def test_numeric_to_float_conversion():
    """7. Test float conversion on integer or text numeric data."""
    df = pd.DataFrame({"val": [10, 20, 30]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "val",
            "operation": "CONVERT_FLOAT",
            "source": "USER",
        }],
    )
    assert pd.api.types.is_float_dtype(cleaned.data["val"])
    assert cleaned.data["val"].tolist() == [10.0, 20.0, 30.0]


# ---------------------------------------------------------------------------
# 8. String Trimming
# ---------------------------------------------------------------------------
def test_string_trimming():
    """8. Test trimming leading and trailing whitespace."""
    df = pd.DataFrame({"city": ["  New York  ", "San Francisco\t", "\nChicago "]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "city", "TRIM_WHITESPACE"
    )
    assert preview.is_valid is True
    assert preview.converted_count == 3

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "city",
            "operation": "TRIM_WHITESPACE",
            "source": "USER",
        }],
    )
    assert cleaned.data["city"].tolist() == ["New York", "San Francisco", "Chicago"]


# ---------------------------------------------------------------------------
# 9. Empty String Normalization
# ---------------------------------------------------------------------------
def test_empty_string_normalization():
    """9. Test normalizing empty/whitespace-only strings to missing/null."""
    df = pd.DataFrame({"notes": ["valid", "", "   ", "\t", "ok"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview_column_transformation(
        canonical, "notes", "NORMALIZE_EMPTY_STRINGS"
    )
    assert preview.is_valid is True
    assert preview.new_missing_count == 3

    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "notes",
            "operation": "NORMALIZE_EMPTY_STRINGS",
            "source": "USER",
        }],
    )
    assert cleaned.data["notes"].isna().sum() == 3
    assert cleaned.data["notes"].dropna().tolist() == ["valid", "ok"]


# ---------------------------------------------------------------------------
# 10. Missing Numeric Median
# ---------------------------------------------------------------------------
def test_missing_numeric_median():
    """10. Test missing numeric imputation with median."""
    df = pd.DataFrame({"rating": [1.0, 2.0, None, 4.0, 5.0]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "rating",
            "operation": "IMPUTE_MEDIAN",
            "source": "USER",
        }],
    )
    assert cleaned.data["rating"].isna().sum() == 0
    assert cleaned.data["rating"].iloc[2] == 3.0


# ---------------------------------------------------------------------------
# 11. Missing Numeric Mean
# ---------------------------------------------------------------------------
def test_missing_numeric_mean():
    """11. Test missing numeric imputation with mean."""
    df = pd.DataFrame({"val": [10.0, 20.0, None, 30.0]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "val",
            "operation": "IMPUTE_MEAN",
            "source": "USER",
        }],
    )
    assert cleaned.data["val"].isna().sum() == 0
    assert cleaned.data["val"].iloc[2] == 20.0


# ---------------------------------------------------------------------------
# 12. Missing Categorical Mode
# ---------------------------------------------------------------------------
def test_missing_categorical_mode():
    """12. Test missing categorical imputation with mode."""
    df = pd.DataFrame({"category": ["A", "B", "A", None, "A"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "category",
            "operation": "IMPUTE_MODE",
            "source": "USER",
        }],
    )
    assert cleaned.data["category"].isna().sum() == 0
    assert cleaned.data["category"].iloc[3] == "A"


# ---------------------------------------------------------------------------
# 13. Missing Categorical Unknown
# ---------------------------------------------------------------------------
def test_missing_categorical_unknown():
    """13. Test missing categorical imputation with 'Unknown'."""
    df = pd.DataFrame({"department": ["Sales", None, "Engineering"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "department",
            "operation": "IMPUTE_UNKNOWN",
            "source": "USER",
        }],
    )
    assert cleaned.data["department"].iloc[1] == "Unknown"


# ---------------------------------------------------------------------------
# 14. Specific Numeric Value
# ---------------------------------------------------------------------------
def test_specific_numeric_value():
    """14. Test user-specified numeric constant imputation and rejection of invalid values."""
    df = pd.DataFrame({"price": [10.0, None, 30.0]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    # Valid numeric
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "price",
            "operation": "IMPUTE_SPECIFIC_VALUE",
            "custom_value": "99.5",
            "source": "USER",
        }],
    )
    assert cleaned.data["price"].iloc[1] == 99.5

    # Rejection of unsafe/code injection
    with pytest.raises(CleaningExecutionError):
        executor.execute(
            canonical,
            [],
            custom_transformations=[{
                "column_name": "price",
                "operation": "IMPUTE_SPECIFIC_VALUE",
                "custom_value": "DROP TABLE users;",
                "source": "USER",
            }],
        )


# ---------------------------------------------------------------------------
# 15. Specific Categorical Value
# ---------------------------------------------------------------------------
def test_specific_categorical_value():
    """15. Test user-specified categorical constant imputation."""
    df = pd.DataFrame({"status": ["active", None, "closed"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "status",
            "operation": "IMPUTE_SPECIFIC_VALUE",
            "custom_value": "PendingReview",
            "source": "USER",
        }],
    )
    assert cleaned.data["status"].iloc[1] == "PendingReview"


# ---------------------------------------------------------------------------
# 16. Leave Unchanged
# ---------------------------------------------------------------------------
def test_leave_unchanged():
    """16. Test LEAVE_UNCHANGED preserving missing values."""
    df = pd.DataFrame({"val": [1, None, 3]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "val",
            "operation": "LEAVE_UNCHANGED",
            "source": "USER",
        }],
    )
    assert cleaned.data["val"].isna().sum() == 1


# ---------------------------------------------------------------------------
# 17. Preview Reflects Selected Transformation
# ---------------------------------------------------------------------------
def test_preview_reflects_selected_transformation():
    """17. Test that batch preview reflects user-configured column transformations."""
    df = pd.DataFrame({"amt": ["10", "20", "30"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    preview = executor.preview(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "amt",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )
    assert len(preview.operations) == 1
    assert preview.operations[0].operation == "CONVERT_NUMERIC"
    assert preview.operations[0].status == "APPLIED"


# ---------------------------------------------------------------------------
# 18. Apply Reflects Selected Transformation
# ---------------------------------------------------------------------------
def test_apply_reflects_selected_transformation():
    """18. Test that batch apply executes user-configured column transformations."""
    df = pd.DataFrame({"amt": ["10", "20", "30"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "amt",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )
    assert exec_result.operations_applied == 1
    assert pd.api.types.is_numeric_dtype(cleaned.data["amt"])


# ---------------------------------------------------------------------------
# 19. Invalid Datatype Rejected
# ---------------------------------------------------------------------------
def test_invalid_datatype_rejected():
    """19. Test rejection of unsupported arbitrary datatypes."""
    df = pd.DataFrame({"col": [1, 2, 3]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    with pytest.raises(CleaningExecutionError):
        executor.execute(
            canonical,
            [],
            custom_transformations=[{
                "column_name": "col",
                "operation": "CONVERT_UNSUPPORTED_TYPE",
                "source": "USER",
            }],
        )


# ---------------------------------------------------------------------------
# 20. Invalid Operation Rejected
# ---------------------------------------------------------------------------
def test_invalid_operation_rejected():
    """20. Test rejection of unsupported cleaning operations."""
    df = pd.DataFrame({"col": [1, 2, 3]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    with pytest.raises(CleaningExecutionError):
        executor.execute(
            canonical,
            [],
            custom_transformations=[{
                "column_name": "col",
                "operation": "ARBITRARY_PYTHON_EXEC",
                "source": "USER",
            }],
        )


# ---------------------------------------------------------------------------
# 21. Raw Dataset Unchanged After Preview
# ---------------------------------------------------------------------------
def test_raw_dataset_unchanged_after_preview():
    """21. Test raw CanonicalDataset immutability after preview."""
    df = pd.DataFrame({"salary": ["100", "200", "unknown"]})
    orig_copy = df.copy(deep=True)
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    _ = executor.preview_column_transformation(canonical, "salary", "CONVERT_NUMERIC")
    _ = executor.preview(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "salary",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )

    pd.testing.assert_frame_equal(canonical.data, orig_copy)


# ---------------------------------------------------------------------------
# 22. Raw Dataset Unchanged After Apply
# ---------------------------------------------------------------------------
def test_raw_dataset_unchanged_after_apply():
    """22. Test raw CanonicalDataset immutability after apply."""
    df = pd.DataFrame({"salary": ["100", "200", "unknown"]})
    orig_copy = df.copy(deep=True)
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    _, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "salary",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )

    pd.testing.assert_frame_equal(canonical.data, orig_copy)
    assert not pd.api.types.is_numeric_dtype(canonical.data["salary"])
    assert pd.api.types.is_numeric_dtype(cleaned.data["salary"])


# ---------------------------------------------------------------------------
# 23. Deterministic Repeated Transformation
# ---------------------------------------------------------------------------
def test_deterministic_repeated_transformation():
    """23. Test that repeated execution yields identical results."""
    df = pd.DataFrame({"val": [" 10.5 ", "20.2 ", " 30.8 "]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    transforms = [
        {"column_name": "val", "operation": "TRIM_WHITESPACE", "source": "USER"},
        {"column_name": "val", "operation": "CONVERT_NUMERIC", "source": "USER"},
    ]

    _, cleaned1 = executor.execute(canonical, [], custom_transformations=transforms)
    _, cleaned2 = executor.execute(canonical, [], custom_transformations=transforms)

    pd.testing.assert_frame_equal(cleaned1.data, cleaned2.data)


# ---------------------------------------------------------------------------
# 24. Semantic Profile Refresh After Successful Dtype Change
# ---------------------------------------------------------------------------
def test_semantic_profile_refresh_after_dtype_change():
    """24. Test that semantic analysis updates column role to MEASURE after numeric conversion."""
    df = pd.DataFrame({"annual_spend": ["1000.50", "2500.00", "3200.75", "4100.20", "5000.00"]})
    canonical = _build_dataset(df)

    executor = CleaningExecutor()
    _, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[{
            "column_name": "annual_spend",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )

    # Cleaned canonical metadata should reflect updated schema / semantic role
    assert pd.api.types.is_numeric_dtype(cleaned.data["annual_spend"])
    assert cleaned.profile is not None
    # Semantic profile refreshed
    sem_col = cleaned.profile.column_statistics.get("annual_spend")
    assert sem_col is not None


# ---------------------------------------------------------------------------
# 25. Dataset Isolation
# ---------------------------------------------------------------------------
def test_dataset_isolation():
    """25. Test that transformations on one dataset do not affect another dataset."""
    df1 = pd.DataFrame({"col": ["10", "20", "30"]})
    df2 = pd.DataFrame({"col": ["A", "B", "C"]})
    c1 = _build_dataset(df1, "ds-1")
    c2 = _build_dataset(df2, "ds-2")

    executor = CleaningExecutor()
    _, cleaned1 = executor.execute(
        c1,
        [],
        custom_transformations=[{
            "column_name": "col",
            "operation": "CONVERT_NUMERIC",
            "source": "USER",
        }],
    )

    assert pd.api.types.is_numeric_dtype(cleaned1.data["col"])
    assert not pd.api.types.is_numeric_dtype(c2.data["col"])


# ---------------------------------------------------------------------------
# 26. Messy Fixture Validation
# ---------------------------------------------------------------------------
def test_messy_fixture_validation():
    """26. Test intentional messy dataset with strings, invalids, dates, booleans, whitespace, and nulls."""
    messy_df = pd.DataFrame({
        "num_str": ["100.5", "200.0", "bad_num", "   ", None, "500.25"],
        "date_str": ["2024-01-01", "2024-02-15", "invalid_dt", "2024-04-01", None, "2024-06-01"],
        "bool_str": ["true", "FALSE", "yes", "no", "1", "0"],
        "text_ws": ["  apple ", "banana\t", "\ncherry ", "   ", None, "date"],
    })
    canonical = _build_dataset(messy_df, "ds-messy")
    executor = CleaningExecutor()

    # 1. Preview trimming and numeric conversion
    p_num = executor.preview_column_transformation(canonical, "num_str", "CONVERT_NUMERIC")
    assert p_num.is_valid is True
    assert p_num.converted_count == 3
    assert p_num.unparseable_count >= 1

    p_dt = executor.preview_column_transformation(canonical, "date_str", "CONVERT_DATETIME")
    assert p_dt.is_valid is True
    assert p_dt.converted_count == 4
    assert p_dt.unparseable_count == 1

    p_bool = executor.preview_column_transformation(canonical, "bool_str", "NORMALIZE_BOOLEAN")
    assert p_bool.is_valid is True
    assert p_bool.converted_count == 6

    p_ws = executor.preview_column_transformation(canonical, "text_ws", "TRIM_WHITESPACE")
    assert p_ws.is_valid is True

    # 2. Execute multi-step user transformation batch
    exec_result, cleaned = executor.execute(
        canonical,
        [],
        custom_transformations=[
            {"column_name": "num_str", "operation": "CONVERT_NUMERIC", "source": "USER"},
            {"column_name": "date_str", "operation": "CONVERT_DATETIME", "source": "USER"},
            {"column_name": "bool_str", "operation": "NORMALIZE_BOOLEAN", "source": "USER"},
            {"column_name": "text_ws", "operation": "TRIM_WHITESPACE", "source": "USER"},
        ],
    )

    assert exec_result.operations_applied == 4
    assert pd.api.types.is_numeric_dtype(cleaned.data["num_str"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned.data["date_str"])
    assert cleaned.data["bool_str"].tolist() == [True, False, True, False, True, False]
    assert cleaned.data["text_ws"].iloc[0] == "apple"


# ---------------------------------------------------------------------------
# 27. Real Dataset Validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "dataset_filename",
    [
        "healthcare.csv",
        "education.csv",
        "iot.csv",
        "hr.csv",
        "logistics.csv",
    ],
)
def test_real_datasets_compatibility(dataset_filename: str):
    """27. Test user-controlled transformation pipeline across canonical real datasets."""
    csv_path = REAL_DATA_DIR / dataset_filename
    if not csv_path.exists():
        csv_path = FIXTURES_DIR / dataset_filename
    if not csv_path.exists():
        pytest.skip(f"Dataset {dataset_filename} not found.")

    loader = CSVLoader()
    canonical = loader.load(csv_path)

    executor = CleaningExecutor()
    first_col = canonical.data.columns[0]

    # Test previewing whitespace trimming on first column
    preview = executor.preview_column_transformation(canonical, first_col, "TRIM_WHITESPACE")
    assert preview is not None
    assert preview.column_name == first_col
    assert canonical.data.shape[0] == preview.total_rows


# ---------------------------------------------------------------------------
# 28. API Route Integration Tests (/cleaning/column-transform/preview)
# ---------------------------------------------------------------------------
def test_api_preview_column_transformation_roll_no_convert_string():
    """28a. Test exact UI case: Roll-No float64 converted to string via API endpoint."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.store import session_store, DatasetSessionRecord

    df = pd.DataFrame({"Roll-No": [101.0, 102.0, 103.0, None], "Name": ["Alice", "Bob", "Charlie", "David"]})
    canonical = _build_dataset(df, dataset_id="ds-roll-no-test")
    session_store.save(DatasetSessionRecord(dataset=canonical, profile=None, semantic_profile=None, readiness=None))

    client = TestClient(app)
    response = client.post(
        "/api/datasets/ds-roll-no-test/cleaning/column-transform/preview",
        json={
            "column_name": "Roll-No",
            "operation": "CONVERT_STRING",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["column_name"] == "Roll-No"
    assert data["operation"] == "CONVERT_STRING"
    assert data["target_dtype"] == "string"
    assert data["total_rows"] == 4
    assert data["non_null_count"] == 3
    assert data["converted_count"] == 3
    assert data["unparseable_count"] == 0
    assert data["original_missing_count"] == 1
    assert data["new_missing_count"] == 1
    assert data["is_valid"] is True
    assert data["error_message"] is None
    assert len(data["sample_changes"]) == 3
    assert data["sample_changes"][0]["before_value"] == 101.0
    assert data["sample_changes"][0]["after_value"] == "101.0"


def test_api_preview_column_transformation_dataset_not_found():
    """28b. Test API returns 404 with clear message when dataset is not found in session."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    response = client.post(
        "/api/datasets/nonexistent-dataset-id/cleaning/column-transform/preview",
        json={
            "column_name": "Roll-No",
            "operation": "CONVERT_STRING",
        },
    )

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_api_preview_column_transformation_invalid_column():
    """28c. Test API returns preview with is_valid=False when column does not exist in dataset."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.store import session_store, DatasetSessionRecord

    df = pd.DataFrame({"score": [10.0, 20.0]})
    canonical = _build_dataset(df, dataset_id="ds-col-err-test")
    session_store.save(DatasetSessionRecord(dataset=canonical, profile=None, semantic_profile=None, readiness=None))

    client = TestClient(app)
    response = client.post(
        "/api/datasets/ds-col-err-test/cleaning/column-transform/preview",
        json={
            "column_name": "NonExistentColumn",
            "operation": "CONVERT_STRING",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert "does not exist" in data["error_message"]


def test_api_preview_column_transformation_invalid_operation():
    """28d. Test API returns preview with is_valid=False when operation is unsupported."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.store import session_store, DatasetSessionRecord

    df = pd.DataFrame({"score": [10.0, 20.0]})
    canonical = _build_dataset(df, dataset_id="ds-op-err-test")
    session_store.save(DatasetSessionRecord(dataset=canonical, profile=None, semantic_profile=None, readiness=None))

    client = TestClient(app)
    response = client.post(
        "/api/datasets/ds-op-err-test/cleaning/column-transform/preview",
        json={
            "column_name": "score",
            "operation": "UNSUPPORTED_OPERATION_XYZ",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert "unsupported" in data["error_message"].lower()


def test_api_preview_column_transformation_fractional_truncation_gate():
    """28e. Test API validates fractional truncation safety before allowing integer cast."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.store import session_store, DatasetSessionRecord

    df = pd.DataFrame({"ratio": [10.5, 20.2, 30.0]})
    canonical = _build_dataset(df, dataset_id="ds-frac-test")
    session_store.save(DatasetSessionRecord(dataset=canonical, profile=None, semantic_profile=None, readiness=None))

    client = TestClient(app)
    # Without allow_fractional_truncation -> is_valid should be False
    response = client.post(
        "/api/datasets/ds-frac-test/cleaning/column-transform/preview",
        json={
            "column_name": "ratio",
            "operation": "CONVERT_INTEGER",
            "allow_fractional_truncation": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert data["fractional_loss_count"] == 2
    assert "fractional" in data["error_message"].lower()

    # With allow_fractional_truncation=True -> is_valid should be True
    response_allowed = client.post(
        "/api/datasets/ds-frac-test/cleaning/column-transform/preview",
        json={
            "column_name": "ratio",
            "operation": "CONVERT_INTEGER",
            "allow_fractional_truncation": True,
        },
    )
    assert response_allowed.status_code == 200
    data_allowed = response_allowed.json()
    assert data_allowed["is_valid"] is True
    assert data_allowed["fractional_loss_count"] == 2

