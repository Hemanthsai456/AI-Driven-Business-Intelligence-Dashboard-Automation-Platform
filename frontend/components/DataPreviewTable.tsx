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
      <div className="p-8 text-center text-xs text-muted-foreground bg-surface rounded-lg border border-border">
        No dataset rows available for preview.
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
      {/* Header */}
      <div className="p-3 bg-surface-muted/60 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Table className="w-4 h-4 text-primary" />
          <h3 className="text-xs font-semibold text-foreground">Dataset Preview</h3>
        </div>
        <Badge variant="blue" size="xs">
          Showing {preview.preview_rows_count} of {preview.total_rows.toLocaleString()} Rows
        </Badge>
      </div>

      {/* Table scroll container */}
      <div className="overflow-x-auto max-h-96">
        <table className="w-full text-left border-collapse text-xs font-mono">
          <thead>
            <tr className="bg-surface-muted/80 border-b border-border text-muted-foreground uppercase text-2xs tracking-wider sticky top-0">
              <th className="py-2 px-3 font-semibold text-muted-foreground border-r border-border/60 w-12 text-center">
                #
              </th>
              {preview.columns.map((col) => (
                <th
                  key={col}
                  className="py-2 px-3 font-semibold text-foreground border-r border-border/60 last:border-r-0"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border text-foreground">
            {preview.rows.map((row, idx) => (
              <tr key={idx} className="hover:bg-surface-muted/40 transition-colors">
                <td className="py-1.5 px-3 text-muted-foreground border-r border-border/60 text-center text-2xs">
                  {idx + 1}
                </td>
                {preview.columns.map((col) => {
                  const val = row[col];
                  const isNull = val === null || val === undefined;

                  return (
                    <td
                      key={col}
                      className="py-1.5 px-3 border-r border-border/60 last:border-r-0 whitespace-nowrap truncate max-w-xs"
                    >
                      {isNull ? (
                        <span className="text-rose-500 font-semibold italic text-2xs">
                          null
                        </span>
                      ) : typeof val === 'boolean' ? (
                        <span className={val ? 'text-emerald-500' : 'text-rose-500'}>
                          {String(val)}
                        </span>
                      ) : (
                        <span>{String(val)}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
