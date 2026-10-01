"""Automated Data Cleaning Layer (Stage 2).

Provides format-agnostic, non-mutating data cleaning driven by preliminary profiling
and semantic inference. Outputs a new CanonicalDataset along with an audit-grade
CleaningReport.
"""

from cleaning.cleaner import DataCleaner, clean_dataset
from cleaning.models import (
    CleaningChange,
    CleaningConfig,
    CleaningReport,
    CleaningResult,
)

__all__ = [
    "DataCleaner",
    "clean_dataset",
    "CleaningChange",
    "CleaningConfig",
    "CleaningReport",
    "CleaningResult",
]
