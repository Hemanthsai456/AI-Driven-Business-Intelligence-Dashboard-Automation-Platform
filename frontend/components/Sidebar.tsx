'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeProvider';
import {
  LayoutDashboard,
  Sparkles,
  BarChart3,
  LineChart,
  Database,
  UploadCloud,
  Layers,
  Brain,
  Terminal,
  Settings,
  ChevronRight,
} from 'lucide-react';

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: 'WORKSPACE',
    items: [
      { href: '/', label: 'Overview', icon: LayoutDashboard },
      { href: '/ask', label: 'Ask AI', icon: Sparkles, badge: 'NL' },
      { href: '/analysis', label: 'Analysis', icon: BarChart3 },
      { href: '/dashboards', label: 'Dashboards', icon: LineChart },
    ],
  },
  {
    title: 'DATA',
    items: [
      { href: '/datasets', label: 'Datasets', icon: Database },
      { href: '/upload', label: 'Upload Dataset', icon: UploadCloud },
    ],
  },
  {
    title: 'INTELLIGENCE',
    items: [
      { href: '/analysis?tab=profile', label: 'Data Profiling', icon: Layers },
      { href: '/analysis?tab=semantic', label: 'Semantic Layer', icon: Brain },
    ],
  },
  {
    title: 'WORKFLOW',
    items: [
      { href: '/plan-runner', label: 'Plan Runner', icon: Terminal },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { href: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const { sidebarCollapsed } = useTheme();

  return (
    <aside
      className={`bg-surface border-r border-border flex flex-col justify-between h-screen sticky top-0 transition-all duration-200 select-none z-40 ${
        sidebarCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Brand Header */}
      <div>
        <div className="h-13 px-4 border-b border-border flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          {!sidebarCollapsed && (
            <div className="min-w-0">
              <h1 className="font-bold text-xs tracking-tight text-foreground truncate">
                AI BI Platform
              </h1>
              <span className="text-2xs text-muted-foreground font-mono tracking-wider uppercase block">
                Enterprise Studio
              </span>
            </div>
          )}
        </div>

        {/* Navigation Sections */}
        <nav className="p-2 space-y-4 overflow-y-auto max-h-[calc(100vh-8rem)]">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="space-y-1">
              {!sidebarCollapsed && (
                <div className="px-2.5 py-1 text-2xs font-semibold text-muted-foreground/70 uppercase tracking-wider font-mono">
                  {section.title}
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const itemPath = item.href.split('?')[0];
                  const isActive =
                    pathname === itemPath ||
                    (itemPath !== '/' && pathname.startsWith(itemPath));

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={sidebarCollapsed ? item.label : undefined}
                      className={`group flex items-center gap-2.5 px-2.5 py-1.5 rounded text-xs font-medium transition-colors relative ${
                        isActive
                          ? 'bg-primary/10 text-primary font-semibold border-l-2 border-primary'
                          : 'text-muted-foreground hover:text-foreground hover:bg-surface-muted'
                      } ${sidebarCollapsed ? 'justify-center px-0' : ''}`}
                    >
                      <Icon
                        className={`w-4 h-4 shrink-0 transition-colors ${
                          isActive
                            ? 'text-primary'
                            : 'text-muted-foreground group-hover:text-foreground'
                        }`}
                      />
                      {!sidebarCollapsed && (
                        <div className="flex-1 flex items-center justify-between min-w-0">
                          <span className="truncate">{item.label}</span>
                          {item.badge && (
                            <span className="px-1.5 py-0.2 rounded text-2xs font-mono font-bold bg-primary/10 text-primary border border-primary/20">
                              {item.badge}
                            </span>
                          )}
                        </div>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      {/* Engine Status Footer */}
      <div className="p-3 border-t border-border">
        {!sidebarCollapsed ? (
          <div className="p-2.5 bg-surface-muted rounded-md border border-border">
            <div className="flex items-center justify-between">
              <span className="text-2xs font-mono font-semibold text-muted-foreground">
                Engine Core
              </span>
              <span className="flex items-center gap-1 text-2xs font-mono text-emerald-600 dark:text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Active
              </span>
            </div>
            <p className="text-2xs text-muted-foreground mt-1 truncate">
              Pass 1/2 Orchestrator v1
            </p>
          </div>
        ) : (
          <div className="flex justify-center" title="Engine Core Active">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
          </div>
        )}
      </div>
    </aside>
  );
};
