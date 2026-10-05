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
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import { Button } from '../Button';
import {
  CleaningExecutionResult,
  CleaningPlan,
  CleaningPreviewResult,
  CleaningRecommendation,
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

  const [activeFilter, setActiveFilter] = useState<FilterStatus>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Preview & Execution State
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewResult, setPreviewResult] = useState<CleaningPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [executionState, setExecutionState] = useState<ExecutionState>('idle');
  const [executionResult, setExecutionResult] = useState<CleaningExecutionResult | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);

  // Registration & Download State (Part 6)
  const [registrationState, setRegistrationState] = useState<RegistrationState>('idle');
  const [registeredData, setRegisteredData] = useState<RegisterCleanedDatasetResponse | null>(null);
  const [registrationError, setRegistrationError] = useState<string | null>(null);

  // Update selections when cleaningPlan changes (e.g. switching datasets)
  React.useEffect(() => {
    if (!cleaningPlan) {
      setSelections({});
      setMethodOverrides({});
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
    setPreviewResult(null);
    setExecutionResult(null);
    setExecutionState('idle');
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);
  }, [cleaningPlan?.dataset_id]);

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
      (r) => methodOverrides[r.recommendation_id] && methodOverrides[r.recommendation_id] !== r.operation
    ).length;
  }, [allRecs, methodOverrides]);

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

  // Preview Action
  const handleGeneratePreview = async () => {
    if (!cleaningPlan || selectedIds.length === 0) return;
    setIsLoadingPreview(true);
    setPreviewError(null);
    try {
      const res = await previewCleaningPlan(cleaningPlan.dataset_id, selectedIds, methodOverrides);
      setPreviewResult(res);
      setIsPreviewOpen(true);
    } catch (err: any) {
      setPreviewError(err.message || 'Failed to generate cleaning preview.');
      setIsPreviewOpen(true);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  // Apply Action
  const handleApplyCleaning = async () => {
    if (!cleaningPlan || selectedIds.length === 0) return;
    setIsPreviewOpen(false);
    setExecutionState('applying');
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);

    try {
      // Simulate quick visual step transition to 'validating'
      const timer = setTimeout(() => {
        setExecutionState('validating');
      }, 400);

      const res = await applyCleaningPlan(cleaningPlan.dataset_id, selectedIds, methodOverrides);
      clearTimeout(timer);
      setExecutionResult(res);
      setExecutionState('complete');
    } catch (err: any) {
      setExecutionError(err.message || 'Failed to execute cleaning plan.');
      setExecutionState('error');
    }
  };

  // Register Cleaned Dataset Action (Part 6)
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
          <p className="text-xs text-muted-foreground max-w-md mx-auto font-mono">
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
          <p className="text-xs text-muted-foreground font-mono">
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
            <h4 className="text-sm font-bold font-mono text-foreground">
              {executionState === 'applying'
                ? 'Applying Selected Cleaning Operations...'
                : 'Validating Invariants & Generating Cleaned In-Memory Dataset...'}
            </h4>
            <p className="text-xs text-muted-foreground font-mono">
              Operating safely on a deep copy. Raw session dataset remains 100% immutable.
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
              <h4 className="text-xs font-bold text-rose-600 dark:text-rose-400 font-mono">
                Cleaning Execution Failed
              </h4>
              <p className="text-xs text-muted-foreground font-mono">
                {executionError || 'An unexpected error occurred during cleaning execution.'}
              </p>
            </div>
          </div>
          <Button variant="secondary" size="xs" onClick={handleResetExecution} className="font-mono">
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
                  <h3 className="text-sm font-bold text-foreground font-mono">
                    Cleaning Execution Complete
                  </h3>
                  <Badge variant="green" size="xs">
                    Validation: {executionResult.validation?.overall_status || 'PASSED'}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-0.5">
                  Cleaned in-memory DataFrame generated successfully. Raw source dataset remains untouched.
                </p>
              </div>
            </div>

            <Button
              variant="secondary"
              size="xs"
              onClick={handleResetExecution}
              leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
              className="font-mono"
            >
              Reconfigure Plan
            </Button>
          </div>

          {/* Metrics Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-3xs uppercase font-mono text-muted-foreground block">
                Row Count
              </span>
              <div className="text-base font-bold font-mono text-foreground">
                {executionResult.cleaned_row_count.toLocaleString()}
                <span className="text-3xs font-normal text-muted-foreground ml-1.5">
                  ({executionResult.row_count_change <= 0 ? executionResult.row_count_change : `+${executionResult.row_count_change}`} rows)
                </span>
              </div>
            </div>

            <div className="p-3 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-3xs uppercase font-mono text-muted-foreground block">
                Operations Applied
              </span>
              <div className="text-base font-bold font-mono text-emerald-500">
                {executionResult.operations_applied}
                <span className="text-3xs font-normal text-muted-foreground ml-1.5">
                  / {executionResult.operations_requested} requested
                </span>
              </div>
            </div>

            <div className="p-3 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-3xs uppercase font-mono text-muted-foreground block">
                Cells Modified
              </span>
              <div className="text-base font-bold font-mono text-primary">
                {executionResult.total_cells_affected.toLocaleString()}
              </div>
            </div>

            <div className="p-3 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-3xs uppercase font-mono text-muted-foreground block">
                Checks Passed
              </span>
              <div className="text-base font-bold font-mono text-foreground">
                {executionResult.validation?.passed_checks || 0}
                <span className="text-3xs font-normal text-muted-foreground ml-1.5">
                  / {executionResult.validation?.total_checks || 0} invariant checks
                </span>
              </div>
            </div>
          </div>

          {/* Validation Checks Accordion/List */}
          {executionResult.validation && executionResult.validation.checks.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-border">
              <span className="text-xs font-bold font-mono text-foreground block">
                Post-Cleaning Invariant Verifications
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {executionResult.validation.checks.map((chk, i) => (
                  <div
                    key={i}
                    className="p-2.5 bg-surface border border-border/80 rounded-md flex items-start gap-2.5 text-xs font-mono"
                  >
                    {chk.status === 'PASSED' ? (
                      <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    ) : chk.status === 'WARNING' ? (
                      <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                    ) : (
                      <X className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                    )}
                    <div className="space-y-0.5">
                      <span className="font-bold text-foreground block text-3xs">
                        {chk.check_name}
                      </span>
                      <p className="text-muted-foreground text-3xs leading-relaxed">
                        {chk.message}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Registration and Download Section (Part 6) */}
          <div className="pt-4 border-t border-border space-y-4 font-mono">
            {registrationState === 'idle' && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 bg-surface rounded-lg border border-border">
                <div className="space-y-1">
                  <h4 className="text-xs font-bold text-foreground">
                    Register Cleaned Dataset
                  </h4>
                  <p className="text-3xs text-muted-foreground">
                    Register this validated in-memory DataFrame as a distinct first-class dataset in Data Studio.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRegisterCleaned}
                  leftIcon={<Sparkles className="w-3.5 h-3.5" />}
                  className="font-mono text-xs shrink-0"
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
                  <p className="text-3xs text-muted-foreground">
                    Generating schema, statistical profile, semantic intelligence, and readiness assessment.
                  </p>
                </div>
              </div>
            )}

            {registrationState === 'error' && (
              <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg flex items-start justify-between gap-3 text-xs">
                <div className="space-y-1">
                  <span className="font-bold text-rose-600 dark:text-rose-400">Registration Failed</span>
                  <p className="text-muted-foreground text-3xs">{registrationError}</p>
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
                    <div className="w-7 h-7 rounded-md bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
                      <Check className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-foreground">Cleaned Dataset Registered</span>
                        <Badge variant="green" size="xs">Ready in Selector</Badge>
                      </div>
                      <p className="text-3xs text-muted-foreground mt-0.5">
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
                        className="font-mono text-xs"
                      >
                        Use Cleaned Dataset
                      </Button>
                    )}

                    <a
                      href={getDatasetDownloadUrl(registeredData.dataset_id, 'csv')}
                      download={`${registeredData.filename}`}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono rounded-md border border-border bg-surface hover:bg-surface-muted text-foreground transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-primary" />
                      <span>Download CSV</span>
                    </a>

                    <a
                      href={getDatasetDownloadUrl(registeredData.dataset_id, 'xlsx')}
                      download={`${registeredData.filename.replace(/\.csv$/, '')}.xlsx`}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono rounded-md border border-border bg-surface hover:bg-surface-muted text-foreground transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Download XLSX</span>
                    </a>
                  </div>
                </div>

                {/* Dataset Details Badge Summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-border/60 text-3xs">
                  <div>
                    <span className="text-muted-foreground block">Cleaned Dataset Name:</span>
                    <span className="text-foreground font-bold truncate block">{registeredData.filename}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block">New Dataset ID:</span>
                    <span className="text-foreground font-bold truncate block">{registeredData.dataset_id}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block">Dimensions:</span>
                    <span className="text-foreground font-bold block">{registeredData.row_count.toLocaleString()} rows × {registeredData.column_count} cols</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block">Source Dataset:</span>
                    <span className="text-foreground font-bold truncate block">{registeredData.source_dataset_id}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 1. Plan Summary Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">
            Total Opportunities
          </span>
          <div className="text-xl font-bold font-mono text-foreground">
            {cleaningPlan.total_recommendations}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Deterministic findings
          </span>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-emerald-600 dark:text-emerald-400 font-mono">
            Safe & Recommended
          </span>
          <div className="text-xl font-bold font-mono text-emerald-500">
            {cleaningPlan.safe_count}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Low risk • Preselected
          </span>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-amber-600 dark:text-amber-400 font-mono">
            Requires Review
          </span>
          <div className={`text-xl font-bold font-mono ${cleaningPlan.review_required_count > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {cleaningPlan.review_required_count}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            User approval needed
          </span>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-primary font-mono">
            Selected for Execution
          </span>
          <div className="text-xl font-bold font-mono text-primary">
            {selectedCount} <span className="text-xs font-normal text-muted-foreground">/ {cleaningPlan.total_recommendations}</span>
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Configured batch actions
          </span>
        </Card>
      </div>

      {/* 2. Filter & Selection Management Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-2 border-b border-border">
        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setActiveFilter('ALL')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'ALL'
                ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            All ({cleaningPlan.total_recommendations})
          </button>

          <button
            onClick={() => setActiveFilter('RECOMMENDED')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'RECOMMENDED'
                ? 'bg-emerald-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Recommended ({cleaningPlan.recommended_count})
          </button>

          <button
            onClick={() => setActiveFilter('REVIEW_REQUIRED')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'REVIEW_REQUIRED'
                ? 'bg-amber-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Review Required ({cleaningPlan.review_required_count})
          </button>

          <button
            onClick={() => setActiveFilter('SELECTED')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
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
            className="text-xs bg-surface border border-border rounded px-2.5 py-1 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary font-mono w-44"
          />

          <Button
            variant="ghost"
            size="xs"
            onClick={selectAllSafe}
            className="text-3xs font-mono"
          >
            Select All Safe
          </Button>

          <Button
            variant="ghost"
            size="xs"
            onClick={deselectAll}
            className="text-3xs font-mono text-muted-foreground hover:text-foreground"
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
          const isModified = currentOp !== rec.operation;

          const riskBadgeVariant: 'green' | 'amber' | 'red' =
            rec.risk_level === 'LOW'
              ? 'green'
              : rec.risk_level === 'MEDIUM'
              ? 'amber'
              : 'red';

          const confidenceVariant: 'green' | 'amber' | 'slate' =
            rec.confidence_level === 'HIGH'
              ? 'green'
              : rec.confidence_level === 'MEDIUM'
              ? 'amber'
              : 'slate';

          const originalVariantLabel =
            rec.supported_variants?.find((v) => v.operation === rec.operation)?.label ||
            rec.operation.replace(/_/g, ' ');

          return (
            <Card
              key={rec.recommendation_id}
              className={`p-5 border transition-all ${
                isSelected
                  ? 'border-primary/50 bg-primary-soft/10 shadow-xs'
                  : 'border-border bg-surface opacity-85 hover:opacity-100'
              }`}
            >
              <div className="space-y-3.5">
                {/* Card Top Row: Checkbox, Target, Operation & Badges */}
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => toggleSelection(rec.recommendation_id)}
                      className="mt-0.5 text-primary hover:text-primary-hover focus:outline-none"
                      title={isSelected ? 'Deselect from plan' : 'Select for plan'}
                    >
                      {isSelected ? (
                        <CheckSquare className="w-5 h-5 text-primary" />
                      ) : (
                        <Square className="w-5 h-5 text-muted-foreground hover:text-foreground" />
                      )}
                    </button>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        {rec.column_name ? (
                          <span className="text-xs font-bold font-mono text-foreground px-2 py-0.5 bg-surface-muted border border-border rounded">
                            {rec.column_name}
                          </span>
                        ) : (
                          <Badge variant="blue" size="xs">
                            DATASET-WIDE
                          </Badge>
                        )}

                        <span className="text-xs font-bold font-mono text-foreground">
                          {currentOp.replace(/_/g, ' ')}
                        </span>

                        <Badge variant="slate" size="xs">
                          {rec.category.replace(/_/g, ' ')}
                        </Badge>

                        {isModified && (
                          <Badge variant="blue" size="xs">
                            Modified (was {originalVariantLabel})
                          </Badge>
                        )}
                      </div>

                      <div className="flex items-center gap-2 text-3xs font-mono text-muted-foreground">
                        <span>
                          Affected: <strong className="text-foreground">{rec.affected_rows.toLocaleString()} rows</strong> ({rec.affected_percentage}%)
                        </span>
                        <span>•</span>
                        <span>
                          ID: <span className="font-mono text-foreground">{rec.recommendation_id}</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Badges on Right */}
                  <div className="flex items-center gap-2">
                    <Badge variant={riskBadgeVariant} size="xs">
                      Risk: {rec.risk_level}
                    </Badge>
                    <Badge variant={confidenceVariant} size="xs">
                      Confidence: {Math.round(rec.confidence * 100)}% ({rec.confidence_level})
                    </Badge>
                    {rec.requires_review && (
                      <Badge variant="amber" size="xs">
                        REVIEW ONLY
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Review-Only Guidance Banner */}
                {rec.requires_review && (
                  <div
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-3xs font-mono border ${
                      isSelected
                        ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400'
                        : 'bg-surface-muted/80 border-border text-muted-foreground'
                    }`}
                  >
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>
                      {isSelected
                        ? 'Selected for review — no automatic transformation will be applied. Data remains unchanged.'
                        : 'Review only — select to include in cleaning report. Data remains unchanged.'}
                    </span>
                  </div>
                )}

                {/* Method Selector (if editable alternatives exist) */}
                {rec.supported_variants && rec.supported_variants.length > 1 && (
                  <div className="flex items-center gap-2 pt-2 border-t border-border/60 text-xs font-mono flex-wrap">
                    <span className="text-3xs uppercase tracking-wider text-muted-foreground font-semibold">
                      Method:
                    </span>
                    <select
                      value={currentOp}
                      onChange={(e) => {
                        const val = e.target.value;
                        setMethodOverrides((prev) => ({
                          ...prev,
                          [rec.recommendation_id]: val,
                        }));
                      }}
                      disabled={rec.requires_review}
                      className="text-xs bg-surface border border-border rounded px-2.5 py-1 text-foreground focus:outline-none focus:border-primary font-mono cursor-pointer"
                    >
                      {rec.supported_variants.map((v) => (
                        <option key={v.operation} value={v.operation}>
                          {v.label}
                        </option>
                      ))}
                    </select>
                    <span className="text-3xs text-muted-foreground font-mono">
                      (Recommended: {originalVariantLabel})
                    </span>
                  </div>
                )}

                {/* Explanation & Rationale */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-border/60 text-xs">
                  <div className="space-y-1">
                    <span className="text-3xs uppercase tracking-wider font-mono text-muted-foreground block">
                      Rationale (Why recommended)
                    </span>
                    <p className="text-foreground leading-relaxed text-xs">
                      {rec.rationale}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <span className="text-3xs uppercase tracking-wider font-mono text-muted-foreground block">
                      Expected Effect (What will happen)
                    </span>
                    <p className="text-muted-foreground leading-relaxed text-xs">
                      {rec.expected_effect}
                    </p>
                  </div>
                </div>

                {/* Evidence Statements */}
                {rec.evidence && rec.evidence.length > 0 && (
                  <div className="pt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-3xs uppercase font-mono text-muted-foreground mr-1">
                      Evidence:
                    </span>
                    {rec.evidence.map((evStr, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 bg-surface-muted/70 border border-border/80 rounded text-3xs font-mono text-foreground"
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
          <Card className="p-8 text-center space-y-2">
            <div className="w-10 h-10 rounded-full bg-surface-muted flex items-center justify-center mx-auto text-muted-foreground">
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            </div>
            <h4 className="text-sm font-bold text-foreground">No Recommendations Found</h4>
            <p className="text-xs text-muted-foreground font-mono">
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
              <h4 className="text-xs font-bold text-foreground font-mono">
                Cleaning Plan Execution
              </h4>
              <Badge variant={selectedCount > 0 ? 'blue' : 'slate'} size="xs">
                {selectedCount} of {cleaningPlan.total_recommendations} Operations Selected
                {modifiedCount > 0 ? ` • ${modifiedCount} Modified` : ''}
              </Badge>
            </div>
            <p className="text-3xs text-muted-foreground mt-0.5">
              Review changes safely before applying. Cleaned DataFrame will be stored separately in-memory.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGeneratePreview}
            disabled={selectedCount === 0 || isLoadingPreview || executionState === 'applying' || executionState === 'validating'}
            leftIcon={<Eye className="w-3.5 h-3.5" />}
            className="font-mono text-xs"
          >
            {isLoadingPreview ? 'Simulating...' : 'Preview Changes'}
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleApplyCleaning}
            disabled={selectedCount === 0 || executionState === 'applying' || executionState === 'validating'}
            leftIcon={<Play className="w-3.5 h-3.5" />}
            className="font-mono text-xs"
          >
            Apply Cleaning ({selectedCount})
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
                  <h3 className="text-sm font-bold text-foreground font-mono">
                    Cleaning Operations Preview
                  </h3>
                  <p className="text-3xs text-muted-foreground font-mono">
                    Deterministic simulation across {selectedCount} selected operations. Raw data is untouched.
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
            <div className="p-5 overflow-y-auto space-y-5 flex-1 font-mono text-xs">
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
                      <span className="text-3xs uppercase text-muted-foreground block">
                        Rows Before
                      </span>
                      <div className="text-sm font-bold text-foreground">
                        {previewResult.original_row_count.toLocaleString()}
                      </div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-3xs uppercase text-muted-foreground block">
                        Rows After Preview
                      </span>
                      <div className="text-sm font-bold text-emerald-500">
                        {previewResult.preview_row_count.toLocaleString()}
                      </div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-3xs uppercase text-muted-foreground block">
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
                                <span className="font-bold text-foreground px-1.5 py-0.5 bg-surface-muted rounded text-3xs border border-border">
                                  {op.column_name}
                                </span>
                              ) : (
                                <Badge variant="blue" size="xs">
                                  DATASET-WIDE
                                </Badge>
                              )}
                              <span className="font-bold text-foreground text-3xs">
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
                              {op.status === 'REVIEW_ONLY' ? 'REVIEW ONLY' : op.status}
                            </Badge>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1 border-t border-border/60 text-3xs">
                            <div>
                              <span className="text-muted-foreground block">Before:</span>
                              <span className={op.status === 'REVIEW_ONLY' ? 'text-muted-foreground font-bold' : 'text-rose-500 font-bold'}>
                                {op.before_statistic}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground block">After:</span>
                              <span className={op.status === 'REVIEW_ONLY' ? 'text-blue-500 dark:text-blue-400 font-bold' : 'text-emerald-500 font-bold'}>
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
                        <table className="w-full text-3xs text-left">
                          <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                            <tr>
                              <th className="p-2">Row</th>
                              <th className="p-2">Column</th>
                              <th className="p-2">Before Value</th>
                              <th className="p-2">Cleaned Value</th>
                              <th className="p-2">Operation</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {previewResult.sample_changes.map((sample, idx) => (
                              <tr key={idx} className="hover:bg-surface-muted/30">
                                <td className="p-2 font-bold text-muted-foreground">#{sample.row_index}</td>
                                <td className="p-2 font-bold text-foreground">{sample.column_name}</td>
                                <td className="p-2 text-rose-500 line-through truncate max-w-[120px]">
                                  {sample.before_value === null ? 'NULL' : String(sample.before_value)}
                                </td>
                                <td className="p-2 text-emerald-500 font-bold truncate max-w-[120px]">
                                  {sample.after_value === null ? 'NULL' : String(sample.after_value)}
                                </td>
                                <td className="p-2 text-muted-foreground truncate max-w-[100px]">{sample.operation}</td>
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
                className="font-mono text-xs"
              >
                Close Preview
              </Button>

              <Button
                variant="primary"
                size="sm"
                onClick={handleApplyCleaning}
                leftIcon={<Play className="w-3.5 h-3.5" />}
                className="font-mono text-xs"
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
