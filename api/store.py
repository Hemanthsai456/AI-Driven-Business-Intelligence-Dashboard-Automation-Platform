"""In-memory dataset session store for development stage.

Stores uploaded CanonicalDatasets and their generated DataProfiles,
DatasetSemanticProfiles, and AnalysisReadiness assessments.
"""

from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from ingestion.models import CanonicalDataset
from intelligence.profiler import DataProfile
from intelligence.semantic_analyzer import DatasetSemanticProfile
from intelligence.schema_validator import AnalysisReadiness


class DatasetSessionRecord:
    def __init__(
        self,
        dataset: CanonicalDataset,
        profile: DataProfile,
        semantic_profile: DatasetSemanticProfile,
        readiness: AnalysisReadiness,
    ):
        self.dataset = dataset
        self.profile = profile
        self.semantic_profile = semantic_profile
        self.readiness = readiness
        self.created_at = datetime.utcnow().isoformat()

    def to_metadata_dict(self) -> Dict:
        return {
            "dataset_id": self.dataset.metadata.dataset_id,
            "filename": self.dataset.metadata.name,
            "source_type": self.dataset.metadata.source_type,
            "row_count": self.dataset.metadata.row_count,
            "column_count": self.dataset.metadata.column_count,
            "columns": [col.to_dict() for col in self.dataset.metadata.schema],
            "dtypes": {col.original_name: col.detected_datatype for col in self.dataset.metadata.schema},
            "ingestion_status": "SUCCESS",
            "ingestion_errors": [],
        }


class SessionStore:
    def __init__(self):
        self._store: Dict[str, DatasetSessionRecord] = {}

    def save(self, record: DatasetSessionRecord) -> str:
        self._store[record.dataset.metadata.dataset_id] = record
        return record.dataset.metadata.dataset_id

    def get(self, dataset_id: str) -> Optional[DatasetSessionRecord]:
        return self._store.get(dataset_id)

    def list_all(self) -> List[DatasetSessionRecord]:
        return list(self._store.values())

    def clear(self) -> None:
        self._store.clear()


# Global in-memory dataset session store instance
session_store = SessionStore()
