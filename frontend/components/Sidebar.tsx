'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeProvider';
import {
  LayoutDashboard,
  UploadCloud,
  BarChart3,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Settings,
  ChevronDown,
  ChevronRight,
  Database,
} from 'lucide-react';

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const WORKSPACE_NAV: NavItem[] = [
  { href: '/', label: 'Home', icon: LayoutDashboard },
  { href: '/upload', label: 'Upload Dataset', icon: UploadCloud },
  { href: '/data-studio', label: 'Data Studio', icon: SlidersHorizontal },
  { href: '/analysis', label: 'Analysis Workspace', icon: BarChart3 },
];

const ADVANCED_NAV: NavItem[] = [
  { href: '/settings', label: 'Settings', icon: Settings },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const { sidebarCollapsed } = useTheme();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Auto-expand advanced if current route is within advanced nav
  const isAdvancedActive = ADVANCED_NAV.some(
    (item) => pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
  );

  return (
    <aside
      className={`bg-surface text-foreground flex flex-col justify-between h-screen sticky top-0 transition-all duration-200 select-none z-40 border-r border-border shrink-0 ${
        sidebarCollapsed ? 'w-16' : 'w-60'
      } max-[900px]:w-16 max-[640px]:hidden`}
    >
      <div className="flex flex-col flex-1 min-h-0">
        {/* Brand Header */}
        <div className="h-14 px-4 border-b border-border flex items-center gap-3 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center shrink-0 font-bold text-xs shadow-xs tracking-wider">
            DC
          </div>
          <div className={`min-w-0 flex-1 ${sidebarCollapsed ? 'hidden' : 'block max-[900px]:hidden'}`}>
            <h1 className="font-bold text-xs tracking-tight text-foreground truncate">
              DashCrate
            </h1>
            <span className="text-2xs text-muted-foreground uppercase tracking-wider block font-mono truncate">
              Business Intelligence
            </span>
          </div>
        </div>

        {/* Navigation Groups */}
        <div className="flex-1 overflow-y-auto p-2 space-y-4">
          {/* Workspace Group */}
          <div>
            <div
              className={`px-2.5 pb-1 text-2xs font-semibold text-muted-foreground uppercase tracking-wider font-mono ${
                sidebarCollapsed ? 'hidden' : 'block max-[900px]:hidden'
              }`}
            >
              Workspace
            </div>
            <nav className="space-y-0.5">
              {WORKSPACE_NAV.map((item) => {
                const Icon = item.icon;
                const isActive =
                  pathname === item.href ||
                  (item.href !== '/' && pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={sidebarCollapsed ? item.label : undefined}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                      isActive
                        ? 'bg-primary-soft text-primary font-semibold border-l-[3px] border-primary'
                        : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
                    } ${sidebarCollapsed ? 'justify-center px-0' : 'max-[900px]:justify-center max-[900px]:px-0'}`}
                  >
                    <Icon
                      className={`w-4 h-4 shrink-0 transition-colors ${
                        isActive ? 'text-primary' : 'text-muted-foreground'
                      }`}
                    />
                    <span
                      className={`truncate ${
                        sidebarCollapsed ? 'hidden' : 'block max-[900px]:hidden'
                      }`}
                    >
                      {item.label}
                    </span>
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Advanced Group (Collapsed by default) */}
          <div>
            <button
              onClick={() => setAdvancedOpen((prev) => !prev)}
              className={`w-full flex items-center justify-between px-2.5 py-1 text-2xs font-semibold text-muted-foreground uppercase tracking-wider font-mono hover:text-foreground transition-colors ${
                sidebarCollapsed ? 'hidden' : 'flex max-[900px]:hidden'
              }`}
            >
              <span>Advanced</span>
              {advancedOpen || isAdvancedActive ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </button>

            {(advancedOpen || isAdvancedActive || sidebarCollapsed) && (
              <nav className="space-y-0.5 mt-0.5">
                {ADVANCED_NAV.map((item) => {
                  const Icon = item.icon;
                  const isActive =
                    pathname === item.href ||
                    (item.href !== '/' && pathname.startsWith(item.href));

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={sidebarCollapsed ? item.label : undefined}
                      className={`flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                        isActive
                          ? 'bg-primary-soft text-primary font-semibold border-l-[3px] border-primary'
                          : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
                      } ${sidebarCollapsed ? 'justify-center px-0' : 'max-[900px]:justify-center max-[900px]:px-0'}`}
                    >
                      <Icon
                        className={`w-4 h-4 shrink-0 transition-colors ${
                          isActive ? 'text-primary' : 'text-muted-foreground'
                        }`}
                      />
                      <span
                        className={`truncate ${
                          sidebarCollapsed ? 'hidden' : 'block max-[900px]:hidden'
                        }`}
                      >
                        {item.label}
                      </span>
                    </Link>
                  );
                })}
              </nav>
            )}
          </div>
        </div>

        {/* Footer Summary */}
        <div className="p-3 border-t border-border shrink-0">
          <div
            className={`p-2.5 bg-surface-muted rounded-card border border-border text-2xs space-y-1 ${
              sidebarCollapsed ? 'hidden' : 'block max-[900px]:hidden'
            }`}
          >
            <div className="flex items-center justify-between text-muted-foreground font-mono">
              <span>Engine</span>
              <span className="flex items-center gap-1 text-success font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-success" />
                Active
              </span>
            </div>
            <p className="text-muted-foreground font-mono truncate">
              DuckDB Analytics
            </p>
          </div>

          <div
            className={`flex justify-center ${
              sidebarCollapsed ? 'block' : 'hidden max-[900px]:flex'
            }`}
            title="Engine Active"
          >
            <span className="w-2 h-2 rounded-full bg-success" />
          </div>
        </div>
      </div>
    </aside>
  );
};
