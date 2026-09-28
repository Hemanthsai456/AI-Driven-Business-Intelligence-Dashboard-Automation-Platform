'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useTheme } from './ThemeProvider';
import { Breadcrumbs } from './Breadcrumbs';
import { healthCheck } from '../lib/api';
import {
  Sun,
  Moon,
  Laptop,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Bell,
  PanelLeftClose,
  PanelLeft,
  Sparkles,
} from 'lucide-react';

interface TopBarProps {
  datasetName?: string;
  sourceType?: string;
  rowCount?: number;
  columnCount?: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  datasetName,
  sourceType,
  rowCount,
  columnCount,
}) => {
  const { theme, setTheme, resolvedTheme, sidebarCollapsed, toggleSidebar } = useTheme();
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [showThemeMenu, setShowThemeMenu] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);

  useEffect(() => {
    let mounted = true;
    healthCheck()
      .then(() => {
        if (mounted) setBackendStatus('connected');
      })
      .catch(() => {
        if (mounted) setBackendStatus('disconnected');
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <>
      <header className="h-13 px-4 sm:px-6 bg-surface border-b border-border flex items-center justify-between sticky top-0 z-30 select-none">
        {/* Left Section: Sidebar Toggle & Breadcrumbs */}
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

          {/* Breadcrumbs */}
          <div className="hidden sm:block truncate">
            <Breadcrumbs extra={datasetName ? `${datasetName} (${rowCount?.toLocaleString()} rows)` : undefined} />
          </div>
        </div>

        {/* Right Section: Compact Status, Theme, Help, Profile */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Compact Backend Connection Indicator */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-2xs font-mono font-medium border ${
              backendStatus === 'connected'
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20'
                : backendStatus === 'disconnected'
                ? 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20'
                : 'bg-surface-muted text-muted-foreground border-border'
            }`}
            title={
              backendStatus === 'connected'
                ? 'FastAPI engine active on http://localhost:8000'
                : 'Backend API connection failed'
            }
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                backendStatus === 'connected'
                  ? 'bg-emerald-500 animate-pulse'
                  : backendStatus === 'disconnected'
                  ? 'bg-rose-500'
                  : 'bg-muted-foreground'
              }`}
            />
            <span className="hidden md:inline">
              {backendStatus === 'connected'
                ? 'Connected'
                : backendStatus === 'disconnected'
                ? 'Offline'
                : 'Checking'}
            </span>
          </div>

          <div className="h-4 w-px bg-border" />

          {/* Help Button */}
          <button
            onClick={() => setShowHelpModal(true)}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
            title="System documentation & shortcut guide"
          >
            <HelpCircle className="w-4 h-4" />
          </button>

          {/* Theme Selector Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowThemeMenu((prev) => !prev)}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors flex items-center"
              title={`Theme: ${theme}`}
            >
              {resolvedTheme === 'dark' ? (
                <Moon className="w-4 h-4 text-sky-400" />
              ) : (
                <Sun className="w-4 h-4 text-amber-500" />
              )}
            </button>

            {showThemeMenu && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowThemeMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-36 bg-surface-elevated border border-border rounded-lg shadow-lg py-1 z-50 text-xs font-medium">
                  <button
                    onClick={() => {
                      setTheme('light');
                      setShowThemeMenu(false);
                    }}
                    className={`w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-surface-muted ${
                      theme === 'light' ? 'text-primary font-semibold' : 'text-foreground'
                    }`}
                  >
                    <Sun className="w-3.5 h-3.5 text-amber-500" />
                    <span>Light</span>
                  </button>
                  <button
                    onClick={() => {
                      setTheme('dark');
                      setShowThemeMenu(false);
                    }}
                    className={`w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-surface-muted ${
                      theme === 'dark' ? 'text-primary font-semibold' : 'text-foreground'
                    }`}
                  >
                    <Moon className="w-3.5 h-3.5 text-sky-400" />
                    <span>Dark</span>
                  </button>
                  <button
                    onClick={() => {
                      setTheme('system');
                      setShowThemeMenu(false);
                    }}
                    className={`w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-surface-muted ${
                      theme === 'system' ? 'text-primary font-semibold' : 'text-foreground'
                    }`}
                  >
                    <Laptop className="w-3.5 h-3.5 text-muted-foreground" />
                    <span>System</span>
                  </button>
                </div>
              </>
            )}
          </div>

          <div className="h-4 w-px bg-border" />

          {/* User / Workspace Avatar */}
          <div className="flex items-center gap-2 pl-1">
            <div className="w-7 h-7 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center text-primary text-xs font-bold font-mono">
              BI
            </div>
            <div className="hidden lg:block text-left">
              <div className="text-xs font-semibold text-foreground leading-none">
                Workspace
              </div>
              <div className="text-2xs text-muted-foreground mt-0.5 leading-none">
                Enterprise v1.0
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Quick Help Modal */}
      {showHelpModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                <h3 className="text-sm font-bold text-foreground">AI BI Platform Guide</h3>
              </div>
              <button
                onClick={() => setShowHelpModal(false)}
                className="text-muted-foreground hover:text-foreground text-xs font-mono"
              >
                ✕
              </button>
            </div>

            <div className="text-xs text-muted-foreground space-y-3">
              <p>
                <strong className="text-foreground">Core Pipeline:</strong> Ingest structured datasets (CSV, XLSX, Parquet), inspect deterministic statistical profiles, analyze semantic role classifications, and run natural-language queries.
              </p>
              <div className="p-3 bg-surface-muted rounded-lg border border-border space-y-1.5 font-mono text-2xs">
                <div>• <span className="text-foreground font-semibold">Overview</span>: High-level metrics & recent activity</div>
                <div>• <span className="text-foreground font-semibold">Ask AI</span>: K-candidate orchestrator with Pass 1/2 validation</div>
                <div>• <span className="text-foreground font-semibold">Analysis</span>: Profiling, missingness, distributions & semantics</div>
                <div>• <span className="text-foreground font-semibold">Dashboards</span>: Interactive grid widgets & KPI metrics</div>
                <div>• <span className="text-foreground font-semibold">Plan Runner</span>: Live DuckDB pipeline execution visualization</div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowHelpModal(false)}
                className="px-4 py-1.5 bg-primary text-primary-foreground text-xs font-semibold rounded hover:bg-primary-hover transition-colors"
              >
                Close Guide
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
