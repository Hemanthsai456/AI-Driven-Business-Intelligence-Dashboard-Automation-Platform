'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Header } from '../../components/Header';
import { FileUploader } from '../../components/FileUploader';
import { Card } from '../../components/Card';
import { FileSpreadsheet, ShieldCheck, Check } from 'lucide-react';
import { DatasetMetadata } from '../../lib/types';

export default function UploadPage() {
  const router = useRouter();

  const handleUploadSuccess = (metadata: DatasetMetadata) => {
    router.push(`/analysis?id=${metadata.dataset_id}`);
  };

  return (
    <div className="flex-1 flex flex-col min-h-screen">

      <div className="p-8 max-w-4xl mx-auto w-full space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Upload Dataset</h1>
          <p className="text-xs text-slate-400 mt-1">
            Ingest real CSV, TSV, XLSX, or Parquet files into the Python intelligence engine for profiling and semantic analysis.
          </p>
        </div>

        <FileUploader onUploadSuccess={handleUploadSuccess} />

        {/* Guidelines Card */}
        <Card title="Ingestion Engine Expectations" subtitle="Deterministic loader specifications">
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-300 font-mono">
            <li className="flex items-start space-x-2">
              <Check className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
              <span>Standard CSV and TSV files (comma or tab separated, UTF-8/Latin1 encodings)</span>
            </li>
            <li className="flex items-start space-x-2">
              <Check className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
              <span>Single-sheet Excel (.xlsx) workbooks and Apache Parquet (.parquet) files</span>
            </li>
            <li className="flex items-start space-x-2">
              <Check className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
              <span>Automatic duplicate header disambiguation (e.g. col_1, col_2)</span>
            </li>
            <li className="flex items-start space-x-2">
              <Check className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
              <span>Preserves original column names & produces clean normalized names</span>
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
