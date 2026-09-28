'use client';

import React, { useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { useTheme } from '@/components/ThemeProvider';
import {
  Settings as SettingsIcon,
  Palette,
  Database,
  Cpu,
  ShieldCheck,
  Check,
  Server,
  Sun,
  Moon,
  Laptop,
  Layers,
  Sparkles,
  Terminal,
} from 'lucide-react';

export default function SettingsPage() {
  const {
    theme,
    setTheme,
    density,
    setDensity,
    accent,
    setAccent,
    sidebarCollapsed,
    setSidebarCollapsed,
  } = useTheme();

  const [activeSection, setActiveSection] = useState<'appearance' | 'data' | 'ai' | 'about'>('appearance');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="pb-2 border-b border-border">
        <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-primary" />
          Platform Settings & System Configuration
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Customize design system tokens, execution sandbox constraints, and orchestrator parameters.
        </p>
      </div>

      {/* Settings Grid Layout */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left Settings Navigation (3 Cols) */}
        <div className="md:col-span-3 space-y-1">
          <button
            onClick={() => setActiveSection('appearance')}
            className={`w-full text-left px-3 py-2 rounded text-xs font-medium flex items-center gap-2.5 transition-colors ${
              activeSection === 'appearance'
                ? 'bg-primary/10 text-primary font-semibold border-l-2 border-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
            }`}
          >
            <Palette className="w-4 h-4 shrink-0" />
            <span>Appearance & Theme</span>
          </button>

          <button
            onClick={() => setActiveSection('data')}
            className={`w-full text-left px-3 py-2 rounded text-xs font-medium flex items-center gap-2.5 transition-colors ${
              activeSection === 'data'
                ? 'bg-primary/10 text-primary font-semibold border-l-2 border-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
            }`}
          >
            <Database className="w-4 h-4 shrink-0" />
            <span>Data & Sandbox Limits</span>
          </button>

          <button
            onClick={() => setActiveSection('ai')}
            className={`w-full text-left px-3 py-2 rounded text-xs font-medium flex items-center gap-2.5 transition-colors ${
              activeSection === 'ai'
                ? 'bg-primary/10 text-primary font-semibold border-l-2 border-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
            }`}
          >
            <Cpu className="w-4 h-4 shrink-0" />
            <span>AI & Orchestrator</span>
          </button>

          <button
            onClick={() => setActiveSection('about')}
            className={`w-full text-left px-3 py-2 rounded text-xs font-medium flex items-center gap-2.5 transition-colors ${
              activeSection === 'about'
                ? 'bg-primary/10 text-primary font-semibold border-l-2 border-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
            }`}
          >
            <Server className="w-4 h-4 shrink-0" />
            <span>System Architecture</span>
          </button>
        </div>

        {/* Right Settings Panel (9 Cols) */}
        <div className="md:col-span-9 space-y-6">
          {/* SECTION 1: Appearance */}
          {activeSection === 'appearance' && (
            <div className="space-y-6">
              <Card title="Interface Theme" subtitle="Switch between dark, light, or automated system preference">
                <div className="grid grid-cols-3 gap-3 pt-1">
                  <button
                    onClick={() => setTheme('light')}
                    className={`p-3 rounded-lg border text-left flex flex-col justify-between h-20 transition-all ${
                      theme === 'light'
                        ? 'border-primary ring-2 ring-primary/20 bg-surface'
                        : 'border-border bg-surface-muted/50 hover:border-border-strong'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <Sun className="w-4 h-4 text-amber-500" />
                      {theme === 'light' && <Check className="w-3.5 h-3.5 text-primary" />}
                    </div>
                    <span className="text-xs font-semibold text-foreground">Light Mode</span>
                  </button>

                  <button
                    onClick={() => setTheme('dark')}
                    className={`p-3 rounded-lg border text-left flex flex-col justify-between h-20 transition-all ${
                      theme === 'dark'
                        ? 'border-primary ring-2 ring-primary/20 bg-surface'
                        : 'border-border bg-surface-muted/50 hover:border-border-strong'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <Moon className="w-4 h-4 text-sky-400" />
                      {theme === 'dark' && <Check className="w-3.5 h-3.5 text-primary" />}
                    </div>
                    <span className="text-xs font-semibold text-foreground">Dark Mode</span>
                  </button>

                  <button
                    onClick={() => setTheme('system')}
                    className={`p-3 rounded-lg border text-left flex flex-col justify-between h-20 transition-all ${
                      theme === 'system'
                        ? 'border-primary ring-2 ring-primary/20 bg-surface'
                        : 'border-border bg-surface-muted/50 hover:border-border-strong'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <Laptop className="w-4 h-4 text-muted-foreground" />
                      {theme === 'system' && <Check className="w-3.5 h-3.5 text-primary" />}
                    </div>
                    <span className="text-xs font-semibold text-foreground">System Default</span>
                  </button>
                </div>
              </Card>

              <Card title="Layout Density" subtitle="Control component spacing and typography sizing">
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <button
                    onClick={() => setDensity('comfortable')}
                    className={`p-3 rounded-lg border text-left flex items-center justify-between transition-all ${
                      density === 'comfortable'
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border bg-surface-muted/50'
                    }`}
                  >
                    <div>
                      <div className="text-xs font-semibold text-foreground">Comfortable</div>
                      <div className="text-2xs text-muted-foreground">Standard spacing and padding</div>
                    </div>
                    {density === 'comfortable' && <Check className="w-4 h-4 text-primary" />}
                  </button>

                  <button
                    onClick={() => setDensity('compact')}
                    className={`p-3 rounded-lg border text-left flex items-center justify-between transition-all ${
                      density === 'compact'
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border bg-surface-muted/50'
                    }`}
                  >
                    <div>
                      <div className="text-xs font-semibold text-foreground">Compact</div>
                      <div className="text-2xs text-muted-foreground">Data-dense enterprise layout</div>
                    </div>
                    {density === 'compact' && <Check className="w-4 h-4 text-primary" />}
                  </button>
                </div>
              </Card>

              <Card title="Sidebar Navigation" subtitle="Set default sidebar behavior">
                <div className="flex items-center justify-between pt-1">
                  <div>
                    <div className="text-xs font-semibold text-foreground">Collapsible Icon Mode</div>
                    <div className="text-2xs text-muted-foreground">
                      Minimize sidebar width to 64px for maximum screen real estate
                    </div>
                  </div>
                  <Button
                    size="xs"
                    variant={sidebarCollapsed ? 'primary' : 'outline'}
                    onClick={() => setSidebarCollapsed((p) => !p)}
                  >
                    {sidebarCollapsed ? 'Collapsed' : 'Expanded'}
                  </Button>
                </div>
              </Card>
            </div>
          )}

          {/* SECTION 2: Data & Sandbox Limits */}
          {activeSection === 'data' && (
            <div className="space-y-6">
              <Card title="DuckDB Query Sandbox Limits" subtitle="Worker isolation parameters from orchestrator/config.py">
                <div className="space-y-3 font-mono text-xs">
                  <div className="flex items-center justify-between p-2.5 bg-surface-muted rounded border border-border">
                    <span className="text-muted-foreground">DUCKDB_MEMORY_LIMIT</span>
                    <span className="font-bold text-foreground">256MB PRAGMA</span>
                  </div>
                  <div className="flex items-center justify-between p-2.5 bg-surface-muted rounded border border-border">
                    <span className="text-muted-foreground">DUCKDB_THREAD_LIMIT</span>
                    <span className="font-bold text-foreground">1 (Single-Thread Predictability)</span>
                  </div>
                  <div className="flex items-center justify-between p-2.5 bg-surface-muted rounded border border-border">
                    <span className="text-muted-foreground">DUCKDB_TIMEOUT_SECONDS</span>
                    <span className="font-bold text-foreground">30.0s Hard Interrupt</span>
                  </div>
                  <div className="flex items-center justify-between p-2.5 bg-surface-muted rounded border border-border">
                    <span className="text-muted-foreground">RESULT_ROW_CAP</span>
                    <span className="font-bold text-foreground">50,000 Rows</span>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {/* SECTION 3: AI & Orchestrator */}
          {activeSection === 'ai' && (
            <div className="space-y-6">
              <Card title="Ranker V1 Scoring Weights" subtitle="Hypotheses weights configured in orchestrator/config.py">
                <div className="space-y-2.5 font-mono text-xs">
                  <div className="flex justify-between p-2 bg-surface-muted rounded">
                    <span>RANK_W1_EVIDENCE (Role Confidence):</span>
                    <span className="font-bold text-primary">0.35 (35%)</span>
                  </div>
                  <div className="flex justify-between p-2 bg-surface-muted rounded">
                    <span>RANK_W2_COVERAGE (Prompt Term Overlap):</span>
                    <span className="font-bold text-primary">0.30 (30%)</span>
                  </div>
                  <div className="flex justify-between p-2 bg-surface-muted rounded">
                    <span>RANK_W3_STABILITY (Perturbation Invariance):</span>
                    <span className="font-bold text-primary">0.20 (20%)</span>
                  </div>
                  <div className="flex justify-between p-2 bg-surface-muted rounded">
                    <span>RANK_W4_ASSUMPTIONS (Filled Defaults Penalty):</span>
                    <span className="font-bold text-rose-500">-0.15 (-15%)</span>
                  </div>
                  <div className="flex justify-between p-2 bg-surface-muted rounded">
                    <span>MAX_CASCADE_DEPTH (Pass 2 Runner-up Fallback):</span>
                    <span className="font-bold text-foreground">2 Rollback Steps</span>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {/* SECTION 4: Architecture */}
          {activeSection === 'about' && (
            <div className="space-y-6">
              <Card title="Engine Architecture Contract" subtitle="System components and frozen layers">
                <div className="space-y-2 text-xs font-mono">
                  <div className="flex items-center gap-2 p-2 bg-surface-muted rounded border border-border">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Locked Layer: Ingestion Loaders (CSV, TSV, XLSX, Parquet)</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-surface-muted rounded border border-border">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Locked Layer: Deterministic Data Profiler & Quality Metrics</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-surface-muted rounded border border-border">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Locked Layer: Rule-Based Semantic Intelligence & Roles</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-surface-muted rounded border border-border">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Orchestrator: Pass 1a/1b Validation & DuckDB Compiler</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-surface-muted rounded border border-border">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Orchestrator: Winner Selection, Pass 2 Suitability & Cascade</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-surface-muted rounded border border-border">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Contract: schemas/dashboard_spec.schema.json</span>
                  </div>
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
