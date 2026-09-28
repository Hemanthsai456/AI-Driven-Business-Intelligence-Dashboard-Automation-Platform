import {
  AnalysisReadiness,
  DataPreviewResponse,
  DataProfile,
  DatasetListItem,
  DatasetMetadata,
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
