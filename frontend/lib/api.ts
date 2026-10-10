import {
  AnalysisReadiness,
  CleaningExecutionResult,
  CleaningPlan,
  CleaningPreviewResult,
  ColumnTransformPreviewRequest,
  ColumnTransformPreviewResult,
  CustomColumnTransformation,
  DataPreviewResponse,
  DataProfile,
  DatasetListItem,
  DatasetMetadata,
  MultiValueApplyRequest,
  MultiValueApplyResponse,
  MultiValueCandidatesResponse,
  MultiValuePreviewRequest,
  MultiValuePreviewResult,
  QualityAssessment,
  RegisterCleanedDatasetResponse,
  SemanticProfile,
  DropColumnsRequest,
  DropColumnsPreviewResult,
  RowFilterRequest,
  RowFilterPreviewResult,
  DuplicateRemovalRequest,
  DuplicateRemovalPreviewResult,
  StructuralRecommendationsResponse,
  SemanticRoleOverrideRequest,
  SemanticRoleOverrideResponse,
  StructuralApplyResponse,
  CleanedDatasetSummaryResponse,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const errorData = await res.json();
      if (typeof errorData.message === 'string' && errorData.message.trim()) {
        errorMsg = errorData.message;
      } else if (Array.isArray(errorData.detail)) {
        errorMsg = errorData.detail
          .map((d: any) => {
            if (typeof d === 'string') return d;
            const loc = Array.isArray(d.loc) ? d.loc.filter((p: any) => p !== 'body').join('.') : '';
            const msg = d.msg || d.message || JSON.stringify(d);
            return loc ? `${loc}: ${msg}` : msg;
          })
          .join('; ');
      } else if (typeof errorData.detail === 'string' && errorData.detail.trim()) {
        errorMsg = errorData.detail;
      } else if (errorData.detail && typeof errorData.detail === 'object') {
        errorMsg = errorData.detail.message || errorData.detail.error || JSON.stringify(errorData.detail);
      } else if (Array.isArray(errorData.issues)) {
        errorMsg = errorData.issues
          .map((i: any) => (typeof i === 'object' ? i.message || i.check || JSON.stringify(i) : String(i)))
          .join('; ');
      } else if (typeof errorData.error === 'string' && errorData.error.trim()) {
        errorMsg = errorData.error;
      }
    } catch {
      // Ignore JSON parse error on error responses
    }
    throw new Error(errorMsg);
  }
  return res.json() as Promise<T>;
}

export async function healthCheck(): Promise<{ status: string; version: string }> {
  const res = await fetch(`${API_BASE}/health`);
  return handleResponse(res);
}

export async function uploadDataset(file: File): Promise<DatasetMetadata> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/datasets/upload`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<DatasetMetadata>(res);
}

export async function listDatasets(): Promise<DatasetListItem[]> {
  const res = await fetch(`${API_BASE}/datasets`);
  return handleResponse<DatasetListItem[]>(res);
}

export async function getDatasetMetadata(datasetId: string): Promise<DatasetMetadata> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}`);
  return handleResponse<DatasetMetadata>(res);
}

export async function getDatasetPreview(datasetId: string, limit: number = 50): Promise<DataPreviewResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/preview?limit=${limit}`);
  return handleResponse<DataPreviewResponse>(res);
}

export async function getDatasetProfile(datasetId: string): Promise<DataProfile> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/profile`);
  return handleResponse<DataProfile>(res);
}

export async function getDatasetSemanticAnalysis(datasetId: string): Promise<SemanticProfile> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/semantic-analysis`);
  return handleResponse<SemanticProfile>(res);
}

export async function getDatasetReadiness(datasetId: string): Promise<AnalysisReadiness> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/readiness`);
  return handleResponse<AnalysisReadiness>(res);
}

export async function getDatasetQualityAssessment(datasetId: string): Promise<QualityAssessment> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/quality-assessment`);
  return handleResponse<QualityAssessment>(res);
}

export async function getDatasetCleaningPlan(datasetId: string): Promise<CleaningPlan> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning-plan`);
  return handleResponse<CleaningPlan>(res);
}

export async function previewColumnTransformation(
  datasetId: string,
  request: ColumnTransformPreviewRequest
): Promise<ColumnTransformPreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/column-transform/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<ColumnTransformPreviewResult>(res);
}

export async function previewCleaningPlan(
  datasetId: string,
  selectedRecommendationIds: string[],
  operationOverrides?: Record<string, string>,
  operationValues?: Record<string, any>,
  customTransformations?: CustomColumnTransformation[]
): Promise<CleaningPreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_recommendation_ids: selectedRecommendationIds,
      operation_overrides: operationOverrides || {},
      operation_values: operationValues || {},
      custom_transformations: customTransformations || [],
    }),
  });
  return handleResponse<CleaningPreviewResult>(res);
}

