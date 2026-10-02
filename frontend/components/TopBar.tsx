'use client';

import React, { useEffect, useState } from 'react';
import { useTheme } from './ThemeProvider';
import { Breadcrumbs } from './Breadcrumbs';
import { healthCheck, getProvidersStatus } from '../lib/api';
import {
  Sun,
  Moon,
  Laptop,
  CheckCircle2,
  AlertTriangle,
  PanelLeftClose,
  PanelLeft,
  Cpu,
} from 'lucide-react';

interface TopBarProps {
  datasetName?: string;
  rowCount?: number;
}

interface ProviderInfo {
  provider: string;
  status: 'live' | 'failed';
  model: string | null;
  reason: string | null;
  is_baseline: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({ datasetName, rowCount }) => {
  const { theme, setTheme, resolvedTheme, sidebarCollapsed, toggleSidebar } = useTheme();
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [providers, setProviders] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    let mounted = true;

    // Check backend health
    healthCheck()
      .then(() => {
        if (mounted) setBackendStatus('connected');
      })
      .catch(() => {
        if (mounted) setBackendStatus('disconnected');
      });

    // Check multi-provider health
    getProvidersStatus()
      .then((res) => {
        if (mounted && res && res.providers) {
          setProviders(res.providers);
        }
      })
      .catch(() => {
        // Fallback if provider endpoint temporarily unavailable
      });

    return () => {
      mounted = false;
    };
  }, []);

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <header className="h-14 px-4 sm:px-6 bg-surface border-b border-border flex items-center justify-between sticky top-0 z-30 select-none shadow-xs">
      {/* Left: Sidebar Toggle & Breadcrumbs */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={toggleSidebar}
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
        >
          {sidebarCollapsed ? (
            <PanelLeft className="w-4 h-4" />
          ) : (
            <PanelLeftClose className="w-4 h-4" />
          )}
        </button>

        <div className="h-4 w-px bg-border hidden sm:block" />

        <div className="hidden sm:block truncate font-sans">
          <Breadcrumbs extra={datasetName ? `${datasetName} (${rowCount?.toLocaleString()} rows)` : undefined} />
        </div>
      </div>

      {/* Right: Provider Chips, Backend Status & Theme Toggle */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {/* Compact Provider Chips */}
        <div className="hidden md:flex items-center gap-1.5">
          {providers.map((p) => {
            const isLive = p.status === 'live';
            const label = p.is_baseline ? 'baseline' : p.provider.replace('_', ' ');

            return (
              <div
                key={p.provider}
                title={
                  !isLive
                    ? `${p.provider} failed: ${p.reason || 'Service unreachable'}`
                    : p.is_baseline
                    ? 'Rule-based baseline provider'
                    : `Active model: ${p.model || 'live'}`
                }
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono font-medium border transition-colors ${
                  isLive
                    ? 'bg-success-soft text-success border-success/30'
                    : 'bg-attention-soft text-attention border-attention/30'
                }`}
              >
                {!isLive ? (
                  <AlertTriangle className="w-3 h-3 text-attention shrink-0" />
                ) : (
                  <CheckCircle2 className="w-3 h-3 text-success shrink-0" />
                )}
                <span className="capitalize">{label}</span>
              </div>
            );
          })}
        </div>

        {/* Backend Status Indicator */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs font-mono font-medium border ${
            backendStatus === 'connected'
              ? 'bg-success-soft text-success border-success/30'
              : backendStatus === 'disconnected'
              ? 'bg-error-soft text-error border-error/30'
              : 'bg-surface-muted text-muted-foreground border-border'
          }`}
          title="Backend API Engine"
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              backendStatus === 'connected'
                ? 'bg-success'
                : backendStatus === 'disconnected'
                ? 'bg-error'
                : 'bg-muted-foreground'
            }`}
          />
          <span className="hidden sm:inline">
            {backendStatus === 'connected'
              ? 'Backend Live'
              : backendStatus === 'disconnected'
              ? 'Backend Offline'
              : 'Connecting...'}
          </span>
        </div>

        <div className="h-4 w-px bg-border" />

        {/* Simple Working Sun / Moon Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors flex items-center"
          title={`Switch to ${resolvedTheme === 'dark' ? 'light' : 'dark'} mode`}
          aria-label="Toggle theme"
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="w-4 h-4 text-attention" />
          ) : (
            <Moon className="w-4 h-4 text-muted-foreground" />
          )}
        </button>
      </div>
    </header>
  );
};
