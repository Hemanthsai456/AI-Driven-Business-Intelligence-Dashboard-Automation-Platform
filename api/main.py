"""FastAPI backend application exposing Python intelligence engine endpoints."""

import os
import tempfile
import uuid
from dotenv import load_dotenv

load_dotenv()
print(f"[STARTUP] Environment loaded. GEMINI_API_KEY present: {'GEMINI_API_KEY' in os.environ}, GROQ_API_KEY present: {'GROQ_API_KEY' in os.environ}")

import io
import pandas as pd
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ingestion.exceptions import (
    IngestionError,
    IngestionFileNotFoundError,
    InvalidExcelStructureError,
    InvalidFileFormatError,
    UnsupportedFileTypeError,
)
from ingestion.loaders import CSVLoader, ExcelLoader, ParquetLoader, TSVLoader, load_dataset
from ingestion.models import CanonicalDataset
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
    GenerateCandidatesRequest,
    GenerateCandidatesResponse,
    PlanRunResponse,
    SemanticProfileResponse,
    SelectWinnerRequest,
    SelectWinnerResponse,
    OrchestratorPipelineRequest,
    OrchestratorPipelineResponse,
    ResolvePipelineRequest,
    ResolveErrorResponse,
    TileFilter,
    TileQueryRequest,
    TileQueryResponse,
    EDAExploreRequest,
    CleaningSelectionRequest,
    ColumnTransformPreviewRequest,
    ColumnTransformPreviewResponse,
    MultiValueCandidatesResponse,
    MultiValuePreviewRequest,
    MultiValuePreviewResponse,
    MultiValueApplyRequest,
    MultiValueApplyResponse,
    DropColumnsRequest,
    DropColumnsPreviewResponse,
    FilterConditionSchema,
    RowFilterRequest,
    RowFilterPreviewResponse,
    DuplicateRemovalRequest,
    DuplicateRemovalPreviewResponse,
    StructuralQualityRecommendationSchema,
    StructuralRecommendationsResponse,
    SemanticRoleOverrideRequest,
    SemanticRoleOverrideResponse,
    StructuralApplyResponse,
    CleanedDatasetSummaryResponse,
)
from api.store import DatasetSessionRecord, session_store
from intelligence.semantic_analyzer import ColumnRole

# In-memory stores for dashboard specifications and cached tile queries
dashboard_specs_store: Dict[str, Any] = {}
original_specs_store: Dict[str, Any] = {}
tile_query_cache: Dict[Tuple[str, str, str], TileQueryResponse] = {}
from orchestrator.run_store import (
    PlanNotFoundError,
    RunExpiredError,
    RunNotFoundError,
    RunResolveError,
    resolve_pipeline_run,
)
from orchestrator.ambiguity import assess_ambiguity
from orchestrator.context_builder import build_llm_context
from orchestrator.executor import execute_plan
from orchestrator.generator import (
    ExternalAgentGenerator,
    LLMDirectGenerator,
    MockAgent,
    PlanGenerationCoordinator,
)
from orchestrator.llm import GeminiClient, LLMClient, LLMClientError, MockLLMClient
from orchestrator.pipeline import run_orchestration_pipeline
from orchestrator.schemas import (
    AggregationType,
    CandidatePlan,
    DimensionSpec,
    ExecutionResult,
    GeneratorCallLog,
    MetricSpec,
    Pass1aResult,
    PlanReasoning,
    VisualizationType,
)
from orchestrator.validator import validate_pass1a, validate_pass1b
from orchestrator.winner import WinnerSelectionError, select_winner
from orchestrator.utils import rank_candidates, check_candidate_output_consistency

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

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB upload limit


@app.get("/api/health")
def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI-Driven Business Intelligence Platform API",
        "version": "1.0.0",
        "capabilities": [
            "Data Ingestion (CSV, TSV, XLSX, Parquet)",
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
def upload_dataset(file: UploadFile = File(...)):
    """Upload a CSV, TSV, XLSX, or Parquet dataset, run ingestion, profiling, and semantic analysis."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".csv", ".tsv", ".xlsx", ".parquet"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Supported formats: CSV, TSV, XLSX, Parquet.",
        )

    # Read uploaded bytes and check size
    contents = file.file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed upload size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB. Maximum file size is 100 MB.",
        )

    # Write to temporary file for loader processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        # 1. Ingestion Loader (dispatched through load_dataset)
        raw_ds = load_dataset(tmp_path)
        raw_ds.metadata.name = filename  # Preserve original filename

        # 2. Data Profiler on raw ingested data
        profile = profile_dataset(raw_ds)

        # 3. Semantic Intelligence Analyzer
        semantic_profile = analyze_semantics(raw_ds, profile=profile, apply_roles=True)

        # 4. Schema & Analysis Readiness Validator
        readiness = assess_readiness(raw_ds, profile=profile, semantic_profile=semantic_profile)

        # 5. Save in Session Store (original raw dataset preserved untouched)
        record = DatasetSessionRecord(
            dataset=raw_ds,
            profile=profile,
            semantic_profile=semantic_profile,
            readiness=readiness,
            cleaning_report=None,
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

    active_ds = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    df = active_ds.data
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
        filename=active_ds.metadata.name,
        total_rows=active_ds.metadata.row_count,
        preview_rows_count=len(rows),
        columns=[col.original_name for col in active_ds.metadata.schema],
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


@app.get("/api/datasets/{dataset_id}/quality-assessment")
@app.get("/api/datasets/{dataset_id}/quality")
def get_dataset_quality_assessment(dataset_id: str):
    """Retrieve deterministic data quality assessment for a dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    from intelligence.quality_assessor import assess_quality
    active_ds = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    assessment = assess_quality(
        canonical=active_ds,
        profile=record.profile,
        semantic_profile=record.semantic_profile,
        readiness=record.readiness,
    )
    return assessment.to_dict()


@app.get("/api/datasets/{dataset_id}/eda")
def get_dataset_eda(dataset_id: str):
    """Generate or retrieve deterministic automated Exploratory Data Analysis (EDA) summary."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    from intelligence.eda import EDAEngine
    engine = EDAEngine()
    active_ds = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    summary = engine.generate_summary(
        canonical=active_ds,
        profile=record.profile,
        semantic_profile=record.semantic_profile,
    )
    return summary.to_dict()


@app.post("/api/datasets/{dataset_id}/eda/explore")
def explore_dataset_eda(dataset_id: str, req: EDAExploreRequest):
    """Execute manual bivariate or univariate exploratory query on dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    from intelligence.eda import EDAEngine
    engine = EDAEngine()
    active_ds = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    result = engine.explore(
        canonical=active_ds,
        chart_type=req.chart_type,
        x_column=req.x_column,
        y_column=req.y_column,
        group_by=req.group_by,
        aggregation=req.aggregation or "mean",
        time_granularity=req.time_granularity,
    )
    return result




@app.post(

    "/api/orchestrator/validate-plan",
    response_model=Pass1aResult,
)
def validate_plan_endpoint(plan: CandidatePlan):
    """Validate a candidate analytical plan against dataset semantic profile and readiness."""
    record = session_store.get(plan.dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{plan.dataset_id}' not found in current session.",
        )
    result = validate_pass1a(
        plan=plan,
        semantic_profile=record.semantic_profile,
        readiness=record.readiness,
    )
    return result


@app.post(
    "/api/orchestrator/run-plan",
    response_model=PlanRunResponse,
)
def run_plan_endpoint(plan: CandidatePlan):
    """Validate, compile, execute on DuckDB, and verify a candidate analytical plan."""
    record = session_store.get(plan.dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{plan.dataset_id}' not found in current session.",
        )

    # 1. Pass 1a Pre-Dispatch Validation
    pass1a_res = validate_pass1a(
        plan=plan,
        semantic_profile=record.semantic_profile,
        readiness=record.readiness,
    )
    if not pass1a_res.passed:
        return PlanRunResponse(
            plan_id=plan.plan_id,
            pass1a=pass1a_res.model_dump(),
            execution=None,
            pass1b=None,
        )

    # 2. DuckDB Execution
    active_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    exec_res = execute_plan(
        plan=plan,
        dataset=active_dataset,
        semantic_profile=record.semantic_profile,
    )

    # 3. Pass 1b Post-Execution Validation
    pass1b_res = validate_pass1b(
        plan=plan,
        exec_result=exec_res,
    )

    return PlanRunResponse(
        plan_id=plan.plan_id,
        pass1a=pass1a_res.model_dump(),
        execution=exec_res.model_dump(),
        pass1b=pass1b_res.model_dump(),
    )


@app.post(
    "/api/orchestrator/generate-candidates",
    response_model=GenerateCandidatesResponse,
)
def generate_candidates_endpoint(req: GenerateCandidatesRequest):
    """Generate candidate analytical plans using LLMDirectGenerator and ExternalAgentGenerator."""
    record = session_store.get(req.dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{req.dataset_id}' not found in current session.",
        )

    # 1. Ambiguity Pre-Check
    ambiguity = assess_ambiguity(req.intent, record.semantic_profile)

    # 2. Build Compact LLM Context
    context = build_llm_context(
        dataset_id=req.dataset_id,
        intent=req.intent,
        semantic_profile=record.semantic_profile,
        data_profile=record.profile,
    )

    # 3. Determine LLM Client (Gemini if key configured, otherwise intelligent Mock client)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        llm_client: LLMClient = GeminiClient(api_key=gemini_key)
    else:
        # Fallback to smart mock client based on dataset columns
        first_measure = "Revenue"
        first_dim = "Category"
        for col, ev in record.semantic_profile.column_evidences.items():
            if ev.candidate_role == ColumnRole.MEASURE:
                first_measure = col
                break
        for col, ev in record.semantic_profile.column_evidences.items():
            if ev.candidate_role in (ColumnRole.DIMENSION, ColumnRole.DATETIME) and col != first_measure:
                first_dim = col
                break

        canned = {
            "dataset_id": req.dataset_id,
            "intent": req.intent,
            "metric": {"column": first_measure, "aggregation": "SUM"},
            "dimensions": [{"column": first_dim}],
            "filters": [],
            "visualization": "BAR",
            "reasoning": {
                "interpretation": f"Aggregated {first_measure} broken down by {first_dim}",
                "evidence": [f"Selected measure '{first_measure}' and dimension '{first_dim}'"],
            },
        }
        llm_client = MockLLMClient(canned_response=canned)

    direct_gen = LLMDirectGenerator(llm_client)
    agent_gen = ExternalAgentGenerator(llm_client)
    coordinator = PlanGenerationCoordinator(
        direct_generator=direct_gen,
        agent_generator=agent_gen,
        mode=req.mode or os.getenv("GENERATOR_MODE", "llm_only"),
    )

    candidates, logs = coordinator.generate_candidates(context, k=req.k)

    return GenerateCandidatesResponse(
        dataset_id=req.dataset_id,
        intent=req.intent,
        ambiguity=ambiguity.model_dump(),
        candidates=[c.model_dump() for c in candidates],
        logs=[l.model_dump() for l in logs],
    )


@app.post(
    "/api/orchestrator/select-winner",
    response_model=SelectWinnerResponse,
)
def select_winner_endpoint(req: SelectWinnerRequest):
    """Re-rank candidates, apply Pass 2 with cascade, and return the winning DashboardSpec.

    Accepts the candidates from /generate-candidates and their execution results
    from /run-plan, then:
    1. Ranks surviving candidates using Ranker V1.
    2. Applies Pass 2 winner-only validation with runner-up cascade.
    3. Returns a structured winner response including tie/cascade metadata.
    """
    record = session_store.get(req.dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{req.dataset_id}' not found in current session.",
        )

    if not req.candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No candidates provided for winner selection.",
        )

    if not req.execution_results:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No execution results provided for winner selection.",
        )

    # 1. Deserialize candidates
    plans = []
    for c in req.candidates:
        try:
            plans.append(CandidatePlan.model_validate(c))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid candidate plan: {str(e)}",
            )

    # 2. Deserialize execution results (plan_id -> ExecutionResult)
    exec_results = {}
    for plan_id, er_dict in req.execution_results.items():
        try:
            exec_results[plan_id] = ExecutionResult.model_validate(er_dict)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid execution result for plan '{plan_id}': {str(e)}",
            )

    # 3. Build (plan, exec_result) pairs — only keep plans that have execution results
    candidate_pairs = []
    for plan in plans:
        if plan.plan_id in exec_results:
            candidate_pairs.append((plan, exec_results[plan.plan_id]))

    if not candidate_pairs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No candidates matched their execution results by plan_id.",
        )

    # 4. Consistency check before ranking
    consistency = check_candidate_output_consistency(candidate_pairs)

    # 5. Rank candidates (intent tokens for coverage score)
    active_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    intent_tokens = req.intent.lower().split()
    semantic_evidences = record.semantic_profile.column_evidences
    ranked, is_tie = rank_candidates(
        candidate_pairs,
        semantic_evidences=semantic_evidences,
        intent_tokens=intent_tokens,
        dataset=active_dataset,
        semantic_profile=record.semantic_profile,
    )

    # 6. Deserialize generator logs (optional)
    gen_logs = []
    for gl_dict in (req.generator_logs or []):
        try:
            gen_logs.append(GeneratorCallLog.model_validate(gl_dict))
        except Exception:
            pass  # non-critical — log dropped silently

    # 7. Select winner with Pass 2 cascade
    try:
        dashboard_spec = select_winner(
            ranked=ranked,
            dataset_id=req.dataset_id,
            intent=req.intent,
            context_hash=req.context_hash or "",
            generator_logs=gen_logs,
            consistency_check=consistency,
            semantic_profile=record.semantic_profile,
            dataset=active_dataset,
        )
    except WinnerSelectionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"All candidates failed Pass 2 after {e.cascade_depth} cascade step(s). "
                "No viable winner could be selected (UNANSWERABLE)."
            ),
        )

    winner = dashboard_spec.winner
    trace = dashboard_spec.trace

    return SelectWinnerResponse(
        spec_id=dashboard_spec.spec_id,
        dataset_id=dashboard_spec.dataset_id,
        intent=dashboard_spec.intent,
        winner_plan_id=winner.plan.plan_id,
        winner_score=winner.score_breakdown.total,
        winner_generator=winner.plan.generator,
        winner_visualization=winner.plan.visualization.value,
        winner_rank_before_cascade=winner.rank,
        pass2_passed=trace.pass2_result.passed if trace.pass2_result else True,
        pass2_issues=[
            i.model_dump() for i in (trace.pass2_result.issues if trace.pass2_result else [])
        ],
        cascade_depth=trace.cascade_depth,
        cascade_triggered=trace.cascade_depth > 0,
        is_tie=dashboard_spec.is_tie,
        alternate_interpretations=[
            {
                "plan_id": alt.plan.plan_id,
                "score": alt.score,
                "reason_not_winner": alt.reason_not_winner,
                "generator": alt.plan.generator,
                "visualization": alt.plan.visualization.value,
                "intent": alt.plan.intent,
            }
            for alt in dashboard_spec.alternate_interpretations
        ],
        winner_plan=winner.plan.model_dump(),
        winner_execution=winner.execution_result.model_dump(),
        score_breakdown=winner.score_breakdown.model_dump(),
        created_at=dashboard_spec.created_at,
    )


