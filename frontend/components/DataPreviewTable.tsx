'use client';

import React from 'react';
import { Table, Eye } from 'lucide-react';
import { DataPreviewResponse } from '../lib/types';
import { Badge } from './Badge';

interface DataPreviewTableProps {
  preview: DataPreviewResponse;
}

export const DataPreviewTable: React.FC<DataPreviewTableProps> = ({ preview }) => {
  if (!preview || preview.rows.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800">
        No dataset rows available for preview.
      </div>
    );
  }

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
      {/* Header */}
      <div className="p-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Table className="w-4 h-4 text-sky-400" />
          <h3 className="text-sm font-semibold text-slate-200">Dataset Preview</h3>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="blue" size="sm">
            <Eye className="w-3 h-3 mr-1 inline" />
            Showing {preview.preview_rows_count} of {preview.total_rows.toLocaleString()} Rows
          </Badge>
        </div>
      </div>

      {/* Table scroll container */}
      <div className="overflow-x-auto max-h-96">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase font-mono text-[10px] tracking-wider sticky top-0">
              <th className="py-2.5 px-4 font-semibold text-slate-500 border-r border-slate-800/80 w-12 text-center">#</th>
              {preview.columns.map((col) => (
                <th key={col} className="py-2.5 px-4 font-semibold text-slate-300 border-r border-slate-800/80 last:border-r-0">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
            {preview.rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                <td className="py-2 px-4 text-slate-500 border-r border-slate-800/60 text-center text-[10px]">
                  {idx + 1}
                </td>
                {preview.columns.map((col) => {
                  const val = row[col];
                  const isNull = val === null || val === undefined;

                  return (
                    <td
                      key={col}
                      className={`py-2 px-4 border-r border-slate-800/60 last:border-r-0 whitespace-nowrap ${
                        isNull ? 'text-slate-600 italic' : ''
                      }`}
                    >
                      {isNull ? 'null' : String(val)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer note */}
      <div className="p-3 bg-slate-950/60 border-t border-slate-800 text-center text-[11px] text-slate-500">
        Preview limited to the first {preview.preview_rows_count} rows for browser performance.
      </div>
    </div>
  );
};
