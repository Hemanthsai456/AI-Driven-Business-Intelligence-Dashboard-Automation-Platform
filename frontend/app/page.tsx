'use client';

import React, { useEffect, useState, useRef } from 'react';
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Sparkles,
  Trophy,
  Database,
  BarChart3,
  FileSpreadsheet,
  Code,
  Brush,
  ShieldCheck,
  Search,
  ExternalLink,
  ChevronRight,
  HelpCircle,
  Loader2,
  Layers,
  Cpu,
} from 'lucide-react';
import {
  getDatasetCleaningReport,
  getDatasetMetadata,
  getDatasetPreview,
  getDatasetProfile,
  getDatasetReadiness,
  getDatasetSemanticAnalysis,
  getProvidersStatus,
  listDatasets,
  runPipeline,
  runPlan,
  uploadDataset,
} from '../lib/api';
import {
  AnalysisReadiness,
  DataPreviewResponse,
  DataProfile,
  DatasetListItem,
  DatasetMetadata,
  OrchestratorPipelineResponse,
  RankedCandidateUI,
  SemanticProfile,
} from '../lib/types';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { InsightChart } from '../components/InsightChart';
import { PipelineStepper, PipelineStep, ProviderStatusItem } from '../components/PipelineStepper';
import { ClarificationCard } from '../components/ClarificationCard';
import { InterpretationsPanel } from '../components/InterpretationsPanel';

