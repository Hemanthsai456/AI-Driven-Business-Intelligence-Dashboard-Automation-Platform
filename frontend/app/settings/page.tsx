'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import { useTheme } from '../../components/ThemeProvider';
import { getProvidersStatus } from '../../lib/api';
import {
  Settings as SettingsIcon,
  Check,
  Sun,
  Moon,
  Laptop,
  Cpu,
  AlertTriangle,
  RefreshCw,
  Loader2,
} from 'lucide-react';

interface ProviderItem {
  provider: string;
  status: 'live' | 'failed';
  model: string | null;
  reason: string | null;
  is_baseline: boolean;
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [providers, setProviders] = useState<ProviderItem[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [providersError, setProvidersError] = useState<string | null>(null);

  const fetchProviders = useCallback(async () => {
    setLoadingProviders(true);
    setProvidersError(null);
    try {
      const res = await getProvidersStatus();
      if (res && res.providers) {
        setProviders(res.providers);
      } else {
        setProviders([]);
      }
    } catch (err: any) {
      setProvidersError(err?.message || 'Failed to fetch provider status from engine');
    } finally {
      setLoadingProviders(false);
    }
  }, []);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="pb-2 border-b border-border">
        <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-primary" />
          Settings & Architecture Overview
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Environment parameters, interface appearance, and development-stage system specifications.
        </p>
      </div>

      {/* Interface Theme */}
      <Card title="Interface Theme" subtitle="Switch between Light theme, Dark theme, or OS default">
        <div className="grid grid-cols-3 gap-3 pt-1">
          <button
            onClick={() => setTheme('light')}
            className={`p-3 rounded-card border text-left flex flex-col justify-between h-20 transition-all ${
              theme === 'light'
                ? 'border-primary bg-surface ring-2 ring-primary/20 shadow-xs'
                : 'border-border bg-surface-muted/30 hover:border-primary/50'
            }`}
          >
            <div className="flex items-center justify-between">
              <Sun className="w-4 h-4 text-attention" />
              {theme === 'light' && <Check className="w-3.5 h-3.5 text-primary" />}
            </div>
            <span className="text-xs font-semibold text-foreground">Light Mode</span>
          </button>

          <button
            onClick={() => setTheme('dark')}
            className={`p-3 rounded-card border text-left flex flex-col justify-between h-20 transition-all ${
              theme === 'dark'
                ? 'border-primary bg-surface ring-2 ring-primary/20 shadow-xs'
                : 'border-border bg-surface-muted/30 hover:border-primary/50'
            }`}
          >
            <div className="flex items-center justify-between">
              <Moon className="w-4 h-4 text-muted-foreground" />
              {theme === 'dark' && <Check className="w-3.5 h-3.5 text-primary" />}
            </div>
            <span className="text-xs font-semibold text-foreground">Dark Mode</span>
          </button>

          <button
            onClick={() => setTheme('system')}
            className={`p-3 rounded-card border text-left flex flex-col justify-between h-20 transition-all ${
              theme === 'system'
                ? 'border-primary bg-surface ring-2 ring-primary/20 shadow-xs'
                : 'border-border bg-surface-muted/30 hover:border-primary/50'
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

      {/* Backend API Details */}
      <Card title="Backend API Layer" subtitle="FastAPI HTTP Service Context">
        <div className="space-y-2.5 text-xs font-mono">
          <div className="flex items-center justify-between p-2.5 bg-surface-muted/50 rounded-card border border-border">
            <span className="text-muted-foreground">API Target URL:</span>
            <span className="text-primary font-bold">http://localhost:8000/api</span>
          </div>
          <div className="flex items-center justify-between p-2.5 bg-surface-muted/50 rounded-card border border-border">
            <span className="text-muted-foreground">Target Framework:</span>
            <span className="text-foreground">FastAPI (Python 3.13) + Next.js App Router</span>
          </div>
          <div className="flex items-center justify-between p-2.5 bg-surface-muted/50 rounded-card border border-border">
            <span className="text-muted-foreground">Storage Architecture:</span>
            <Badge variant="amber">In-Memory Session Store</Badge>
          </div>
        </div>
      </Card>

      {/* Providers Section */}
      <Card
        title="Providers"
        subtitle="Dynamic multi-provider status, active model configurations, and consensus routing health"
        headerAction={
          <button
            onClick={fetchProviders}
            disabled={loadingProviders}
            className="flex items-center gap-1.5 px-2.5 py-1 text-2xs font-mono font-medium rounded border border-border bg-surface hover:bg-surface-muted transition-colors disabled:opacity-50 text-foreground"
            title="Refresh provider health"
          >
            <RefreshCw className={`w-3 h-3 ${loadingProviders ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        }
      >
        {loadingProviders && providers.length === 0 ? (
          <div className="py-8 flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground font-mono">
            <Loader2 className="w-5 h-5 animate-spin text-primary" />
            <span>Checking provider statuses...</span>
          </div>
        ) : providersError && providers.length === 0 ? (
          <div className="p-3 bg-error-soft border border-error/30 rounded-card text-xs text-error flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{providersError}</span>
            </div>
            <button
              onClick={fetchProviders}
              className="px-2.5 py-1 text-2xs font-bold rounded bg-surface border border-error/40 hover:bg-surface-muted text-error transition-colors"
            >
              Retry
            </button>
          </div>
        ) : providers.length === 0 ? (
          <div className="py-6 text-center text-xs font-mono text-muted-foreground">
            No AI generation providers configured.
          </div>
        ) : (
          <div className="space-y-3">
            {/* Summary Bar */}
            <div className="flex items-center justify-between text-2xs font-mono text-muted-foreground pb-2 border-b border-border">
              <span>
                {providers.filter((p) => p.status === 'live').length} of {providers.length} provider(s) active
              </span>
              <span className="text-3xs uppercase tracking-wider">
                Multi-Agent Consensus Layer
              </span>
            </div>

            {/* Provider Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {providers.map((p) => {
                const isLive = p.status === 'live';
                return (
                  <div
                    key={p.provider}
                    className="p-3 rounded-card bg-surface-muted/40 border border-border flex flex-col justify-between gap-2.5 transition-colors hover:border-border/80"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Cpu className="w-3.5 h-3.5 text-primary shrink-0" />
                          <span className="font-mono font-semibold text-xs text-foreground capitalize truncate">
                            {p.provider.replace(/_/g, ' ')}
                          </span>
                          {p.is_baseline && (
                            <Badge variant="slate" size="xs">
                              Baseline
                            </Badge>
                          )}
                        </div>
                        <Badge variant={isLive ? 'green' : 'red'} size="xs" dot>
                          {isLive ? 'Live' : 'Failed'}
                        </Badge>
                      </div>

                      <div className="mt-2 space-y-1 text-2xs font-mono">
                        <div className="flex items-baseline justify-between text-muted-foreground">
                          <span>Model:</span>
                          <span className="text-foreground font-medium truncate max-w-[190px]" title={p.model || '—'}>
                            {p.model || '—'}
                          </span>
                        </div>
                        <div className="flex items-baseline justify-between text-muted-foreground">
                          <span>Role:</span>
                          <span>
                            {p.is_baseline ? 'Rule-based heuristic' : 'LLM Candidate Planner'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {!isLive && p.reason && (
                      <div
                        className="mt-1 p-2 rounded bg-attention-soft/50 border border-attention/20 text-3xs font-mono text-attention leading-relaxed break-words"
                        title={p.reason}
                      >
                        <div className="flex items-center gap-1 font-semibold mb-0.5">
                          <AlertTriangle className="w-3 h-3 shrink-0" />
                          <span>Diagnostics</span>
                        </div>
                        <p className="line-clamp-3">{p.reason}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>

      {/* System Capabilities Matrix */}
      <Card title="Locked Engine Capabilities" subtitle="Source-of-truth Python package exports">
        <ul className="space-y-2 text-xs font-mono text-foreground">
          <li className="flex items-center gap-2 p-2 bg-surface-muted/50 rounded-card border border-border">
            <Check className="w-4 h-4 text-success shrink-0" />
            <span>Canonical Data Model & Ingestion Loaders</span>
          </li>
          <li className="flex items-center gap-2 p-2 bg-surface-muted/50 rounded-card border border-border">
            <Check className="w-4 h-4 text-success shrink-0" />
            <span>Deterministic Data Profiling & Cleaning Engine</span>
          </li>
          <li className="flex items-center gap-2 p-2 bg-surface-muted/50 rounded-card border border-border">
            <Check className="w-4 h-4 text-success shrink-0" />
            <span>Rule-Based & LLM Semantic Intelligence</span>
          </li>
          <li className="flex items-center gap-2 p-2 bg-surface-muted/50 rounded-card border border-border">
            <Check className="w-4 h-4 text-success shrink-0" />
            <span>Multi-Agent Consensus & Pass 1 / Pass 2 Validation</span>
          </li>
          <li className="flex items-center gap-2 p-2 bg-surface-muted/50 rounded-card border border-border">
            <Check className="w-4 h-4 text-success shrink-0" />
            <span>Ranker V1 with Perturbation Robustness Across Interpretations</span>
          </li>
        </ul>
      </Card>

      {/* Development Limitations Notice */}
      <Card title="Architecture Decoupling" subtitle="Session Scope">
        <p className="text-xs text-muted-foreground leading-relaxed">
          Uploaded datasets are stored in-memory in the FastAPI application process for the duration of the server session. Storage interfaces are strictly decoupled so persistent storage can be plugged in without altering frontend API contracts.
        </p>
      </Card>
    </div>
  );
}