@app.get("/api/datasets/{dataset_id}/cleaning")
def get_dataset_cleaning_report(dataset_id: str):
    """Retrieve data cleaning report for a dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )
    if record.cleaning_report:
        return record.cleaning_report.model_dump() if hasattr(record.cleaning_report, "model_dump") else record.cleaning_report
    return {"dataset_id": dataset_id, "changes": []}


@app.get("/api/datasets/{dataset_id}/cleaning-plan")
def get_dataset_cleaning_plan(dataset_id: str):
    """Retrieve deterministic cleaning recommendations and plan for a dataset."""
    from cleaning.planner import CleaningPlanner

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    planner = CleaningPlanner()
    plan = planner.generate_plan(
        canonical=target_dataset,
        profile=record.profile,
        semantic_profile=record.semantic_profile,
        quality_assessment=getattr(record, "quality_assessment", None),
    )
    return plan.to_dict()


@app.get(
    "/api/datasets/{dataset_id}/cleaning-summary",
    response_model=CleanedDatasetSummaryResponse,
)
@app.get(
    "/api/datasets/{dataset_id}/cleaning/summary",
    response_model=CleanedDatasetSummaryResponse,
)
def get_cleaned_dataset_summary(dataset_id: str):
    """Retrieve summary metrics, applied operations, and remaining data quality issues for current cleaned dataset."""
    record = session_store.get(dataset_id)
    if not record or not record.dataset or record.dataset.data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    df_raw = record.dataset.data
    df_clean = record.cleaned_dataset.data if (record.cleaned_dataset is not None and record.cleaned_dataset.data is not None) else None
    has_cleaned = df_clean is not None or len(record.applied_operations) > 0

    # 1. Non-mutating calculation of BEFORE metrics from raw dataset
    rows_before = int(len(df_raw))
    cols_before = int(len(df_raw.columns))
    missing_before = int(df_raw.isna().sum().sum())
    dups_before = int(df_raw.duplicated().sum())

    # 2. Non-mutating calculation of AFTER metrics from active cleaned dataset
    df_active = df_clean if df_clean is not None else df_raw
    rows_after = int(len(df_active))
    cols_after = int(len(df_active.columns))
    missing_after = int(df_active.isna().sum().sum())
    dups_after = int(df_active.duplicated().sum())

    metrics = {
        "rows": {
            "before": rows_before,
            "after": rows_after,
            "change": rows_after - rows_before,
        },
        "columns": {
            "before": cols_before,
            "after": cols_after,
            "change": cols_after - cols_before,
        },
        "missing_cells": {
            "before": missing_before,
            "after": missing_after,
            "change": missing_after - missing_before,
        },
        "duplicate_rows": {
            "before": dups_before,
            "after": dups_after,
            "change": dups_after - dups_before,
        },
    }

    # 3. Changes Applied (concise list of actual operations)
    changes_applied: List[str] = []
    if has_cleaned and record.applied_operations:
        for op in record.applied_operations:
            s = op.get("summary")
            if s and s not in changes_applied:
                changes_applied.append(s)

    # 4. Remaining Data Quality Issues from the CURRENT cleaned dataset
    remaining_issues: List[str] = []
    if missing_after > 0:
        cols_with_na = [col for col in df_active.columns if df_active[col].isna().sum() > 0]
        col_preview = ", ".join(cols_with_na[:3])
        if len(cols_with_na) > 3:
            col_preview += f" (+{len(cols_with_na) - 3} more)"
        remaining_issues.append(f"{missing_after} missing values remain across {len(cols_with_na)} column(s) ({col_preview})")

    if dups_after > 0:
        remaining_issues.append(f"{dups_after} duplicate row(s) remain")

    for col in df_active.columns:
        na_count = int(df_active[col].isna().sum())
        if len(df_active) > 0:
            na_pct = (na_count / len(df_active)) * 100.0
            if na_pct >= 80.0:
                remaining_issues.append(f"Column '{col}' has {na_pct:.1f}% missing values ({na_count}/{len(df_active)} rows)")

    # Check non-numeric values in measure/numeric columns
    if record.semantic_profile and record.semantic_profile.column_evidences:
        for col_name, ev in record.semantic_profile.column_evidences.items():
            if col_name in df_active.columns:
                role_str = ev.candidate_role.value if hasattr(ev.candidate_role, "value") else str(ev.candidate_role)
                if role_str == "MEASURE":
                    col_series = df_active[col_name]
                    if col_series.dtype == object or str(col_series.dtype) == "string":
                        coerced = pd.to_numeric(col_series, errors="coerce")
                        non_num_count = int(coerced.isna().sum() - col_series.isna().sum())
                        if non_num_count > 0:
                            remaining_issues.append(f"{non_num_count} non-numeric value(s) remain in '{col_name}'")

    if not remaining_issues:
        remaining_issues = ["✓ No major data-quality issues detected."]

    status_msg = (
        f"Cleaned dataset contains {len(changes_applied)} applied operation(s)."
        if has_cleaned and changes_applied
        else "No cleaning changes have been applied yet."
    )

    return {
        "dataset_id": dataset_id,
        "has_cleaned": has_cleaned,
        "status_message": status_msg,
        "raw_data_protection": "Original dataset remains unchanged.",
        "metrics": metrics,
        "changes_applied": changes_applied,
        "remaining_quality_issues": remaining_issues,
        "registered_cleaned_dataset_id": record.registered_cleaned_dataset_id,
    }


@app.post(
    "/api/datasets/{dataset_id}/cleaning/column-transform/preview",
    response_model=ColumnTransformPreviewResponse,
)
def preview_column_transformation(dataset_id: str, request: ColumnTransformPreviewRequest):
    """Generate a non-mutating preview of a single user-controlled column transformation."""
    from cleaning.executor import CleaningExecutionError, CleaningExecutor

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        executor = CleaningExecutor()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        preview_result = executor.preview_column_transformation(
            canonical=target_dataset,
            column_name=request.column_name,
            operation=request.operation,
            target_type=request.target_type,
            custom_value=request.custom_value,
            allow_fractional_truncation=request.allow_fractional_truncation,
        )
        return preview_result.to_dict()
    except CleaningExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate column transformation preview: {str(ex)}",
        )


@app.get(
    "/api/datasets/{dataset_id}/cleaning/multivalue/candidates",
    response_model=MultiValueCandidatesResponse,
)
def get_multivalue_candidates(dataset_id: str):
    """Detect columns containing multi-valued cells inside the canonical dataset."""
    from cleaning.multivalue import MultiValueDetector

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        detector = MultiValueDetector()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        candidates = detector.detect_candidates(
            canonical=target_dataset,
            semantic_profile=record.semantic_profile,
        )
        return {
            "dataset_id": dataset_id,
            "candidates_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
        }
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect multi-valued column candidates: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/multivalue/preview",
    response_model=MultiValuePreviewResponse,
)
def preview_multivalue_transformation(dataset_id: str, request: MultiValuePreviewRequest):
    """Generate a non-mutating preview of splitting or expanding a multi-valued column."""
    from cleaning.multivalue import MultiValueExecutionError, MultiValueHandler

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        handler = MultiValueHandler()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        delim = request.delimiter if request.delimiter else ","
        preview_result = handler.preview(
            canonical=target_dataset,
            column_name=request.column_name,
            action=request.action,
            delimiter=delim,
        )
        return preview_result.to_dict()
    except MultiValueExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate multi-value transformation preview: {str(ex)}",
        )


def _refresh_record_cleaned_state(record: DatasetSessionRecord, cleaned_canonical: CanonicalDataset):
    """Synchronize profile, semantic intelligence, schema roles, and readiness assessment on the session record."""
    from intelligence.profiler import DataProfiler
    from intelligence.semantic_analyzer import ColumnRole, SemanticAnalyzer
    from intelligence.schema_validator import assess_readiness

    record.cleaned_dataset = cleaned_canonical
    record.registered_cleaned_dataset_id = None  # Invalidate cached registration

    try:
        profiler = DataProfiler()
        record.profile = profiler.profile(cleaned_canonical, attach=True)
        semantic_analyzer = SemanticAnalyzer()
        sem_profile = semantic_analyzer.analyze(cleaned_canonical, profile=record.profile, apply_roles=True)
        if hasattr(record, "user_semantic_role_overrides") and record.user_semantic_role_overrides:
            for col_name, role_str in record.user_semantic_role_overrides.items():
                if col_name in cleaned_canonical.data.columns:
                    ev = sem_profile.get_evidence(col_name)
                    if ev is not None:
                        if not hasattr(ev, "system_role") or getattr(ev, "system_role") is None:
                            ev.system_role = ev.candidate_role
                        ev.user_override_role = ColumnRole(role_str)
                        ev.candidate_role = ColumnRole(role_str)
                        ev.is_user_overridden = True
                        ev.evidence = list(ev.evidence) + [f"User explicitly designated column as {role_str}."]
                    for col_meta in cleaned_canonical.metadata.schema:
                        if col_meta.original_name == col_name:
                            col_meta.semantic_role = ColumnRole(role_str)
        record.semantic_profile = sem_profile
        record.readiness = assess_readiness(cleaned_canonical, profile=record.profile, semantic_profile=sem_profile)
    except Exception:
        pass


@app.post(
    "/api/datasets/{dataset_id}/cleaning/multivalue/apply",
    response_model=MultiValueApplyResponse,
)
def apply_multivalue_transformation(dataset_id: str, request: MultiValueApplyRequest):
    """Apply a multi-valued column transformation on a copy, updating the in-memory cleaned dataset."""
    from cleaning.multivalue import MultiValueExecutionError, MultiValueHandler

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        handler = MultiValueHandler()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        delim = request.delimiter if request.delimiter else ","
        cleaned_canonical, audit_info = handler.apply(
            canonical=target_dataset,
            column_name=request.column_name,
            action=request.action,
            delimiter=delim,
        )

        _refresh_record_cleaned_state(record, cleaned_canonical)
        record.last_cleaning_result = {
            "dataset_id": dataset_id,
            "action": request.action,
            "column_name": request.column_name,
            "audit_info": audit_info,
            "status": "APPLIED",
        }
        action_name = "split into columns" if request.action == "SPLIT_COLUMNS" else "expanded into rows"
        record.record_applied_operation(
            op_type="MULTIVALUE",
            summary=f"1 multi-valued column '{request.column_name}' {action_name}",
            details={"column": request.column_name, "action": request.action, **audit_info},
        )

        return {
            "dataset_id": dataset_id,
            "action": request.action,
            "column_name": request.column_name,
            "audit_info": audit_info,
            "cleaned_row_count": len(cleaned_canonical.data),
            "cleaned_column_count": len(cleaned_canonical.data.columns),
            "status": "SUCCESS",
        }
    except MultiValueExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply multi-value transformation: {str(ex)}",
        )


# =========================================================================
# Part 6.4 — Structural Cleaning & Semantic Role Overrides Endpoints
# =========================================================================


@app.get(
    "/api/datasets/{dataset_id}/cleaning/structural/recommendations",
    response_model=StructuralRecommendationsResponse,
)
def get_structural_recommendations(dataset_id: str):
    """Retrieve deterministic data-quality structural recommendations."""
    from cleaning.structural import StructuralCleaner

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        recs = cleaner.get_structural_recommendations(
            canonical=target_dataset,
            profile=record.profile,
            semantic_profile=record.semantic_profile,
        )
        return {
            "dataset_id": dataset_id,
            "total_recommendations": len(recs),
            "recommendations": [r.to_dict() for r in recs],
        }
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate structural recommendations: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/drop-columns/preview",
    response_model=DropColumnsPreviewResponse,
)
def preview_drop_columns(dataset_id: str, request: DropColumnsRequest):
    """Non-mutating preview of column dropping."""
    from cleaning.structural import StructuralCleaner, StructuralExecutionError

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        preview_result = cleaner.preview_drop_columns(
            canonical=target_dataset,
            columns_to_drop=request.columns,
        )
        return preview_result.to_dict()
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview column drop: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/drop-columns/apply",
    response_model=StructuralApplyResponse,
)
def apply_drop_columns(dataset_id: str, request: DropColumnsRequest):
    """Apply column dropping on a copy, updating the in-memory cleaned dataset."""
    from cleaning.structural import StructuralCleaner, StructuralExecutionError
    from intelligence.profiler import DataProfiler
    from intelligence.semantic_analyzer import SemanticAnalyzer

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        cleaned_canonical, audit_info = cleaner.apply_drop_columns(
            canonical=target_dataset,
            columns_to_drop=request.columns,
        )

        _refresh_record_cleaned_state(record, cleaned_canonical)
        record.last_cleaning_result = {
            "dataset_id": dataset_id,
            "action": "DROP_COLUMNS",
            "audit_info": audit_info,
            "status": "APPLIED",
        }
        cols_str = ", ".join(request.columns)
        record.record_applied_operation(
            op_type="DROP_COLUMNS",
            summary=f"{len(request.columns)} column(s) removed ({cols_str})",
            details={"columns": request.columns, **audit_info},
        )

        return {
            "dataset_id": dataset_id,
            "action": "DROP_COLUMNS",
            "audit_info": audit_info,
            "cleaned_row_count": len(cleaned_canonical.data),
            "cleaned_column_count": len(cleaned_canonical.data.columns),
            "status": "SUCCESS",
        }
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply column drop: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/filter-rows/preview",
    response_model=RowFilterPreviewResponse,
)
def preview_filter_rows(dataset_id: str, request: RowFilterRequest):
    """Non-mutating preview of row removal based on conditions."""
    from cleaning.structural import FilterCondition, StructuralCleaner, StructuralExecutionError

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        conditions = [
            FilterCondition(column=c.column, operator=c.operator, value=c.value)
            for c in request.conditions
        ]
        preview_result = cleaner.preview_filter_rows(
            canonical=target_dataset,
            conditions=conditions,
            logical_operator=request.logical_operator,
        )
        return preview_result.to_dict()
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview row filtering: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/filter-rows/apply",
    response_model=StructuralApplyResponse,
)
def apply_filter_rows(dataset_id: str, request: RowFilterRequest):
    """Apply row filtering on a copy, updating the in-memory cleaned dataset."""
    from cleaning.structural import FilterCondition, StructuralCleaner, StructuralExecutionError
    from intelligence.profiler import DataProfiler
    from intelligence.semantic_analyzer import SemanticAnalyzer

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        conditions = [
            FilterCondition(column=c.column, operator=c.operator, value=c.value)
            for c in request.conditions
        ]
        cleaned_canonical, audit_info = cleaner.apply_filter_rows(
            canonical=target_dataset,
            conditions=conditions,
            logical_operator=request.logical_operator,
        )

        _refresh_record_cleaned_state(record, cleaned_canonical)
        record.last_cleaning_result = {
            "dataset_id": dataset_id,
            "action": "FILTER_ROWS",
            "audit_info": audit_info,
            "status": "APPLIED",
        }
        rows_removed = audit_info.get("rows_removed", 0)
        record.record_applied_operation(
            op_type="FILTER_ROWS",
            summary=f"{rows_removed} rows removed via filtering",
            details=audit_info,
        )

        return {
            "dataset_id": dataset_id,
            "action": "FILTER_ROWS",
            "audit_info": audit_info,
            "cleaned_row_count": len(cleaned_canonical.data),
            "cleaned_column_count": len(cleaned_canonical.data.columns),
            "status": "SUCCESS",
        }
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply row filter: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/duplicates/preview",
    response_model=DuplicateRemovalPreviewResponse,
)
def preview_duplicate_removal(dataset_id: str, request: DuplicateRemovalRequest):
    """Non-mutating preview of duplicate row removal."""
    from cleaning.structural import StructuralCleaner, StructuralExecutionError

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        preview_result = cleaner.preview_remove_duplicates(
            canonical=target_dataset,
            keep_strategy=request.keep_strategy,
        )
        return preview_result.to_dict()
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview duplicate removal: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/duplicates/apply",
    response_model=StructuralApplyResponse,
)
def apply_duplicate_removal(dataset_id: str, request: DuplicateRemovalRequest):
    """Apply duplicate row removal on a copy, updating the in-memory cleaned dataset."""
    from cleaning.structural import StructuralCleaner, StructuralExecutionError
    from intelligence.profiler import DataProfiler
    from intelligence.semantic_analyzer import SemanticAnalyzer

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        cleaned_canonical, audit_info = cleaner.apply_remove_duplicates(
            canonical=target_dataset,
            keep_strategy=request.keep_strategy,
        )

        _refresh_record_cleaned_state(record, cleaned_canonical)
        record.last_cleaning_result = {
            "dataset_id": dataset_id,
            "action": "REMOVE_DUPLICATES",
            "audit_info": audit_info,
            "status": "APPLIED",
        }
        dups_removed = audit_info.get("duplicate_rows_removed", 0)
        record.record_applied_operation(
            op_type="REMOVE_DUPLICATES",
            summary=f"{dups_removed} duplicate rows removed",
            details=audit_info,
        )

        return {
            "dataset_id": dataset_id,
            "action": "REMOVE_DUPLICATES",
            "audit_info": audit_info,
            "cleaned_row_count": len(cleaned_canonical.data),
            "cleaned_column_count": len(cleaned_canonical.data.columns),
            "status": "SUCCESS",
        }
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply duplicate removal: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/semantic-role/preview",
    response_model=SemanticRoleOverrideResponse,
)
def preview_semantic_role_override(dataset_id: str, request: SemanticRoleOverrideRequest):
    """Non-mutating preview of overriding a column's semantic role."""
    from cleaning.structural import StructuralCleaner, StructuralExecutionError

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        preview_result = cleaner.preview_semantic_role_override(
            canonical=target_dataset,
            column_name=request.column_name,
            selected_role=request.selected_role,
            semantic_profile=record.semantic_profile,
        )
        return {
            **preview_result.to_dict(),
            "status": "SUCCESS",
        }
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview semantic role override: {str(ex)}",
        )


