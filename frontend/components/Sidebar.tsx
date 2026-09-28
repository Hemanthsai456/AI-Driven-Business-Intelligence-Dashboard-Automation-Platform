'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  FileSpreadsheet,
  BarChart3,
  Settings,
  Sparkles,
  Terminal,
} from 'lucide-react';

const navItems = [
  { href: '/', label: 'Home', icon: LayoutDashboard },
  { href: '/ask', label: 'Ask (NL Query)', icon: Sparkles },
  { href: '/upload', label: 'Upload Dataset', icon: FileSpreadsheet },
  { href: '/analysis', label: 'Analysis Workspace', icon: BarChart3 },
  { href: '/plan-runner', label: 'Plan Runner', icon: Terminal },
  { href: '/settings', label: 'Settings', icon: Settings },
];



export const Sidebar: React.FC = () => {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col justify-between h-screen sticky top-0">
      <div>
        {/* Brand Header */}
        <div className="px-6 py-5 border-b border-slate-800/80 flex items-center space-x-3">
          <div className="p-2 bg-gradient-to-tr from-sky-600 to-indigo-600 rounded-lg shadow-md shadow-sky-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-wide text-slate-100">AI BI Platform</h1>
            <span className="text-[10px] text-sky-400 font-mono tracking-wider uppercase">Phase 1 Engine</span>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="p-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center space-x-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/80'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-sky-400' : 'text-slate-500'}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Capabilities Summary Footer */}
      <div className="p-4 m-4 bg-slate-900/80 border border-slate-800 rounded-xl">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300 mb-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Active Engine Features</span>
        </div>
        <ul className="text-[11px] text-slate-400 space-y-1 pl-3.5 list-disc font-mono">
          <li>CSV / XLSX Ingestion</li>
          <li>Data Profiler</li>
          <li>Semantic Evidence</li>
          <li>Schema Readiness</li>
        </ul>
      </div>
    </aside>
  );
};
