'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeProvider';
import {
  LayoutDashboard,
  Sparkles,
  UploadCloud,
  BarChart3,
  Terminal,
  Settings,
} from 'lucide-react';

const NAV_ITEMS = [
  { href: '/', label: 'Home', icon: LayoutDashboard },
  { href: '/ask', label: 'Ask (NL Query)', icon: Sparkles },
  { href: '/upload', label: 'Upload Dataset', icon: UploadCloud },
  { href: '/analysis', label: 'Analysis Workspace', icon: BarChart3 },
  { href: '/plan-runner', label: 'Plan Runner', icon: Terminal },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const { sidebarCollapsed } = useTheme();

  return (
    <aside
      className={`bg-[#212121] text-[#F5EBE1] flex flex-col justify-between h-screen sticky top-0 transition-all duration-200 select-none z-40 border-r border-[#333333] ${
        sidebarCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      <div>
        {/* Brand Header */}
        <div className="h-14 px-4 border-b border-[#333333] flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-[#EA6928] text-white flex items-center justify-center shrink-0 font-bold text-xs">
            BI
          </div>
          {!sidebarCollapsed && (
            <div className="min-w-0">
              <h1 className="font-bold text-xs tracking-tight text-white truncate">
                AI BI Platform
              </h1>
              <span className="text-2xs text-[#A89D91] uppercase tracking-wider block font-mono">
                Enterprise Studio
              </span>
            </div>
          )}
        </div>

        {/* Navigation Items */}
        <nav className="p-2 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href ||
              (item.href !== '/' && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                title={sidebarCollapsed ? item.label : undefined}
                className={`flex items-center gap-3 px-3 py-2 rounded text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-[#2E2B27] text-white font-semibold border-l-3 border-[#EA6928]'
                    : 'text-[#A89D91] hover:text-white hover:bg-[#2A2A2A]'
                } ${sidebarCollapsed ? 'justify-center px-0' : ''}`}
              >
                <Icon
                  className={`w-4 h-4 shrink-0 transition-colors ${
                    isActive ? 'text-[#EA6928]' : 'text-[#A89D91]'
                  }`}
                />
                {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Capabilities Summary Footer */}
      <div className="p-3 border-t border-[#333333]">
        {!sidebarCollapsed ? (
          <div className="p-2.5 bg-[#2A2A2A] rounded border border-[#3A3530] text-2xs space-y-1">
            <div className="flex items-center justify-between text-[#A89D91] font-mono">
              <span>Engine Status</span>
              <span className="flex items-center gap-1 text-emerald-400 font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Active
              </span>
            </div>
            <p className="text-[#8E8377] font-mono truncate">
              Deterministic DuckDB v1
            </p>
          </div>
        ) : (
          <div className="flex justify-center" title="Engine Active">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
          </div>
        )}
      </div>
    </aside>
  );
};
