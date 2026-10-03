'use client';

import React, { useEffect, useState, useRef, useMemo } from 'react';
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Sparkles,
  Database,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Loader2,
  X,
  FileSpreadsheet,
  Key,
  Calendar,
  Tag,
  TrendingUp,
  Table,
  Check,
} from 'lucide-react';
import {
  getDatasetCleaningReport,
  getDatasetMetadata,
  getDatasetPreview,
  getDatasetReadiness,
  getDatasetSemanticAnalysis,
  getProvidersStatus,
  listDatasets,
  resolvePipeline,
  runPipeline,
  uploadDataset,
} from '../lib/api';
import {
  AnalysisReadiness,
  DataPreviewResponse,
  DatasetListItem,
  DatasetMetadata,
  OrchestratorPipelineResponse,
  SemanticProfile,
} from '../lib/types';
import { Button } from '../components/Button';
import { Badge } from '../components/Badge';
import { PipelineStepper, PipelineStep, ProviderStatusItem } from '../components/PipelineStepper';
import { ClarificationCard } from '../components/ClarificationCard';
import { DashboardPanelsView } from '../components/DashboardPanelsView';

export default function HomePage() {
  // 1. Dataset & Ingestion State
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [semanticProfile, setSemanticProfile] = useState<SemanticProfile | null>(null);
  const [readiness, setReadiness] = useState<AnalysisReadiness | null>(null);
  const [previewData, setPreviewData] = useState<DataPreviewResponse | null>(null);
  const [cleaningReport, setCleaningReport] = useState<any>(null);
  const [cleaningExpanded, setCleaningExpanded] = useState<boolean>(false);

  // Uploading state
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDraggingFile, setIsDraggingFile] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 2. Natural Language Brief & Execution State
  // Rule: Do not hardcode dataset names, column names or example briefs anywhere.
  const [intent, setIntent] = useState<string>('');
  const [pipelineStep, setPipelineStep] = useState<PipelineStep>('idle');
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineResult, setPipelineResult] = useState<OrchestratorPipelineResponse | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Cancellation controller
  const abortControllerRef = useRef<AbortController | null>(null);

  // Providers Health
  const [providers, setProviders] = useState<ProviderStatusItem[]>([]);

  // Initial Load: Fetch existing datasets and provider health concurrently
  useEffect(() => {
    listDatasets()
      .then((list) => {
        setDatasets(list);
        if (list.length > 0) {
          selectDataset(list[0].dataset_id);
        }
      })
      .catch((e) => console.error('Failed to load datasets:', e));

    getProvidersStatus()
      .then((provRes) => {
        if (provRes && provRes.providers) {
          setProviders(provRes.providers);
        }
      })
      .catch((e) => console.error('Failed to load provider health:', e));
  }, []);

  // Elapsed seconds timer during pipeline execution
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    const isRunning = ['clean', 'understand', 'propose', 'rank', 'build'].includes(pipelineStep);

    if (isRunning) {
      const startTime = Date.now();
      timer = setInterval(() => {
        setElapsedSeconds(Number(((Date.now() - startTime) / 1000).toFixed(1)));
      }, 100);
    } else if (pipelineStep === 'idle') {
      setElapsedSeconds(0);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [pipelineStep]);

  // Handler to load dataset details
  const selectDataset = async (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setUploadError(null);
    setPipelineResult(null);
    setPipelineStep('idle');
    setCleaningExpanded(false);

    if (!datasetId) {
      setMetadata(null);
      setSemanticProfile(null);
      setReadiness(null);
      setPreviewData(null);
      setCleaningReport(null);
      return;
    }

    try {
      const [meta, sem, rdy, prev, cln] = await Promise.all([
        getDatasetMetadata(datasetId).catch(() => null),
        getDatasetSemanticAnalysis(datasetId).catch(() => null),
        getDatasetReadiness(datasetId).catch(() => null),
        getDatasetPreview(datasetId, 20).catch(() => null),
        getDatasetCleaningReport(datasetId).catch(() => null),
      ]);
      setMetadata(meta);
      setSemanticProfile(sem);
      setReadiness(rdy);
      setPreviewData(prev);
      setCleaningReport(cln);
    } catch (err: any) {
      console.error('Error loading dataset details:', err);
    }
  };

  // File Upload Handler (Dropzone)
  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const meta = await uploadDataset(file);
      const updatedList = await listDatasets();
      setDatasets(updatedList);
      await selectDataset(meta.dataset_id);
    } catch (err: any) {
      setUploadError(err.message || 'File upload failed');
    } finally {
      setIsUploading(false);
      setIsDraggingFile(false);
    }
  };

  // Suggestion chips generated dynamically at runtime from detected roles
  const suggestionChips = useMemo(() => {
    if (!semanticProfile?.column_evidences) return [];
    const evidences = Object.values(semanticProfile.column_evidences);
    const measures = evidences.filter((c) => c.candidate_role === 'MEASURE').map((c) => c.column_name);
    const dimensions = evidences.filter((c) => c.candidate_role === 'DIMENSION').map((c) => c.column_name);
    const datetimes = evidences.filter((c) => c.candidate_role === 'DATETIME').map((c) => c.column_name);

    const chips: string[] = [];
    if (measures.length > 0 && dimensions.length > 0) {
      chips.push(`${measures[0]} by ${dimensions[0]}`);
    }
    if (measures.length > 0 && datetimes.length > 0) {
      chips.push(`${measures[0]} trend over ${datetimes[0]}`);
    }
    if (measures.length > 1 && dimensions.length > 0) {
      chips.push(`Average ${measures[1]} across ${dimensions[0]}`);
    } else if (dimensions.length > 1 && measures.length > 0) {
      chips.push(`Distribution of ${measures[0]} by ${dimensions[1]}`);
    } else if (measures.length > 0) {
      chips.push(`Total ${measures[0]}`);
    }
    return chips.slice(0, 3);
  }, [semanticProfile]);

  // Detected role counts
  const roleSummary = useMemo(() => {
    if (!semanticProfile?.column_evidences) return { identifiers: 0, datetimes: 0, dimensions: 0, measures: 0 };
    const evidences = Object.values(semanticProfile.column_evidences);
    return {
      identifiers: evidences.filter((c) => c.candidate_role === 'IDENTIFIER').length,
      datetimes: evidences.filter((c) => c.candidate_role === 'DATETIME').length,
      dimensions: evidences.filter((c) => c.candidate_role === 'DIMENSION').length,
      measures: evidences.filter((c) => c.candidate_role === 'MEASURE').length,
    };
  }, [semanticProfile]);

  // Cleaning changes count
  const cleaningChangesCount = useMemo(() => {
    if (!cleaningReport) return 0;
    if (typeof cleaningReport.total_changes === 'number') return cleaningReport.total_changes;
    if (Array.isArray(cleaningReport.transformations)) {
      return cleaningReport.transformations.reduce((sum: number, t: any) => sum + (t.affected_count || 1), 0);
    }
    return cleaningReport.cleaned_rows_count || 0;
  }, [cleaningReport]);

  // Trigger End-to-End Pipeline Execution
  const handleRunPipeline = async (chosenPlanId?: string) => {
    if (!selectedDatasetId) return;

    abortControllerRef.current = new AbortController();
    setPipelineError(null);
    setPipelineStep('clean');

    let t1: NodeJS.Timeout | null = null;
    let t2: NodeJS.Timeout | null = null;

    try {
      t1 = setTimeout(() => {
        setPipelineStep((prev) => (prev === 'clean' ? 'understand' : prev));
      }, 350);
      t2 = setTimeout(() => {
        setPipelineStep((prev) => (prev === 'understand' ? 'propose' : prev));
      }, 750);

      const res = await runPipeline(
        selectedDatasetId,
        intent,
        'both',
        3,
        true, // require_clarification
        chosenPlanId
      );

      if (t1) clearTimeout(t1);
      if (t2) clearTimeout(t2);

      setPipelineResult(res);

      if (res.status === 'NEEDS_CLARIFICATION') {
        setPipelineStep('rank');
      } else if (res.status === 'SUCCESS' && res.winner) {
        setPipelineStep('done');
      } else if (res.status === 'UNANSWERABLE' || res.status === 'REFUSED') {
        setPipelineStep('error');
        setPipelineError(res.message || 'Pipeline could not answer intent.');
      } else {
        setPipelineStep('done');
      }
    } catch (err: any) {
      if (t1) clearTimeout(t1);
      if (t2) clearTimeout(t2);
      if (err.name === 'AbortError') {
        setPipelineStep('idle');
      } else {
        setPipelineStep('error');
        setPipelineError(err.message || 'Pipeline execution failed.');
      }
    } finally {
      abortControllerRef.current = null;
    }
  };

  // Cancel action
  const handleCancelRun = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setPipelineStep('idle');
    setElapsedSeconds(0);
  };

  // Clarification Selection Handler
  const handleSelectClarificationOption = async (chosenPlanId: string) => {
    if (pipelineResult?.run_id) {
      setPipelineStep('propose');
      setPipelineError(null);
      try {
        const resolved = await resolvePipeline(pipelineResult.run_id, chosenPlanId);
        setPipelineResult(resolved);
        if (resolved.status === 'SUCCESS' && resolved.winner) {
          setPipelineStep('done');
        } else if (resolved.status === 'NEEDS_CLARIFICATION') {
          setPipelineStep('rank');
        } else {
          setPipelineStep('done');
        }
      } catch (err: any) {
        setPipelineStep('error');
        setPipelineError(err.message || 'Pipeline resolution failed.');
      }
    } else {
      await handleRunPipeline(chosenPlanId);
    }
  };

  const isPipelineRunning = ['clean', 'understand', 'propose', 'rank', 'build'].includes(pipelineStep);

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-16 font-sans">
      {/* Page Title */}
      <div className="pb-1">
        <h1 className="text-page-title font-bold text-foreground tracking-tight">
          AI Business Intelligence Studio
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Autonomous analytical intelligence, multi-provider consensus, and verified dashboard generation.
        </p>
      </div>

      {/* --------------------------------------------------------------------- */}
      {/* CARD 1: DATASET */}
      {/* --------------------------------------------------------------------- */}
      <section
        onDragOver={(e) => {
          e.preventDefault();
          setIsDraggingFile(true);
        }}
        onDragLeave={() => setIsDraggingFile(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDraggingFile(false);
          if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
        }}
        className={`bg-surface border rounded-card p-6 shadow-xs transition-all space-y-4 ${
          isDraggingFile ? 'border-primary ring-2 ring-primary/20 bg-primary-soft/20' : 'border-border'
        }`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div className="flex items-center gap-2.5">
            <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-xs shrink-0">
              1
            </span>
            <div>
              <h2 className="text-section font-semibold text-foreground">
                Dataset
              </h2>
              <p className="text-xs text-muted-foreground">
                Ingested and normalized data structure
              </p>
            </div>
          </div>

          {/* Dataset Switcher Dropdown (Merged into Card) */}
          {datasets.length > 0 && (
            <div className="flex items-center gap-2">
              <label htmlFor="dataset-select" className="text-2xs font-mono uppercase text-muted-foreground">
                Switch Dataset:
              </label>
              <select
                id="dataset-select"
                aria-label="Active Dataset Selection"
                value={selectedDatasetId}
                onChange={(e) => selectDataset(e.target.value)}
                className="text-xs font-mono bg-surface border border-border rounded-md px-2.5 py-1 text-foreground focus-visible:ring-2 focus-visible:ring-primary focus:outline-none"
              >
                {datasets.map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.filename} ({d.row_count} rows)
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* State A: No Dataset Loaded -> Full Dropzone */}
        {!metadata ? (
          <div
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-card p-10 text-center cursor-pointer transition-all ${
              isUploading
                ? 'border-primary bg-primary-soft/30'
                : 'border-border hover:border-primary/60 bg-surface-muted/20 hover:bg-surface-muted/40'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.tsv,.xlsx,.parquet"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
              }}
            />
            <div className="flex flex-col items-center justify-center gap-2">
              <div className="p-3 bg-primary-soft text-primary rounded-full">
                <UploadCloud className="w-6 h-6 stroke-[2]" />
              </div>
              <div className="text-xs font-semibold text-foreground">
                {isUploading ? 'Ingesting, cleaning, and profiling...' : 'Drag and drop your dataset here, or click to browse'}
              </div>
              <p className="text-2xs text-muted-foreground font-mono">
                Supports CSV, TSV, Parquet, and Excel (.xlsx) up to 100MB
              </p>
            </div>
          </div>
        ) : (
          /* State B: Dataset Loaded -> Compact View with Roles & Cleaning Row */
          <div className="space-y-4">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.tsv,.xlsx,.parquet"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
              }}
            />

            {/* Header info row with Replace Button */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-surface-muted/30 rounded-card border border-border">
              <div className="flex items-center gap-3 min-w-0">
                <div className="p-2.5 bg-primary-soft text-primary rounded-md shrink-0">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-foreground truncate">
                      {metadata.filename}
                    </span>
                    <Badge variant="blue" size="xs">
                      {metadata.source_type?.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="text-xs font-mono text-muted-foreground mt-0.5">
                    {metadata.row_count.toLocaleString()} rows • {metadata.column_count} columns
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2.5 shrink-0">
                {/* Readiness Badge */}
                <div
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${
                    readiness?.status === 'READY' || readiness?.status === 'READY_WITH_WARNINGS'
                      ? 'bg-success-soft text-success border-success/30'
                      : 'bg-attention-soft text-attention border-attention/30'
                  }`}
                >
                  {readiness?.status === 'READY' || readiness?.status === 'READY_WITH_WARNINGS' ? (
                    <ShieldCheck className="w-3.5 h-3.5" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {readiness?.status === 'READY'
                      ? 'Ready for Analysis'
                      : readiness?.status === 'READY_WITH_WARNINGS'
                      ? 'Ready (With Warnings)'
                      : 'Readiness Caution'}
                  </span>
                </div>

                {/* Compact Replace dataset button */}
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => fileInputRef.current?.click()}
                  leftIcon={<UploadCloud className="w-3.5 h-3.5" />}
                >
                  Replace dataset
                </Button>
              </div>
            </div>

            {/* Inferred Roles Chips */}
            <div className="space-y-1.5">
              <span className="text-2xs font-mono uppercase text-muted-foreground tracking-wider font-semibold">
                Detected Column Roles:
              </span>
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border border-border bg-surface-muted text-foreground font-mono">
                  <TrendingUp className="w-3.5 h-3.5 text-primary shrink-0" />
                  <span>{roleSummary.measures} measure{roleSummary.measures === 1 ? '' : 's'}</span>
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border border-border bg-surface-muted text-foreground font-mono">
                  <Tag className="w-3.5 h-3.5 text-primary shrink-0" />
                  <span>{roleSummary.dimensions} dimension{roleSummary.dimensions === 1 ? '' : 's'}</span>
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border border-border bg-surface-muted text-foreground font-mono">
                  <Calendar className="w-3.5 h-3.5 text-primary shrink-0" />
                  <span>{roleSummary.datetimes} datetime</span>
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border border-border bg-surface-muted text-foreground font-mono">
                  <Key className="w-3.5 h-3.5 text-primary shrink-0" />
                  <span>{roleSummary.identifiers} identifier{roleSummary.identifiers === 1 ? '' : 's'}</span>
                </span>
              </div>
            </div>

            {/* Expandable Cleaning Row */}
            <div className="border border-border rounded-card overflow-hidden">
              <button
                onClick={() => setCleaningExpanded((p) => !p)}
                className="w-full flex items-center justify-between p-3 bg-surface-muted/20 hover:bg-surface-muted/50 transition-colors text-left"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-foreground">
                    Data Cleaning:
                  </span>
                  <span className="text-xs font-mono text-muted-foreground">
                    {cleaningChangesCount} change{cleaningChangesCount === 1 ? '' : 's'} applied
                  </span>
                </div>
                <div className="flex items-center gap-1 text-2xs text-muted-foreground">
                  <span>{cleaningExpanded ? 'Hide Report' : 'Show Report'}</span>
                  {cleaningExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </div>
              </button>

              {cleaningExpanded && (
                <div className="p-3 border-t border-border bg-surface space-y-2">
                  <div className="overflow-x-auto max-h-48">
                    <table className="w-full text-left text-xs font-mono border-collapse">
                      <thead>
                        <tr className="border-b border-border text-2xs uppercase text-muted-foreground bg-surface-muted/40">
                          <th className="py-1.5 px-2.5 font-semibold">Rule</th>
                          <th className="py-1.5 px-2.5 font-semibold">Target Column</th>
                          <th className="py-1.5 px-2.5 font-semibold text-right">Count / Details</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border text-foreground">
                        {cleaningReport?.transformations && cleaningReport.transformations.length > 0 ? (
                          cleaningReport.transformations.map((t: any, idx: number) => (
                            <tr key={idx} className="hover:bg-surface-muted/20">
                              <td className="py-1.5 px-2.5">{t.rule_name || t.type || 'Normalization'}</td>
                              <td className="py-1.5 px-2.5 font-semibold">{t.column_name || t.column || 'All'}</td>
                              <td className="py-1.5 px-2.5 text-right text-muted-foreground font-mono">
                                {t.affected_count || t.count || 1}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={3} className="py-3 px-2.5 text-center text-muted-foreground italic">
                              No type coercion or null-fill anomalies detected in this dataset.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-2xs text-muted-foreground italic font-mono pt-1">
                    Original data is preserved unchanged in the ingestion stage.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {uploadError && (
          <div className="p-3 bg-error-soft border border-error/30 rounded-card text-error text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Upload Failed: {uploadError}</span>
          </div>
        )}
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* CARD 2: BRIEF */}
      {/* --------------------------------------------------------------------- */}
      <section className="bg-surface border border-border rounded-card p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="flex items-center gap-2.5">
            <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-xs shrink-0">
              2
            </span>
            <div>
              <h2 className="text-section font-semibold text-foreground">
                Analytical Brief
              </h2>
              <p className="text-xs text-muted-foreground">
                Describe what you want to understand, analyze, or compare
              </p>
            </div>
          </div>
        </div>

        {/* Input box */}
        <div className="space-y-2">
          <div className="relative">
            <textarea
              rows={2}
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                  e.preventDefault();
                  if (!isPipelineRunning && selectedDatasetId) {
                    handleRunPipeline();
                  }
                }
              }}
              placeholder="e.g. Compare total revenue by product category, or leave empty for an automated executive dashboard overview"
              className="w-full p-3 text-xs bg-surface border border-border rounded-card text-foreground placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-primary focus:outline-none resize-none leading-relaxed"
            />
          </div>
          <div className="flex items-center justify-between text-2xs text-muted-foreground font-mono">
            <span>Press Cmd+Enter or Ctrl+Enter to generate</span>
            <span>{intent.length} characters</span>
          </div>
        </div>

        {/* Runtime Suggestion Chips (Only example text; derived purely from detected roles) */}
        {suggestionChips.length > 0 && (
          <div className="space-y-1.5 pt-1">
            <span className="text-2xs font-mono uppercase text-muted-foreground tracking-wider font-semibold">
              Suggested Briefs for this Dataset:
            </span>
            <div className="flex flex-wrap gap-2">
              {suggestionChips.map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => setIntent(chip)}
                  className="px-2.5 py-1 text-xs rounded-md border border-border bg-surface-muted/40 hover:bg-primary-soft hover:text-primary hover:border-primary/40 transition-colors text-foreground font-medium"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Action Toolbar */}
        <div className="flex items-center justify-end gap-3 pt-2">
          {isPipelineRunning && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleCancelRun}
              leftIcon={<X className="w-3.5 h-3.5" />}
            >
              Cancel
            </Button>
          )}

          <Button
            variant="primary"
            size="sm"
            onClick={() => handleRunPipeline()}
            disabled={!selectedDatasetId || isPipelineRunning}
            isLoading={isPipelineRunning}
            leftIcon={!isPipelineRunning ? <Play className="w-3.5 h-3.5" /> : undefined}
          >
            {isPipelineRunning ? `Generating… (${elapsedSeconds.toFixed(1)}s)` : 'Generate Dashboard'}
          </Button>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* CARD 3: RESULT */}
      {/* --------------------------------------------------------------------- */}
      <section className="bg-surface border border-border rounded-card p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="flex items-center gap-2.5">
            <span className="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-xs shrink-0">
              3
            </span>
            <div>
              <h2 className="text-section font-semibold text-foreground">
                Dashboard & Analytical Result
              </h2>
              <p className="text-xs text-muted-foreground">
                Multi-agent consensus winner and robustness matrix
              </p>
            </div>
          </div>

          {pipelineStep === 'done' && (
            <span className="text-xs font-mono text-success flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              <span>Complete</span>
            </span>
          )}
        </div>

        {/* Sub-state 1: Running Stepper */}
        {isPipelineRunning && (
          <div className="space-y-3 py-2">
            <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
              <span>Pipeline execution in progress</span>
              <span>Elapsed: {elapsedSeconds.toFixed(1)}s</span>
            </div>
            <PipelineStepper
              currentStep={pipelineStep}
              errorMessage={pipelineError}
              providers={providers}
            />
          </div>
        )}

        {/* Sub-state 2: Error State with Typed Backend Message and Retry */}
        {pipelineStep === 'error' && (
          <div className="p-4 bg-error-soft border border-error/30 rounded-card text-xs text-error space-y-3">
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>Pipeline Execution Failed</span>
            </div>
            <p className="font-mono text-2xs leading-relaxed opacity-95">
              {pipelineError || 'The orchestrator could not answer the brief with statistical confidence.'}
            </p>
            <div>
              <Button
                variant="outline"
                size="xs"
                onClick={() => handleRunPipeline()}
                leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
              >
                Retry Execution
              </Button>
            </div>
          </div>
        )}

        {/* Sub-state 3: Clarification Needed State */}
        {pipelineStep === 'rank' && pipelineResult?.status === 'NEEDS_CLARIFICATION' && (
          <ClarificationCard
            message={pipelineResult.message || 'Multiple candidate interpretations produced comparable confidence scores.'}
            options={pipelineResult.clarification_options || []}
            onSelectOption={handleSelectClarificationOption}
          />
        )}

        {/* Sub-state 4: Success Result State with Full DashboardPanelsView */}
        {pipelineStep === 'done' && (pipelineResult?.dashboard_spec || pipelineResult?.panels || (pipelineResult as any)?.tiles) && (
          <DashboardPanelsView
            spec={pipelineResult?.dashboard_spec || pipelineResult}
            previewData={previewData}
            cleaningReport={cleaningReport}
            providers={providers}
            onSelectCandidate={(planId) => handleRunPipeline(planId)}
          />
        )}

        {/* Sub-state 5: Empty State */}
        {pipelineStep === 'idle' && !pipelineResult && (
          <div className="py-12 px-4 text-center space-y-3 bg-surface-muted/20 rounded-card border border-dashed border-border">
            <div className="w-10 h-10 rounded-full bg-surface-muted text-muted-foreground flex items-center justify-center mx-auto">
              <Sparkles className="w-5 h-5" />
            </div>
            <div className="text-xs font-semibold text-foreground">
              No Analysis Generated Yet
            </div>
            <p className="text-2xs text-muted-foreground max-w-sm mx-auto">
              Upload a dataset in Step 1 and type an analytical brief in Step 2 to generate an automated Recharts dashboard with perturbation robustness verification.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