@app.post(
    "/api/datasets/{dataset_id}/cleaning/structural/semantic-role/apply",
    response_model=SemanticRoleOverrideResponse,
)
def apply_semantic_role_override(dataset_id: str, request: SemanticRoleOverrideRequest):
    """Apply user-controlled semantic role override, storing it as authoritative."""
    from cleaning.structural import StructuralCleaner, StructuralExecutionError

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        cleaner = StructuralCleaner()
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        updated_sem_profile, audit_info = cleaner.apply_semantic_role_override(
            canonical=target_dataset,
            column_name=request.column_name,
            selected_role=request.selected_role,
            semantic_profile=record.semantic_profile,
            user_role_overrides_dict=record.user_semantic_role_overrides,
        )
        record.semantic_profile = updated_sem_profile
        record.registered_cleaned_dataset_id = None  # Invalidate cached registration
        record.record_applied_operation(
            op_type="SEMANTIC_ROLE_OVERRIDE",
            summary=f"1 semantic-role override on '{request.column_name}' ({request.selected_role.upper().strip()})",
            details={"column": request.column_name, "role": request.selected_role},
        )

        # Also update column metadata schema if present
        for col in target_dataset.metadata.schema:
            if col.original_name == request.column_name:
                col.semantic_role = ColumnRole(request.selected_role.upper().strip())

        ev = updated_sem_profile.get_evidence(request.column_name)
        system_role = (
            ev.system_role.value if ev and hasattr(ev.system_role, "value")
            else (str(ev.system_role) if ev and ev.system_role else "UNKNOWN")
        )

        return {
            "dataset_id": dataset_id,
            "column_name": request.column_name,
            "system_role": system_role,
            "selected_role": request.selected_role.upper().strip(),
            "physical_dtype": str(target_dataset.data[request.column_name].dtype),
            "evidence": ev.evidence if ev else [],
            "status": "SUCCESS",
        }
    except StructuralExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply semantic role override: {str(ex)}",
        )


