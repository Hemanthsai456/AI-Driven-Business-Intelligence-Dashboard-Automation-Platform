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

export interface ValidationIssue {
  check: string;
  status: 'PASSED' | 'FAILED' | 'WARNING';
  message: string;
  column?: string;
}

export interface Pass1aResult {
  plan_id: string;
  passed: boolean;
  issues: ValidationIssue[];
}

export interface ExecutionResult {
  plan_id: string;
  status: 'SUCCESS' | 'TIMEOUT' | 'MEMORY_EXCEEDED' | 'SYNTAX_ERROR' | 'RUNTIME_ERROR';
  rows: Record<string, any>[];
  columns: string[];
  row_count: number;
  compiled_sql?: string;
  failed_cast_count: number;
  failed_cast_rate: number;
  warnings: string[];
  error_message?: string;
  runtime_seconds: number;
}

export interface Pass1bResult {
  plan_id: string;
  passed: boolean;
  issues: ValidationIssue[];
}

export interface PlanRunResponse {
  plan_id: string;
  pass1a: Pass1aResult;
  execution?: ExecutionResult;
  pass1b?: Pass1bResult;
}

export interface CandidatePlanUI {
  plan_id: string;
  dataset_id: string;
  intent: string;
  generator: 'llm_direct' | 'external_agent' | string;
  metric: {
    column: string;
    aggregation: string;
  };
  dimensions: {
    column: string;
    granularity?: string;
  }[];
  filters: {
    column: string;
    operator: string;
    value: any;
  }[];
  visualization: string;
  reasoning: {
    interpretation: string;
    evidence: string[];
  };
}

export interface GeneratorCallLogUI {
  model: string;
  generator: string;
  steps: number;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  latency_seconds: number;
  estimated_cost_usd: number;
}

export interface GenerateCandidatesResponse {
  dataset_id: string;
  intent: string;
  ambiguity: {
    status: string;
    message?: string;
    ambiguities: any[];
  };
  candidates: CandidatePlanUI[];
  logs: GeneratorCallLogUI[];
}

export interface SelectWinnerAlternate {
  plan_id: string;
  score: number;
  reason_not_winner: string;
  generator: string;
  visualization: string;
  intent: string;
}

export interface SelectWinnerResponse {
  spec_id: string;
  dataset_id: string;
  intent: string;
  winner_plan_id: string;
  winner_score: number;
  winner_generator: string;
  winner_visualization: string;
  winner_rank_before_cascade: number;
  pass2_passed: boolean;
  pass2_issues: any[];
  cascade_depth: number;
  cascade_triggered: boolean;
  is_tie: boolean;
  alternate_interpretations: SelectWinnerAlternate[];
  winner_plan: any;
  winner_execution: any;
  score_breakdown: {
    evidence: number;
    coverage: number;
    stability: number;
    assumptions: number;
    total: number;
  };
  created_at: string;
}

export interface RankedCandidateUI {
  rank: number;
  plan_id: string;
  generator: string;
  visualization: string;
  metric: string;
  dimensions: string[];
  score: number;
  score_breakdown: {
    evidence: number;
    coverage: number;
    stability: number;
    assumptions: number;
    total: number;
  };
  is_winner: boolean;
}

export interface ClarificationOption {
  plan_id: string;
  label?: string;
  description?: string;
  interpretation?: string;
  metric?: string;
  dimension?: string;
  dimensions?: string[];
  aggregation?: string;
  score: number;
  robustness?: number | null;
  coverage?: number;
  evidence?: number;
  visualization?: string;
}

export interface DashboardPanelUI {
  panel_id: string;
  panel_type: 'KPI' | 'BAR' | 'LINE' | 'TABLE' | 'HEATMAP' | 'INSIGHT' | 'ALTERNATES';
  title: string;
  description?: string;
  data: Record<string, any>[];
  x_key?: string;
  y_keys?: string[];
  metadata?: Record<string, any>;
}

export interface TileSize {
  w: number;
  h: number;
}

export interface SlicerOption {
  value: any;
  label: string;
  count?: number;
}

export interface SlicerDef {
  id: string;
  column: string;
  role: string;
  control_type: 'date_range' | 'multi_select';
  min_date?: string;
  max_date?: string;
  options: SlicerOption[];
}

export interface TileEvidence {
  strength?: number;
  robustness?: number;
  fdr_passed?: boolean;
  fdr_q_value?: number;
  n?: number;
  score?: number;
}

export interface DashboardTileUI {
  id: string;
  title: string;
  chart_type: string;
  size: TileSize;
  priority: number;
  candidate_id?: string;
  generator: string;
  evidence: TileEvidence;
  why_chosen?: string;
  plan?: any;
  compiled_sql?: string;
  data: Record<string, any>[];
  x_key?: string;
  y_keys: string[];
  dimensions: string[];
  metrics: string[];
  delta?: {
    value?: number | string;
    percentage?: number;
    direction?: 'up' | 'down' | 'neutral';
    label?: string;
  };
  metadata?: Record<string, any>;
}

export interface OrchestratorPipelineResponse {
  status: 'SUCCESS' | 'REFUSED' | 'UNANSWERABLE' | 'NEEDS_CLARIFICATION' | string;
  message: string;
  spec_id?: string;
  headline?: string;
  panels?: DashboardPanelUI[];
  tiles?: DashboardTileUI[];
  slicers?: SlicerDef[];
  dashboard_spec?: any;
  ranked_candidates: RankedCandidateUI[];
  winner?: {
    plan_id: string;
    generator: string;
    visualization: string;
    score: number;
    score_breakdown: {
      evidence: number;
      coverage: number;
      stability?: number;
      assumptions: number;
      total: number;
    };
    metric: string;
    dimensions: string[];
    reasoning: {
      interpretation: string;
      evidence: string[];
    };
    pass2_passed: boolean;
    pass2_issues: any[];
    execution: any;
  };
  is_tie: boolean;
  cascade_depth: number;
  ambiguity_status: string;
  ambiguity_message?: string;
  clarification_needed: boolean;
  clarification_options?: ClarificationOption[];
  options?: ClarificationOption[];
  cached_candidates?: any[];
  run_id?: string;
  resolved_by?: string;
  decision_log_entry?: any;
  explainability_log_entry?: any;
  mode?: 'focused' | 'discovery';
  rejected_insights?: any[];
}

export interface ChatMessageUI {
  message_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  intent_type?: string;
  query_plan?: any;
  compiled_sql?: string;
  data?: Record<string, any>[];
  columns?: string[];
  row_count?: number;
  evidence?: any;
  confidence?: number;
  warnings?: string[];
  clarification_needed?: boolean;
  clarification_options?: string[];
  provenance?: any;
}

export interface ChatResponseUI {
  conversation_id: string;
  message_id: string;
  dataset_id: string;
  question: string;
  answer: string;
  intent_type: string;
  query_plan?: any;
  compiled_sql?: string;
  data?: Record<string, any>[];
  columns?: string[];
  row_count: number;
  evidence?: any;
  confidence: number;
  warnings: string[];
  ambiguity_status: string;
  clarification_needed: boolean;
  clarification_options?: string[];
  provenance?: any;
  runtime_seconds: number;
  error?: string;
}

