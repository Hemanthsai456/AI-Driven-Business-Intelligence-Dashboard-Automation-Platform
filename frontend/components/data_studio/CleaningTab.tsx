'use client';

import React, { useState, useMemo } from 'react';
import {
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  Info,
  CheckCircle2,
  Filter,
  CheckSquare,
  Square,
  ArrowRight,
  Database,
  Layers,
  HelpCircle,
  Clock,
  Eye,
  Play,
  RotateCcw,
  X,
  Check,
  AlertCircle,
  FileCheck2,
  Table,
  Zap,
  Download,
  Sliders,
  Wand2,
  PlusCircle,
  Trash2,
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import { Button } from '../Button';
import {
  CleaningExecutionResult,
  CleaningPlan,
  CleaningPreviewResult,
  CleaningRecommendation,
  ColumnTransformPreviewResult,
  CustomColumnTransformation,
  DatasetMetadata,
  OperationExecutionResult,
  QualityAssessment,
  RegisterCleanedDatasetResponse,
  SampleCellChange,
  SemanticProfile,
} from '../../lib/types';
import {
  applyCleaningPlan,
  getDatasetDownloadUrl,
  previewCleaningPlan,
  previewColumnTransformation,
  registerCleanedDataset,
} from '../../lib/api';

interface CleaningTabProps {
  metadata: DatasetMetadata;
  cleaningPlan: CleaningPlan | null;
  semanticProfile: SemanticProfile | null;
  qualityAssessment: QualityAssessment | null;
  isLoadingPlan?: boolean;
  planError?: string | null;
  onRetryPlan?: () => void;
  onSelectDataset?: (datasetId: string) => void;
  onDatasetRegistered?: (newDatasetId: string) => void;
}

type FilterStatus = 'ALL' | 'RECOMMENDED' | 'REVIEW_REQUIRED' | 'SELECTED';
type ExecutionState = 'idle' | 'applying' | 'validating' | 'complete' | 'error';
type RegistrationState = 'idle' | 'registering' | 'registered' | 'error';

export const CleaningTab: React.FC<CleaningTabProps> = ({
  metadata,
  cleaningPlan,
  semanticProfile,
  qualityAssessment,
  isLoadingPlan = false,
  planError = null,
  onRetryPlan,
  onSelectDataset,
  onDatasetRegistered,
}) => {
  // Local state for user-controlled selection overrides
  const [selections, setSelections] = useState<Record<string, boolean>>(() => {
    if (!cleaningPlan) return {};
    const initial: Record<string, boolean> = {};
    for (const rec of cleaningPlan.recommendations) {
      initial[rec.recommendation_id] = rec.default_selected;
    }
    return initial;
  });

  // Local state for user-selected method overrides (recommendation_id -> selected_operation)
  const [methodOverrides, setMethodOverrides] = useState<Record<string, string>>({});
  // Local state for user-specified custom values (recommendation_id -> custom_value_string)
  const [customValues, setCustomValues] = useState<Record<string, string>>({});

  const [activeFilter, setActiveFilter] = useState<FilterStatus>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // User-Controlled Column Transformations State
  const availableColumns = useMemo<string[]>(() => {
    if (metadata?.columns && Array.isArray(metadata.columns) && metadata.columns.length > 0) {
      return metadata.columns.map((c) => (typeof c === 'string' ? c : c.original_name));
    }
    return [];
  }, [metadata]);

  const [selectedCol, setSelectedCol] = useState<string>(() => {
    if (metadata?.columns && Array.isArray(metadata.columns) && metadata.columns.length > 0) {
      const first = metadata.columns[0];
      return typeof first === 'string' ? first : first.original_name;
    }
    return '';
  });
  const [selectedTransformType, setSelectedTransformType] = useState<string>('CONVERT_NUMERIC');
  const [customTransformVal, setCustomTransformVal] = useState<string>('');
  const [allowFractional, setAllowFractional] = useState<boolean>(false);
  const [colPreviewLoading, setColPreviewLoading] = useState<boolean>(false);
  const [colPreviewResult, setColPreviewResult] = useState<ColumnTransformPreviewResult | null>(null);
  const [colPreviewError, setColPreviewError] = useState<string | null>(null);
  const [customTransformations, setCustomTransformations] = useState<CustomColumnTransformation[]>([]);

  // Preview & Execution State
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewResult, setPreviewResult] = useState<CleaningPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [executionState, setExecutionState] = useState<ExecutionState>('idle');
  const [executionResult, setExecutionResult] = useState<CleaningExecutionResult | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);

  // Registration & Download State
  const [registrationState, setRegistrationState] = useState<RegistrationState>('idle');
  const [registeredData, setRegisteredData] = useState<RegisterCleanedDatasetResponse | null>(null);
  const [registrationError, setRegistrationError] = useState<string | null>(null);

  // Update selections when cleaningPlan changes (e.g. switching datasets)
  React.useEffect(() => {
    if (!cleaningPlan) {
      setSelections({});
      setMethodOverrides({});
      setCustomValues({});
      setCustomTransformations([]);
      setColPreviewResult(null);
      setColPreviewError(null);
      setPreviewResult(null);
      setExecutionResult(null);
      setExecutionState('idle');
      setRegistrationState('idle');
      setRegisteredData(null);
      setRegistrationError(null);
      return;
    }
    const initial: Record<string, boolean> = {};
    for (const rec of cleaningPlan.recommendations) {
      initial[rec.recommendation_id] = rec.default_selected;
    }
    setSelections(initial);
    setMethodOverrides({});
    setCustomValues({});
    setCustomTransformations([]);
    setColPreviewResult(null);
    setColPreviewError(null);
    setPreviewResult(null);
    setExecutionResult(null);
    setExecutionState('idle');
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);
  }, [cleaningPlan?.dataset_id]);

  React.useEffect(() => {
    if (availableColumns.length > 0 && (!selectedCol || !availableColumns.includes(selectedCol))) {
      setSelectedCol(availableColumns[0]);
    }
  }, [availableColumns, selectedCol]);

  const toggleSelection = (recId: string) => {
    setSelections((prev) => ({
      ...prev,
      [recId]: !prev[recId],
    }));
  };

  const selectAllSafe = () => {
    if (!cleaningPlan) return;
    setSelections((prev) => {
      const next = { ...prev };
      for (const rec of cleaningPlan.recommendations) {
        if (rec.risk_level === 'LOW' && rec.status === 'RECOMMENDED') {
          next[rec.recommendation_id] = true;
        }
      }
      return next;
    });
  };

  const deselectAll = () => {
    if (!cleaningPlan) return;
    setSelections((prev) => {
      const next = { ...prev };
      for (const rec of cleaningPlan.recommendations) {
        next[rec.recommendation_id] = false;
      }
      return next;
    });
  };

  const allRecs = cleaningPlan?.recommendations || [];

  const selectedIds = useMemo(() => {
    return allRecs
      .filter((r) => selections[r.recommendation_id])
      .map((r) => r.recommendation_id);
  }, [allRecs, selections]);

  const selectedCount = selectedIds.length;

  const modifiedCount = useMemo(() => {
    return allRecs.filter(
      (r) =>
        (methodOverrides[r.recommendation_id] && methodOverrides[r.recommendation_id] !== r.operation) ||
        (customValues[r.recommendation_id] && customValues[r.recommendation_id].trim() !== '')
    ).length;
  }, [allRecs, methodOverrides, customValues]);

  const isDiagnosticOnly = (op: string) => {
    return (
      op.startsWith('REVIEW_') ||
      op === 'REVIEW_OUTLIERS' ||
      op === 'REVIEW_CONSTANT_COLUMN' ||
      op === 'REVIEW_DATETIME_MISSING' ||
      op === 'REVIEW_IDENTIFIER_MISSING' ||
      op === 'REVIEW_HIGH_MISSINGNESS'
    );
  };

  const selectedColInfo = useMemo(() => {
    if (!selectedCol) return null;
    const colMeta = metadata?.columns?.find(
      (c) => (typeof c === 'string' ? c : c.original_name) === selectedCol
    );
    const semCol = semanticProfile?.column_evidences?.[selectedCol];
    const dtype = (typeof colMeta === 'object' ? colMeta?.detected_datatype : null) || 'Unknown';
    const role = semCol?.candidate_role || (typeof colMeta === 'object' ? colMeta?.semantic_role : null) || 'UNKNOWN';
    const nullCount = (typeof colMeta === 'object' ? colMeta?.null_count : null) ?? 0;
    const nullPct =
      (typeof colMeta === 'object' ? colMeta?.null_percentage : null) ??
      (metadata?.row_count && metadata.row_count > 0 ? (nullCount / metadata.row_count) * 100 : 0);
    return {
      dtype,
      role,
      nullCount,
      nullPct: Math.round(nullPct * 10) / 10,
    };
  }, [selectedCol, semanticProfile, metadata]);

  const getTransformExplanation = () => {
    if (!selectedColInfo) return '';
    const { nullCount } = selectedColInfo;

    switch (selectedTransformType) {
      case 'CONVERT_NUMERIC':
      case 'CONVERT_FLOAT':
        return `${nullCount > 0 ? `${nullCount} values are missing and the ` : 'The '}column contains numeric-looking values. Converting to numeric parses numbers and converts unparseable tokens to missing (null). Semantic role refreshes to MEASURE.`;
      case 'CONVERT_INTEGER':
        return `Converts values to whole integers. If fractional values exist, conversion safely halts to prevent data loss unless explicitly confirmed.`;
      case 'CONVERT_DATETIME':
        return `Parses date and timestamp strings using standard patterns. Unparseable formats become missing.`;
      case 'NORMALIZE_BOOLEAN':
      case 'CONVERT_BOOLEAN':
        return `Standardizes boolean representations (true/false, yes/no, 1/0) into strict boolean booleans.`;
      case 'CONVERT_STRING':
        return `Casts column values to clean text/string representation.`;
      case 'TRIM_WHITESPACE':
        return `Strips leading and trailing spaces, tabs, and newline characters from string values.`;
      case 'NORMALIZE_EMPTY_STRINGS':
        return `Converts empty ("") and whitespace-only text cells into true null/missing values.`;
      case 'IMPUTE_MEDIAN':
        return `Fills ${nullCount} missing values with the median of valid numeric values.`;
      case 'IMPUTE_MEAN':
        return `Fills ${nullCount} missing values with the arithmetic mean of valid numeric values.`;
      case 'IMPUTE_MODE':
        return `Fills ${nullCount} missing values with the most frequent value.`;
      case 'IMPUTE_UNKNOWN':
        return `Fills ${nullCount} missing values with the standard placeholder "Unknown".`;
      case 'IMPUTE_SPECIFIC_VALUE':
        return `Fills ${nullCount} missing values with user-provided constant "${customTransformVal || '...'}" after type validation.`;
      case 'LEAVE_UNCHANGED':
        return `Preserves missing values without modification.`;
      default:
        return 'Apply deterministic transformation to column.';
    }
  };

  // Preview Action for Single User Column Transformation
  const handlePreviewColumnTransform = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || !selectedCol) return;
    setColPreviewLoading(true);
    setColPreviewError(null);
    try {
      const res = await previewColumnTransformation(targetDatasetId, {
        column_name: selectedCol,
        operation: selectedTransformType,
        custom_value: customTransformVal,
        allow_fractional_truncation: allowFractional,
      });
      setColPreviewResult(res);
      if (!res.is_valid && res.error_message) {
        setColPreviewError(res.error_message);
      }
    } catch (err: any) {
      setColPreviewError(err.message || 'Failed to preview column transformation.');
      setColPreviewResult(null);
    } finally {
      setColPreviewLoading(false);
    }
  };

  // Direct Apply for Single User Column Transformation
  const handleApplySingleTransform = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || !selectedCol) return;
    setIsPreviewOpen(false);
    setExecutionState('applying');
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);

    const singleTransform: CustomColumnTransformation = {
      column_name: selectedCol,
      operation: selectedTransformType,
      custom_value: customTransformVal,
      allow_fractional_truncation: allowFractional,
      source: 'USER',
    };

    try {
      const timer = setTimeout(() => {
        setExecutionState('validating');
      }, 400);

      const res = await applyCleaningPlan(
        targetDatasetId,
        [],
        {},
        {},
        [singleTransform]
      );
      clearTimeout(timer);
      setExecutionResult(res);
      setExecutionState('complete');
    } catch (err: any) {
      setExecutionError(err.message || 'Failed to execute column transformation.');
      setExecutionState('error');
    }
  };

  const handleQueueCustomTransform = () => {
    if (!selectedCol) return;
    const newTransform: CustomColumnTransformation = {
      column_name: selectedCol,
      operation: selectedTransformType,
      custom_value: customTransformVal,
      allow_fractional_truncation: allowFractional,
      source: 'USER',
    };
    setCustomTransformations((prev) => {
      const filtered = prev.filter((t) => t.column_name !== selectedCol);
      return [...filtered, newTransform];
    });
  };

  const handleRemoveCustomTransform = (colName: string) => {
    setCustomTransformations((prev) => prev.filter((t) => t.column_name !== colName));
  };

  const filteredRecommendations = useMemo(() => {
    return allRecs.filter((rec) => {
      const isSelected = !!selections[rec.recommendation_id];

      // Status filter
      if (activeFilter === 'RECOMMENDED' && rec.status !== 'RECOMMENDED') return false;
      if (activeFilter === 'REVIEW_REQUIRED' && !rec.requires_review) return false;
      if (activeFilter === 'SELECTED' && !isSelected) return false;

      // Search query
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesCol = rec.column_name ? rec.column_name.toLowerCase().includes(query) : false;
        const matchesOp = rec.operation.toLowerCase().includes(query);
        const matchesCat = rec.category.toLowerCase().includes(query);
        const matchesRationale = rec.rationale.toLowerCase().includes(query);
        if (!matchesCol && !matchesOp && !matchesCat && !matchesRationale) {
          return false;
        }
      }

      return true;
    });
  }, [allRecs, selections, activeFilter, searchQuery]);

  // Preview Action for Batch Plan
  const handleGeneratePreview = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || (selectedIds.length === 0 && customTransformations.length === 0)) return;
    setIsLoadingPreview(true);
    setPreviewError(null);
    try {
      const res = await previewCleaningPlan(
        targetDatasetId,
        selectedIds,
        methodOverrides,
        customValues,
        customTransformations
      );
      setPreviewResult(res);
      setIsPreviewOpen(true);
    } catch (err: any) {
      setPreviewError(err.message || 'Failed to generate cleaning preview.');
      setIsPreviewOpen(true);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  // Apply Action for Batch Plan
  const handleApplyCleaning = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || (selectedIds.length === 0 && customTransformations.length === 0)) return;
    setIsPreviewOpen(false);
    setExecutionState('applying');
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);

    try {
      const timer = setTimeout(() => {
        setExecutionState('validating');
      }, 400);

      const res = await applyCleaningPlan(
        targetDatasetId,
        selectedIds,
        methodOverrides,
        customValues,
        customTransformations
      );
      clearTimeout(timer);
      setExecutionResult(res);
      setExecutionState('complete');
    } catch (err: any) {
      setExecutionError(err.message || 'Failed to execute cleaning plan.');
      setExecutionState('error');
    }
  };

  // Register Cleaned Dataset Action
  const handleRegisterCleaned = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId) {
      setRegistrationError('No active dataset found for registration.');
      setRegistrationState('error');
      return;
    }
    setRegistrationState('registering');
    setRegistrationError(null);
    try {
      const res = await registerCleanedDataset(targetDatasetId);
      setRegisteredData(res);
      setRegistrationState('registered');
      if (onDatasetRegistered) {
        onDatasetRegistered(res.dataset_id);
      }
    } catch (err: any) {
      let msg = err.message || 'Failed to register cleaned dataset.';
      if (msg.includes('Not Found') || msg.includes('404')) {
        msg = `${msg} (Ensure the backend server has reloaded latest API routes).`;
      }
      setRegistrationError(msg);
      setRegistrationState('error');
    }
  };

  const handleResetExecution = () => {
    setExecutionState('idle');
    setExecutionResult(null);
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);
  };

  // 1. Loading State
  if (isLoadingPlan) {
    return (
      <Card className="p-12 text-center space-y-3">
        <div className="w-10 h-10 mx-auto text-primary">
          <svg className="animate-spin w-10 h-10" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-foreground">Generating Cleaning Plan</h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            Evaluating data profile and quality observations to generate deterministic cleaning recommendations...
          </p>
        </div>
      </Card>
    );
  }

  // 2. Error or Missing Plan State
  if (planError || !cleaningPlan) {
    return (
      <Card className="p-10 text-center space-y-4 border-rose-500/20 bg-rose-500/5 max-w-lg mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-500 flex items-center justify-center mx-auto">
          <AlertTriangle className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-foreground">Unable to Generate Cleaning Plan</h3>
          <p className="text-xs text-muted-foreground">
            {planError || 'No cleaning plan could be generated for this dataset.'}
          </p>
        </div>
        {onRetryPlan && (
          <div className="pt-2">
            <Button variant="primary" size="sm" onClick={onRetryPlan} leftIcon={<Sparkles className="w-3.5 h-3.5" />}>
              Retry Generating Plan
            </Button>
          </div>
        )}
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Execution Running Banner */}
      {(executionState === 'applying' || executionState === 'validating') && (
        <Card className="p-6 border-primary/40 bg-primary-soft/20 text-center space-y-3 animate-pulse">
          <div className="w-8 h-8 mx-auto text-primary">
            <svg className="animate-spin w-8 h-8" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
          <div className="space-y-1">
            <h4 className="text-sm font-bold text-foreground">
              {executionState === 'applying'
                ? 'Applying Selected Cleaning Operations...'
                : 'Validating Invariants & Generating Cleaned In-Memory Dataset...'}
            </h4>
            <p className="text-xs text-muted-foreground">
              Operating safely on a deep copy. Raw source dataset remains 100% immutable.
            </p>
          </div>
        </Card>
      )}

      {/* Execution Error Banner */}
      {executionState === 'error' && (
        <Card className="p-5 border-rose-500/30 bg-rose-500/10 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="text-xs font-bold text-rose-600 dark:text-rose-400">
                Cleaning Execution Failed
              </h4>
              <p className="text-xs text-muted-foreground">
                {executionError || 'An unexpected error occurred during cleaning execution.'}
              </p>
            </div>
          </div>
          <Button variant="secondary" size="xs" onClick={handleResetExecution}>
            Dismiss
          </Button>
        </Card>
      )}

      {/* Cleaned Result Panel (Post Execution) */}
      {executionState === 'complete' && executionResult && (
        <Card className="p-6 border-emerald-500/40 bg-emerald-500/5 space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/20 text-emerald-500 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-foreground">
                    Cleaning Execution Complete
                  </h3>
                  <Badge variant="green" size="xs">
                    Validation: {executionResult.validation?.overall_status || 'PASSED'}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Cleaned in-memory DataFrame generated successfully. Raw source dataset remains untouched.
                </p>
              </div>
            </div>

            <Button
              variant="secondary"
              size="xs"
              onClick={handleResetExecution}
              leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
            >
              Reconfigure Plan
            </Button>
          </div>

          {/* Metrics Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Row Count
              </span>
              <div className="text-lg font-bold text-foreground">
                {executionResult.cleaned_row_count.toLocaleString()}
                <span className="text-2xs font-normal text-muted-foreground ml-1.5">
                  ({executionResult.row_count_change <= 0 ? executionResult.row_count_change : `+${executionResult.row_count_change}`} rows)
                </span>
              </div>
            </div>

            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Operations Applied
              </span>
              <div className="text-lg font-bold text-emerald-500">
                {executionResult.operations_applied}
                <span className="text-2xs font-normal text-muted-foreground ml-1.5">
                  / {executionResult.operations_requested} requested
                </span>
              </div>
            </div>

            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Cells Modified
              </span>
              <div className="text-lg font-bold text-primary">
                {executionResult.total_cells_affected.toLocaleString()}
              </div>
            </div>

            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Checks Passed
              </span>
              <div className="text-lg font-bold text-foreground">
                {executionResult.validation?.passed_checks || 0}
                <span className="text-2xs font-normal text-muted-foreground ml-1.5">
                  / {executionResult.validation?.total_checks || 0} invariant checks
                </span>
              </div>
            </div>
          </div>

          {/* Validation Checks Accordion/List */}
          {executionResult.validation && executionResult.validation.checks.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-border">
              <span className="text-xs font-semibold text-foreground block">
                Post-Cleaning Invariant Verifications
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {executionResult.validation.checks.map((chk, i) => (
                  <div
                    key={i}
                    className="p-3 bg-surface border border-border/80 rounded-md flex items-start gap-2.5 text-xs"
                  >
                    {chk.status === 'PASSED' ? (
                      <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    ) : chk.status === 'WARNING' ? (
                      <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                    ) : (
                      <X className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                    )}
                    <div className="space-y-0.5">
                      <span className="font-semibold text-foreground block text-xs">
                        {chk.check_name}
                      </span>
                      <p className="text-muted-foreground text-2xs leading-relaxed">
                        {chk.message}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Registration and Download Section */}
          <div className="pt-4 border-t border-border space-y-4">
            {registrationState === 'idle' && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 bg-surface rounded-lg border border-border">
                <div className="space-y-1">
                  <h4 className="text-sm font-semibold text-foreground">
                    Register Cleaned Dataset
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    Register this validated in-memory DataFrame as a distinct first-class dataset in Data Studio.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRegisterCleaned}
                  leftIcon={<Sparkles className="w-3.5 h-3.5" />}
                  className="text-xs shrink-0"
                >
                  Register Cleaned Dataset
                </Button>
              </div>
            )}

            {registrationState === 'registering' && (
              <div className="p-4 bg-surface rounded-lg border border-primary/30 flex items-center gap-3 animate-pulse">
                <div className="w-5 h-5 text-primary">
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                </div>
                <div className="space-y-0.5">
                  <span className="text-xs font-bold text-foreground">Registering Cleaned Dataset...</span>
                  <p className="text-2xs text-muted-foreground">
                    Generating schema, statistical profile, semantic intelligence, and readiness assessment.
                  </p>
                </div>
              </div>
            )}

            {registrationState === 'error' && (
              <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg flex items-start justify-between gap-3 text-xs">
                <div className="space-y-1">
                  <span className="font-bold text-rose-600 dark:text-rose-400">Registration Failed</span>
                  <p className="text-muted-foreground text-2xs">{registrationError}</p>
                </div>
                <Button variant="secondary" size="xs" onClick={handleRegisterCleaned}>
                  Retry Registration
                </Button>
              </div>
            )}

            {registrationState === 'registered' && registeredData && (
              <div className="p-4 bg-surface rounded-lg border border-emerald-500/30 space-y-3.5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
                      <Check className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-foreground">Cleaned Dataset Registered</span>
                        <Badge variant="green" size="xs">Ready in Selector</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Available as an independent dataset with complete profiling and semantic intelligence.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    {onSelectDataset && (
                      <Button
                        variant="primary"
                        size="xs"
                        onClick={() => onSelectDataset(registeredData.dataset_id)}
                        leftIcon={<ArrowRight className="w-3.5 h-3.5" />}
                        className="text-xs"
                      >
                        Use Cleaned Dataset
                      </Button>
                    )}

                    <a
                      href={getDatasetDownloadUrl(registeredData.dataset_id, 'csv')}
                      download={`${registeredData.filename}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-border bg-surface hover:bg-surface-muted text-foreground transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-primary" />
                      <span>Download CSV</span>
                    </a>

                    <a
                      href={getDatasetDownloadUrl(registeredData.dataset_id, 'xlsx')}
                      download={`${registeredData.filename.replace(/\.csv$/, '')}.xlsx`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-border bg-surface hover:bg-surface-muted text-foreground transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Download XLSX</span>
                    </a>
                  </div>
                </div>

                {/* Dataset Details Badge Summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2.5 border-t border-border/60 text-xs">
                  <div>
                    <span className="text-2xs text-muted-foreground block">Cleaned Dataset Name</span>
                    <span className="text-foreground font-semibold truncate block mt-0.5">{registeredData.filename}</span>
                  </div>
                  <div>
                    <span className="text-2xs text-muted-foreground block">New Dataset ID</span>
                    <span className="text-foreground font-mono font-medium truncate block mt-0.5">{registeredData.dataset_id}</span>
                  </div>
                  <div>
                    <span className="text-2xs text-muted-foreground block">Dimensions</span>
                    <span className="text-foreground font-semibold block mt-0.5">{registeredData.row_count.toLocaleString()} rows × {registeredData.column_count} cols</span>
                  </div>
                  <div>
                    <span className="text-2xs text-muted-foreground block">Source Dataset</span>
                    <span className="text-foreground font-mono font-medium truncate block mt-0.5">{registeredData.source_dataset_id}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 1. Plan Summary Banner */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-foreground">Cleaning Plan</h2>
            <p className="text-xs text-muted-foreground">
              {cleaningPlan.total_recommendations} cleaning opportunities detected from profiling and quality checks.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card className="p-4 space-y-1">
            <span className="text-xs text-muted-foreground font-medium">
              Issues found
            </span>
            <div className="text-xl font-bold text-foreground">
              {cleaningPlan.total_recommendations}
            </div>
            <span className="text-2xs text-muted-foreground">
              Deterministic opportunities
            </span>
          </Card>

          <Card className="p-4 space-y-1">
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              Recommended
            </span>
            <div className="text-xl font-bold text-emerald-500">
              {cleaningPlan.safe_count}
            </div>
            <span className="text-2xs text-muted-foreground">
              Low risk · Preselected
            </span>
          </Card>

          <Card className="p-4 space-y-1">
            <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
              Requires decision
            </span>
            <div className={`text-xl font-bold ${cleaningPlan.review_required_count > 0 ? 'text-amber-500' : 'text-foreground'}`}>
              {cleaningPlan.review_required_count}
            </div>
            <span className="text-2xs text-muted-foreground">
              User approval needed
            </span>
          </Card>

          <Card className="p-4 space-y-1">
            <span className="text-xs text-primary font-medium">
              Selected
            </span>
            <div className="text-xl font-bold text-primary">
              {selectedCount} <span className="text-xs font-normal text-muted-foreground">/ {cleaningPlan.total_recommendations}</span>
            </div>
            <span className="text-2xs text-muted-foreground">
              Configured batch actions
            </span>
          </Card>
        </div>
      </div>

      {/* 2. User-Controlled Column Transformations Card */}
      <Card className="p-5 border border-border/80 bg-surface shadow-xs space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">
                  Column Transformations
                </h3>
                <Badge variant="blue" size="xs">
                  User Controlled
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Directly configure datatype conversion, string normalization, or missing-value strategies for any column.
              </p>
            </div>
          </div>

          {customTransformations.length > 0 && (
            <Badge variant="blue" size="xs">
              {customTransformations.length} manual operation{customTransformations.length > 1 ? 's' : ''} queued
            </Badge>
          )}
        </div>

        {/* Column Selection & Action Form */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start">
          {/* Column Selector & Details */}
          <div className="md:col-span-4 space-y-2">
            <label className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>Select Column</span>
              {selectedColInfo && (
                <span className="text-2xs font-normal text-muted-foreground">
                  {selectedColInfo.nullCount > 0 ? `${selectedColInfo.nullCount} missing (${selectedColInfo.nullPct}%)` : 'No missing values'}
                </span>
              )}
            </label>
            <select
              value={selectedCol}
              onChange={(e) => {
                setSelectedCol(e.target.value);
                setColPreviewResult(null);
                setColPreviewError(null);
              }}
              className="w-full text-xs bg-surface-muted/40 border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:border-primary font-medium"
            >
              {availableColumns.map((col) => (
                <option key={col} value={col}>
                  {col}
                </option>
              ))}
            </select>

            {/* Column Metadata Badges */}
            {selectedColInfo && (
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <Badge variant="slate" size="xs">
                  Current Type: <span className="font-semibold ml-1">{selectedColInfo.dtype}</span>
                </Badge>
                <Badge variant="blue" size="xs">
                  Semantic Role: <span className="font-semibold ml-1">{selectedColInfo.role}</span>
                </Badge>
              </div>
            )}
          </div>

          {/* Transformation Selection */}
          <div className="md:col-span-5 space-y-2">
            <label className="text-xs font-semibold text-foreground block">
              Transformation Action
            </label>
            <select
              value={selectedTransformType}
              onChange={(e) => {
                setSelectedTransformType(e.target.value);
                setColPreviewResult(null);
                setColPreviewError(null);
              }}
              className="w-full text-xs bg-surface-muted/40 border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:border-primary font-medium"
            >
              <optgroup label="Datatype Conversions">
                <option value="CONVERT_NUMERIC">Convert to Numeric / Float</option>
                <option value="CONVERT_INTEGER">Convert to Integer (Safe Check)</option>
                <option value="CONVERT_DATETIME">Convert to Datetime (ISO Parse)</option>
                <option value="NORMALIZE_BOOLEAN">Convert to Boolean</option>
                <option value="CONVERT_STRING">Convert to Text / String</option>
              </optgroup>
              <optgroup label="String Normalization">
                <option value="TRIM_WHITESPACE">Trim Leading / Trailing Whitespace</option>
                <option value="NORMALIZE_EMPTY_STRINGS">Normalize Empty Strings to Missing</option>
              </optgroup>
              <optgroup label="Missing-Value Strategies">
                <option value="IMPUTE_MEDIAN">Impute with Median (Numeric)</option>
                <option value="IMPUTE_MEAN">Impute with Mean (Numeric)</option>
                <option value="IMPUTE_MODE">Impute with Most Frequent / Mode</option>
                <option value="IMPUTE_UNKNOWN">Impute with 'Unknown' (Text)</option>
                <option value="IMPUTE_SPECIFIC_VALUE">Impute with Specific Constant Value</option>
                <option value="LEAVE_UNCHANGED">Leave Missing Unchanged</option>
              </optgroup>
            </select>

            {/* Custom Value Input (if specific value selected) */}
            {selectedTransformType === 'IMPUTE_SPECIFIC_VALUE' && (
              <div className="pt-1">
                <input
                  type="text"
                  placeholder="Enter constant value (e.g. 0.0 or N/A)..."
                  value={customTransformVal}
                  onChange={(e) => setCustomTransformVal(e.target.value)}
                  className="w-full text-xs bg-surface border border-border rounded-md px-3 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
                />
              </div>
            )}
          </div>

          {/* Action Trigger */}
          <div className="md:col-span-3 space-y-2 flex flex-col justify-end pt-5 md:pt-0">
            <span className="text-2xs text-muted-foreground hidden md:block">
              Simulate before applying
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={handlePreviewColumnTransform}
              disabled={colPreviewLoading || !selectedCol}
              leftIcon={<Eye className="w-3.5 h-3.5" />}
              className="w-full text-xs"
            >
              {colPreviewLoading ? 'Simulating...' : 'Preview Change'}
            </Button>
          </div>
        </div>

        {/* Dynamic Contextual Explanation */}
        <div className="p-3 bg-surface-muted/30 border border-border/60 rounded-lg text-xs flex items-start gap-2.5">
          <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <p className="text-muted-foreground text-xs leading-relaxed">
            {getTransformExplanation()}
          </p>
        </div>

        {/* Error Display */}
        {colPreviewError && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs flex items-start gap-2.5 text-rose-500">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-semibold block">Transformation Validation Error</span>
              <p className="text-2xs text-rose-600 dark:text-rose-400">{colPreviewError}</p>
            </div>
          </div>
        )}

        {/* Fractional Warning & Truncation Confirmation */}
        {colPreviewResult && colPreviewResult.fractional_loss_count > 0 && (
          <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs space-y-2 text-amber-600 dark:text-amber-400">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Fractional Truncation Notice</span>
                <p className="text-2xs mt-0.5">
                  Integer conversion would truncate fractional values across {colPreviewResult.fractional_loss_count} rows (e.g. 12.5 → 12).
                </p>
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer pt-1 text-2xs font-semibold text-foreground">
              <input
                type="checkbox"
                checked={allowFractional}
                onChange={(e) => setAllowFractional(e.target.checked)}
                className="rounded text-primary focus:ring-primary h-3.5 w-3.5 border-border bg-surface"
              />
              <span>Explicitly allow truncation of fractional values to integer</span>
            </label>
          </div>
        )}

        {/* Deterministic Preview Result Panel */}
        {colPreviewResult && colPreviewResult.is_valid && (
          <div className="p-4 bg-surface-muted/20 border border-primary/20 rounded-lg space-y-3.5">
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <span className="text-xs font-bold text-foreground">
                Conversion Preview: {colPreviewResult.column_name}
              </span>
              <Badge variant="green" size="xs">
                {colPreviewResult.target_type}
              </Badge>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Data Type</span>
                <span className="font-semibold text-foreground text-xs">
                  {colPreviewResult.original_dtype} → <span className="text-primary font-bold">{colPreviewResult.target_dtype}</span>
                </span>
              </div>
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Converted</span>
                <span className="font-bold text-emerald-500 text-xs">
                  {colPreviewResult.converted_count} rows
                </span>
              </div>
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Unparseable / Failed</span>
                <span className={`font-bold text-xs ${colPreviewResult.unparseable_count > 0 ? 'text-amber-500' : 'text-muted-foreground'}`}>
                  {colPreviewResult.unparseable_count} {colPreviewResult.unparseable_count > 0 ? '(coerced to null)' : ''}
                </span>
              </div>
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Missing Values</span>
                <span className="font-semibold text-foreground text-xs">
                  {colPreviewResult.original_missing_count} → {colPreviewResult.new_missing_count}
                </span>
              </div>
            </div>

            {/* Unparseable values badges */}
            {colPreviewResult.unparseable_samples && colPreviewResult.unparseable_samples.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap text-2xs pt-1">
                <span className="text-muted-foreground font-medium">Unparseable tokens coerced to null:</span>
                {colPreviewResult.unparseable_samples.slice(0, 5).map((s, idx) => (
                  <Badge key={idx} variant="amber" size="xs">
                    "{String(s)}"
                  </Badge>
                ))}
              </div>
            )}

            {/* Sample Changes Table */}
            {colPreviewResult.sample_changes && colPreviewResult.sample_changes.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <span className="text-2xs font-semibold text-foreground block">
                  Sample Value Changes (First {colPreviewResult.sample_changes.length} rows)
                </span>
                <div className="border border-border rounded-md overflow-hidden max-h-36 overflow-y-auto">
                  <table className="w-full text-2xs text-left">
                    <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                      <tr>
                        <th className="p-1.5">Row</th>
                        <th className="p-1.5">Before Value</th>
                        <th className="p-1.5">Cleaned / Target Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border font-mono">
                      {colPreviewResult.sample_changes.map((change, idx) => (
                        <tr key={idx} className="hover:bg-surface-muted/30">
                          <td className="p-1.5 text-muted-foreground font-sans">#{change.row_index}</td>
                          <td className="p-1.5 text-rose-500 line-through truncate max-w-[150px]">
                            {change.before_value === null ? 'NULL' : String(change.before_value)}
                          </td>
                          <td className="p-1.5 text-emerald-500 font-bold truncate max-w-[150px]">
                            {change.after_value === null ? 'NULL' : String(change.after_value)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Action Buttons for Previewed Transformation */}
            <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-border/60">
              <Button
                variant="secondary"
                size="xs"
                onClick={handleQueueCustomTransform}
                leftIcon={<PlusCircle className="w-3.5 h-3.5 text-primary" />}
                className="text-xs"
              >
                Add to Cleaning Plan
              </Button>
              <Button
                variant="primary"
                size="xs"
                onClick={handleApplySingleTransform}
                leftIcon={<Play className="w-3.5 h-3.5" />}
                className="text-xs"
              >
                Apply Transformation Directly
              </Button>
            </div>
          </div>
        )}

        {/* Queued Custom Transformations List */}
        {customTransformations.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-border">
            <span className="text-xs font-semibold text-foreground block">
              Queued User Transformations ({customTransformations.length})
            </span>
            <div className="flex flex-wrap gap-2">
              {customTransformations.map((t, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-2 p-2 bg-primary/5 border border-primary/20 rounded-md text-xs"
                >
                  <span className="font-semibold text-foreground font-mono">{t.column_name}</span>
                  <Badge variant="blue" size="xs">
                    {t.operation.replace(/_/g, ' ')}
                  </Badge>
                  {t.custom_value && (
                    <span className="text-2xs text-muted-foreground font-mono">val="{t.custom_value}"</span>
                  )}
                  <button
                    onClick={() => handleRemoveCustomTransform(t.column_name)}
                    className="text-muted-foreground hover:text-rose-500 focus:outline-none ml-1"
                    title="Remove transformation"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* 3. Filter & Selection Management Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-2 border-b border-border">
        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setActiveFilter('ALL')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'ALL'
                ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            All ({cleaningPlan.total_recommendations})
          </button>

          <button
            onClick={() => setActiveFilter('RECOMMENDED')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'RECOMMENDED'
                ? 'bg-emerald-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Recommended ({cleaningPlan.recommended_count})
          </button>

          <button
            onClick={() => setActiveFilter('REVIEW_REQUIRED')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'REVIEW_REQUIRED'
                ? 'bg-amber-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Requires Decision ({cleaningPlan.review_required_count})
          </button>

          <button
            onClick={() => setActiveFilter('SELECTED')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'SELECTED'
                ? 'bg-blue-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Selected ({selectedCount})
          </button>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Filter recommendations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="text-xs bg-surface border border-border rounded-md px-3 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary w-48"
          />

          <Button
            variant="ghost"
            size="xs"
            onClick={selectAllSafe}
            className="text-xs"
          >
            Select All Safe
          </Button>

          <Button
            variant="ghost"
            size="xs"
            onClick={deselectAll}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Deselect All
          </Button>
        </div>
      </div>

      {/* 3. Recommendation List */}
      <div className="space-y-4">
        {filteredRecommendations.map((rec) => {
          const isSelected = !!selections[rec.recommendation_id];
          const currentOp = methodOverrides[rec.recommendation_id] || rec.user_selected_operation || rec.operation;
          const customVal = customValues[rec.recommendation_id] ?? '';
          const isModified = currentOp !== rec.operation || customVal.trim() !== '';
          const isDiagnostic = isDiagnosticOnly(rec.operation);
          const isReviewRequired = rec.requires_review && !isDiagnostic;
          const isSpecificValue = currentOp === 'IMPUTE_SPECIFIC_VALUE' || currentOp === 'FILL_SPECIFIC_VALUE';

          const riskBadgeVariant: 'green' | 'amber' | 'red' =
            rec.risk_level === 'LOW'
              ? 'green'
              : rec.risk_level === 'MEDIUM'
              ? 'amber'
              : 'red';

          const riskLabel =
            rec.risk_level === 'LOW'
              ? 'Low Risk'
              : rec.risk_level === 'MEDIUM'
              ? 'Medium Risk'
              : 'High Risk';

          const originalVariantLabel =
            rec.supported_variants?.find((v) => v.operation === rec.operation)?.label ||
            rec.operation.replace(/_/g, ' ');

          const currentChoiceLabel =
            rec.supported_variants?.find((v) => v.operation === currentOp)?.label ||
            currentOp.replace(/_/g, ' ');

          // Friendly Category / Problem Name
          const problemTitle = rec.category.replace(/_/g, ' ');

          return (
            <Card
              key={rec.recommendation_id}
              className={`p-5 border transition-all ${
                isSelected
                  ? 'border-primary/50 bg-primary-soft/10 shadow-xs'
                  : 'border-border bg-surface opacity-90 hover:opacity-100'
              }`}
            >
              <div className="space-y-4">
                {/* 1. Header: Target Scope, Risk Badge, and Status */}
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => toggleSelection(rec.recommendation_id)}
                      className="mt-1 text-primary hover:text-primary-hover focus:outline-none"
                      title={isSelected ? 'Deselect from plan' : 'Select for plan'}
                    >
                      {isSelected ? (
                        <CheckSquare className="w-5 h-5 text-primary" />
                      ) : (
                        <Square className="w-5 h-5 text-muted-foreground hover:text-foreground" />
                      )}
                    </button>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        {rec.column_name ? (
                          <span className="text-base font-bold text-foreground">
                            {rec.column_name}
                          </span>
                        ) : (
                          <span className="text-base font-bold text-foreground">
                            Whole Dataset
                          </span>
                        )}

                        <Badge variant={riskBadgeVariant} size="xs">
                          {riskLabel}
                        </Badge>

                        {isDiagnostic ? (
                          <Badge variant="amber" size="xs">
                            Review Only
                          </Badge>
                        ) : isReviewRequired ? (
                          <Badge variant="amber" size="xs">
                            Requires your decision
                          </Badge>
                        ) : (
                          <Badge variant="green" size="xs">
                            Recommended
                          </Badge>
                        )}

                        {isModified && (
                          <Badge variant="blue" size="xs">
                            Modified
                          </Badge>
                        )}
                      </div>

                      {/* Problem and Scope count */}
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">{problemTitle}</span>
                        <span>·</span>
                        <span>
                          <strong className="text-foreground">{rec.affected_rows.toLocaleString()} values</strong> ({rec.affected_percentage}% of rows)
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Right side quick toggle button */}
                  <button
                    onClick={() => toggleSelection(rec.recommendation_id)}
                    className={`px-3 py-1 rounded-md text-xs font-medium border transition-colors ${
                      isSelected
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-surface-muted text-muted-foreground hover:text-foreground border-border'
                    }`}
                  >
                    {isSelected ? 'Selected' : 'Include'}
                  </button>
                </div>

                {/* 2. State Guidance / Diagnostic Banner */}
                {isDiagnostic && (
                  <div
                    className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg text-xs border ${
                      isSelected
                        ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400'
                        : 'bg-surface-muted/70 border-border text-muted-foreground'
                    }`}
                  >
                    <Info className="w-4 h-4 shrink-0" />
                    <span>
                      {isSelected
                        ? 'Selected for review. No automatic transformation will be applied.'
                        : 'Review only. Select to include in cleaning report summary.'}
                    </span>
                  </div>
                )}

                {/* 3. Recommended Action & User Choice Controls */}
                {!isDiagnostic && rec.supported_variants && rec.supported_variants.length > 0 && (
                  <div className="p-3.5 bg-surface-muted/30 border border-border/80 rounded-lg space-y-3">
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-foreground">
                          {isReviewRequired ? 'Choose Action:' : 'Action:'}
                        </span>
                        {isModified && (
                          <span className="text-2xs text-muted-foreground">
                            System recommended: <strong className="text-foreground">{originalVariantLabel}</strong>
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        <select
                          value={currentOp}
                          onChange={(e) => {
                            const val = e.target.value;
                            setMethodOverrides((prev) => ({
                              ...prev,
                              [rec.recommendation_id]: val,
                            }));
                          }}
                          className="text-xs bg-surface border border-border rounded-md px-3 py-1.5 text-foreground focus:outline-none focus:border-primary cursor-pointer min-w-[200px]"
                        >
                          {rec.supported_variants.map((v) => (
                            <option key={v.operation} value={v.operation}>
                              {v.label}
                            </option>
                          ))}
                        </select>

                        {!isModified && (
                          <span className="text-2xs text-muted-foreground">
                            (Default recommendation)
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Specific Value Custom Input */}
                    {isSpecificValue && (
                      <div className="pt-2 border-t border-border/60 flex items-center gap-3 flex-wrap">
                        <span className="text-xs font-semibold text-primary">
                          Fill value:
                        </span>
                        <input
                          type={currentOp === 'IMPUTE_SPECIFIC_VALUE' ? 'number' : 'text'}
                          step="any"
                          value={customVal}
                          onChange={(e) => {
                            const val = e.target.value;
                            setCustomValues((prev) => ({
                              ...prev,
                              [rec.recommendation_id]: val,
                            }));
                          }}
                          placeholder={currentOp === 'IMPUTE_SPECIFIC_VALUE' ? 'e.g. 15.0' : 'e.g. Unknown'}
                          className="text-xs bg-surface border border-primary/40 focus:border-primary rounded-md px-3 py-1.5 text-foreground w-48"
                        />
                        <span className="text-2xs text-muted-foreground">
                          {currentOp === 'IMPUTE_SPECIFIC_VALUE'
                            ? 'Enter custom numeric constant'
                            : 'Enter custom text constant'}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* 4. Why & Expected Result in 2 Columns */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-border/60 text-xs">
                  <div className="space-y-1">
                    <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider block">
                      Why this is recommended
                    </span>
                    <p className="text-foreground leading-relaxed">
                      {rec.rationale}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider block">
                      Expected result
                    </span>
                    <p className="text-foreground leading-relaxed">
                      {rec.expected_effect}
                    </p>
                  </div>
                </div>

                {/* 5. Evidence Section */}
                {rec.evidence && rec.evidence.length > 0 && (
                  <div className="pt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider mr-1">
                      Evidence:
                    </span>
                    {rec.evidence.map((evStr, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-0.5 bg-surface-muted border border-border rounded-md text-2xs text-muted-foreground"
                      >
                        {evStr}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          );
        })}

        {filteredRecommendations.length === 0 && (
          <Card className="p-10 text-center space-y-2">
            <div className="w-10 h-10 rounded-full bg-surface-muted flex items-center justify-center mx-auto text-muted-foreground">
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            </div>
            <h4 className="text-sm font-bold text-foreground">No Recommendations Found</h4>
            <p className="text-xs text-muted-foreground">
              No cleaning recommendations match the current filter or search criteria.
            </p>
          </Card>
        )}
      </div>

      {/* 4. Action Bar (Preview & Batch Apply) */}
      <Card className="p-4 border border-primary/30 bg-primary-soft/10 flex flex-col sm:flex-row items-center justify-between gap-4 sticky bottom-4 shadow-lg backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg text-primary shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-bold text-foreground">
                Cleaning Plan Execution
              </h4>
              <Badge variant={(selectedCount + customTransformations.length) > 0 ? 'blue' : 'slate'} size="xs">
                {selectedCount} Plan Ops {customTransformations.length > 0 ? `+ ${customTransformations.length} Manual` : ''}
                {modifiedCount > 0 ? ` · ${modifiedCount} Modified` : ''}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Review simulated changes before applying. Cleaned DataFrame is stored separately in-memory.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGeneratePreview}
            disabled={(selectedCount + customTransformations.length) === 0 || isLoadingPreview || executionState === 'applying' || executionState === 'validating'}
            leftIcon={<Eye className="w-3.5 h-3.5" />}
            className="text-xs"
          >
            {isLoadingPreview ? 'Simulating...' : 'Preview Changes'}
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleApplyCleaning}
            disabled={(selectedCount + customTransformations.length) === 0 || executionState === 'applying' || executionState === 'validating'}
            leftIcon={<Play className="w-3.5 h-3.5" />}
            className="text-xs"
          >
            Apply Cleaning ({selectedCount + customTransformations.length})
          </Button>
        </div>
      </Card>

      {/* 5. Preview Modal / Slide-Over */}
      {isPreviewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-border flex items-center justify-between bg-surface-muted/30">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-primary/10 text-primary">
                  <Eye className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    Cleaning Operations Preview
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Deterministic simulation across {selectedCount + customTransformations.length} selected and manual operations. Raw data is untouched.
                  </p>
                </div>
              </div>

              <button
                onClick={() => setIsPreviewOpen(false)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-5 flex-1 text-xs">
              {previewError && (
                <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-500 text-xs">
                  {previewError}
                </div>
              )}

              {previewResult && (
                <>
                  {/* Summary Comparison Grid */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-2xs text-muted-foreground block font-medium">
                        Rows Before
                      </span>
                      <div className="text-sm font-bold text-foreground">
                        {previewResult.original_row_count.toLocaleString()}
                      </div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-2xs text-muted-foreground block font-medium">
                        Rows After Preview
                      </span>
                      <div className="text-sm font-bold text-emerald-500">
                        {previewResult.preview_row_count.toLocaleString()}
                      </div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-2xs text-muted-foreground block font-medium">
                        Net Row Change
                      </span>
                      <div className="text-sm font-bold text-foreground">
                        {previewResult.row_count_change === 0
                          ? '0'
                          : `${previewResult.row_count_change.toLocaleString()} rows`}
                      </div>
                    </div>
                  </div>

                  {/* Operations Summary */}
                  <div className="space-y-2.5">
                    <span className="text-xs font-bold text-foreground block">
                      Transformation Comparison ({previewResult.operations.length} operations)
                    </span>
                    <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                      {previewResult.operations.map((op, i) => (
                        <div
                          key={i}
                          className="p-3 bg-surface border border-border/80 rounded-lg space-y-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              {op.column_name ? (
                                <span className="font-semibold text-foreground px-2 py-0.5 bg-surface-muted rounded text-xs border border-border">
                                  {op.column_name}
                                </span>
                              ) : (
                                <Badge variant="blue" size="xs">
                                  DATASET-WIDE
                                </Badge>
                              )}
                              <span className="font-semibold text-foreground text-xs">
                                {op.operation.replace(/_/g, ' ')}
                              </span>
                            </div>

                            <Badge
                              variant={
                                op.status === 'APPLIED'
                                  ? 'green'
                                  : op.status === 'REVIEW_ONLY'
                                  ? 'amber'
                                  : op.status === 'WARNING'
                                  ? 'amber'
                                  : 'slate'
                              }
                              size="xs"
                            >
                              {op.status === 'REVIEW_ONLY' ? 'Review Only' : op.status}
                            </Badge>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1 border-t border-border/60 text-2xs">
                            <div>
                              <span className="text-muted-foreground block">Before:</span>
                              <span className={op.status === 'REVIEW_ONLY' ? 'text-muted-foreground font-semibold' : 'text-rose-500 font-semibold'}>
                                {op.before_statistic}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground block">After:</span>
                              <span className={op.status === 'REVIEW_ONLY' ? 'text-blue-500 dark:text-blue-400 font-semibold' : 'text-emerald-500 font-semibold'}>
                                {op.after_statistic}
                              </span>
                            </div>
                            <div className="col-span-2 sm:col-span-1">
                              <span className="text-muted-foreground block">Method:</span>
                              <span className="text-foreground truncate block">{op.method_used}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Sample Changed Cells Table */}
                  {previewResult.sample_changes.length > 0 && (
                    <div className="space-y-2 pt-2 border-t border-border">
                      <span className="text-xs font-bold text-foreground block">
                        Sample Cell Modifications (First {previewResult.sample_changes.length} changed items)
                      </span>
                      <div className="border border-border rounded-lg overflow-hidden max-h-40 overflow-y-auto">
                        <table className="w-full text-2xs text-left">
                          <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                            <tr>
                              <th className="p-2">Row</th>
                              <th className="p-2">Column</th>
                              <th className="p-2">Before Value</th>
                              <th className="p-2">Cleaned Value</th>
                              <th className="p-2">Operation</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border font-mono">
                            {previewResult.sample_changes.map((sample, idx) => (
                              <tr key={idx} className="hover:bg-surface-muted/30">
                                <td className="p-2 font-semibold text-muted-foreground">#{sample.row_index}</td>
                                <td className="p-2 font-semibold text-foreground">{sample.column_name}</td>
                                <td className="p-2 text-rose-500 line-through truncate max-w-[120px]">
                                  {sample.before_value === null ? 'NULL' : String(sample.before_value)}
                                </td>
                                <td className="p-2 text-emerald-500 font-bold truncate max-w-[120px]">
                                  {sample.after_value === null ? 'NULL' : String(sample.after_value)}
                                </td>
                                <td className="p-2 text-muted-foreground truncate max-w-[100px] font-sans">{sample.operation}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-border flex items-center justify-between bg-surface-muted/30">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsPreviewOpen(false)}
                className="text-xs"
              >
                Close Preview
              </Button>

              <Button
                variant="primary"
                size="sm"
                onClick={handleApplyCleaning}
                leftIcon={<Play className="w-3.5 h-3.5" />}
                className="text-xs"
              >
                Apply Cleaning Now
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