@app.post("/api/datasets/{dataset_id}/cleaning/preview")
def preview_dataset_cleaning(dataset_id: str, request: CleaningSelectionRequest):
    """Generate a non-mutating preview of selected cleaning operations against canonical cleaned dataset."""
    from cleaning.executor import CleaningExecutionError, CleaningExecutor
    from cleaning.planner import CleaningPlanner

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        planner = CleaningPlanner()
        plan = planner.generate_plan(
            canonical=target_dataset,
            profile=record.profile,
            semantic_profile=record.semantic_profile,
            quality_assessment=getattr(record, "quality_assessment", None),
        )
        executor = CleaningExecutor(planner=planner)
        preview_result = executor.preview(
            canonical=target_dataset,
            selected_recommendation_ids=request.selected_recommendation_ids,
            plan=plan,
            operation_overrides=request.operation_overrides,
            operation_values=request.operation_values,
            custom_transformations=request.custom_transformations,
        )
        return preview_result.to_dict()
    except CleaningExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate cleaning preview: {str(ex)}",
        )


@app.post("/api/datasets/{dataset_id}/cleaning/apply")
def apply_dataset_cleaning(dataset_id: str, request: CleaningSelectionRequest):
    """Execute selected cleaning operations on a copy of current cleaned/raw dataset, validating results."""
    from cleaning.executor import CleaningExecutionError, CleaningExecutor
    from cleaning.planner import CleaningPlanner
    from intelligence.profiler import DataProfiler
    from intelligence.semantic_analyzer import SemanticAnalyzer

    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    try:
        target_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
        planner = CleaningPlanner()
        plan = planner.generate_plan(
            canonical=target_dataset,
            profile=record.profile,
            semantic_profile=record.semantic_profile,
            quality_assessment=getattr(record, "quality_assessment", None),
        )
        executor = CleaningExecutor(planner=planner)
        exec_result, cleaned_canonical = executor.execute(
            canonical=target_dataset,
            selected_recommendation_ids=request.selected_recommendation_ids,
            plan=plan,
            operation_overrides=request.operation_overrides,
            operation_values=request.operation_values,
            custom_transformations=request.custom_transformations,
        )

        _refresh_record_cleaned_state(record, cleaned_canonical)
        record.last_cleaning_result = exec_result.to_dict()

        if hasattr(exec_result, "applied_operations") and exec_result.applied_operations:
            for op in exec_result.applied_operations:
                op_status = getattr(op, "status", None) or (op.get("status") if isinstance(op, dict) else "")
                if op_status != "APPLIED":
                    continue
                op_name = getattr(op, "operation", "") or (op.get("operation") if isinstance(op, dict) else "")
                col_name = getattr(op, "column_name", "") or (op.get("column_name") if isinstance(op, dict) else "")
                cells_affected = getattr(op, "cells_affected", 0) or (op.get("cells_affected", 0) if isinstance(op, dict) else 0)
                method_used = getattr(op, "method_used", "") or (op.get("method_used", "") if isinstance(op, dict) else "")
                before_stat = getattr(op, "before_statistic", "") or (op.get("before_statistic", "") if isinstance(op, dict) else "")
                after_stat = getattr(op, "after_statistic", "") or (op.get("after_statistic", "") if isinstance(op, dict) else "")

                if "CONVERT" in op_name:
                    desc = f"1 datatype conversion on '{col_name}' ({before_stat} → {after_stat})"
                elif "IMPUTE" in op_name or "FILL" in op_name or "DROP_MISSING" in op_name:
                    desc = f"{cells_affected} missing values handled on '{col_name}' ({method_used or op_name})"
                elif "DUPLICATE" in op_name:
                    desc = f"{cells_affected} duplicate rows removed"
                else:
                    target_str = f"on '{col_name}'" if col_name else "across dataset"
                    desc = f"Applied {op_name.replace('_', ' ').lower()} {target_str} ({cells_affected} cells affected)"

                record.record_applied_operation(
                    op_type=op_name,
                    summary=desc,
                    details=op.to_dict() if hasattr(op, "to_dict") else (op if isinstance(op, dict) else {}),
                )

        return exec_result.to_dict()
    except CleaningExecutionError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute cleaning plan: {str(ex)}",
        )


