"""In-memory dataset session store for development stage.

Stores uploaded CanonicalDatasets and their generated DataProfiles,
DatasetSemanticProfiles, AnalysisReadiness assessments, and ConversationContexts.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
import pandas as pd

from ingestion.models import CanonicalDataset
from intelligence.profiler import DataProfile
from intelligence.semantic_analyzer import DatasetSemanticProfile
from intelligence.schema_validator import AnalysisReadiness
from orchestrator.chat.schemas import ConversationContext


class DatasetSessionRecord:
    def __init__(
        self,
        dataset: CanonicalDataset,
        profile: Optional[DataProfile],
        semantic_profile: Optional[DatasetSemanticProfile],
        readiness: Optional[AnalysisReadiness],
        cleaning_report: Optional[Any] = None,
    ):
        self.dataset = dataset
        self.profile = profile
        self.semantic_profile = semantic_profile
        self.readiness = readiness
        self.cleaning_report = cleaning_report
        self.cached_candidates: Dict[str, List[Any]] = {}
        self.conversations: Dict[str, ConversationContext] = {}
        self.created_at = datetime.now(timezone.utc).isoformat()

    def get_or_create_conversation(self, conversation_id: Optional[str] = None) -> ConversationContext:
        """Retrieve existing ConversationContext or create a new one."""
        cid = conversation_id or str(uuid4())
        if cid not in self.conversations:
            self.conversations[cid] = ConversationContext(
                conversation_id=cid,
                dataset_id=self.dataset.metadata.dataset_id if self.dataset and self.dataset.metadata else "unknown_ds",
            )
        return self.conversations[cid]

    def get_conversation(self, conversation_id: str) -> Optional[ConversationContext]:
        """Retrieve specific conversation context."""
        return self.conversations.get(conversation_id)

    def clear_conversation(self, conversation_id: str) -> bool:
        """Reset history for a specific conversation."""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            return True
        return False

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
            "cleaning_report": self.cleaning_report.model_dump() if hasattr(self.cleaning_report, "model_dump") else None,
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
