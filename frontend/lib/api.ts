import {
  AnalysisReadiness,
  CleaningExecutionResult,
  CleaningPlan,
  CleaningPreviewResult,
  DataPreviewResponse,
  DataProfile,
  DatasetListItem,
  DatasetMetadata,
  QualityAssessment,
  RegisterCleanedDatasetResponse,
  SemanticProfile,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const errorData = await res.json();
      errorMsg = errorData.message || errorData.detail || errorMsg;
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

export async function previewCleaningPlan(
  datasetId: string,
  selectedRecommendationIds: string[],
  operationOverrides?: Record<string, string>,
  operationValues?: Record<string, any>
): Promise<CleaningPreviewResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_recommendation_ids: selectedRecommendationIds,
      operation_overrides: operationOverrides || {},
      operation_values: operationValues || {},
    }),
  });
  return handleResponse<CleaningPreviewResult>(res);
}

export async function applyCleaningPlan(
  datasetId: string,
  selectedRecommendationIds: string[],
  operationOverrides?: Record<string, string>,
  operationValues?: Record<string, any>
): Promise<CleaningExecutionResult> {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/cleaning/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_recommendation_ids: selectedRecommendationIds,
      operation_overrides: operationOverrides || {},
      operation_values: operationValues || {},
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

export function getDatasetDownloadUrl(datasetId: string, format: 'csv' | 'xlsx'): string {
  return `${API_BASE}/datasets/${datasetId}/download?format=${format}`;
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



