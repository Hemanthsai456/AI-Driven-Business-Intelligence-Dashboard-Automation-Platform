'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Header } from '../../components/Header';
import { DatasetOverview } from '../../components/DatasetOverview';
import { DataPreviewTable } from '../../components/DataPreviewTable';
import { ProfileTab } from '../../components/ProfileTab';
import { SemanticTab } from '../../components/SemanticTab';
import { LoadingSpinner } from '../../components/LoadingSpinner';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
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
  Sparkles,
  UploadCloud,
  ChevronDown,
  Database,
} from 'lucide-react';

function AnalysisContent() {
  const searchParams = useSearchParams();
  const datasetIdParam = searchParams.get('id');

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

  // 1. Fetch dataset list
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

  // 2. Fetch full analysis details when activeDatasetId changes
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
      <div className="flex-1 flex flex-col min-h-screen">
        <Header />
        <LoadingSpinner label="Fetching ingestion metadata, data profile & semantic analysis..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col min-h-screen">
        <Header />
        <div className="p-8 max-w-4xl mx-auto w-full space-y-4">
          <Alert title="Dataset Load Error" message={error} variant="error" />
          <Link href="/upload">
            <Button variant="primary">Upload New Dataset</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (!metadata || !activeDatasetId) {
    return (
      <div className="flex-1 flex flex-col min-h-screen">
        <Header />
        <div className="p-8 max-w-2xl mx-auto w-full text-center space-y-4">
          <Card className="p-8">
            <Database className="w-12 h-12 text-slate-500 mx-auto mb-3" />
            <h2 className="text-lg font-bold text-slate-200">No Dataset Selected</h2>
            <p className="text-xs text-slate-400 mt-1">
              Please upload a CSV, TSV, XLSX, or Parquet dataset to inspect profiling statistics and semantic column roles.
            </p>
            <div className="pt-4">
              <Link href="/upload">
                <Button variant="primary">
                  <UploadCloud className="w-4 h-4 mr-2" />
                  <span>Upload Dataset</span>
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  const missingnessPct = profile?.dataset_summary?.overall_missing_percentage ?? 0;
  const duplicateRows = profile?.dataset_summary?.duplicate_row_count ?? 0;

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <Header
        datasetName={metadata.filename}
        sourceType={metadata.source_type}
        rowCount={metadata.row_count}
        columnCount={metadata.column_count}
      />

      <div className="p-8 max-w-7xl mx-auto w-full space-y-6">
        {/* Dataset Switcher Bar (if multiple datasets in session) */}
        {allDatasets.length > 1 && (
          <div className="flex items-center justify-between p-3 bg-slate-900/80 border border-slate-800 rounded-xl text-xs">
            <span className="text-slate-400">Active Session Datasets:</span>
            <div className="flex items-center space-x-2">
              {allDatasets.map((ds) => (
                <button
                  key={ds.dataset_id}
                  onClick={() => setActiveDatasetId(ds.dataset_id)}
                  className={`px-3 py-1.5 rounded-lg font-mono transition-all ${
                    ds.dataset_id === activeDatasetId
                      ? 'bg-sky-600 text-white font-semibold'
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {ds.filename}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Overview KPIs */}
        <DatasetOverview
          metadata={metadata}
          readiness={readiness || undefined}
          missingnessPct={missingnessPct}
          duplicateRows={duplicateRows}
        />

        {/* Workspace Tab Navigation */}
        <div className="border-b border-slate-800 flex items-center space-x-2 text-sm font-medium">
          <button
            onClick={() => setActiveTab('preview')}
            className={`flex items-center space-x-2 px-4 py-2.5 border-b-2 transition-all ${
              activeTab === 'preview'
                ? 'border-sky-400 text-sky-400 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Table className="w-4 h-4" />
            <span>Data Preview</span>
          </button>

          <button
            onClick={() => setActiveTab('profile')}
            className={`flex items-center space-x-2 px-4 py-2.5 border-b-2 transition-all ${
              activeTab === 'profile'
                ? 'border-sky-400 text-sky-400 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Data Profiling</span>
          </button>

          <button
            onClick={() => setActiveTab('semantic')}
            className={`flex items-center space-x-2 px-4 py-2.5 border-b-2 transition-all ${
              activeTab === 'semantic'
                ? 'border-purple-400 text-purple-400 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Semantic Intelligence</span>
          </button>
        </div>

        {/* Active Tab View */}
        <div>
          {activeTab === 'preview' && preview && <DataPreviewTable preview={preview} />}
          {activeTab === 'profile' && profile && <ProfileTab profile={profile} />}
          {activeTab === 'semantic' && semanticProfile && (
            <SemanticTab semanticProfile={semanticProfile} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={<LoadingSpinner label="Loading Analysis Workspace..." />}>
      <AnalysisContent />
    </Suspense>
  );
}
