"""Dataset Metadata & Structure Handler for Dataset Chat.

Answers questions about:
- Available columns & schema
- Row count, column count, source format
- Detectable measures (numeric metrics) and dimensions (categorical/temporal)
- Missing values and data cleanliness observations
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from ingestion.models import CanonicalDataset, ColumnRole
from intelligence.profiler import DataProfile
from intelligence.schema_validator import AnalysisReadiness
from intelligence.semantic_analyzer import DatasetSemanticProfile


class DatasetMetadataHandler:
    """Answers dataset structure and schema understanding questions using existing metadata."""

    def handle_metadata_query(
        self,
        question: str,
        dataset: CanonicalDataset,
        profile: Optional[DataProfile],
        semantic_profile: Optional[DatasetSemanticProfile],
        readiness: Optional[AnalysisReadiness],
    ) -> Dict[str, Any]:
        """Generate structured and natural-language dataset overview response."""
        meta = dataset.metadata
        df = dataset.data
        q_lower = question.lower()

        # 1. Categorize columns from SemanticProfile
        measures: List[str] = []
        dimensions: List[str] = []
        identifiers: List[str] = []
        datetimes: List[str] = []

        if semantic_profile:
            for col_name, ev in semantic_profile.column_evidences.items():
                role = ev.candidate_role
                if role == ColumnRole.MEASURE:
                    measures.append(col_name)
                elif role == ColumnRole.DIMENSION:
                    dimensions.append(col_name)
                elif role == ColumnRole.IDENTIFIER:
                    identifiers.append(col_name)
                elif role == ColumnRole.DATETIME:
                    datetimes.append(col_name)

        # Fallback if semantic profile not populated
        if not measures and not dimensions:
            for col in meta.schema:
                col_name = col.original_name
                dt = col.detected_datatype.lower()
                if any(t in dt for t in ("int", "float", "double", "num")):
                    measures.append(col_name)
                elif any(t in dt for t in ("date", "time")):
                    datetimes.append(col_name)
                else:
                    dimensions.append(col_name)

        # 2. Build specific responses depending on the nuance of the question
        if any(w in q_lower for w in ("how many rows", "how many records", "row count", "size")):
            answer = f"The dataset contains **{meta.row_count:,} rows** and **{meta.column_count} columns**."

        elif any(w in q_lower for w in ("what metrics", "what measures", "what can i calculate", "measures")):
            m_list = ", ".join([f"`{m}`" for m in measures]) if measures else "none detected"
            answer = f"You can analyze the following numeric measures in this dataset: {m_list}."

        elif any(w in q_lower for w in ("what dimensions", "what categories", "group by")):
            d_list = ", ".join([f"`{d}`" for d in dimensions]) if dimensions else "none detected"
            answer = f"You can group or segment by these categorical dimensions: {d_list}."

        elif any(w in q_lower for w in ("missing values", "nulls", "cleanliness", "quality")):
            null_summary = []
            if profile and profile.column_statistics:
                for c_name, c_stat in profile.column_statistics.items():
                    if c_stat.null_count > 0:
                        null_summary.append(f"`{c_name}` ({c_stat.null_count} nulls, {c_stat.null_percentage:.1f}%)")
            if null_summary:
                answer = f"Missing values were observed in: {', '.join(null_summary)}."
            else:
                answer = "The dataset has zero missing values across all columns."

        else:
            # Full summary
            m_str = ", ".join([f"`{m}`" for m in measures]) if measures else "None"
            d_str = ", ".join([f"`{d}`" for d in dimensions]) if dimensions else "None"
            dt_str = ", ".join([f"`{t}`" for t in datetimes]) if datetimes else "None"

            answer = (
                f"**Dataset Overview for `{meta.name}`**:\n"
                f"- **Shape**: {meta.row_count:,} rows × {meta.column_count} columns\n"
                f"- **Measures / Metrics**: {m_str}\n"
                f"- **Dimensions / Categories**: {d_str}\n"
                f"- **Date & Time Fields**: {dt_str}\n"
                f"- **Source Format**: {meta.source_type.upper()}"
            )

        # Build schema data table for UI rendering
        schema_rows = []
        for col in meta.schema:
            ev = semantic_profile.get_evidence(col.original_name) if semantic_profile else None
            schema_rows.append({
                "column": col.original_name,
                "data_type": col.detected_datatype,
                "semantic_role": ev.candidate_role.value if ev else "UNKNOWN",
                "sample_values": str(df[col.original_name].dropna().head(3).tolist()) if col.original_name in df.columns else "[]",
            })

        return {
            "answer": answer,
            "data": schema_rows,
            "columns": ["column", "data_type", "semantic_role", "sample_values"],
            "row_count": len(schema_rows),
            "evidence": {
                "row_count": meta.row_count,
                "column_count": meta.column_count,
                "measures": measures,
                "dimensions": dimensions,
                "identifiers": identifiers,
                "datetimes": datetimes,
            },
        }
