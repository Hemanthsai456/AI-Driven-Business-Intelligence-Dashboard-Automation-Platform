'use client';

import React from 'react';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import { useTheme } from '../../components/ThemeProvider';
import { Settings as SettingsIcon, Check, Sun, Moon, Laptop } from 'lucide-react';

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();

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
