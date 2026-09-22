'use client';

import React from 'react';
import { Database, CheckCircle2 } from 'lucide-react';
import { Badge } from './Badge';

interface HeaderProps {
  datasetName?: string;
  sourceType?: string;
  rowCount?: number;
  columnCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  datasetName,
  sourceType,
  rowCount,
  columnCount,
}) => {
  return (
    <header className="bg-slate-950/80 backdrop-blur-md border-b border-slate-800 px-8 py-4 flex items-center justify-between sticky top-0 z-10">
      <div className="flex items-center space-x-3">
        {datasetName ? (
          <>
            <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg text-slate-300">
              <Database className="w-4 h-4 text-sky-400" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-sm font-semibold text-slate-100">{datasetName}</h2>
                <Badge variant="blue" size="sm">{sourceType?.toUpperCase()}</Badge>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {rowCount?.toLocaleString()} rows • {columnCount} columns
              </p>
            </div>
          </>
        ) : (
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Business Intelligence Platform</h2>
            <p className="text-xs text-slate-400">Phase 1 Data Foundation & Semantic Intelligence</p>
          </div>
        )}
      </div>

      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full text-xs text-emerald-400 font-medium">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Backend Connected</span>
        </div>
      </div>
    </header>
  );
};
