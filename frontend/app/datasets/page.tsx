'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import { listDatasets } from '../../lib/api';
import { DatasetListItem } from '../../lib/types';
import {
  Database,
  UploadCloud,
  Search,
  Filter,
  BarChart3,
  Sparkles,
  Terminal,
  RefreshCw,
  SlidersHorizontal,
  Layers,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'READY' | 'WARNINGS'>('ALL');

  const fetchDatasets = () => {
    setLoading(true);
    listDatasets()
      .then((data) => setDatasets(data))
      .catch((err) => console.error('Failed to list datasets:', err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  const filteredDatasets = datasets.filter((d) => {
    const matchesSearch =
      d.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.dataset_id.toLowerCase().includes(searchQuery.toLowerCase());

    if (statusFilter === 'ALL') return matchesSearch;
    if (statusFilter === 'READY') return matchesSearch && d.readiness_status === 'READY';
    if (statusFilter === 'WARNINGS')
      return matchesSearch && d.readiness_status === 'READY_WITH_WARNINGS';
    return matchesSearch;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Database className="w-5 h-5 text-primary" />
            Datasets
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Manage ingested tabular datasets, schema health, and analytical readiness.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchDatasets}
            isLoading={loading}
            leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Refresh
          </Button>
          <Link href="/upload">
            <Button
              variant="primary"
              size="sm"
              leftIcon={<UploadCloud className="w-3.5 h-3.5" />}
            >
              Upload Dataset
            </Button>
          </Link>
        </div>
      </div>

      {/* Search and Filters Toolbar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-surface border border-border rounded-lg">
        <div className="relative w-full sm:w-80">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search datasets by filename or ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8.5 pr-3 py-1.5 text-xs bg-surface-muted border border-border rounded text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="flex items-center gap-1 text-2xs text-muted-foreground font-mono mr-1">
            <Filter className="w-3 h-3" />
            <span>Filter:</span>
          </div>
          <button
            onClick={() => setStatusFilter('ALL')}
            className={`px-2.5 py-1 text-xs rounded transition-colors ${
              statusFilter === 'ALL'
                ? 'bg-primary text-primary-foreground font-semibold'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            All ({datasets.length})
          </button>
          <button
            onClick={() => setStatusFilter('READY')}
            className={`px-2.5 py-1 text-xs rounded transition-colors ${
              statusFilter === 'READY'
                ? 'bg-emerald-600 text-white font-semibold'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Ready
          </button>
          <button
            onClick={() => setStatusFilter('WARNINGS')}
            className={`px-2.5 py-1 text-xs rounded transition-colors ${
              statusFilter === 'WARNINGS'
                ? 'bg-amber-600 text-white font-semibold'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Warnings
          </button>
        </div>
      </div>

      {/* Datasets Table */}
      <Card padding="none">
        {loading ? (
          <div className="p-12 text-center text-xs text-muted-foreground">
            Loading datasets catalog...
          </div>
        ) : filteredDatasets.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Database className="w-10 h-10 text-muted-foreground mx-auto" />
            <div className="text-sm font-semibold text-foreground">
              {datasets.length === 0 ? 'No datasets uploaded yet' : 'No matching datasets'}
            </div>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              {datasets.length === 0
                ? 'Upload your first CSV, TSV, XLSX, or Parquet dataset to begin profiling and AI analysis.'
                : 'Try adjusting your search query or filter to find the dataset you are looking for.'}
            </p>
            {datasets.length === 0 && (
              <div className="pt-2">
                <Link href="/upload">
                  <Button size="sm" variant="primary" leftIcon={<UploadCloud className="w-3.5 h-3.5" />}>
                    Upload Dataset
                  </Button>
                </Link>
              </div>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-surface-muted/60 text-2xs font-mono text-muted-foreground uppercase">
                  <th className="py-3 px-4 font-semibold">Name & ID</th>
                  <th className="py-3 px-4 font-semibold">Source</th>
                  <th className="py-3 px-4 font-semibold">Rows</th>
                  <th className="py-3 px-4 font-semibold">Columns</th>
                  <th className="py-3 px-4 font-semibold">Readiness Status</th>
                  <th className="py-3 px-4 font-semibold">Quality</th>
                  <th className="py-3 px-4 font-semibold">Created</th>
                  <th className="py-3 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono text-foreground">
                {filteredDatasets.map((ds) => (
                  <tr key={ds.dataset_id} className="hover:bg-surface-muted/40 transition-colors">
                    <td className="py-3 px-4">
                      <div className="font-semibold text-foreground flex items-center gap-2">
                        <Database className="w-3.5 h-3.5 text-primary shrink-0" />
                        <span className="truncate max-w-[200px]">{ds.filename}</span>
                      </div>
                      <div className="text-2xs text-muted-foreground font-mono mt-0.5">
                        {ds.dataset_id}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant="blue" size="xs">
                        {ds.source_type?.toUpperCase() || 'FILE'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 font-medium">
                      {ds.row_count.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 font-medium">
                      {ds.column_count}
                    </td>
                    <td className="py-3 px-4">
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
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5 text-2xs">
                        <span className="w-2 h-2 rounded-full bg-emerald-500" />
                        <span>High (100%)</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-2xs text-muted-foreground">
                      {ds.created_at ? new Date(ds.created_at).toLocaleDateString() : 'Active'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex items-center gap-1">
                        <Link href={`/analysis?id=${ds.dataset_id}`}>
                          <Button size="xs" variant="secondary" title="Open Analysis Workspace">
                            Analyze
                          </Button>
                        </Link>
                        <Link href={`/ask?dataset=${ds.dataset_id}`}>
                          <Button size="xs" variant="ghost" title="Ask AI natural language questions">
                            Ask AI
                          </Button>
                        </Link>
                        <Link href={`/plan-runner`}>
                          <Button size="xs" variant="icon" title="Open Plan Runner">
                            <Terminal className="w-3.5 h-3.5" />
                          </Button>
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
