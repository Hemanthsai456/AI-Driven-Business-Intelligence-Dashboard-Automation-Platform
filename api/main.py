"""FastAPI backend application exposing Python intelligence engine endpoints."""

import os
import tempfile
import uuid
import pandas as pd
from typing import Dict, List, Optional
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ingestion.exceptions import (
    IngestionError,
    IngestionFileNotFoundError,
    InvalidExcelStructureError,
    InvalidFileFormatError,
    UnsupportedFileTypeError,
)
from ingestion.loaders.csv_loader import CSVLoader
from ingestion.loaders.excel_loader import ExcelLoader
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics
from intelligence.schema_validator import assess_readiness

from api.schemas import (
    APIErrorResponse,
    AnalysisReadinessResponse,
    DataPreviewResponse,
    DataProfileResponse,
    DatasetListItem,
    DatasetMetadataResponse,
    SemanticProfileResponse,
)
from api.store import DatasetSessionRecord, session_store

app = FastAPI(
    title="AI-Driven Business Intelligence Platform API",
    description="REST API wrapping Ingestion, Profiling, Semantic Intelligence, and Schema Readiness engines.",
    version="1.0.0",
)

# Enable CORS for Next.js frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB development upload limit


@app.get("/api/health")
def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI-Driven Business Intelligence Platform API",
        "version": "1.0.0",
        "capabilities": [
            "CSV/XLSX Ingestion",
            "Data Profiling",
            "Rule-Based Semantic Intelligence",
            "Schema Readiness Assessment",
        ],
    }


@app.post(
    "/api/datasets/upload",
    response_model=DatasetMetadataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a CSV or XLSX dataset, run ingestion, profiling, and semantic analysis."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".csv", ".xlsx", ".xls"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Only .csv and .xlsx files are supported.",
        )

    # Read uploaded bytes and check size
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed upload size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    # Write to temporary file for loader processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        # 1. Ingestion Loader
        if ext == ".csv":
            loader = CSVLoader()
        else:
            loader = ExcelLoader()
        
        canonical_ds = loader.load(tmp_path)
        canonical_ds.metadata.name = filename  # Preserve original filename

        # 2. Data Profiler
        profile = profile_dataset(canonical_ds)

        # 3. Semantic Intelligence Analyzer
        semantic_profile = analyze_semantics(canonical_ds, profile=profile)

        # 4. Schema & Analysis Readiness Validator
        readiness = assess_readiness(canonical_ds, profile=profile, semantic_profile=semantic_profile)

        # 5. Save in Session Store
        record = DatasetSessionRecord(
            dataset=canonical_ds,
            profile=profile,
            semantic_profile=semantic_profile,
            readiness=readiness,
        )
        session_store.save(record)

        return record.to_metadata_dict()

    except (UnsupportedFileTypeError, InvalidFileFormatError, InvalidExcelStructureError, IngestionFileNotFoundError, IngestionError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset processing error: {str(e)}",
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error during dataset processing: {str(e)}",
        )
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.get("/api/datasets", response_model=List[DatasetListItem])
def list_datasets():
    """List all active datasets loaded in the current session."""
    records = session_store.list_all()
    return [
        DatasetListItem(
            dataset_id=r.dataset.metadata.dataset_id,
            filename=r.dataset.metadata.name,
            source_type=r.dataset.metadata.source_type,
            row_count=r.dataset.metadata.row_count,
            column_count=r.dataset.metadata.column_count,
            created_at=r.created_at,
            readiness_status=r.readiness.status.value,
        )
        for r in records
    ]


@app.get("/api/datasets/{dataset_id}", response_model=DatasetMetadataResponse)
def get_dataset_metadata(dataset_id: str):
    """Retrieve metadata for a specific dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    return record.to_metadata_dict()


@app.get("/api/datasets/{dataset_id}/preview", response_model=DataPreviewResponse)
def get_dataset_preview(dataset_id: str, limit: int = 50):
    """Retrieve limited data preview rows for interactive table display."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    df = record.dataset.data
    preview_df = df.head(limit)
    
    # Replace NaN/Infinity with None for JSON compliance
    clean_preview = preview_df.where(pd.notnull(preview_df), None)
    
    # Convert datetimes to ISO strings for JSON output
    for col in clean_preview.columns:
        if pd.api.types.is_datetime64_any_dtype(clean_preview[col]):
            clean_preview[col] = clean_preview[col].astype(str)

    rows = clean_preview.to_dict(orient="records")

    return DataPreviewResponse(
        dataset_id=dataset_id,
        filename=record.dataset.metadata.name,
        total_rows=record.dataset.metadata.row_count,
        preview_rows_count=len(rows),
        columns=[col.original_name for col in record.dataset.metadata.schema],
        rows=rows,
        is_preview=True,
    )


@app.get("/api/datasets/{dataset_id}/profile", response_model=DataProfileResponse)
def get_dataset_profile(dataset_id: str):
    """Retrieve full DataProfile for a dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    return record.profile.to_dict()


@app.get(
    "/api/datasets/{dataset_id}/semantic-analysis",
    response_model=SemanticProfileResponse,
)
def get_dataset_semantic_analysis(dataset_id: str):
    """Retrieve SemanticProfile for a dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    return record.semantic_profile.to_dict()


@app.get(
    "/api/datasets/{dataset_id}/readiness",
    response_model=AnalysisReadinessResponse,
)
def get_dataset_readiness(dataset_id: str):
    """Retrieve AnalysisReadiness assessment for a dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    return record.readiness.to_dict()


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIErrorResponse(
            error=exc.detail if isinstance(exc.detail, str) else "Request error",
            message=str(exc.detail),
            status_code=exc.status_code,
        ).model_dump(),
    )