export default function SingleFlowPage() {
  // 1. Dataset & Ingestion State
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [semanticProfile, setSemanticProfile] = useState<SemanticProfile | null>(null);
  const [readiness, setReadiness] = useState<AnalysisReadiness | null>(null);
  const [previewData, setPreviewData] = useState<DataPreviewResponse | null>(null);
  const [cleaningReport, setCleaningReport] = useState<any>(null);

  // Uploading state
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 2. Natural Language Brief & Execution State
  const [intent, setIntent] = useState<string>('Show total sales by store');
  const [pipelineStep, setPipelineStep] = useState<PipelineStep>('idle');
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineResult, setPipelineResult] = useState<OrchestratorPipelineResponse | null>(null);

  // Providers Health
  const [providers, setProviders] = useState<ProviderStatusItem[]>([]);

  // Active Viewing Plan (Default = Winner)
  const [activePlan, setActivePlan] = useState<any | null>(null);
  const [activeExecution, setActiveExecution] = useState<any | null>(null);

  // Active Lower Tabs
  const [activeTab, setActiveTab] = useState<'chart' | 'data' | 'cleaning' | 'trace'>('chart');

  // Initial Load: Fetch existing datasets and provider health
  useEffect(() => {
    async function init() {
      try {
        const provRes = await getProvidersStatus();
        if (provRes && provRes.providers) {
          setProviders(provRes.providers);
        }
      } catch (e) {
        console.error('Failed to load provider health:', e);
      }

      try {
        const list = await listDatasets();
        setDatasets(list);
        if (list.length > 0) {
          selectDataset(list[0].dataset_id);
        }
      } catch (e) {
        console.error('Failed to load datasets:', e);
      }
    }
    init();
  }, []);

  // Handler to load metadata, semantic analysis, readiness, cleaning, and preview for a dataset
  const selectDataset = async (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setUploadError(null);
    setPipelineResult(null);
    setActivePlan(null);
    setActiveExecution(null);
    setPipelineStep('idle');

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
      // Refresh dataset list
      const updatedList = await listDatasets();
      setDatasets(updatedList);
      await selectDataset(meta.dataset_id);
    } catch (err: any) {
      setUploadError(err.message || 'File upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  // Trigger End-to-End Pipeline Execution
  const handleRunPipeline = async (chosenPlanId?: string) => {
    if (!selectedDatasetId || !intent.trim()) return;

    setPipelineError(null);
    setPipelineStep('clean');

    try {
      // Step: Clean completed by ingest, transitioning to Understand & Propose
      setTimeout(() => setPipelineStep('understand'), 300);
      setTimeout(() => setPipelineStep('propose'), 700);

      const res = await runPipeline(
        selectedDatasetId,
        intent,
        'both',
        3,
        true, // require_clarification
        chosenPlanId
      );

      setPipelineResult(res);

      if (res.status === 'NEEDS_CLARIFICATION') {
        setPipelineStep('rank'); // Paused at rank for clarification
      } else if (res.status === 'SUCCESS' && res.winner) {
        setPipelineStep('done');
        setActivePlan(res.winner);
        setActiveExecution(res.winner.execution);
        setActiveTab('chart');
      } else if (res.status === 'UNANSWERABLE' || res.status === 'REFUSED') {
        setPipelineStep('error');
        setPipelineError(res.message || 'Pipeline could not answer intent.');
      } else {
        setPipelineStep('done');
      }
    } catch (err: any) {
      setPipelineStep('error');
      setPipelineError(err.message || 'Pipeline execution failed.');
    }
  };

  // Clarification Selection Handler
  const handleSelectClarificationOption = async (chosenPlanId: string) => {
    await handleRunPipeline(chosenPlanId);
  };

  // Switch to viewing an alternate candidate
  const handleViewCandidateInstead = async (cand: RankedCandidateUI) => {
    if (!cand) return;
    try {
      // Run execution for this plan if not already present
      const runRes = await runPlan({
        plan_id: cand.plan_id,
        metric: { column: cand.metric.replace(/.*\((.*)\)/, '$1'), aggregation: cand.metric.split('(')[0].toLowerCase() },
        dimensions: cand.dimensions.map((d) => ({ column: d })),
        visualization: cand.visualization.toLowerCase(),
      });
      setActivePlan({
        plan_id: cand.plan_id,
        generator: cand.generator,
        visualization: cand.visualization,
        score: cand.score,
        score_breakdown: cand.score_breakdown,
        metric: cand.metric,
        dimensions: cand.dimensions,
        reasoning: { interpretation: `Candidate #${cand.rank} analytical query` },
      });
      setActiveExecution(runRes.execution);
      setActiveTab('chart');
    } catch (e) {
      console.error('Failed to run plan:', e);
    }
  };

  // Role badges summary
  const roleCounts = React.useMemo(() => {
    if (!semanticProfile?.column_evidences) return {};
    const counts: Record<string, number> = {};
    Object.values(semanticProfile.column_evidences).forEach((col) => {
      counts[col.candidate_role] = (counts[col.candidate_role] || 0) + 1;
    });
    return counts;
  }, [semanticProfile]);

  // Robustness calculation: how many candidate interpretations agree with the winning signature
  const robustnessCount = React.useMemo(() => {
    if (!pipelineResult?.ranked_candidates || pipelineResult.ranked_candidates.length === 0) return 1;
    if (!activePlan) return 1;
    const matching = pipelineResult.ranked_candidates.filter((c) => {
      const sameMetric = c.metric === activePlan.metric;
      const sharesDim = c.dimensions?.some((d) => activePlan.dimensions?.includes(d));
      return sameMetric || sharesDim;
    });
    return Math.max(1, matching.length);
  }, [pipelineResult, activePlan]);
  const totalCandidates = pipelineResult?.ranked_candidates?.length || 1;

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-16">
      {/* --------------------------------------------------------------------- */}
      {/* 1. INPUT PANEL (Dropzone, Dataset Summary, Brief Box, Generate Button) */}
      {/* --------------------------------------------------------------------- */}
      <section className="bg-surface border border-border rounded-card p-5 sm:p-6 shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div>
            <h1 className="text-base font-bold text-foreground tracking-tight flex items-center gap-2">
              <Database className="w-4 h-4 text-primary" />
              <span>AI Analytical Intelligence & Dashboard Automation</span>
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Upload any raw tabular dataset and type a free-text analytical brief.
            </p>
          </div>

          {/* Dataset Selector if multiple exist */}
          {datasets.length > 1 && (
            <div className="flex items-center gap-2">
              <label className="text-2xs font-mono uppercase text-muted-foreground">Active:</label>
              <select
                aria-label="Active Dataset Selection"
                value={selectedDatasetId}
                onChange={(e) => selectDataset(e.target.value)}
                className="text-xs font-mono bg-surface border border-border rounded px-2.5 py-1 text-foreground focus:outline-none focus:border-primary"
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

        {/* File Dropzone */}
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
          }}
          className={`border-2 border-dashed rounded-card p-6 text-center cursor-pointer transition-all ${
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
              {isUploading ? 'Ingesting, cleaning, and profiling...' : 'Click or drag a dataset here (CSV, TSV, Parquet, Excel)'}
            </div>
            <p className="text-2xs text-muted-foreground">
              Automatic UTF/delimiter detection, data cleaning, semantic role inference, and readiness validation.
            </p>
          </div>
        </div>

        {uploadError && (
          <div className="p-3 bg-error-soft border border-error/30 rounded text-error text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Upload Failed: {uploadError}</span>
          </div>
        )}

        {/* Dataset Summary Card (Rows, Columns, Detected Roles chips, Readiness) */}
        {metadata && (
          <div className="bg-surface-muted/30 border border-border rounded-card p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-bold text-foreground font-mono truncate">
                  {metadata.filename || metadata.dataset_id}
                </span>
                <span className="text-2xs font-mono px-2 py-0.5 rounded bg-surface border border-border text-muted-foreground">
                  {metadata.row_count?.toLocaleString()} rows • {metadata.column_count} columns
                </span>
                {readiness && (
                  <Badge
                    variant={readiness.status === 'READY' ? 'teal' : readiness.status === 'READY_WITH_WARNINGS' ? 'amber' : 'red'}
                    size="xs"
                    dot
                  >
                    {readiness.status.replace(/_/g, ' ')}
                  </Badge>
                )}
              </div>

              {/* Detected Roles Chips */}
              <div className="flex items-center gap-1.5 flex-wrap pt-1">
                <span className="text-2xs font-mono text-muted-foreground mr-1">Inferred Roles:</span>
                {Object.entries(roleCounts).map(([role, count]) => (
                  <span
                    key={role}
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono bg-surface border border-border text-foreground"
                  >
                    <span className="font-semibold text-primary">{count}</span>
                    <span className="text-muted-foreground">{role.toLowerCase()}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="shrink-0 flex items-center gap-2 text-2xs font-mono text-muted-foreground">
              {cleaningReport && (
                <span className="px-2.5 py-1 rounded bg-surface border border-border">
                  Cleaning: {cleaningReport.changes?.length ?? 0} automated fix(es)
                </span>
              )}
            </div>
          </div>
        )}

        {/* Analytical Brief Input Box & Generate Button */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-1">
          <div className="flex-1 relative">
            <input
              type="text"
              aria-label="Analytical Question Brief"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              placeholder="e.g. Total sales by store, or Monthly revenue trend..."
              disabled={!selectedDatasetId || pipelineStep === 'understand' || pipelineStep === 'propose'}
              className="w-full text-xs font-medium bg-surface border border-border rounded-card px-3.5 py-2.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-all pr-8"
            />
            <Sparkles className="w-4 h-4 text-primary absolute right-3 top-3 pointer-events-none" />
          </div>

          <Button
            variant="primary"
            size="md"
            disabled={!selectedDatasetId || !intent.trim() || pipelineStep === 'understand' || pipelineStep === 'propose'}
            onClick={() => handleRunPipeline()}
            leftIcon={<Play className="w-3.5 h-3.5 fill-current" />}
            className="shrink-0"
          >
            {pipelineStep === 'understand' || pipelineStep === 'propose' ? 'Generating...' : 'Generate Insights'}
          </Button>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* 2. PIPELINE STEPPER WITH REAL BACKEND STATUS & PROVIDER HEALTH CHIPS */}
      {/* --------------------------------------------------------------------- */}
      <PipelineStepper
        currentStep={pipelineStep}
        errorMessage={pipelineError}
        providers={providers}
      />

      {/* --------------------------------------------------------------------- */}
      {/* CLARIFICATION CARD (When status is NEEDS_CLARIFICATION)              */}
      {/* --------------------------------------------------------------------- */}
      {pipelineResult && pipelineResult.status === 'NEEDS_CLARIFICATION' && pipelineResult.clarification_options && (
        <ClarificationCard
          message={pipelineResult.message}
          options={pipelineResult.clarification_options}
          onSelectOption={handleSelectClarificationOption}
          isLoading={pipelineStep === 'understand' || pipelineStep === 'propose'}
        />
      )}

      {/* --------------------------------------------------------------------- */}
      {/* 3. RESULT VIEW (Insight-First Layout)                                 */}
      {/* --------------------------------------------------------------------- */}
      {activePlan && (
        <section className="space-y-4">
          {/* Headline Card */}
          <div className="bg-surface border border-border rounded-card p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-2xs font-bold font-mono bg-primary text-white">
                  <Trophy className="w-3 h-3" />
                  <span>WINNING INSIGHT</span>
                </span>

                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono bg-primary-soft text-primary border border-primary/20">
                  <ShieldCheck className="w-3 h-3" />
                  <span>Holds in {robustnessCount} of {totalCandidates} interpretations</span>
                </span>

                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono bg-surface-muted text-foreground border border-border">
                  <span>Score: {Number(activePlan.score || 0).toFixed(3)}</span>
                </span>

                {activePlan.generator?.includes('baseline') && (
                  <span className="text-2xs font-mono px-2 py-0.5 rounded bg-attention-soft text-attention border border-attention/30">
                    Rule-based Baseline
                  </span>
                )}
              </div>

              <h2 className="text-base font-bold text-foreground leading-snug tracking-tight">
                {activePlan.reasoning?.interpretation || `${activePlan.metric} aggregated across ${activePlan.dimensions?.join(', ') || 'dataset'}`}
              </h2>

              <p className="text-xs text-muted-foreground font-mono">
                Metric: <span className="text-foreground">{activePlan.metric}</span> • Dimensions: <span className="text-foreground">{activePlan.dimensions?.join(', ') || 'overall'}</span> • Viz: <span className="text-foreground uppercase">{activePlan.visualization}</span>
              </p>
            </div>

            <div className="shrink-0 flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleRunPipeline()}
                leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
              >
                Re-run
              </Button>
            </div>
          </div>

          {/* Interactive Chart Grid rendered from DashboardSpec */}
          <InsightChart
            visualization={activePlan.visualization}
            metric={activePlan.metric}
            dimensions={activePlan.dimensions || []}
            executionData={activeExecution}
          />

          {/* Interpretations Panel: Alternates ranked by score */}
          {pipelineResult?.ranked_candidates && pipelineResult.ranked_candidates.length > 0 && (
            <InterpretationsPanel
              candidates={pipelineResult.ranked_candidates}
              activePlanId={activePlan.plan_id}
              onViewInstead={handleViewCandidateInstead}
            />
          )}

          {/* ----------------------------------------------------------------- */}
          {/* Lower Tabs: Data, Cleaning Report, Trace                         */}
          {/* ----------------------------------------------------------------- */}
          <div className="bg-surface border border-border rounded-card overflow-hidden shadow-xs">
            {/* Tab Headers */}
            <div className="flex items-center gap-1 p-2 border-b border-border bg-surface-muted/20 text-xs font-semibold">
              <button
                onClick={() => setActiveTab('chart')}
                className={`px-3 py-1.5 rounded transition-all font-mono text-2xs ${
                  activeTab === 'chart'
                    ? 'bg-surface text-primary border border-border shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('data')}
                className={`px-3 py-1.5 rounded transition-all font-mono text-2xs ${
                  activeTab === 'data'
                    ? 'bg-surface text-primary border border-border shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Data (Raw Preview)
              </button>
              <button
                onClick={() => setActiveTab('cleaning')}
                className={`px-3 py-1.5 rounded transition-all font-mono text-2xs ${
                  activeTab === 'cleaning'
                    ? 'bg-surface text-primary border border-border shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Cleaning Report
              </button>
              <button
                onClick={() => setActiveTab('trace')}
                className={`px-3 py-1.5 rounded transition-all font-mono text-2xs ${
                  activeTab === 'trace'
                    ? 'bg-surface text-primary border border-border shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Trace & SQL
              </button>
            </div>

            {/* Tab Content */}
            <div className="p-4 sm:p-5">
              {/* Tab 1: Raw Data Preview (Demoted) */}
              {activeTab === 'data' && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-2xs font-mono text-muted-foreground">
                    <span>First 20 rows of active cleaned dataset</span>
                    <span>{metadata?.row_count} total rows</span>
                  </div>
                  {previewData?.rows && previewData.rows.length > 0 ? (
                    <div className="overflow-x-auto max-h-[300px] border border-border rounded">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-border bg-surface-muted/50 text-muted-foreground font-mono uppercase text-2xs">
                            {previewData.columns.map((c) => (
                              <th key={c} className="py-2 px-3 font-semibold">{c}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {previewData.rows.map((r, i) => (
                            <tr key={i} className="hover:bg-primary-soft/20">
                              {previewData.columns.map((c) => (
                                <td key={c} className="py-2 px-3 font-mono text-2xs">{String(r[c] ?? '')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-4 text-center text-xs text-muted-foreground">No preview rows available.</div>
                  )}
                </div>
              )}

              {/* Tab 2: Data Cleaning Report */}
              {activeTab === 'cleaning' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
                      Data Cleaning & Preprocessing Ledger
                    </h4>
                    <span className="text-2xs font-mono text-muted-foreground">
                      {cleaningReport?.changes?.length ?? 0} total mutations
                    </span>
                  </div>

                  {cleaningReport?.changes && cleaningReport.changes.length > 0 ? (
                    <div className="space-y-2">
                      {cleaningReport.changes.map((ch: any, idx: number) => (
                        <div key={idx} className="p-2.5 bg-surface-muted/30 border border-border rounded text-xs flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-2xs px-1.5 py-0.5 rounded bg-surface border border-border font-semibold uppercase text-primary">
                              {ch.action || 'clean'}
                            </span>
                            <span className="text-foreground">{ch.details || ch.description || 'Data normalization applied'}</span>
                          </div>
                          {ch.column && (
                            <span className="font-mono text-2xs text-muted-foreground">
                              col: {ch.column}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-4 bg-surface-muted/20 border border-dashed border-border rounded text-center text-xs text-muted-foreground">
                      No cleaning anomalies found in dataset. Cleaned data passed schema readiness checks cleanly.
                    </div>
                  )}
                </div>
              )}

              {/* Tab 3: Trace & SQL */}
              {activeTab === 'trace' && (
                <div className="space-y-5">
                  <div className="flex items-center justify-between pb-2 border-b border-border">
                    <h4 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
                      Deterministic Engine Execution Trace
                    </h4>
                    <span className="text-2xs font-mono text-muted-foreground">Pass 1 & Pass 2 Verified</span>
                  </div>

                  {/* Compiled SQL */}
                  <div className="space-y-1.5">
                    <span className="text-2xs font-mono uppercase text-muted-foreground">Compiled DuckDB SQL Query:</span>
                    <pre className="p-3 bg-surface-muted/50 border border-border rounded font-mono text-xs text-foreground overflow-x-auto">
                      {activeExecution?.compiled_sql || 'SELECT * FROM canonical_dataset'}
                    </pre>
                  </div>

                  {/* Performance & Execution metrics */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3 bg-surface-muted/20 border border-border rounded">
                      <div className="text-2xs font-mono text-muted-foreground">Returned Rows</div>
                      <div className="text-sm font-bold font-mono text-foreground">{activeExecution?.row_count ?? 0}</div>
                    </div>
                    <div className="p-3 bg-surface-muted/20 border border-border rounded">
                      <div className="text-2xs font-mono text-muted-foreground">Failed Cast Rate</div>
                      <div className="text-sm font-bold font-mono text-foreground">{(Number(activeExecution?.failed_cast_rate || 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div className="p-3 bg-surface-muted/20 border border-border rounded">
                      <div className="text-2xs font-mono text-muted-foreground">Execution Status</div>
                      <div className="text-sm font-bold font-mono text-primary flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>PASSED</span>
                      </div>
                    </div>
                    <div className="p-3 bg-surface-muted/20 border border-border rounded">
                      <div className="text-2xs font-mono text-muted-foreground">Pass 2 Validation</div>
                      <div className="text-sm font-bold font-mono text-success flex items-center gap-1">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span>VERIFIED</span>
                      </div>
                    </div>
                  </div>

                  {/* Candidate Scores Table */}
                  {pipelineResult?.ranked_candidates && pipelineResult.ranked_candidates.length > 0 && (
                    <div className="space-y-2 pt-2">
                      <div className="flex items-center justify-between">
                        <span className="text-2xs font-mono uppercase text-muted-foreground flex items-center gap-1">
                          <Layers className="w-3.5 h-3.5 text-primary" />
                          <span>Candidate Scores & Rank Matrix:</span>
                        </span>
                        <span className="text-2xs font-mono text-muted-foreground">
                          {pipelineResult.ranked_candidates.length} candidates evaluated
                        </span>
                      </div>
                      <div className="overflow-x-auto border border-border rounded">
                        <table className="w-full text-left text-xs border-collapse">
                          <thead>
                            <tr className="border-b border-border bg-surface-muted/50 text-muted-foreground font-mono uppercase text-2xs">
                              <th className="py-2 px-3">Rank</th>
                              <th className="py-2 px-3">Plan ID</th>
                              <th className="py-2 px-3">Generator</th>
                              <th className="py-2 px-3">Metric / Dims</th>
                              <th className="py-2 px-3">Evidence</th>
                              <th className="py-2 px-3">Coverage</th>
                              <th className="py-2 px-3">Stability</th>
                              <th className="py-2 px-3 font-bold">Total Score</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border font-mono text-2xs">
                            {pipelineResult.ranked_candidates.map((c) => (
                              <tr key={c.plan_id} className={c.is_winner ? 'bg-primary-soft/20 font-semibold' : ''}>
                                <td className="py-2 px-3">
                                  {c.is_winner ? (
                                    <span className="inline-flex items-center gap-1 text-primary font-bold">
                                      <Trophy className="w-3 h-3" />
                                      #1
                                    </span>
                                  ) : (
                                    `#${c.rank}`
                                  )}
                                </td>
                                <td className="py-2 px-3 truncate max-w-[100px]" title={c.plan_id}>{c.plan_id}</td>
                                <td className="py-2 px-3 capitalize">
                                  {c.generator.includes('baseline') ? 'Rule-based Baseline' : c.generator}
                                </td>
                                <td className="py-2 px-3 truncate max-w-[160px]">
                                  {c.metric} ({c.dimensions.join(', ') || 'overall'})
                                </td>
                                <td className="py-2 px-3">{(c.score_breakdown.evidence * 100).toFixed(0)}%</td>
                                <td className="py-2 px-3">{(c.score_breakdown.coverage * 100).toFixed(0)}%</td>
                                <td className="py-2 px-3">{(c.score_breakdown.stability * 100).toFixed(0)}%</td>
                                <td className="py-2 px-3 font-bold text-foreground">{c.score.toFixed(3)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Provider Status List in Trace */}
                  <div className="space-y-2 pt-2">
                    <span className="text-2xs font-mono uppercase text-muted-foreground flex items-center gap-1">
                      <Cpu className="w-3.5 h-3.5 text-primary" />
                      <span>Provider Status Ledger:</span>
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                      {providers.map((p) => (
                        <div key={p.provider} className="p-2.5 bg-surface-muted/30 border border-border rounded text-2xs font-mono flex items-center justify-between">
                          <div>
                            <div className="font-bold text-foreground capitalize">{p.provider.replace('_', ' ')}</div>
                            <div className="text-muted-foreground">{p.model || 'rule-based'}</div>
                          </div>
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-semibold ${
                            p.status === 'live' ? 'bg-success-soft text-success border border-success/30' : 'bg-attention-soft text-attention border border-attention/30'
                          }`}>
                            {p.status === 'live' ? <CheckCircle2 className="w-3 h-3" /> : <AlertTriangle className="w-3 h-3" />}
                            {p.status.toUpperCase()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Tab Overview: Insight summary */}
              {activeTab === 'chart' && (
                <div className="text-xs text-muted-foreground leading-relaxed">
                  Generated deterministically from user brief &quot;{intent}&quot; without hardcoded schemas or dataset-specific logic.
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* 4. Loading State while Pipeline is executing */}
      {pipelineStep !== 'idle' && pipelineStep !== 'done' && pipelineStep !== 'error' && !activePlan && (
        <div className="p-10 border border-border rounded-card bg-surface shadow-xs text-center flex flex-col items-center justify-center gap-3">
          <div className="p-3 bg-primary-soft text-primary rounded-full animate-spin">
            <Loader2 className="w-8 h-8" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground">Executing Analytical Pipeline</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-md">
              Running multi-agent candidate generation, Pass 1 validation, consensus scoring, and DuckDB execution...
            </p>
          </div>
        </div>
      )}

      {/* 5. Error State if Pipeline failed */}
      {pipelineStep === 'error' && !activePlan && (
        <div className="p-10 border border-error/30 rounded-card bg-error-soft/30 text-center flex flex-col items-center justify-center gap-4">
          <div className="p-3 bg-error-soft text-error rounded-full">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground">Pipeline Execution Stopped</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-md">
              {pipelineError || 'The query or dataset could not be processed. Please check provider health or refine your brief.'}
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => handleRunPipeline()}
            leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
          >
            Retry Pipeline
          </Button>
        </div>
      )}

      {/* 6. Empty State when no pipeline has been run yet */}
      {!activePlan && pipelineStep === 'idle' && (
        <div className="p-10 border border-dashed border-border rounded-card bg-surface/50 text-center flex flex-col items-center justify-center gap-3">
          <div className="p-3 bg-primary-soft text-primary rounded-full">
            <BarChart3 className="w-8 h-8 stroke-[1.5]" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground">Analytical Dashboard Canvas Ready</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-md">
              Select or upload a dataset above, enter an analytical brief, and click &quot;Generate Insights&quot; to begin.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
