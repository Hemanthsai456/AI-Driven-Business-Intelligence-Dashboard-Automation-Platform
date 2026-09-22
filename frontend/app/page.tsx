'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Header } from '../components/Header';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { listDatasets } from '../lib/api';
import { DatasetListItem } from '../lib/types';
import {
  UploadCloud,
  CheckCircle2,
  BarChart3,
  Sparkles,
  ArrowRight,
  Database,
  FileSpreadsheet,
  Clock,
} from 'lucide-react';

export default function HomePage() {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listDatasets()
      .then((data) => setDatasets(data))
      .catch((err) => console.error('Failed to load active datasets:', err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <Header />

      <div className="p-8 max-w-6xl mx-auto w-full space-y-8">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-900/90 to-sky-950/40 border border-slate-800 rounded-3xl p-8 relative overflow-hidden shadow-2xl">
          <div className="max-w-2xl space-y-4 relative z-10">
            <div className="inline-flex items-center space-x-2 px-3 py-1 bg-sky-500/10 border border-sky-500/20 rounded-full text-xs font-semibold text-sky-400">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Production Interface • Phase 1</span>
            </div>

            <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-100 tracking-tight leading-tight">
              AI-Driven Business Intelligence
            </h1>

            <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
              Turn structured data into explainable analytical understanding and, eventually, interactive dashboards.
            </p>

            <div className="pt-2 flex items-center space-x-4">
              <Link href="/upload">
                <Button size="lg" className="shadow-sky-500/20">
                  <UploadCloud className="w-5 h-5 mr-2" />
                  <span>Upload Dataset</span>
                </Button>
              </Link>
            </div>
          </div>

          {/* Decorative subtle ambient backdrop */}
          <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-sky-500/10 to-transparent pointer-events-none" />
        </div>

        {/* Capabilities Grid */}
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Current Engine Capabilities
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="hover:border-slate-700 transition-all">
              <div className="flex items-center space-x-3 mb-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <h3 className="font-semibold text-slate-200 text-sm">CSV/XLSX Ingestion</h3>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Deterministic raw data loading, encoding detection, and canonical dataset construction.
              </p>
            </Card>

            <Card className="hover:border-slate-700 transition-all">
              <div className="flex items-center space-x-3 mb-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <h3 className="font-semibold text-slate-200 text-sm">Data Profiling</h3>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Statistical distribution calculations, null counts, distinct values, and anomaly detection.
              </p>
            </Card>

            <Card className="hover:border-slate-700 transition-all">
              <div className="flex items-center space-x-3 mb-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <h3 className="font-semibold text-slate-200 text-sm">Semantic Intelligence</h3>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Rule-based column role classification (Measure, Dimension, Datetime, Identifier) with rule evidence.
              </p>
            </Card>

            <Card className="hover:border-slate-700 transition-all">
              <div className="flex items-center space-x-3 mb-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <h3 className="font-semibold text-slate-200 text-sm">Schema Readiness</h3>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Structural integrity validation ensuring dataset readiness for downstream analytical execution.
              </p>
            </Card>
          </div>
        </div>

        {/* Active Session Datasets */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
              Active Session Datasets
            </h2>
            <Link href="/upload" className="text-xs text-sky-400 hover:underline flex items-center">
              <span>Upload New File</span>
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Link>
          </div>

          {loading ? (
            <div className="p-8 text-center text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800">
              Loading active datasets...
            </div>
          ) : datasets.length === 0 ? (
            <Card className="text-center p-8 space-y-3">
              <div className="p-3 bg-slate-800/80 rounded-full w-12 h-12 mx-auto flex items-center justify-center text-slate-400">
                <FileSpreadsheet className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-200">No Datasets Uploaded in Current Session</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Upload a real CSV or XLSX dataset to inspect ingestion metadata, data profiles, and semantic column roles.
              </p>
              <Link href="/upload" className="inline-block pt-2">
                <Button variant="primary" size="sm">
                  <UploadCloud className="w-4 h-4 mr-2" />
                  <span>Upload Dataset Now</span>
                </Button>
              </Link>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {datasets.map((ds) => (
                <Link key={ds.dataset_id} href={`/analysis?id=${ds.dataset_id}`}>
                  <Card className="hover:border-slate-700 transition-all cursor-pointer group">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        <div className="p-2 bg-slate-800 rounded-lg text-sky-400">
                          <Database className="w-4 h-4" />
                        </div>
                        <div>
                          <h4 className="font-semibold text-slate-100 text-sm group-hover:text-sky-400 transition-colors">
                            {ds.filename}
                          </h4>
                          <span className="text-[11px] font-mono text-slate-500">ID: {ds.dataset_id}</span>
                        </div>
                      </div>
                      <Badge variant="blue" size="sm">{ds.source_type.toUpperCase()}</Badge>
                    </div>

                    <div className="flex items-center justify-between text-xs text-slate-400 pt-3 border-t border-slate-800/80">
                      <span>{ds.row_count.toLocaleString()} rows • {ds.column_count} cols</span>
                      <div className="flex items-center space-x-1 text-slate-500">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{new Date(ds.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
