'use client';

import React, { useEffect, useState } from 'react';
import { useTheme } from './ThemeProvider';
import { Breadcrumbs } from './Breadcrumbs';
import { healthCheck } from '../lib/api';
import {
  Sun,
  Moon,
  Laptop,
  CheckCircle2,
  PanelLeftClose,
  PanelLeft,
  HelpCircle,
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
    <header className="h-14 px-4 sm:px-6 bg-surface border-b border-border flex items-center justify-between sticky top-0 z-30 select-none shadow-xs">
      {/* Left: Sidebar Toggle & Breadcrumbs */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={toggleSidebar}
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
        >
          {sidebarCollapsed ? (
            <PanelLeft className="w-4 h-4" />
          ) : (
            <PanelLeftClose className="w-4 h-4" />
          )}
        </button>

        <div className="h-4 w-px bg-border hidden sm:block" />

        <div className="hidden sm:block truncate">
          <Breadcrumbs extra={datasetName ? `${datasetName} (${rowCount?.toLocaleString()} rows)` : undefined} />
        </div>
      </div>

      {/* Right: Backend Status & Theme Toggle */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Compact Backend Connection Indicator */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs font-mono font-medium border ${
            backendStatus === 'connected'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800'
              : backendStatus === 'disconnected'
              ? 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-800'
              : 'bg-surface-muted text-muted-foreground border-border'
          }`}
          title="Backend API (http://localhost:8000/api)"
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              backendStatus === 'connected'
                ? 'bg-emerald-600'
                : backendStatus === 'disconnected'
                ? 'bg-rose-600'
                : 'bg-muted-foreground'
            }`}
          />
          <span>
            {backendStatus === 'connected'
              ? 'Backend Connected'
              : backendStatus === 'disconnected'
              ? 'Backend Offline'
              : 'Connecting...'}
          </span>
        </div>

        <div className="h-4 w-px bg-border" />

        {/* Theme Selector */}
        <div className="relative">
          <button
            onClick={() => setShowThemeMenu((p) => !p)}
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors flex items-center"
            title={`Current theme: ${theme}`}
          >
            {resolvedTheme === 'dark' ? (
              <Moon className="w-4 h-4 text-amber-400" />
            ) : (
              <Sun className="w-4 h-4 text-amber-600" />
            )}
          </button>

          {showThemeMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowThemeMenu(false)} />
              <div className="absolute right-0 mt-2 w-32 bg-surface border border-border rounded shadow-md py-1 z-50 text-xs font-medium">
                <button
                  onClick={() => {
                    setTheme('light');
                    setShowThemeMenu(false);
                  }}
                  className={`w-full px-3 py-1.5 text-left flex items-center gap-2 hover:bg-surface-muted ${
                    theme === 'light' ? 'text-primary font-semibold' : 'text-foreground'
                  }`}
                >
                  <Sun className="w-3.5 h-3.5 text-amber-600" />
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
                  <Moon className="w-3.5 h-3.5 text-amber-400" />
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
      </div>
    </header>
  );
};