export async function applyCleaningPlan(
  datasetId: string,
  selectedRecommendationIds: string[],
  operationOverrides?: Record<string, string>,
  operationValues?: Record<string, any>,
  customTransformations?: CustomColumnTransformation[]
): Promise<CleaningExecutionResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_recommendation_ids: selectedRecommendationIds,
      operation_overrides: operationOverrides || {},
      operation_values: operationValues || {},
      custom_transformations: customTransformations || [],
    }),
  });
  return handleResponse<CleaningExecutionResult>(res);
}

export async function registerCleanedDataset(datasetId: string): Promise<RegisterCleanedDatasetResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaned/register`, {
    method: 'POST',
  });
  return handleResponse<RegisterCleanedDatasetResponse>(res);
}

export async function getCleanedDatasetSummary(
  datasetId: string
): Promise<CleanedDatasetSummaryResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning-summary`);
  return handleResponse<CleanedDatasetSummaryResponse>(res);
}

export function getDatasetDownloadUrl(datasetId: string, format: 'csv' | 'xlsx'): string {
  return `${API_BASE}/datasets/${datasetId}/download?format=${format}`;
}

export async function getMultiValueCandidates(datasetId: string): Promise<MultiValueCandidatesResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/multivalue/candidates`);
  return handleResponse<MultiValueCandidatesResponse>(res);
}

export async function previewMultiValue(
  datasetId: string,
  request: MultiValuePreviewRequest
): Promise<MultiValuePreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/multivalue/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<MultiValuePreviewResult>(res);
}

export async function applyMultiValue(
  datasetId: string,
  request: MultiValueApplyRequest
): Promise<MultiValueApplyResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/multivalue/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<MultiValueApplyResponse>(res);
}

// ----------------------------------------------------
// PART 6.4 — STRUCTURAL CLEANING & SEMANTIC ROLES API
// ----------------------------------------------------

export async function getStructuralRecommendations(
  datasetId: string
): Promise<StructuralRecommendationsResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/recommendations`);
  return handleResponse<StructuralRecommendationsResponse>(res);
}

export async function previewDropColumns(
  datasetId: string,
  request: DropColumnsRequest
): Promise<DropColumnsPreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/drop-columns/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<DropColumnsPreviewResult>(res);
}

export async function applyDropColumns(
  datasetId: string,
  request: DropColumnsRequest
): Promise<StructuralApplyResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/drop-columns/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<StructuralApplyResponse>(res);
}

export async function previewFilterRows(
  datasetId: string,
  request: RowFilterRequest
): Promise<RowFilterPreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/filter-rows/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<RowFilterPreviewResult>(res);
}

export async function applyFilterRows(
  datasetId: string,
  request: RowFilterRequest
): Promise<StructuralApplyResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/filter-rows/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<StructuralApplyResponse>(res);
}

export async function previewRemoveDuplicates(
  datasetId: string,
  request: DuplicateRemovalRequest
): Promise<DuplicateRemovalPreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/duplicates/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<DuplicateRemovalPreviewResult>(res);
}

export async function applyRemoveDuplicates(
  datasetId: string,
  request: DuplicateRemovalRequest
): Promise<StructuralApplyResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/duplicates/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<StructuralApplyResponse>(res);
}

export async function previewSemanticRoleOverride(
  datasetId: string,
  request: SemanticRoleOverrideRequest
): Promise<SemanticRoleOverrideResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/semantic-role/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<SemanticRoleOverrideResponse>(res);
}

export async function applySemanticRoleOverride(
  datasetId: string,
  request: SemanticRoleOverrideRequest
): Promise<SemanticRoleOverrideResponse> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/structural/semantic-role/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<SemanticRoleOverrideResponse>(res);
}



export async function validatePlan(plan: any): Promise<import('./types').Pass1aResult> {
  const res = await fetch(`${API_BASE}/orchestrator/validate-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(plan),
  });
  return handleResponse<import('./types').Pass1aResult>(res);
}

export async function runPlan(plan: any): Promise<import('./types').PlanRunResponse> {
  const res = await fetch(`${API_BASE}/orchestrator/run-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(plan),
  });
  return handleResponse<import('./types').PlanRunResponse>(res);
}

export async function generateCandidates(
  datasetId: string,
  intent: string,
  k: number = 3,
  mode?: string
): Promise<import('./types').GenerateCandidatesResponse> {
  const res = await fetch(`${API_BASE}/orchestrator/generate-candidates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, intent, k, mode }),
  });
  return handleResponse<import('./types').GenerateCandidatesResponse>(res);
}

export async function selectWinner(
  datasetId: string,
  intent: string,
  candidates: any[],
  executionResults: Record<string, any>,
  generatorLogs: any[] = [],
  contextHash?: string
): Promise<import('./types').SelectWinnerResponse> {
  const res = await fetch(`${API_BASE}/orchestrator/select-winner`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: datasetId,
      intent,
      candidates,
      execution_results: executionResults,
      generator_logs: generatorLogs,
      context_hash: contextHash,
    }),
  });
  return handleResponse<import('./types').SelectWinnerResponse>(res);
}

export async function getDatasetCleaningReport(datasetId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning`);
  return handleResponse<any>(res);
}

