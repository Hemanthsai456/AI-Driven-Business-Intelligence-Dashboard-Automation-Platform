"""FastAPI backend application exposing Python intelligence engine endpoints."""

import os
import tempfile
import uuid
from dotenv import load_dotenv

load_dotenv()
print(f"[STARTUP] Environment loaded. GEMINI_API_KEY present: {'GEMINI_API_KEY' in os.environ}, GROQ_API_KEY present: {'GROQ_API_KEY' in os.environ}")

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
from ingestion.loaders import CSVLoader, ExcelLoader, ParquetLoader, TSVLoader, load_dataset
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
)
from api.store import DatasetSessionRecord, session_store
from intelligence.semantic_analyzer import ColumnRole
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
async def upload_dataset(file: UploadFile = File(...)):
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
    contents = await file.read()
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
        canonical_ds = load_dataset(tmp_path)
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
    exec_res = execute_plan(
        plan=plan,
        dataset=record.dataset,
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
    intent_tokens = req.intent.lower().split()
    semantic_evidences = record.semantic_profile.column_evidences
    ranked, is_tie = rank_candidates(
        candidate_pairs,
        semantic_evidences=semantic_evidences,
        intent_tokens=intent_tokens,
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

    pipeline_result = run_orchestration_pipeline(
        dataset=record.dataset,
        semantic_profile=record.semantic_profile,
        readiness=record.readiness,
        intent=req.intent,
        data_profile=record.profile,
        mode=req.mode or "both",
        k=req.k or 3,
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

    return OrchestratorPipelineResponse(
        status=pipeline_result.status,
        message=pipeline_result.message,
        spec_id=spec.spec_id if spec else None,
        dashboard_spec=spec.model_dump() if spec else None,
        ranked_candidates=ranked_list,
        winner=winner_dict,
        is_tie=pipeline_result.is_tie,
        cascade_depth=pipeline_result.cascade_depth,
        ambiguity_status=pipeline_result.ambiguity.status.value if pipeline_result.ambiguity else "CLEAR",
        ambiguity_message=pipeline_result.ambiguity.message if pipeline_result.ambiguity else None,
        clarification_needed=pipeline_result.is_tie or (
            pipeline_result.ambiguity is not None and pipeline_result.ambiguity.status.value != "CLEAR"
        ),
        decision_log_entry=pipeline_result.decision_log_entry,
        explainability_log_entry=pipeline_result.explainability_log_entry,
    )


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
