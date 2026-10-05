'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  SlidersHorizontal,
  Database,
  UploadCloud,
  Play,
  RotateCcw,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  FileSpreadsheet,
  Table,
  BarChart3,
  Activity,
  Sparkle,
} from 'lucide-react';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import {
  getDatasetMetadata,
  getDatasetPreview,
  getDatasetProfile,
  getDatasetSemanticAnalysis,
  getDatasetReadiness,
  getDatasetQualityAssessment,
  getDatasetCleaningPlan,
  listDatasets,
} from '../../lib/api';
import {
  AnalysisReadiness,
  CleaningPlan,
  DataPreviewResponse,
  DataProfile,
  DatasetListItem,
  DatasetMetadata,
  QualityAssessment,
  SemanticProfile,
} from '../../lib/types';
import { OverviewTab } from '../../components/data_studio/OverviewTab';
import { QualityTab } from '../../components/data_studio/QualityTab';
import { ProfilingTab } from '../../components/data_studio/ProfilingTab';
import { CleaningTab } from '../../components/data_studio/CleaningTab';

type DataStudioTab = 'overview' | 'quality' | 'profiling' | 'cleaning' | 'eda';
type AnalysisState = 'idle' | 'analyzing' | 'ready' | 'error';

function DataStudioContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const datasetIdParam = searchParams.get('id');
  const initialTabParam = searchParams.get('tab') as DataStudioTab | null;

  // 1. Dataset Selection State
  const [allDatasets, setAllDatasets] = useState<DatasetListItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [loadingDatasets, setLoadingDatasets] = useState<boolean>(true);

  // 2. Active Tab State
  const [activeTab, setActiveTab] = useState<DataStudioTab>(
    initialTabParam && ['overview', 'quality', 'profiling', 'cleaning', 'eda'].includes(initialTabParam)
      ? initialTabParam
      : 'overview'
  );

  // 3. Analysis Lifecycle State
  const [analysisState, setAnalysisState] = useState<AnalysisState>('idle');
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // 4. Dataset Intelligence State
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [preview, setPreview] = useState<DataPreviewResponse | null>(null);
  const [profile, setProfile] = useState<DataProfile | null>(null);
  const [semanticProfile, setSemanticProfile] = useState<SemanticProfile | null>(null);
  const [readiness, setReadiness] = useState<AnalysisReadiness | null>(null);
  const [qualityAssessment, setQualityAssessment] = useState<QualityAssessment | null>(null);
  const [cleaningPlan, setCleaningPlan] = useState<CleaningPlan | null>(null);
  const [loadingPlan, setLoadingPlan] = useState<boolean>(false);
  const [planError, setPlanError] = useState<string | null>(null);

  // Load registered datasets list on initial mount
  useEffect(() => {
    listDatasets()
      .then((items) => {
        setAllDatasets(items);
        if (items.length > 0) {
          const targetId =
            datasetIdParam && items.some((d) => d.dataset_id === datasetIdParam)
              ? datasetIdParam
              : items[0].dataset_id;
          setSelectedDatasetId(targetId);
        }
      })
      .catch((err) => {
        console.error('Failed to list datasets:', err);
      })
      .finally(() => {
        setLoadingDatasets(false);
      });
  }, [datasetIdParam]);

  // Sync tab change with URL search param
  const handleTabChange = (tab: DataStudioTab) => {
    setActiveTab(tab);
    const params = new URLSearchParams(window.location.search);
    params.set('tab', tab);
    if (selectedDatasetId) {
      params.set('id', selectedDatasetId);
    }
    router.replace(`/data-studio?${params.toString()}`);
  };

  // Dedicated cleaning plan fetch handler (supports retry and on-demand load)
  const fetchCleaningPlan = async (datasetId: string) => {
    if (!datasetId) return;
    setLoadingPlan(true);
    setPlanError(null);
    try {
      const plan = await getDatasetCleaningPlan(datasetId);
      setCleaningPlan(plan);
    } catch (err: any) {
      console.error('Failed to fetch cleaning plan:', err);
      setPlanError(err.message || 'Failed to generate cleaning plan.');
    } finally {
      setLoadingPlan(false);
    }
  };

  // Handle Dataset Switching
  const handleDatasetChange = (newDatasetId: string) => {
    setSelectedDatasetId(newDatasetId);
    setAnalysisState('idle');
    setAnalysisError(null);
    setMetadata(null);
    setPreview(null);
    setProfile(null);
    setSemanticProfile(null);
    setReadiness(null);
    setQualityAssessment(null);
    setCleaningPlan(null);
    setPlanError(null);
    setLoadingPlan(false);

    const params = new URLSearchParams(window.location.search);
    params.set('id', newDatasetId);
    params.set('tab', activeTab);
    router.replace(`/data-studio?${params.toString()}`);
  };

  // Explicit "Analyze Data" Execution Trigger
  const handleAnalyzeData = async () => {
    if (!selectedDatasetId) return;

    setAnalysisState('analyzing');
    setAnalysisError(null);
    setLoadingPlan(true);
    setPlanError(null);

    try {
      const [meta, prev, prof, sem, read, qual, planRes] = await Promise.all([
        getDatasetMetadata(selectedDatasetId),
        getDatasetPreview(selectedDatasetId, 50),
        getDatasetProfile(selectedDatasetId),
        getDatasetSemanticAnalysis(selectedDatasetId),
        getDatasetReadiness(selectedDatasetId),
        getDatasetQualityAssessment(selectedDatasetId).catch(() => null),
        getDatasetCleaningPlan(selectedDatasetId)
          .then((p) => ({ plan: p, error: null }))
          .catch((e: any) => ({ plan: null, error: e.message || 'Failed to generate cleaning plan.' })),
      ]);

      setMetadata(meta);
      setPreview(prev);
      setProfile(prof);
      setSemanticProfile(sem);
      setReadiness(read);
      setQualityAssessment(qual);
      setCleaningPlan(planRes.plan);
      setPlanError(planRes.error);
      setLoadingPlan(false);
      setAnalysisState('ready');
    } catch (err: any) {
      console.error('Error during Data Studio analysis:', err);
      setAnalysisError(err.message || 'Failed to analyze dataset.');
      setLoadingPlan(false);
      setAnalysisState('error');
    }
  };

  // Loading initial dataset listing
  if (loadingDatasets) {
    return (
      <div className="flex flex-col items-center justify-center p-20 space-y-3">
        <svg className="animate-spin w-6 h-6 text-primary" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span className="text-xs font-mono text-muted-foreground">
          Loading Data Studio workspace...
        </span>
      </div>
    );
  }

  // Empty State: No Datasets Uploaded in session
  if (allDatasets.length === 0) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-border">
          <div className="p-2.5 bg-primary-soft border border-primary/20 rounded-lg text-primary shrink-0">
            <SlidersHorizontal className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-foreground">Data Studio</h1>
              <Badge variant="blue" size="xs">Workspace</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Dataset readiness, health, profiling, quality assessment, and data preparation.
            </p>
          </div>
        </div>

        <Card className="p-12 text-center space-y-4 max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-full bg-primary-soft border border-primary/20 flex items-center justify-center mx-auto text-primary">
            <Database className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm font-bold text-foreground">No Datasets Available</h2>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              Upload a dataset to begin inspecting health, profiling statistics, and preparing your data in Data Studio.
            </p>
          </div>
          <Link href="/upload">
            <Button variant="primary" size="sm" leftIcon={<UploadCloud className="w-3.5 h-3.5" />}>
              Upload Dataset
            </Button>
          </Link>
        </Card>
      </div>
    );
  }

  const currentDataset = allDatasets.find((d) => d.dataset_id === selectedDatasetId) || allDatasets[0];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Workspace Header & Dataset Selector Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-primary-soft border border-primary/20 rounded-lg text-primary shrink-0 shadow-xs">
            <SlidersHorizontal className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-foreground">Data Studio</h1>
              <Badge variant="blue" size="xs">Workspace</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Inspect dataset health, comprehensive profiling, quality assessment, and data preparation.
            </p>
          </div>
        </div>

        {/* Dataset Selector & Analyze Data Trigger */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2 bg-surface border border-border rounded-md px-3 py-1.5 shadow-2xs">
            <Database className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            <select
              id="dataset-selector"
              value={selectedDatasetId}
              onChange={(e) => handleDatasetChange(e.target.value)}
              className="text-xs bg-transparent text-foreground focus:outline-none font-medium cursor-pointer max-w-xs truncate"
            >
              {allDatasets.map((ds) => (
                <option key={ds.dataset_id} value={ds.dataset_id}>
                  {ds.filename} ({ds.row_count.toLocaleString()} rows)
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="primary"
            size="sm"
            onClick={handleAnalyzeData}
            isLoading={analysisState === 'analyzing'}
            leftIcon={
              analysisState === 'ready' ? (
                <RotateCcw className="w-3.5 h-3.5" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )
            }
          >
            {analysisState === 'ready' ? 'Re-analyze Data' : 'Analyze Data'}
          </Button>

          <Link href={`/analysis?id=${selectedDatasetId}`}>
            <Button variant="secondary" size="sm" leftIcon={<BarChart3 className="w-3.5 h-3.5" />}>
              Analysis Workspace
            </Button>
          </Link>
        </div>
      </div>

      {/* Selected Dataset Summary Card */}
      {currentDataset && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-surface-muted/50 border border-border rounded-lg text-xs">
          <div className="flex items-center gap-2 font-mono">
            <FileSpreadsheet className="w-4 h-4 text-primary" />
            <span className="font-semibold text-foreground">{currentDataset.filename}</span>
            <Badge variant="slate" size="xs">
              {currentDataset.source_type?.toUpperCase()}
            </Badge>
          </div>
          <div className="flex items-center gap-4 text-muted-foreground font-mono">
            <span>
              Rows: <strong className="text-foreground">{currentDataset.row_count.toLocaleString()}</strong>
            </span>
            <span>
              Columns: <strong className="text-foreground">{currentDataset.column_count}</strong>
            </span>
            <span>
              ID: <strong className="text-foreground">{currentDataset.dataset_id.slice(0, 14)}...</strong>
            </span>
            {metadata && readiness && (
              <span className="flex items-center gap-1">
                Readiness:
                <Badge
                  variant={
                    readiness.status === 'READY'
                      ? 'green'
                      : readiness.status === 'READY_WITH_WARNINGS'
                      ? 'amber'
                      : 'red'
                  }
                  size="xs"
                >
                  {readiness.status}
                </Badge>
              </span>
            )}
            {qualityAssessment && (
              <span className="flex items-center gap-1">
                Quality:
                <Badge
                  variant={
                    qualityAssessment.status === 'Good'
                      ? 'green'
                      : qualityAssessment.status === 'Needs Attention'
                      ? 'amber'
                      : 'red'
                  }
                  size="xs"
                >
                  {qualityAssessment.status}
                </Badge>
              </span>
            )}
          </div>
        </div>
      )}

      {/* State Machine Views */}

      {/* 1. IDLE State */}
      {analysisState === 'idle' && (
        <Card className="p-10 text-center space-y-4 border-dashed border-2 max-w-xl mx-auto">
          <div className="w-12 h-12 rounded-full bg-primary-soft border border-primary/20 flex items-center justify-center mx-auto text-primary">
            <Play className="w-5 h-5 ml-0.5" />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-sm font-bold text-foreground">
              Ready to Inspect {currentDataset.filename}
            </h2>
            <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
              Click <strong className="text-foreground font-semibold">Analyze Data</strong> to activate the Data Studio workspace. This will profile distributions, assess data quality, and initialize the preparation workspace.
            </p>
          </div>
          <div className="pt-2">
            <Button
              variant="primary"
              size="md"
              onClick={handleAnalyzeData}
              leftIcon={<Sparkles className="w-4 h-4" />}
            >
              Analyze Data
            </Button>
          </div>
        </Card>
      )}

      {/* 2. ANALYZING State */}
      {analysisState === 'analyzing' && (
        <Card className="p-12 text-center space-y-4 max-w-lg mx-auto">
          <div className="w-10 h-10 mx-auto text-primary">
            <svg className="animate-spin w-10 h-10" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
          <div className="space-y-1">
            <h2 className="text-sm font-bold text-foreground">Analyzing Dataset in Data Studio</h2>
            <p className="text-xs text-muted-foreground font-mono">
              Running deterministic profiling, schema validation, and quality assessment...
            </p>
          </div>
        </Card>
      )}

      {/* 3. ERROR State */}
      {analysisState === 'error' && (
        <Card className="p-8 text-center space-y-3 max-w-lg mx-auto border-rose-500/20 bg-rose-500/5">
          <div className="w-10 h-10 rounded-full bg-rose-500/10 text-rose-500 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <h2 className="text-sm font-bold text-foreground">Analysis Failed</h2>
          <p className="text-xs text-muted-foreground">{analysisError}</p>
          <Button variant="secondary" size="sm" onClick={handleAnalyzeData}>
            Retry Analysis
          </Button>
        </Card>
      )}

      {/* 4. READY State (Tabs & Content) */}
      {analysisState === 'ready' && metadata && (
        <div className="space-y-6">
          {/* First-Class Data Studio Tab Navigation */}
          <div className="flex items-center gap-1 border-b border-border overflow-x-auto pb-px">
            <button
              onClick={() => handleTabChange('overview')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-t-md transition-colors border-b-2 ${
                activeTab === 'overview'
                  ? 'border-primary text-primary bg-surface'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-surface-muted/50'
              }`}
            >
              <Table className="w-3.5 h-3.5" />
              <span>Overview</span>
            </button>

            <button
              onClick={() => handleTabChange('quality')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-t-md transition-colors border-b-2 ${
                activeTab === 'quality'
                  ? 'border-primary text-primary bg-surface'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-surface-muted/50'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Quality</span>
              {qualityAssessment && (
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    qualityAssessment.status === 'Good'
                      ? 'bg-emerald-500'
                      : qualityAssessment.status === 'Needs Attention'
                      ? 'bg-amber-500'
                      : 'bg-rose-500'
                  }`}
                />
              )}
            </button>

            <button
              onClick={() => handleTabChange('profiling')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-t-md transition-colors border-b-2 ${
                activeTab === 'profiling'
                  ? 'border-primary text-primary bg-surface'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-surface-muted/50'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Profiling</span>
            </button>

            <button
              onClick={() => handleTabChange('cleaning')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-t-md transition-colors border-b-2 ${
                activeTab === 'cleaning'
                  ? 'border-primary text-primary bg-surface'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-surface-muted/50'
              }`}
            >
              <Sparkle className="w-3.5 h-3.5" />
              <span>Cleaning</span>
            </button>

            <button
              onClick={() => handleTabChange('eda')}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-t-md transition-colors border-b-2 ${
                activeTab === 'eda'
                  ? 'border-primary text-primary bg-surface'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-surface-muted/50'
              }`}
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span>EDA</span>
            </button>
          </div>

          {/* Tab Content Panels */}
          <div>
            {/* Tab 1: Overview */}
            {activeTab === 'overview' && (
              <OverviewTab
                metadata={metadata}
                profile={profile}
                semanticProfile={semanticProfile}
                readiness={readiness}
                qualityAssessment={qualityAssessment}
                preview={preview}
              />
            )}

            {/* Tab 2: Quality */}
            {activeTab === 'quality' && (
              <QualityTab
                metadata={metadata}
                profile={profile}
                semanticProfile={semanticProfile}
                readiness={readiness}
                qualityAssessment={qualityAssessment}
              />
            )}

            {/* Tab 3: Profiling */}
            {activeTab === 'profiling' && (
              <ProfilingTab
                metadata={metadata}
                profile={profile}
                semanticProfile={semanticProfile}
                qualityAssessment={qualityAssessment}
              />
            )}

            {/* Tab 4: Cleaning Plan */}
            {activeTab === 'cleaning' && (
              <CleaningTab
                metadata={metadata}
                cleaningPlan={cleaningPlan}
                semanticProfile={semanticProfile}
                qualityAssessment={qualityAssessment}
                isLoadingPlan={loadingPlan}
                planError={planError}
                onRetryPlan={() => fetchCleaningPlan(selectedDatasetId)}
              />
            )}

            {/* Tab 5: EDA Placeholder (Part 7) */}
            {activeTab === 'eda' && (
              <Card className="p-10 text-center space-y-3">
                <div className="w-12 h-12 rounded-full bg-primary-soft border border-primary/20 flex items-center justify-center mx-auto text-primary">
                  <BarChart3 className="w-6 h-6" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-center gap-2">
                    <h3 className="text-sm font-bold text-foreground">Exploratory Data Analysis (EDA)</h3>
                    <Badge variant="blue" size="xs">Coming in Part 7</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
                    Deterministic correlation analysis, univariate and bivariate distributions, statistical outliers, and interactive column exploration.
                  </p>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DataStudioPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-xs text-muted-foreground font-mono">
          Loading Data Studio...
        </div>
      }
    >
      <DataStudioContent />
    </Suspense>
  );
}