@app.post("/api/datasets/{dataset_id}/cleaned/register")
def register_cleaned_dataset(dataset_id: str):
    """Register the successfully validated in-memory cleaned dataset as a distinct first-class dataset."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    target_cleaned = record.cleaned_dataset if record.cleaned_dataset is not None else (
        record.dataset if record.last_cleaning_result else None
    )

    if target_cleaned is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No validated cleaned result is available. Apply cleaning first.",
        )

    # Check for duplicate registration - return existing registered cleaned dataset if unchanged
    if record.registered_cleaned_dataset_id:
        existing_cleaned = session_store.get(record.registered_cleaned_dataset_id)
        if existing_cleaned:
            return {
                "status": "SUCCESS",
                "message": "Cleaned dataset already registered.",
                "dataset_id": existing_cleaned.dataset.metadata.dataset_id,
                "filename": existing_cleaned.dataset.metadata.name,
                "row_count": existing_cleaned.dataset.metadata.row_count,
                "column_count": existing_cleaned.dataset.metadata.column_count,
                "source_dataset_id": dataset_id,
                "already_registered": True,
                "metadata": existing_cleaned.to_metadata_dict(),
            }

    # Generate distinct, collision-safe cleaned dataset ID
    base_stem = "".join(
        c if c.isalnum() else "_" for c in os.path.splitext(record.dataset.metadata.name)[0].lower()
    ).strip("_")
    cleaned_dataset_id = f"ds_{base_stem}_cleaned_{uuid.uuid4().hex[:6]}"

    # Determine filename
    orig_name = record.dataset.metadata.name
    root, ext = os.path.splitext(orig_name)
    cleaned_name = f"{root}_cleaned{ext if ext else '.csv'}"

    # Extract schema from cleaned data
    from ingestion.loaders import CSVLoader
    loader = CSVLoader()
    schema = loader.extract_column_metadata(target_cleaned.data)

    from ingestion.models import CanonicalDataset, DatasetMetadata
    cleaned_meta = DatasetMetadata(
        dataset_id=cleaned_dataset_id,
        name=cleaned_name,
        source_type=record.dataset.metadata.source_type,
        row_count=len(target_cleaned.data),
        column_count=len(target_cleaned.data.columns),
        schema=schema,
        custom_metadata={
            "source_dataset_id": dataset_id,
            "source_dataset_name": record.dataset.metadata.name,
            "derivation": "cleaning",
            "derived_from_cleaning": True,
            "operations_applied": (record.last_cleaning_result or {}).get("operations_applied", 0),
        },
    )
    cleaned_canonical = CanonicalDataset(
        metadata=cleaned_meta,
        data=target_cleaned.data.copy(deep=True),
    )

    # Run profiler, semantic analyzer, readiness validator
    profile = profile_dataset(cleaned_canonical)
    semantic_profile = analyze_semantics(cleaned_canonical, profile=profile, apply_roles=True)

    # Re-apply any existing user semantic role overrides to the registered dataset's profile & schema
    cleaned_overrides: Dict[str, str] = {}
    if hasattr(record, "user_semantic_role_overrides") and record.user_semantic_role_overrides:
        cleaned_overrides = dict(record.user_semantic_role_overrides)
        for col_name, role_str in cleaned_overrides.items():
            if col_name in cleaned_canonical.data.columns:
                ev = semantic_profile.get_evidence(col_name)
                if ev is not None:
                    if not hasattr(ev, "system_role") or getattr(ev, "system_role") is None:
                        ev.system_role = ev.candidate_role
                    ev.user_override_role = ColumnRole(role_str)
                    ev.candidate_role = ColumnRole(role_str)
                    ev.is_user_overridden = True
                    ev.evidence = list(ev.evidence) + [f"User explicitly designated column as {role_str}."]
                for col_meta in cleaned_canonical.metadata.schema:
                    if col_meta.original_name == col_name:
                        col_meta.semantic_role = ColumnRole(role_str)

    readiness = assess_readiness(cleaned_canonical, profile=profile, semantic_profile=semantic_profile)

    # Save to session store as independent DatasetSessionRecord
    cleaned_record = DatasetSessionRecord(
        dataset=cleaned_canonical,
        profile=profile,
        semantic_profile=semantic_profile,
        readiness=readiness,
        cleaning_report=None,
    )
    cleaned_record.user_semantic_role_overrides = cleaned_overrides
    session_store.save(cleaned_record)
    record.registered_cleaned_dataset_id = cleaned_dataset_id

    return {
        "status": "SUCCESS",
        "message": "Cleaned dataset registered successfully.",
        "dataset_id": cleaned_dataset_id,
        "filename": cleaned_name,
        "row_count": cleaned_canonical.metadata.row_count,
        "column_count": cleaned_canonical.metadata.column_count,
        "source_dataset_id": dataset_id,
        "already_registered": False,
        "metadata": cleaned_record.to_metadata_dict(),
    }


@app.get("/api/datasets/{dataset_id}/download")
def download_dataset(dataset_id: str, format: str = "csv"):
    """Download registered dataset or latest cleaned state in CSV or XLSX format."""
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in current session.",
        )

    norm_format = format.lower().strip()
    if norm_format not in ["csv", "xlsx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported download format '{format}'. Supported formats: csv, xlsx.",
        )

    active_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    base_name = os.path.splitext(active_dataset.metadata.name)[0]
    safe_base = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in base_name).strip() or "dataset"

    if norm_format == "csv":
        csv_bytes = active_dataset.data.to_csv(index=False).encode("utf-8")
        filename = f"{safe_base}.csv"
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    elif norm_format == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            active_dataset.data.to_excel(writer, index=False, sheet_name="Sheet1")
        xlsx_bytes = output.getvalue()
        filename = f"{safe_base}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@app.get("/api/providers/status")
def get_providers_status():
    """Retrieve live availability and diagnostic status for configured LLM providers."""
    from providers.factory import LLMProviderFactory
    from providers.base import ProviderInitializationError, LLMClientError

    providers_to_check = ["gemini", "groq", "groq_secondary", "ollama", "rule_based_baseline"]
    results = []
    for p in providers_to_check:
        is_baseline = p in ("rule_based_baseline", "zero_cost_local", "local")
        try:
            client = LLMProviderFactory.create_client(p)
            results.append({
                "provider": p,
                "status": "live",
                "model": getattr(client, "model_name", "rule-based"),
                "reason": None,
                "is_baseline": is_baseline,
            })
        except (ProviderInitializationError, LLMClientError, Exception) as e:
            results.append({
                "provider": p,
                "status": "failed",
                "model": None,
                "reason": str(e),
                "is_baseline": is_baseline,
            })
    return {"providers": results}


@app.post(
    "/pipeline",
    response_model=OrchestratorPipelineResponse,
)
@app.post(
    "/api/orchestrator/pipeline",
    response_model=OrchestratorPipelineResponse,
)
def run_orchestrator_pipeline_endpoint(req: OrchestratorPipelineRequest):
    """Execute end-to-end orchestration pipeline from natural language intent to validated DashboardSpec."""
    record = session_store.get(req.dataset_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{req.dataset_id}' not found in current session.",
        )

    # Check for pre-existing candidates if re-running from chosen interpretation
    existing_cands = record.cached_candidates.get(req.intent) if req.chosen_plan_id else None

    pipe_kwargs: Dict[str, Any] = {}
    generator = getattr(app.state, "mock_generator", None)
    if generator is not None:
        pipe_kwargs["generator"] = generator
    if req.rank_tie_epsilon is not None:
        pipe_kwargs["rank_tie_epsilon"] = req.rank_tie_epsilon
    if req.robustness_tie_floor is not None:
        pipe_kwargs["robustness_tie_floor"] = req.robustness_tie_floor

    active_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    pipeline_result = run_orchestration_pipeline(
        dataset=active_dataset,
        semantic_profile=record.semantic_profile,
        readiness=record.readiness,
        intent=req.intent,
        data_profile=record.profile,
        mode=req.mode or "both",
        k=req.k or 3,
        require_clarification=bool(req.require_clarification),
        chosen_plan_id=req.chosen_plan_id,
        existing_candidates=existing_cands,
        **pipe_kwargs,
    )

    # Cache generated candidates in session store for subsequent clarification follow-ups
    if pipeline_result.cached_candidates:
        record.cached_candidates[req.intent] = pipeline_result.cached_candidates

    spec = pipeline_result.dashboard_spec
    ranked_list = []
    if pipeline_result.ranked_candidates:
        for plan, res, score, rank in pipeline_result.ranked_candidates:
            ranked_list.append({
                "rank": rank,
                "plan_id": plan.plan_id,
                "generator": plan.generator,
                "visualization": plan.visualization.value,
                "metric": f"{plan.metric.aggregation.value}({plan.metric.column})",
                "dimensions": [
                    f"{d.column}{' (' + d.granularity.value + ')' if d.granularity else ''}"
                    for d in plan.dimensions
                ],
                "score": round(score.total, 4),
                "score_breakdown": score.model_dump(),
                "is_winner": (spec is not None and spec.winner.plan.plan_id == plan.plan_id),
            })

    winner_dict = None
    if spec:
        winner_dict = {
            "plan_id": spec.winner.plan.plan_id,
            "generator": spec.winner.plan.generator,
            "visualization": spec.winner.plan.visualization.value,
            "score": round(spec.winner.score_breakdown.total, 4),
            "score_breakdown": spec.winner.score_breakdown.model_dump(),
            "metric": f"{spec.winner.plan.metric.aggregation.value}({spec.winner.plan.metric.column})",
            "dimensions": [
                f"{d.column}{' (' + d.granularity.value + ')' if d.granularity else ''}"
                for d in spec.winner.plan.dimensions
            ],
            "reasoning": spec.winner.plan.reasoning.model_dump(),
            "pass2_passed": spec.trace.pass2_result.passed if spec.trace.pass2_result else True,
            "pass2_issues": [
                i.model_dump() for i in (spec.trace.pass2_result.issues if spec.trace.pass2_result else [])
            ],
            "execution": spec.winner.execution_result.model_dump(),
        }

    if spec:
        dashboard_specs_store[spec.spec_id] = spec
        if spec.spec_id not in original_specs_store:
            original_specs_store[spec.spec_id] = spec

    return OrchestratorPipelineResponse(
        status=pipeline_result.status,
        message=pipeline_result.message,
        spec_id=spec.spec_id if spec else None,
        headline=spec.headline if spec else None,
        panels=[p.model_dump() for p in spec.panels] if spec else None,
        dashboard_spec=spec.model_dump() if spec else None,
        ranked_candidates=ranked_list,
        winner=winner_dict,
        is_tie=pipeline_result.is_tie,
        cascade_depth=pipeline_result.cascade_depth,
        ambiguity_status=pipeline_result.ambiguity.status.value if pipeline_result.ambiguity else "CLEAR",
        ambiguity_message=pipeline_result.ambiguity.message if pipeline_result.ambiguity else None,
        clarification_needed=(
            pipeline_result.status == "NEEDS_CLARIFICATION"
            or pipeline_result.is_tie
            or (pipeline_result.ambiguity is not None and pipeline_result.ambiguity.status.value != "CLEAR")
        ),
        clarification_options=pipeline_result.clarification_options,
        options=pipeline_result.options,
        run_id=pipeline_result.run_id,
        cached_candidates=[c.model_dump() for c in pipeline_result.cached_candidates] if pipeline_result.cached_candidates else None,
        decision_log_entry=pipeline_result.decision_log_entry,
        explainability_log_entry=pipeline_result.explainability_log_entry,
        mode=spec.mode if spec else "focused",
        rejected_insights=spec.rejected_insights if spec else None,
    )


@app.post(
    "/pipeline/resolve",
    response_model=OrchestratorPipelineResponse,
    responses={
        404: {"model": ResolveErrorResponse},
        410: {"model": ResolveErrorResponse},
        422: {"model": ResolveErrorResponse},
    },
)
@app.post(
    "/api/orchestrator/pipeline/resolve",
    response_model=OrchestratorPipelineResponse,
    responses={
        404: {"model": ResolveErrorResponse},
        410: {"model": ResolveErrorResponse},
        422: {"model": ResolveErrorResponse},
    },
)
def resolve_pipeline_endpoint(req: ResolvePipelineRequest):
    """Resolve a tied pipeline run with a user-selected candidate plan."""
    try:
        pipeline_result = resolve_pipeline_run(
            run_id=req.run_id,
            selected_plan_id=req.selected_plan_id,
        )
    except RunResolveError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.__class__.__name__,
                "message": e.message,
                "error_type": e.error_type,
                "status_code": e.status_code,
            },
        )

    spec = pipeline_result.dashboard_spec
    ranked_list = []
    if pipeline_result.ranked_candidates:
        for plan, res, score, rank in pipeline_result.ranked_candidates:
            ranked_list.append({
                "rank": rank,
                "plan_id": plan.plan_id,
                "generator": plan.generator,
                "visualization": plan.visualization.value,
                "metric": f"{plan.metric.aggregation.value}({plan.metric.column})",
                "dimensions": [
                    f"{d.column}{' (' + d.granularity.value + ')' if d.granularity else ''}"
                    for d in plan.dimensions
                ],
                "score": round(score.total, 4),
                "score_breakdown": score.model_dump(),
                "is_winner": (spec is not None and spec.winner.plan.plan_id == plan.plan_id),
            })

    winner_dict = None
    if spec:
        winner_dict = {
            "plan_id": spec.winner.plan.plan_id,
            "generator": spec.winner.plan.generator,
            "visualization": spec.winner.plan.visualization.value,
            "score": round(spec.winner.score_breakdown.total, 4),
            "score_breakdown": spec.winner.score_breakdown.model_dump(),
            "metric": f"{spec.winner.plan.metric.aggregation.value}({spec.winner.plan.metric.column})",
            "dimensions": [
                f"{d.column}{' (' + d.granularity.value + ')' if d.granularity else ''}"
                for d in spec.winner.plan.dimensions
            ],
            "reasoning": spec.winner.plan.reasoning.model_dump(),
            "pass2_passed": spec.trace.pass2_result.passed if spec.trace.pass2_result else True,
            "pass2_issues": [
                i.model_dump() for i in (spec.trace.pass2_result.issues if spec.trace.pass2_result else [])
            ],
            "execution": spec.winner.execution_result.model_dump(),
        }

    if spec:
        dashboard_specs_store[spec.spec_id] = spec
        if spec.spec_id not in original_specs_store:
            original_specs_store[spec.spec_id] = spec

    return OrchestratorPipelineResponse(
        status=pipeline_result.status,
        message=pipeline_result.message,
        spec_id=spec.spec_id if spec else None,
        headline=spec.headline if spec else None,
        panels=[p.model_dump() for p in spec.panels] if spec else None,
        dashboard_spec=spec.model_dump() if spec else None,
        ranked_candidates=ranked_list,
        winner=winner_dict,
        is_tie=pipeline_result.is_tie,
        cascade_depth=pipeline_result.cascade_depth,
        ambiguity_status=pipeline_result.ambiguity.status.value if pipeline_result.ambiguity else "CLEAR",
        ambiguity_message=pipeline_result.ambiguity.message if pipeline_result.ambiguity else None,
        clarification_needed=False,
        clarification_options=None,
        options=None,
        cached_candidates=None,
        run_id=req.run_id,
        resolved_by="user",
        decision_log_entry=pipeline_result.decision_log_entry,
        explainability_log_entry=pipeline_result.explainability_log_entry,
        mode=spec.mode if spec else "focused",
        rejected_insights=spec.rejected_insights if spec else None,
    )


@app.post(
    "/dashboard/{spec_id}/tile/{tile_id}/query",
    response_model=TileQueryResponse,
    summary="Query a dashboard tile with recompiled filters",
)
@app.post(
    "/api/dashboard/{spec_id}/tile/{tile_id}/query",
    response_model=TileQueryResponse,
    summary="Query a dashboard tile with recompiled filters (API prefix)",
)
def query_dashboard_tile(
    spec_id: str,
    tile_id: str,
    req: TileQueryRequest,
):
    """Recompiles the tile's stored plan with added client filters.

    Validates columns against semantic profile roles.
    Rejects unknown columns with typed error (400).
    Rejects SQL injection patterns with typed error (400).
    Caches responses by (spec, tile, filters).
    Returns INSUFFICIENT_DATA status if row count is below threshold.
    """
    # 1. Lookup DashboardSpec
    spec = dashboard_specs_store.get(spec_id)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dashboard spec not found",
                "message": f"Spec '{spec_id}' was not found in active session",
                "error_type": "SPEC_NOT_FOUND",
                "status_code": 404,
            },
        )

    # 2. Find Tile
    tile = next((t for t in spec.tiles if t.id == tile_id or getattr(t, "candidate_id", None) == tile_id), None)
    if not tile:
        if hasattr(spec, "winner") and spec.winner:
            from orchestrator.schemas import DashboardTile
            tile = DashboardTile(
                id=tile_id,
                title=spec.headline or "Key Analytical Finding",
                chart_type="bar",
                plan=spec.winner.plan,
                compiled_sql=spec.winner.execution_result.compiled_sql,
                data=spec.winner.execution_result.rows or [],
            )
        else:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Tile not found",
                    "message": f"Tile '{tile_id}' not found in dashboard spec",
                    "error_type": "TILE_NOT_FOUND",
                    "status_code": 404,
                },
            )

    # 3. Cache check
    filter_repr = tuple(
        sorted(
            (f.column, f.operator.strip().upper(), str(f.values if f.values is not None else f.value))
            for f in req.filters
        )
    )
    cache_key = (spec_id, tile_id, str(filter_repr))
    if cache_key in tile_query_cache:
        cached_resp = tile_query_cache[cache_key]
        return TileQueryResponse(
            tile_id=tile_id,
            status=cached_resp.status,
            row_count=cached_resp.row_count,
            data=cached_resp.data,
            compiled_sql=cached_resp.compiled_sql,
            cached=True,
            message=cached_resp.message,
        )

    # 4. Dataset & Semantic Profile lookup
    session_rec = session_store.get(spec.dataset_id)
    if session_rec:
        dataset = session_rec.cleaned_dataset if session_rec.cleaned_dataset is not None else session_rec.dataset
        semantic_profile = session_rec.semantic_profile
    else:
        dataset = None
        semantic_profile = None

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{spec.dataset_id}' could not be located",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )

    valid_columns = set()
    if semantic_profile and semantic_profile.column_evidences:
        valid_columns = set(semantic_profile.column_evidences.keys())
    elif hasattr(dataset, "data") and dataset.data is not None:
        valid_columns = set(dataset.data.columns)

    # 5. Validate filters
    ALLOWED_OPERATORS = {"=", "!=", "<>", "<", "<=", ">", ">=", "BETWEEN", "IN", "NOT IN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL"}
    INJECTION_TOKENS = ["'", '"', ";", "--", "/*", "xp_", "exec ", "union ", "drop ", "delete "]

    for flt in req.filters:
        # Validate column
        if valid_columns and flt.column not in valid_columns:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Unknown column",
                    "message": f"Column '{flt.column}' does not exist in dataset roles",
                    "error_type": "UNKNOWN_COLUMN",
                    "status_code": 400,
                },
            )

        # Validate operator
        if flt.operator.strip().upper() not in ALLOWED_OPERATORS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid operator",
                    "message": f"Operator '{flt.operator}' is not supported",
                    "error_type": "INVALID_OPERATOR",
                    "status_code": 400,
                },
            )

        # Check injection in string representation of individual values
        vals_to_check = flt.values if isinstance(flt.values, list) else [flt.values if flt.values is not None else flt.value]
        for v in vals_to_check:
            v_str = str(v).lower()
            if any(token in v_str for token in INJECTION_TOKENS):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid filter value",
                        "message": "SQL injection pattern detected in filter value",
                        "error_type": "INVALID_FILTER_VALUE",
                        "status_code": 400,
                    },
                )

    # 6. Recompile Plan with Filters
    from orchestrator.schemas import FilterSpec
    from engine.duckdb_executor import DuckDBExecutor

    base_plan = tile.plan or spec.winner.plan
    # Replace any pre-existing base_plan filters on the same columns that client is filtering
    req_filter_cols = {f.column.lower() for f in req.filters}
    new_filters = [f for f in (base_plan.filters or []) if f.column.lower() not in req_filter_cols]

    # Deduplicate client filters by column (keep latest if duplicate)
    client_filters_by_col = {}
    for flt in req.filters:
        client_filters_by_col[flt.column.lower()] = flt

    for flt in client_filters_by_col.values():
        op = flt.operator.strip().upper()
        val = flt.values if flt.values is not None else flt.value
        if op in ("=", "!=", "<>", "<", "<=", ">", ">=") and isinstance(val, (list, tuple)) and len(val) == 1:
            val = val[0]
        elif op == "BETWEEN" and isinstance(val, (list, tuple)) and len(val) >= 2:
            val = [val[0], val[1]]
        new_filters.append(
            FilterSpec(
                column=flt.column,
                operator=flt.operator,
                value=val,
            )
        )

    modified_plan = base_plan.model_copy(
        update={
            "filters": new_filters,
            "plan_id": str(uuid.uuid4()),
        }
    )

    executor = DuckDBExecutor()
    result = executor.execute_plan(modified_plan, dataset, semantic_profile)

    rows = result.rows or []
    is_empty = len(rows) < 1 or (
        len(rows) == 1
        and not getattr(tile, "dimensions", None)
        and all(v is None for v in rows[0].values())
    )
    if is_empty:
        resp = TileQueryResponse(
            tile_id=tile_id,
            status="INSUFFICIENT_DATA",
            row_count=0,
            data=[],
            compiled_sql=result.compiled_sql,
            cached=False,
            message="Insufficient data after filtering (0 rows returned)",
        )   
    else:
        resp = TileQueryResponse(
            tile_id=tile_id,
            status="SUCCESS",
            row_count=len(rows),
            data=rows,
            compiled_sql=result.compiled_sql,
            cached=False,
        )

    tile_query_cache[cache_key] = resp
    return resp


class UpdateDashboardTileRequest(BaseModel):
    """Payload for updating an existing dashboard tile with a new candidate plan."""

    title: Optional[str] = None
    description: Optional[str] = None
    chart_type: Optional[str] = None
    plan: CandidatePlan


@app.put(
    "/api/dashboard/{spec_id}/tile/{tile_id}",
    summary="Update a dashboard tile with a newly validated candidate plan",
)
def update_dashboard_tile(
    spec_id: str,
    tile_id: str,
    req: UpdateDashboardTileRequest,
):
    """Validate, re-execute, and update an existing dashboard tile within the working DashboardSpec."""
    spec = dashboard_specs_store.get(spec_id)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dashboard spec not found",
                "message": f"Spec '{spec_id}' was not found in active session",
                "error_type": "SPEC_NOT_FOUND",
                "status_code": 404,
            },
        )

    # Ensure original spec snapshot is saved before applying edits
    if spec_id not in original_specs_store:
        original_specs_store[spec_id] = spec

    tile_idx = None
    existing_tile = None
    for idx, t in enumerate(spec.tiles):
        if t.id == tile_id or getattr(t, "candidate_id", None) == tile_id:
            tile_idx = idx
            existing_tile = t
            break

    if existing_tile is None or tile_idx is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Tile not found",
                "message": f"Tile '{tile_id}' not found in dashboard spec",
                "error_type": "TILE_NOT_FOUND",
                "status_code": 404,
            },
        )

    record = session_store.get(spec.dataset_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{spec.dataset_id}' could not be located",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )

    active_dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset

    # 1. Pass 1a Pre-Dispatch Validation
    pass1a_res = validate_pass1a(
        plan=req.plan,
        semantic_profile=record.semantic_profile,
        readiness=record.readiness,
    )
    if not pass1a_res.passed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Plan validation failed",
                "message": "Candidate plan failed Pass 1a pre-dispatch validation",
                "issues": [i.model_dump() for i in pass1a_res.issues],
                "error_type": "VALIDATION_FAILED",
                "status_code": 422,
            },
        )

    # 2. DuckDB Execution on Active Dataset
    from engine.duckdb_executor import DuckDBExecutor
    from orchestrator.schemas import ExecutionStatus, TileEvidence
    executor = DuckDBExecutor()
    exec_res = executor.execute_plan(
        plan=req.plan,
        dataset=active_dataset,
        semantic_profile=record.semantic_profile,
    )
    if exec_res.status != ExecutionStatus.SUCCESS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Execution failed",
                "message": exec_res.error_message or "Query execution on DuckDB failed",
                "error_type": "EXECUTION_FAILED",
                "status_code": 400,
            },
        )

    # 3. Pass 1b Post-Execution Validation
    pass1b_res = validate_pass1b(
        plan=req.plan,
        exec_result=exec_res,
    )

    # 4. Resolve dimensions, metric keys, x_key, y_keys
    dims = [d.column for d in req.plan.dimensions]
    x_key = dims[0] if dims else None

    agg_val = (
        req.plan.metric.aggregation.value
        if hasattr(req.plan.metric.aggregation, "value")
        else str(req.plan.metric.aggregation)
    ).lower()
    col_val = "records" if req.plan.metric.column == "*" else req.plan.metric.column
    expected_metric_alias = f"{agg_val}_{col_val}"

    y_keys = [expected_metric_alias] if expected_metric_alias in (exec_res.columns or []) else (
        [c for c in (exec_res.columns or []) if c not in dims] or ["value"]
    )

    # 5. Update Evidence provenance
    from orchestrator.schemas import TileEvidence
    new_evidence = TileEvidence(
        strength=existing_tile.evidence.strength if existing_tile.evidence else 0.8,
        robustness=existing_tile.evidence.robustness if existing_tile.evidence else 0.85,
        fdr_passed=existing_tile.evidence.fdr_passed if existing_tile.evidence else True,
        fdr_q_value=existing_tile.evidence.fdr_q_value if existing_tile.evidence else None,
        n=exec_res.row_count,
        score=existing_tile.evidence.score if existing_tile.evidence else 0.8,
    )

    chart_type = req.chart_type or (
        req.plan.visualization.value
        if hasattr(req.plan.visualization, "value")
        else str(req.plan.visualization)
    )

    updated_tile = existing_tile.model_copy(
        update={
            "title": req.title or existing_tile.title,
            "chart_type": chart_type,
            "plan": req.plan,
            "compiled_sql": exec_res.compiled_sql,
            "data": exec_res.rows or [],
            "dimensions": dims,
            "metrics": [f"{agg_val}({req.plan.metric.column})"],
            "x_key": x_key,
            "y_keys": y_keys,
            "evidence": new_evidence,
            "why_chosen": req.description or existing_tile.why_chosen,
            "metadata": {
                **(existing_tile.metadata or {}),
                "is_edited": True,
                "dq_warnings": list(exec_res.warnings or []),
                "execution_duration_ms": int(exec_res.runtime_seconds * 1000) if exec_res.runtime_seconds else None,
            },
        }
    )

    # Update spec in store
    new_tiles = list(spec.tiles)
    new_tiles[tile_idx] = updated_tile
    updated_spec = spec.model_copy(update={"tiles": new_tiles})
    dashboard_specs_store[spec_id] = updated_spec

    # Invalidate cached queries for this tile
    keys_to_delete = [k for k in tile_query_cache.keys() if k[0] == spec_id and (k[1] == tile_id or k[1] == existing_tile.id)]
    for k in keys_to_delete:
        del tile_query_cache[k]

    return {
        "status": "SUCCESS",
        "tile": updated_tile.model_dump(),
        "spec_id": spec_id,
        "pass1a": pass1a_res.model_dump(),
        "pass1b": pass1b_res.model_dump(),
    }


@app.delete(
    "/api/dashboard/{spec_id}/tile/{tile_id}",
    summary="Remove a tile from the working DashboardSpec",
)
def delete_dashboard_tile(
    spec_id: str,
    tile_id: str,
):
    """Remove a dashboard tile from the active working DashboardSpec."""
    spec = dashboard_specs_store.get(spec_id)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dashboard spec not found",
                "message": f"Spec '{spec_id}' was not found in active session",
                "error_type": "SPEC_NOT_FOUND",
                "status_code": 404,
            },
        )

    if spec_id not in original_specs_store:
        original_specs_store[spec_id] = spec

    new_tiles = [t for t in spec.tiles if t.id != tile_id and getattr(t, "candidate_id", None) != tile_id]
    if len(new_tiles) == len(spec.tiles):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Tile not found",
                "message": f"Tile '{tile_id}' not found in dashboard spec",
                "error_type": "TILE_NOT_FOUND",
                "status_code": 404,
            },
        )

    updated_spec = spec.model_copy(update={"tiles": new_tiles})
    dashboard_specs_store[spec_id] = updated_spec

    keys_to_delete = [k for k in tile_query_cache.keys() if k[0] == spec_id and k[1] == tile_id]
    for k in keys_to_delete:
        del tile_query_cache[k]

    return {
        "status": "SUCCESS",
        "message": f"Tile '{tile_id}' removed from dashboard.",
        "remaining_count": len(new_tiles),
    }


@app.post(
    "/api/dashboard/{spec_id}/tile/{tile_id}/reset",
    summary="Reset an edited tile back to its original AI-generated configuration",
)
def reset_dashboard_tile(
    spec_id: str,
    tile_id: str,
):
    """Reset a tile back to its immutable original state from initial generation."""
    spec = dashboard_specs_store.get(spec_id)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dashboard spec not found",
                "message": f"Spec '{spec_id}' was not found in active session",
                "error_type": "SPEC_NOT_FOUND",
                "status_code": 404,
            },
        )

    original_spec = original_specs_store.get(spec_id)
    if not original_spec:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Original dashboard spec not found",
                "message": f"Original spec for '{spec_id}' is not available for reset",
                "error_type": "ORIGINAL_SPEC_NOT_FOUND",
                "status_code": 404,
            },
        )

    orig_tile = next((t for t in original_spec.tiles if t.id == tile_id or getattr(t, "candidate_id", None) == tile_id), None)
    if not orig_tile:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Original tile not found",
                "message": f"Original tile '{tile_id}' could not be located",
                "error_type": "TILE_NOT_FOUND",
                "status_code": 404,
            },
        )

    new_tiles = []
    found = False
    for t in spec.tiles:
        if t.id == tile_id or getattr(t, "candidate_id", None) == tile_id:
            new_tiles.append(orig_tile)
            found = True
        else:
            new_tiles.append(t)
    if not found:
        new_tiles.append(orig_tile)

    updated_spec = spec.model_copy(update={"tiles": new_tiles})
    dashboard_specs_store[spec_id] = updated_spec

    keys_to_delete = [k for k in tile_query_cache.keys() if k[0] == spec_id and k[1] == tile_id]
    for k in keys_to_delete:
        del tile_query_cache[k]

    return {
        "status": "SUCCESS",
        "message": f"Tile '{tile_id}' reset to original configuration.",
        "tile": orig_tile.model_dump(),
    }


@app.post(
    "/api/dashboard/{spec_id}/reset",
    summary="Reset all tiles in dashboard back to original AI-generated state",
)
def reset_entire_dashboard(
    spec_id: str,
):
    """Reset all tiles in working spec back to original AI-generated spec."""
    original_spec = original_specs_store.get(spec_id)
    if not original_spec:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Original dashboard spec not found",
                "message": f"Original spec for '{spec_id}' is not available for reset",
                "error_type": "ORIGINAL_SPEC_NOT_FOUND",
                "status_code": 404,
            },
        )

    dashboard_specs_store[spec_id] = original_spec

    keys_to_delete = [k for k in tile_query_cache.keys() if k[0] == spec_id]
    for k in keys_to_delete:
        del tile_query_cache[k]

    return {
        "status": "SUCCESS",
        "message": "Dashboard successfully reset to original specification.",
        "spec": original_spec.model_dump(),
    }


class AnalyticalQueryRequest(BaseModel):
    """Payload for natural language analytical query execution."""

    dataset_id: str
    question: str
    row_limit: Optional[int] = None


class AnalyticalQueryResponse(BaseModel):
    """Structured response for natural language analytical query."""

    status: str
    question: str
    compiled_sql: Optional[str] = None
    data: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    row_count: int = 0
    validation_status: str = "PASSED"
    validation_issues: List[Dict[str, Any]] = Field(default_factory=list)
    ambiguity_status: str = "CLEAR"
    ambiguity_details: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 1.0
    evidence: List[str] = Field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    structured_intent: Optional[Dict[str, Any]] = None
    runtime_seconds: float = 0.0
    message: Optional[str] = None


@app.post(
    "/api/query",
    response_model=AnalyticalQueryResponse,
    summary="Execute a generalized natural-language analytical query",
)
@app.post(
    "/api/analytical-query",
    response_model=AnalyticalQueryResponse,
    summary="Execute a generalized natural-language analytical query (alias)",
)
def handle_analytical_query(req: AnalyticalQueryRequest):
    """Execute arbitrary natural-language analytical query with SQL provenance."""
    record = session_store.get(req.dataset_id)
    if not record or not record.dataset:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{req.dataset_id}' not found in active session",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )
    dataset = record.dataset
    semantic_profile = record.semantic_profile
    if not semantic_profile:
        from intelligence.semantic_analyzer import analyze_semantics
        semantic_profile = analyze_semantics(dataset, record.profile)
        record.semantic_profile = semantic_profile

    from orchestrator.query_engine import execute_analytical_query
    from orchestrator.schemas import AmbiguityStatus

    res = execute_analytical_query(
        question=req.question,
        dataset=dataset,
        semantic_profile=semantic_profile,
        row_limit=req.row_limit,
    )

    is_success = res.validation_status in ("PASSED", "WARNING") and res.ambiguity_status == AmbiguityStatus.CLEAR
    return AnalyticalQueryResponse(
        status="SUCCESS" if is_success else "FAILED",
        question=res.question,
        compiled_sql=res.compiled_sql,
        data=res.rows,
        columns=res.columns,
        row_count=res.row_count,
        validation_status=res.validation_status,
        validation_issues=[i.model_dump() for i in res.validation_issues],
        ambiguity_status=res.ambiguity_status.value if hasattr(res.ambiguity_status, "value") else str(res.ambiguity_status),
        ambiguity_details=[a.model_dump() for a in res.ambiguity_details],
        confidence=res.confidence,
        evidence=res.evidence,
        plan=res.plan.model_dump() if res.plan else None,
        structured_intent=res.structured_intent.model_dump() if res.structured_intent else None,
        runtime_seconds=res.runtime_seconds,
        message=res.error_message,
    )


class DiscoverInsightsRequest(BaseModel):
    """Payload for evidence-grounded insight generation."""

    dataset_id: str
    max_insights: Optional[int] = 8
    use_llm: Optional[bool] = True


class DiscoverInsightsResponse(BaseModel):
    """Structured response for evidence-grounded insights."""

    status: str
    dataset_id: str
    insights: List[Dict[str, Any]] = Field(default_factory=list)
    rejections: List[Dict[str, Any]] = Field(default_factory=list)
    total_candidates_generated: int = 0
    total_candidates_executed: int = 0
    total_insights_validated: int = 0
    total_insights_selected: int = 0
    runtime_seconds: float = 0.0
    summary_notice: Optional[str] = None


@app.post(
    "/api/insights",
    response_model=DiscoverInsightsResponse,
    summary="Generate evidence-grounded AI insights for a dataset",
)
@app.post(
    "/api/discover-insights",
    response_model=DiscoverInsightsResponse,
    summary="Generate evidence-grounded AI insights for a dataset (alias)",
)
def handle_discover_insights(req: DiscoverInsightsRequest):
    """Generate deterministic, evidence-grounded insights with full DuckDB provenance."""
    record = session_store.get(req.dataset_id)
    if not record or not record.dataset:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{req.dataset_id}' not found in active session",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )
    dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    profile = record.profile
    semantic_profile = record.semantic_profile
    if not semantic_profile:
        from intelligence.semantic_analyzer import analyze_semantics
        semantic_profile = analyze_semantics(dataset, profile)
        record.semantic_profile = semantic_profile

    from orchestrator.insights import generate_grounded_insights

    res = generate_grounded_insights(
        dataset=dataset,
        semantic_profile=semantic_profile,
        max_insights=req.max_insights or 8,
        use_llm=req.use_llm if req.use_llm is not None else True,
    )

    return DiscoverInsightsResponse(
        status="SUCCESS",
        dataset_id=res.dataset_id,
        insights=[i.model_dump() for i in res.insights],
        rejections=[r.model_dump() for r in res.rejections],
        total_candidates_generated=res.total_candidates_generated,
        total_candidates_executed=res.total_candidates_executed,
        total_insights_validated=res.total_insights_validated,
        total_insights_selected=res.total_insights_selected,
        runtime_seconds=res.runtime_seconds,
        summary_notice=res.summary_notice,
    )


class OverviewDashboardRequest(BaseModel):
    """Payload for autonomous whole-dataset overview dashboard generation."""

    dataset_id: str
    use_llm: Optional[bool] = True


@app.post(
    "/api/overview",
    response_model=OrchestratorPipelineResponse,
    summary="Generate autonomous whole-dataset overview dashboard",
)
@app.post(
    "/api/overview-dashboard",
    response_model=OrchestratorPipelineResponse,
    summary="Generate autonomous whole-dataset overview dashboard (alias)",
)
def handle_overview_dashboard(req: OverviewDashboardRequest):
    """Generate autonomous whole-dataset overview dashboard backed by DuckDB and Evidence-Grounded Insights."""
    record = session_store.get(req.dataset_id)
    if not record or not record.dataset:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{req.dataset_id}' not found in active session",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )
    dataset = record.cleaned_dataset if record.cleaned_dataset is not None else record.dataset
    profile = record.profile
    semantic_profile = record.semantic_profile
    if not semantic_profile:
        from intelligence.semantic_analyzer import analyze_semantics
        semantic_profile = analyze_semantics(dataset, profile)
        record.semantic_profile = semantic_profile

    from orchestrator.overview import generate_overview_dashboard

    spec = generate_overview_dashboard(
        dataset=dataset,
        semantic_profile=semantic_profile,
        readiness=record.readiness,
        data_profile=profile,
        use_llm=req.use_llm if req.use_llm is not None else True,
    )

    dashboard_specs_store[spec.spec_id] = spec
    if spec.spec_id not in original_specs_store:
        original_specs_store[spec.spec_id] = spec

    ranked_list = []
    if spec.winner:
        ranked_list.append({
            "rank": 1,
            "plan_id": spec.winner.plan.plan_id,
            "generator": spec.winner.plan.generator,
            "visualization": spec.winner.plan.visualization.value,
            "metric": f"{spec.winner.plan.metric.aggregation.value}({spec.winner.plan.metric.column})",
            "dimensions": [
                f"{d.column}{' (' + d.granularity.value + ')' if d.granularity else ''}"
                for d in spec.winner.plan.dimensions
            ],
            "score": round(spec.winner.score_breakdown.total, 4) if spec.winner.score_breakdown else 0.9,
            "score_breakdown": spec.winner.score_breakdown.model_dump() if spec.winner.score_breakdown else {},
            "is_winner": True,
        })

    winner_dict = {
        "plan_id": spec.winner.plan.plan_id,
        "generator": spec.winner.plan.generator,
        "visualization": spec.winner.plan.visualization.value,
        "score": round(spec.winner.score_breakdown.total, 4) if spec.winner.score_breakdown else 0.9,
        "score_breakdown": spec.winner.score_breakdown.model_dump() if spec.winner.score_breakdown else {},
        "metric": f"{spec.winner.plan.metric.aggregation.value}({spec.winner.plan.metric.column})",
        "dimensions": [
            f"{d.column}{' (' + d.granularity.value + ')' if d.granularity else ''}"
            for d in spec.winner.plan.dimensions
        ],
        "reasoning": spec.winner.plan.reasoning.model_dump() if spec.winner.plan.reasoning else {},
        "pass2_passed": True,
        "pass2_issues": [],
        "execution": spec.winner.execution_result.model_dump() if spec.winner.execution_result else {},
    }

    return OrchestratorPipelineResponse(
        status="SUCCESS",
        message="Overview dashboard generated successfully.",
        spec_id=spec.spec_id,
        headline=spec.headline,
        panels=[p.model_dump() for p in spec.panels],
        dashboard_spec=spec.model_dump(),
        ranked_candidates=ranked_list,
        winner=winner_dict,
        is_tie=False,
        cascade_depth=0,
        ambiguity_status="CLEAR",
        ambiguity_message=None,
        clarification_needed=False,
        clarification_options=None,
        options=None,
        cached_candidates=None,
        run_id=None,
        resolved_by="system",
        mode="overview",
        rejected_insights=spec.rejected_insights,
    )


# ---------------------------------------------------------------------------
# Step 8 / Roadmap #7 — Evidence-Grounded Dataset Interaction / Chat
# ---------------------------------------------------------------------------

from orchestrator.chat import (
    ChatRequest,
    ChatResponse,
    execute_chat_turn,
)


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    summary="Evidence-Grounded Dataset Chat / Conversational Interaction",
)
@app.post(
    "/api/dataset-chat",
    response_model=ChatResponse,
    summary="Evidence-Grounded Dataset Chat / Conversational Interaction (alias)",
)
def handle_dataset_chat(req: ChatRequest):
    """Process natural language conversational interaction grounded in dataset evidence."""
    record = session_store.get(req.dataset_id)
    if not record or not record.dataset:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{req.dataset_id}' not found in active session",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )
    dataset = record.dataset
    semantic_profile = record.semantic_profile
    if not semantic_profile:
        from intelligence.semantic_analyzer import analyze_semantics
        semantic_profile = analyze_semantics(dataset, record.profile)
        record.semantic_profile = semantic_profile

    context = record.get_or_create_conversation(req.conversation_id)

    res = execute_chat_turn(
        dataset=dataset,
        semantic_profile=semantic_profile,
        message=req.message,
        context=context,
        readiness=record.readiness,
        data_profile=record.profile,
        use_llm=req.use_llm if req.use_llm is not None else True,
    )
    return res


@app.post(
    "/api/chat/conversation/{dataset_id}/{conversation_id}/clear",
    summary="Clear conversation history for a dataset session",
)
def clear_chat_conversation(dataset_id: str, conversation_id: str):
    record = session_store.get(dataset_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Dataset not found",
                "message": f"Dataset '{dataset_id}' not found in active session",
                "error_type": "DATASET_NOT_FOUND",
                "status_code": 404,
            },
        )
    cleared = record.clear_conversation(conversation_id)
    return {"status": "SUCCESS", "cleared": cleared, "conversation_id": conversation_id}


@app.exception_handler(HTTPException)

def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIErrorResponse(
            error=exc.detail if isinstance(exc.detail, str) else (exc.detail.get("error", "Request error") if isinstance(exc.detail, dict) else "Request error"),
            message=str(exc.detail if isinstance(exc.detail, str) else (exc.detail.get("message", str(exc.detail)) if isinstance(exc.detail, dict) else str(exc.detail))),
            status_code=exc.status_code,
        ).model_dump(),
    )
