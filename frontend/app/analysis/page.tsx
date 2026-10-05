'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { DatasetOverview } from '../../components/DatasetOverview';
import { DataPreviewTable } from '../../components/DataPreviewTable';
import { ProfileTab } from '../../components/ProfileTab';
import { SemanticTab } from '../../components/SemanticTab';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import {
  getDatasetMetadata,
  getDatasetPreview,
  getDatasetProfile,
  getDatasetSemanticAnalysis,
  getDatasetReadiness,
  listDatasets,
} from '../../lib/api';
import {
  AnalysisReadiness,
  DataPreviewResponse,
  DataProfile,
  DatasetListItem,
  DatasetMetadata,
  SemanticProfile,
} from '../../lib/types';
import {
  Table,
  BarChart3,
  Brain,
  UploadCloud,
  Database,
  Sparkles,
} from 'lucide-react';

function AnalysisContent() {
  const searchParams = useSearchParams();
  const datasetIdParam = searchParams.get('id');
  const initialTab = searchParams.get('tab') as 'preview' | 'profile' | 'semantic' | null;

  const [activeDatasetId, setActiveDatasetId] = useState<string | null>(datasetIdParam);
  const [allDatasets, setAllDatasets] = useState<DatasetListItem[]>([]);

  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [preview, setPreview] = useState<DataPreviewResponse | null>(null);
  const [profile, setProfile] = useState<DataProfile | null>(null);
  const [semanticProfile, setSemanticProfile] = useState<SemanticProfile | null>(null);
  const [readiness, setReadiness] = useState<AnalysisReadiness | null>(null);

  const [activeTab, setActiveTab] = useState<'preview' | 'profile' | 'semantic'>('preview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialTab && ['preview', 'profile', 'semantic'].includes(initialTab)) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  useEffect(() => {
    listDatasets()
      .then((items) => {
        setAllDatasets(items);
        if (!datasetIdParam && items.length > 0) {
          setActiveDatasetId(items[0].dataset_id);
        }
      })
      .catch((err) => console.error('Failed to list datasets:', err));
  }, [datasetIdParam]);

  useEffect(() => {
    if (!activeDatasetId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    Promise.all([
      getDatasetMetadata(activeDatasetId),
      getDatasetPreview(activeDatasetId, 50),
      getDatasetProfile(activeDatasetId),
      getDatasetSemanticAnalysis(activeDatasetId),
      getDatasetReadiness(activeDatasetId),
    ])
      .then(([meta, prev, prof, sem, read]) => {
        setMetadata(meta);
        setPreview(prev);
        setProfile(prof);
        setSemanticProfile(sem);
        setReadiness(read);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to fetch dataset analysis from engine.');
      })
      .finally(() => setLoading(false));
  }, [activeDatasetId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-16 space-y-3">
        <svg className="animate-spin w-6 h-6 text-primary" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span className="text-xs font-mono text-muted-foreground">
          Loading statistical profile & semantic intelligence...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <Card className="max-w-xl mx-auto p-6 text-center space-y-4">
        <div className="text-rose-700 font-bold text-sm">Failed to Load Dataset</div>
        <p className="text-xs text-muted-foreground">{error}</p>
        <Link href="/upload">
          <Button variant="primary" size="sm">Upload Dataset</Button>
        </Link>
      </Card>
    );
  }

  if (!metadata || !activeDatasetId) {
    return (
      <Card className="max-w-md mx-auto p-8 text-center space-y-4">
        <Database className="w-10 h-10 text-muted-foreground mx-auto" />
        <div className="text-sm font-bold text-foreground">No Dataset Selected</div>
        <p className="text-xs text-muted-foreground">
          Upload a structured dataset to inspect column distributions and semantic roles.
        </p>
        <Link href="/upload">
          <Button variant="primary" size="sm" leftIcon={<UploadCloud className="w-3.5 h-3.5" />}>
            Upload Dataset
          </Button>
        </Link>
      </Card>
    );
  }

  const missingnessPct = profile?.dataset_summary?.overall_missing_percentage ?? 0;
  const duplicateRows = profile?.dataset_summary?.duplicate_row_count ?? 0;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Workspace Header Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-soft border border-primary/20 rounded-md text-primary shrink-0">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-foreground truncate max-w-sm sm:max-w-md">
                {metadata.filename}
              </h1>
              <Badge variant="blue" size="xs">
                {metadata.source_type?.toUpperCase()}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">
              {metadata.row_count.toLocaleString()} rows • {metadata.column_count} columns • ID: {metadata.dataset_id.slice(0, 12)}...
            </p>
          </div>
        </div>

        {/* Dataset Switcher & Ask AI Action */}
        <div className="flex items-center gap-2">
          {allDatasets.length > 1 && (
            <select
              value={activeDatasetId}
              onChange={(e) => setActiveDatasetId(e.target.value)}
              className="text-xs bg-surface border border-border rounded px-2.5 py-1.5 text-foreground focus:outline-none focus:border-primary font-mono"
            >
              {allDatasets.map((ds) => (
                <option key={ds.dataset_id} value={ds.dataset_id}>
                  {ds.filename} ({ds.row_count} rows)
                </option>
              ))}
            </select>
          )}

          <Link href={`/?dataset=${metadata.dataset_id}`}>
            <Button variant="primary" size="sm" leftIcon={<BarChart3 className="w-3.5 h-3.5" />}>
              Generate Dashboard
            </Button>
          </Link>
        </div>
      </div>

      {/* Dataset Overview Cards & Schema Readiness Banner */}
      <DatasetOverview
        metadata={metadata}
        readiness={readiness || undefined}
        missingnessPct={missingnessPct}
        duplicateRows={duplicateRows}
      />

      {/* Tab Navigation */}
      <div className="flex items-center gap-2 border-b border-border text-xs font-medium">
        <button
          onClick={() => setActiveTab('preview')}
          className={`flex items-center gap-2 px-3.5 py-2 border-b-2 transition-all ${
            activeTab === 'preview'
              ? 'border-primary text-primary font-bold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Table className="w-3.5 h-3.5" />
          <span>Data Preview</span>
        </button>

        <button
          onClick={() => setActiveTab('profile')}
          className={`flex items-center gap-2 px-3.5 py-2 border-b-2 transition-all ${
            activeTab === 'profile'
              ? 'border-primary text-primary font-bold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5" />
          <span>Data Profiling</span>
        </button>

        <button
          onClick={() => setActiveTab('semantic')}
          className={`flex items-center gap-2 px-3.5 py-2 border-b-2 transition-all ${
            activeTab === 'semantic'
              ? 'border-primary text-primary font-bold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Brain className="w-3.5 h-3.5" />
          <span>Semantic Intelligence</span>
        </button>
      </div>

      {/* Tab Content Panels */}
      <div>
        {activeTab === 'preview' && preview && (
          <DataPreviewTable preview={preview} />
        )}

        {activeTab === 'profile' && profile && (
          <ProfileTab profile={profile} />
        )}

        {activeTab === 'semantic' && semanticProfile && (
          <SemanticTab semanticProfile={semanticProfile} />
        )}
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-xs text-muted-foreground font-mono">
          Loading Analysis Workspace...
        </div>
      }
    >
      <AnalysisContent />
    </Suspense>
  );
}
