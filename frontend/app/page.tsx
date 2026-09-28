'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { listDatasets } from '../lib/api';
import { DatasetListItem } from '../lib/types';
import {
  UploadCloud,
  CheckCircle2,
  Database,
  ArrowRight,
  FileSpreadsheet,
  BarChart3,
  Brain,
  ShieldCheck,
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
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Compact Application Introduction Banner */}
      <div className="bg-surface border border-border rounded-lg p-6 shadow-xs">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-2xs font-semibold font-mono bg-[#E6D4B8] text-[#212121] border border-border">
            <span>Production Interface • Phase 1</span>
          </div>

          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            AI-Driven Business Intelligence
          </h1>

          <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
            Turn structured data into explainable analytical understanding and, eventually, interactive dashboards.
          </p>

          <div className="pt-1 flex items-center gap-3">
            <Link href="/upload">
              <Button
                variant="primary"
                size="sm"
                leftIcon={<UploadCloud className="w-4 h-4" />}
              >
                Upload Dataset
              </Button>
            </Link>
            <Link href="/ask">
              <Button
                variant="secondary"
                size="sm"
              >
                Ask (NL Query)
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Current Engine Capabilities */}
      <div className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground font-mono">
          Current Engine Capabilities
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card padding="md">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-[#E6D4B8] rounded text-[#EA6928] shrink-0 mt-0.5">
                <FileSpreadsheet className="w-4 h-4" />
              </div>
              <div className="space-y-1 min-w-0">
                <h3 className="text-xs font-bold text-foreground">
                  CSV / TSV / XLSX / Parquet Ingestion
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Deterministic raw data loading, encoding detection, and canonical dataset construction with read-only guarantees.
                </p>
              </div>
            </div>
          </Card>

          <Card padding="md">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-[#E6D4B8] rounded text-[#EA6928] shrink-0 mt-0.5">
                <BarChart3 className="w-4 h-4" />
              </div>
              <div className="space-y-1 min-w-0">
                <h3 className="text-xs font-bold text-foreground">
                  Data Profiling
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Statistical distribution calculations, null counts, distinct values, and numerical summary metrics.
                </p>
              </div>
            </div>
          </Card>

          <Card padding="md">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-[#E6D4B8] rounded text-[#EA6928] shrink-0 mt-0.5">
                <Brain className="w-4 h-4" />
              </div>
              <div className="space-y-1 min-w-0">
                <h3 className="text-xs font-bold text-foreground">
                  Semantic Intelligence
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Rule-based evidence classification into MEASURE, DIMENSION, DATETIME, and IDENTIFIER semantic roles.
                </p>
              </div>
            </div>
          </Card>

          <Card padding="md">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-[#E6D4B8] rounded text-[#EA6928] shrink-0 mt-0.5">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div className="space-y-1 min-w-0">
                <h3 className="text-xs font-bold text-foreground">
                  Schema Readiness & Validation
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  C3 validation gate verifying metadata alignment, nullability thresholds, and downstream query readiness.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Active Session Datasets Table (Real Data Only) */}
      <div className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground font-mono">
          Active Session Datasets
        </h2>

        <Card padding="none">
          {loading ? (
            <div className="p-8 text-center text-xs text-muted-foreground font-mono">
              Loading active datasets...
            </div>
          ) : datasets.length === 0 ? (
            <div className="p-8 text-center space-y-2">
              <Database className="w-8 h-8 text-muted-foreground mx-auto" />
              <div className="text-xs font-bold text-foreground">No datasets ingested yet</div>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                Upload a structured file (CSV, TSV, XLSX, Parquet) to inspect profiling statistics and semantic column roles.
              </p>
              <div className="pt-2">
                <Link href="/upload">
                  <Button size="sm" variant="primary" leftIcon={<UploadCloud className="w-3.5 h-3.5" />}>
                    Upload Dataset
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs font-mono">
                <thead>
                  <tr className="border-b border-border bg-[#E6D4B8]/40 text-2xs uppercase text-muted-foreground">
                    <th className="py-2.5 px-4 font-semibold">Dataset Name</th>
                    <th className="py-2.5 px-4 font-semibold">Format</th>
                    <th className="py-2.5 px-4 font-semibold">Rows</th>
                    <th className="py-2.5 px-4 font-semibold">Columns</th>
                    <th className="py-2.5 px-4 font-semibold">Readiness Status</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {datasets.map((ds) => (
                    <tr key={ds.dataset_id} className="hover:bg-[#E6D4B8]/20 transition-colors">
                      <td className="py-2.5 px-4 font-bold text-foreground flex items-center gap-2">
                        <Database className="w-3.5 h-3.5 text-[#EA6928] shrink-0" />
                        <span className="truncate max-w-xs">{ds.filename}</span>
                      </td>
                      <td className="py-2.5 px-4">
                        <Badge variant="blue" size="xs">
                          {ds.source_type?.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">
                        {ds.row_count.toLocaleString()}
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">
                        {ds.column_count}
                      </td>
                      <td className="py-2.5 px-4">
                        <Badge
                          variant={
                            ds.readiness_status === 'READY'
                              ? 'green'
                              : ds.readiness_status === 'READY_WITH_WARNINGS'
                              ? 'amber'
                              : 'slate'
                          }
                          size="xs"
                          dot
                        >
                          {ds.readiness_status}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        <Link href={`/analysis?id=${ds.dataset_id}`}>
                          <Button size="xs" variant="secondary">
                            Analyze
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
