export interface ColumnMetadata {
  original_name: string;
  normalized_name: string;
  detected_datatype: string;
  semantic_role: string;
  null_count: number;
  null_percentage: number;
  distinct_count: number;
  is_unique: boolean;
  sample_values: any[];
}

export interface DatasetMetadata {
  dataset_id: string;
  filename: string;
  source_type: string;
  row_count: number;
  column_count: number;
  columns: ColumnMetadata[];
  dtypes: Record<string, string>;
  ingestion_status: string;
  ingestion_errors: string[];
}

export interface DataPreviewResponse {
  dataset_id: string;
  filename: string;
  total_rows: number;
  preview_rows_count: number;
  columns: string[];
  rows: Record<string, any>[];
  is_preview: boolean;
}

export interface ColumnStatistics {
  column_name: string;
  detected_datatype: string;
  total_count: number;
  non_null_count: number;
  null_count: number;
  null_percentage: number;
  distinct_count: number;
  is_unique: boolean;
  is_constant: boolean;
  is_all_null: boolean;
  observations: string[];
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  std?: number;
  q25?: number;
  q75?: number;
  most_frequent_values?: { value: any; count: number }[];
  [key: string]: any;
}

export interface DataProfile {
  profile_id: string;
  dataset_id: string;
  generated_at: string;
  dataset_summary: {
    row_count: number;
    column_count: number;
    duplicate_row_count?: number;
    duplicate_row_percentage?: number;
    total_cells?: number;
    overall_missing_count?: number;
    overall_missing_percentage?: number;
    [key: string]: any;
  };
  column_statistics: Record<string, ColumnStatistics>;
  quality_issues: {
    issue_type: string;
    target?: string;
    message: string;
    severity: string;
  }[];
  correlation_matrix: Record<string, Record<string, number>>;
}

export interface SemanticColumn {
  column_name: string;
  candidate_role: 'MEASURE' | 'DIMENSION' | 'DATETIME' | 'IDENTIFIER' | 'UNKNOWN';
  confidence: number;
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE';
  evidence: string[];
}

export interface SemanticProfile {
  dataset_id: string;
  generated_at: string;
  column_evidences: Record<string, SemanticColumn>;
}

export interface ReadinessCheck {
  check_name: string;
  passed: boolean;
  message: string;
  is_blocking: boolean;
}

export interface AnalysisReadiness {
  dataset_id: string;
  status: 'READY' | 'READY_WITH_WARNINGS' | 'NOT_READY';
  generated_at: string;
  summary: string;
  blocking_issues: string[];
  warnings: string[];
  checked_columns: string[];
  checked_row_count: number;
  checked_column_count: number;
  checks: ReadinessCheck[];
}

export interface DatasetListItem {
  dataset_id: string;
  filename: string;
  source_type: string;
  row_count: number;
  column_count: number;
  created_at: string;
  readiness_status: string;
}

export interface APIError {
  error: string;
  message: string;
  status_code: number;
}