export async function getProvidersStatus(): Promise<{
  providers: {
    provider: string;
    status: 'live' | 'failed';
    model: string | null;
    reason: string | null;
    is_baseline: boolean;
  }[];
}> {
  const res = await fetch(`${API_BASE}/providers/status`);
  return handleResponse<any>(res);
}

export async function runPipeline(
  datasetId: string,
  intent: string,
  mode?: string,
  k: number = 3,
  requireClarification: boolean = true,
  chosenPlanId?: string
): Promise<import('./types').OrchestratorPipelineResponse> {
  const res = await fetch(`${API_BASE}/orchestrator/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: datasetId,
      intent,
      mode,
      k,
      require_clarification: requireClarification,
      chosen_plan_id: chosenPlanId,
    }),
  });
  return handleResponse<import('./types').OrchestratorPipelineResponse>(res);
}

export async function resolvePipeline(
  runId: string,
  selectedPlanId: string
): Promise<import('./types').OrchestratorPipelineResponse> {
  const res = await fetch(`${API_BASE}/orchestrator/pipeline/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      run_id: runId,
      selected_plan_id: selectedPlanId,
    }),
  });
  return handleResponse<import('./types').OrchestratorPipelineResponse>(res);
}

export async function queryTile(
  specId: string,
  tileId: string,
  filters: { column: string; operator: string; values: any[] }[]
): Promise<{
  tile_id: string;
  data: Record<string, any>[];
  row_count: number;
  status: 'SUCCESS' | 'INSUFFICIENT_DATA';
  compiled_sql?: string;
  filters_applied?: any[];
}> {
  const res = await fetch(`${API_BASE}/dashboard/${specId}/tile/${tileId}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filters }),
  });
  return handleResponse<any>(res);
}

export async function generateOverviewDashboard(
  datasetId: string,
  useLlm: boolean = true
): Promise<import('./types').OrchestratorPipelineResponse> {
  const res = await fetch(`${API_BASE}/overview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, use_llm: useLlm }),
  });
  return handleResponse<import('./types').OrchestratorPipelineResponse>(res);
}

export async function sendChatMessage(
  datasetId: string,
  message: string,
  conversationId?: string,
  useLlm: boolean = true
): Promise<import('./types').ChatResponseUI> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_id: datasetId,
      message,
      conversation_id: conversationId,
      use_llm: useLlm,
    }),
  });
  return handleResponse<import('./types').ChatResponseUI>(res);
}

export async function clearChatConversation(
  datasetId: string,
  conversationId: string
): Promise<{ status: string; cleared: boolean; conversation_id: string }> {
  const res = await fetch(`${API_BASE}/chat/conversation/${datasetId}/${conversationId}/clear`, {
    method: 'POST',
  });
  return handleResponse<any>(res);
}

export async function getDatasetEDASummary(
  datasetId: string
): Promise<import('./types').EDASummary> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/eda`);
  return handleResponse<import('./types').EDASummary>(res);
}

export async function exploreDatasetEDA(
  datasetId: string,
  request: import('./types').EDAExploreRequest
): Promise<import('./types').EDAExploreResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/eda/explore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<import('./types').EDAExploreResult>(res);
}

// ----------------------------------------------------
// PART 8 — EDITABLE DASHBOARD TILE MANAGEMENT API
// ----------------------------------------------------

export async function updateDashboardTile(
  specId: string,
  tileId: string,
  request: {
    title?: string;
    description?: string;
    chart_type?: string;
    plan: any;
  }
): Promise<{
  status: string;
  tile: import('./types').DashboardTileUI;
  spec_id: string;
  pass1a?: any;
  pass1b?: any;
}> {
  const res = await fetch(`${API_BASE}/dashboard/${specId}/tile/${tileId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<any>(res);
}

export async function deleteDashboardTile(
  specId: string,
  tileId: string
): Promise<{ status: string; message: string; remaining_count: number }> {
  const res = await fetch(`${API_BASE}/dashboard/${specId}/tile/${tileId}`, {
    method: 'DELETE',
  });
  return handleResponse<any>(res);
}

export async function resetDashboardTile(
  specId: string,
  tileId: string
): Promise<{ status: string; message: string; tile: import('./types').DashboardTileUI }> {
  const res = await fetch(`${API_BASE}/dashboard/${specId}/tile/${tileId}/reset`, {
    method: 'POST',
  });
  return handleResponse<any>(res);
}

export async function resetDashboard(
  specId: string
): Promise<{ status: string; message: string; spec: any }> {
  const res = await fetch(`${API_BASE}/dashboard/${specId}/reset`, {
    method: 'POST',
  });
  return handleResponse<any>(res);
}




