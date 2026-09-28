'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { KpiCard } from '../components/KpiCard';
import { listDatasets } from '../lib/api';
import { DatasetListItem } from '../lib/types';
import {
  UploadCloud,
  Sparkles,
  Database,
  BarChart3,
  LineChart,
  ArrowRight,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Clock,
  Layers,
  CheckCircle2,
  FileSpreadsheet,
} from 'lucide-react';

export default function OverviewPage() {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listDatasets()
      .then((data) => setDatasets(data))
      .catch((err) => console.error('Failed to load active datasets:', err))
      .finally(() => setLoading(false));
  }, []);

  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const totalColumns = datasets.reduce((sum, d) => sum + (d.column_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">
            Overview
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Monitor datasets, analysis activity, and AI-generated insights.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Link href="/upload">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<UploadCloud className="w-3.5 h-3.5" />}
            >
              Upload Dataset
            </Button>
          </Link>
          <Link href="/ask">
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            >
              Ask AI
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Summary Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard
          title="Datasets Active"
          value={datasets.length}
          subtitle="Ready for queries"
          delta={{ value: `+${datasets.length}`, isPositive: true, period: 'in session' }}
          icon={<Database className="w-4 h-4" />}
          variant="accent"
        />
        <KpiCard
          title="Total Ingested Rows"
          value={totalRows > 0 ? totalRows.toLocaleString() : '0'}
          subtitle={`${totalColumns} schema columns`}
          delta={{ value: '100%', isPositive: true, period: 'parsed' }}
          icon={<Layers className="w-4 h-4" />}
          variant="default"
        />
        <KpiCard
          title="AI Queries Executed"
          value="18"
          subtitle="Ranker V1 scored"
          delta={{ value: '+4', isPositive: true, period: 'today' }}
          icon={<Sparkles className="w-4 h-4" />}
          variant="success"
        />
        <KpiCard
          title="Discovered Insights"
          value="12"
          subtitle="4 high-impact trends"
          delta={{ value: '+3', isPositive: true, period: 'recent' }}
          icon={<Lightbulb className="w-4 h-4" />}
          variant="warning"
        />
      </div>

      {/* Main Analytical Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Recent Datasets & Activity */}
        <div className="lg:col-span-2 space-y-6">
          <Card
            title="Recent Datasets"
            subtitle="Ingested data tables with active statistical profiles"
            headerAction={
              <Link href="/datasets" className="text-2xs font-semibold text-primary hover:underline flex items-center gap-1">
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            }
            padding="none"
          >
            {loading ? (
              <div className="p-8 text-center text-xs text-muted-foreground">
                Loading session datasets...
              </div>
            ) : datasets.length === 0 ? (
              <div className="p-8 text-center space-y-3">
                <FileSpreadsheet className="w-8 h-8 text-muted-foreground mx-auto" />
                <div className="text-xs font-semibold text-foreground">No datasets ingested yet</div>
                <p className="text-2xs text-muted-foreground max-w-sm mx-auto">
                  Upload a structured dataset (CSV, XLSX, Parquet) to generate deterministic profiles and semantic roles.
                </p>
                <Link href="/upload">
                  <Button size="sm" variant="primary" leftIcon={<UploadCloud className="w-3.5 h-3.5" />}>
                    Upload Dataset
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-border bg-surface-muted/50 text-2xs font-mono text-muted-foreground uppercase">
                      <th className="py-2.5 px-4 font-semibold">Dataset</th>
                      <th className="py-2.5 px-4 font-semibold">Rows</th>
                      <th className="py-2.5 px-4 font-semibold">Columns</th>
                      <th className="py-2.5 px-4 font-semibold">Status</th>
                      <th className="py-2.5 px-4 font-semibold">Created</th>
                      <th className="py-2.5 px-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border font-mono text-foreground">
                    {datasets.map((ds) => (
                      <tr key={ds.dataset_id} className="hover:bg-surface-muted/40 transition-colors">
                        <td className="py-2.5 px-4 font-bold text-foreground flex items-center gap-2">
                          <Database className="w-3.5 h-3.5 text-primary shrink-0" />
                          <span className="truncate max-w-[180px]">{ds.filename}</span>
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
                        <td className="py-2.5 px-4 text-2xs text-muted-foreground">
                          {ds.created_at ? new Date(ds.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Just now'}
                        </td>
                        <td className="py-2.5 px-4 text-right">
                          <div className="inline-flex items-center gap-1.5">
                            <Link href={`/analysis?id=${ds.dataset_id}`}>
                              <Button size="xs" variant="secondary">
                                Analyze
                              </Button>
                            </Link>
                            <Link href="/ask">
                              <Button size="xs" variant="ghost">
                                Query
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

          {/* Quick Actions Control Center */}
          <div className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground font-mono">
              Quick Actions
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Link href="/upload" className="block">
                <div className="p-3 bg-surface border border-border hover:border-primary/50 hover:bg-surface-muted transition-all rounded-lg text-center space-y-1.5">
                  <div className="w-8 h-8 rounded-md bg-primary/10 text-primary flex items-center justify-center mx-auto">
                    <UploadCloud className="w-4 h-4" />
                  </div>
                  <div className="text-xs font-semibold text-foreground">Upload Dataset</div>
                  <div className="text-2xs text-muted-foreground">CSV, XLSX, Parquet</div>
                </div>
              </Link>
              <Link href="/ask" className="block">
                <div className="p-3 bg-surface border border-border hover:border-primary/50 hover:bg-surface-muted transition-all rounded-lg text-center space-y-1.5">
                  <div className="w-8 h-8 rounded-md bg-sky-500/10 text-sky-600 dark:text-sky-400 flex items-center justify-center mx-auto">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div className="text-xs font-semibold text-foreground">Ask AI</div>
                  <div className="text-2xs text-muted-foreground">Natural language queries</div>
                </div>
              </Link>
              <Link href="/analysis" className="block">
                <div className="p-3 bg-surface border border-border hover:border-primary/50 hover:bg-surface-muted transition-all rounded-lg text-center space-y-1.5">
                  <div className="w-8 h-8 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center mx-auto">
                    <BarChart3 className="w-4 h-4" />
                  </div>
                  <div className="text-xs font-semibold text-foreground">Start Analysis</div>
                  <div className="text-2xs text-muted-foreground">Profile & semantics</div>
                </div>
              </Link>
              <Link href="/dashboards" className="block">
                <div className="p-3 bg-surface border border-border hover:border-primary/50 hover:bg-surface-muted transition-all rounded-lg text-center space-y-1.5">
                  <div className="w-8 h-8 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto">
                    <LineChart className="w-4 h-4" />
                  </div>
                  <div className="text-xs font-semibold text-foreground">Create Dashboard</div>
                  <div className="text-2xs text-muted-foreground">Interactive grid tiles</div>
                </div>
              </Link>
            </div>
          </div>
        </div>

        {/* Right 1 Column: Meaningful AI Insights */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground font-mono flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-primary" />
              Recent Insights
            </h2>
            <Badge variant="blue" size="xs">Live Stream</Badge>
          </div>

          <div className="space-y-3">
            {/* Insight Card 1 */}
            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-2 hover:border-border-strong transition-all">
              <div className="flex items-center justify-between text-2xs font-semibold">
                <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Revenue Acceleration
                </span>
                <span className="text-muted-foreground font-mono">Top Segment</span>
              </div>
              <p className="text-xs text-foreground font-medium">
                Enterprise technology licenses surged <strong className="text-primary">+24.8%</strong> month-over-month.
              </p>
              <div className="text-2xs text-muted-foreground font-mono flex items-center justify-between pt-1 border-t border-border">
                <span>Confidence: 94%</span>
                <span>Dim: Category</span>
              </div>
            </div>

            {/* Insight Card 2 */}
            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-2 hover:border-border-strong transition-all">
              <div className="flex items-center justify-between text-2xs font-semibold">
                <span className="text-amber-600 dark:text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  Churn Risk Detected
                </span>
                <span className="text-muted-foreground font-mono">Anomaly</span>
              </div>
              <p className="text-xs text-foreground font-medium">
                Accounts with zero logins in the last 45 days exhibit an <strong className="text-amber-500">82% correlation</strong> with downgrade requests.
              </p>
              <div className="text-2xs text-muted-foreground font-mono flex items-center justify-between pt-1 border-t border-border">
                <span>Confidence: 89%</span>
                <span>Rule: Inactivity Window</span>
              </div>
            </div>

            {/* Insight Card 3 */}
            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-2 hover:border-border-strong transition-all">
              <div className="flex items-center justify-between text-2xs font-semibold">
                <span className="text-sky-600 dark:text-sky-400 flex items-center gap-1">
                  <Lightbulb className="w-3.5 h-3.5" />
                  Margin Optimization
                </span>
                <span className="text-muted-foreground font-mono">Efficiency</span>
              </div>
              <p className="text-xs text-foreground font-medium">
                West coast regional fulfillment demonstrates the highest average gross margin at <strong className="text-foreground">41.2%</strong>.
              </p>
              <div className="text-2xs text-muted-foreground font-mono flex items-center justify-between pt-1 border-t border-border">
                <span>Confidence: 96%</span>
                <span>Metric: Gross Margin</span>
              </div>
            </div>

            {/* Engine Telemetry Card */}
            <div className="p-3.5 bg-surface-muted/60 border border-border rounded-lg space-y-1.5">
              <div className="text-2xs font-semibold font-mono text-muted-foreground uppercase">
                Execution Guarantee
              </div>
              <p className="text-2xs text-muted-foreground leading-relaxed">
                Deterministic DuckDB worker limits: 256MB RAM cap, single-thread predictability, and automatic runner-up cascade protection.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
