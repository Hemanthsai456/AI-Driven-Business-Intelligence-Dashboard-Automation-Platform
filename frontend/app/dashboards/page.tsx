'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { KpiCard } from '@/components/KpiCard';
import {
  LineChart as LineChartIcon,
  BarChart3,
  Calendar,
  Filter,
  Share2,
  Download,
  Plus,
  Sparkles,
  TrendingUp,
  DollarSign,
  Users,
  ShoppingCart,
  Percent,
  MoreVertical,
  Maximize2,
} from 'lucide-react';

export default function DashboardsPage() {
  const [dateRange, setDateRange] = useState('Last 30 Days');
  const [selectedRegion, setSelectedRegion] = useState('All Regions');
  const [widgets, setWidgets] = useState([
    { id: 'rev_cat', title: 'Revenue by Product Category', type: 'BAR' },
    { id: 'growth_trend', title: 'Monthly Revenue Growth', type: 'LINE' },
    { id: 'reg_dist', title: 'Regional Contribution Share', type: 'DONUT' },
    { id: 'top_orders', title: 'Top 5 Transactions', type: 'TABLE' },
  ]);

  const categoryData = [
    { label: 'Technology', value: 425000, pct: 45 },
    { label: 'Office Supplies', value: 285000, pct: 30 },
    { label: 'Furniture', value: 165000, pct: 18 },
    { label: 'Services', value: 68000, pct: 7 },
  ];

  const trendData = [
    { month: 'Apr', val: 120 },
    { month: 'May', val: 145 },
    { month: 'Jun', val: 138 },
    { month: 'Jul', val: 172 },
    { month: 'Aug', val: 198 },
    { month: 'Sep', val: 240 },
  ];

  return (
    <div className="space-y-6">
      {/* Dashboard Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              Executive Performance Dashboard
            </h1>
            <Badge variant="green" size="xs" dot>Live Sync</Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Real-time interactive analytical widgets powered by canonical semantic models.
          </p>
        </div>

        {/* Toolbar Actions */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Date Range Picker */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-surface border border-border rounded text-xs text-foreground">
            <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="bg-transparent focus:outline-none text-xs font-medium cursor-pointer"
            >
              <option value="Last 7 Days">Last 7 Days</option>
              <option value="Last 30 Days">Last 30 Days</option>
              <option value="Q3 2026">Q3 2026</option>
              <option value="Year to Date">Year to Date</option>
            </select>
          </div>

          <Button
            variant="outline"
            size="sm"
            leftIcon={<Share2 className="w-3.5 h-3.5" />}
          >
            Share
          </Button>

          <Button
            variant="outline"
            size="sm"
            leftIcon={<Download className="w-3.5 h-3.5" />}
          >
            Export
          </Button>

          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
          >
            Add Widget
          </Button>
        </div>
      </div>

      {/* Global Filter Bar */}
      <div className="flex flex-wrap items-center gap-2 p-2.5 bg-surface border border-border rounded-lg text-xs">
        <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider font-mono flex items-center gap-1 mr-1">
          <Filter className="w-3 h-3" /> Filters:
        </span>

        {['All Regions', 'North America', 'EMEA', 'APAC', 'LATAM'].map((reg) => (
          <button
            key={reg}
            onClick={() => setSelectedRegion(reg)}
            className={`px-2 py-0.5 rounded text-2xs transition-colors ${
              selectedRegion === reg
                ? 'bg-primary text-primary-foreground font-semibold'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            {reg}
          </button>
        ))}

        <div className="h-3 w-px bg-border mx-1" />

        <Badge variant="blue" size="xs">Currency: USD ($)</Badge>
        <Badge variant="slate" size="xs">Granularity: Monthly</Badge>
      </div>

      {/* Top KPI Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard
          title="Total Net Revenue"
          value="$943,000"
          subtitle="vs $815,000 previous period"
          delta={{ value: '+15.7%', isPositive: true }}
          icon={<DollarSign className="w-4 h-4" />}
          variant="accent"
        />
        <KpiCard
          title="Active Customer Accounts"
          value="4,280"
          subtitle="Retained cohorts"
          delta={{ value: '+8.2%', isPositive: true }}
          icon={<Users className="w-4 h-4" />}
          variant="default"
        />
        <KpiCard
          title="Average Order Value"
          value="$220.35"
          subtitle="Basket size expanding"
          delta={{ value: '+3.1%', isPositive: true }}
          icon={<ShoppingCart className="w-4 h-4" />}
          variant="success"
        />
        <KpiCard
          title="Gross Margin Ratio"
          value="42.8%"
          subtitle="Efficiency target 40%"
          delta={{ value: '+1.4%', isPositive: true }}
          icon={<Percent className="w-4 h-4" />}
          variant="warning"
        />
      </div>

      {/* Grid-Based Analytical Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Widget 1: Revenue by Category (Bar Chart) */}
        <Card
          title="Revenue by Product Category"
          subtitle="Aggregated SUM(Revenue) grouped by Category dimension"
          headerAction={
            <div className="flex items-center gap-1">
              <Badge variant="blue" size="xs">BAR VIZ</Badge>
              <button className="p-1 text-muted-foreground hover:text-foreground">
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          }
        >
          <div className="space-y-3 pt-2">
            {categoryData.map((item, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs font-mono">
                  <span className="font-semibold text-foreground">{item.label}</span>
                  <span className="text-muted-foreground">
                    ${item.value.toLocaleString()} ({item.pct}%)
                  </span>
                </div>
                <div className="h-2.5 bg-surface-muted rounded-full overflow-hidden border border-border">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-500"
                    style={{ width: `${item.pct * 2}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Widget 2: Monthly Revenue Growth (Line Chart) */}
        <Card
          title="Monthly Revenue Growth Trend"
          subtitle="6-Month historical progression with seasonality"
          headerAction={
            <div className="flex items-center gap-1">
              <Badge variant="green" size="xs">LINE VIZ</Badge>
              <button className="p-1 text-muted-foreground hover:text-foreground">
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          }
        >
          <div className="space-y-4 pt-2">
            {/* Simple SVG Line Chart */}
            <div className="h-44 w-full flex items-end justify-between gap-3 pt-4 px-2">
              {trendData.map((item, idx) => {
                const heightPct = (item.val / 250) * 100;
                return (
                  <div key={idx} className="flex-1 flex flex-col items-center gap-2 h-full justify-end group">
                    <span className="text-2xs font-mono text-muted-foreground group-hover:text-primary transition-colors">
                      ${item.val}k
                    </span>
                    <div className="w-full bg-surface-muted rounded-t-sm h-full max-h-32 flex items-end overflow-hidden border border-border/50">
                      <div
                        className="w-full bg-emerald-500/80 hover:bg-emerald-500 rounded-t-sm transition-all duration-300"
                        style={{ height: `${heightPct}%` }}
                      />
                    </div>
                    <span className="text-2xs font-mono font-semibold text-foreground">
                      {item.month}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="flex items-center justify-between text-2xs text-muted-foreground font-mono pt-2 border-t border-border">
              <span>Low: $120k (Apr)</span>
              <span className="text-emerald-500 font-semibold">Peak: $240k (Sep) • +100% Growth</span>
            </div>
          </div>
        </Card>

        {/* Widget 3: Regional Share */}
        <Card
          title="Regional Revenue Contribution"
          subtitle="Distribution across core global operational territories"
          headerAction={<Badge variant="purple" size="xs">SHARE</Badge>}
        >
          <div className="space-y-3 pt-2 font-mono text-xs">
            <div className="flex items-center justify-between p-2 bg-surface-muted rounded border border-border">
              <span className="text-foreground">North America</span>
              <span className="font-bold text-primary">$490,000 (52%)</span>
            </div>
            <div className="flex items-center justify-between p-2 bg-surface-muted rounded border border-border">
              <span className="text-foreground">Europe (EMEA)</span>
              <span className="font-bold text-purple-500">$264,000 (28%)</span>
            </div>
            <div className="flex items-center justify-between p-2 bg-surface-muted rounded border border-border">
              <span className="text-foreground">Asia Pacific (APAC)</span>
              <span className="font-bold text-emerald-500">$141,000 (15%)</span>
            </div>
            <div className="flex items-center justify-between p-2 bg-surface-muted rounded border border-border">
              <span className="text-foreground">Latin America (LATAM)</span>
              <span className="font-bold text-amber-500">$48,000 (5%)</span>
            </div>
          </div>
        </Card>

        {/* Widget 4: AI Insights Stream */}
        <Card
          title="Automated AI Insights & Anomalies"
          subtitle="Continuous discovery across active dataset telemetry"
          headerAction={
            <div className="flex items-center gap-1 text-2xs font-mono text-primary">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Real-Time</span>
            </div>
          }
        >
          <div className="space-y-2.5 pt-1">
            <div className="p-3 bg-surface-muted/60 border border-border rounded text-xs space-y-1">
              <div className="flex items-center justify-between text-2xs font-semibold">
                <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-mono">
                  <TrendingUp className="w-3.5 h-3.5" /> Trend Notice
                </span>
                <span className="text-muted-foreground font-mono">High Confidence</span>
              </div>
              <p className="text-foreground">
                Technology licenses exhibited a <strong>+24.8% spike</strong> in adoption during the last 2 weeks.
              </p>
            </div>

            <div className="p-3 bg-surface-muted/60 border border-border rounded text-xs space-y-1">
              <div className="flex items-center justify-between text-2xs font-semibold">
                <span className="text-amber-600 dark:text-amber-400 flex items-center gap-1 font-mono">
                  Anomaly Alert
                </span>
                <span className="text-muted-foreground font-mono">Review Advised</span>
              </div>
              <p className="text-foreground">
                Inactivity clustering identified in enterprise tier accounts with no activity past 45 days.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
