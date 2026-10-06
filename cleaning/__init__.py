"""Automated Data Cleaning Layer (Stage 2).

Provides format-agnostic, non-mutating data cleaning driven by preliminary profiling
and semantic inference. Outputs a new CanonicalDataset along with an audit-grade
CleaningReport.
"""

from cleaning.cleaner import DataCleaner, clean_dataset
from cleaning.executor import (
    CleaningExecutionError,
    CleaningExecutor,
    execute_cleaning_plan,
    preview_cleaning_plan,
)
from cleaning.models import (
    CleaningChange,
    CleaningConfig,
    CleaningExecutionResult,
    CleaningPlan,
    CleaningPreviewResult,
    CleaningRecommendation,
    CleaningReport,
    CleaningResult,
    CleaningValidationCheck,
    CleaningValidationResult,
    ColumnTransformPreviewResult,
    OperationExecutionResult,
    SampleCellChange,
)
from cleaning.planner import CleaningPlanner, generate_cleaning_plan

__all__ = [
    "DataCleaner",
    "clean_dataset",
    "CleaningChange",
    "CleaningConfig",
    "CleaningReport",
    "CleaningResult",
    "CleaningPlan",
    "CleaningRecommendation",
    "CleaningPlanner",
    "generate_cleaning_plan",
    "CleaningExecutionError",
    "CleaningExecutor",
    "execute_cleaning_plan",
    "preview_cleaning_plan",
    "CleaningExecutionResult",
    "CleaningPreviewResult",
    "CleaningValidationCheck",
    "CleaningValidationResult",
    "ColumnTransformPreviewResult",
    "OperationExecutionResult",
    "SampleCellChange",
]

