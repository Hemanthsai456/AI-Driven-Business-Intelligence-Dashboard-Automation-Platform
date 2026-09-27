'use client';

import React, { useState, useRef } from 'react';
import { UploadCloud, FileSpreadsheet, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react';
import { Button } from './Button';
import { uploadDataset } from '../lib/api';
import { DatasetMetadata } from '../lib/types';

interface FileUploaderProps {
  onUploadSuccess: (metadata: DatasetMetadata) => void;
}

export const FileUploader: React.FC<FileUploaderProps> = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedDataset, setUploadedDataset] = useState<DatasetMetadata | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndUpload = async (file: File) => {
    setError(null);
    setUploadedDataset(null);

    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.csv', '.tsv', '.xlsx', '.parquet'].includes(ext)) {
      setError(`Invalid file format '${ext}'. Supported formats: CSV, TSV, XLSX, Parquet.`);
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError('Maximum file size is 100 MB.');
      return;
    }

    setIsUploading(true);
    try {
      const metadata = await uploadDataset(file);
      setUploadedDataset(metadata);
      onUploadSuccess(metadata);
    } catch (err: any) {
      setError(err.message || 'Failed to upload and process dataset.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndUpload(e.target.files[0]);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-sky-500 bg-sky-500/10 scale-[1.01]'
            : 'border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/80'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.parquet"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="p-4 bg-slate-800/80 rounded-full border border-slate-700 text-sky-400">
            {isUploading ? (
              <svg className="animate-spin w-8 h-8 text-sky-400" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <UploadCloud className="w-8 h-8" />
            )}
          </div>

          <div>
            <h3 className="text-base font-semibold text-slate-200">
              {isUploading ? 'Ingesting & Profiling Dataset...' : 'Upload Dataset'}
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              Drag and drop your file here, or click to browse from disk
            </p>
          </div>

          <div className="flex items-center space-x-2 text-[11px] text-slate-500 font-mono">
            <span>Supported formats: CSV, TSV, XLSX, Parquet</span>
            <span>•</span>
            <span>Maximum file size: 100 MB</span>
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start space-x-3 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-rose-200">Ingestion Error</h4>
            <p className="text-xs mt-1 text-rose-300">{error}</p>
          </div>
        </div>
      )}

      {/* Success Notification */}
      {uploadedDataset && (
        <div className="p-5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-center justify-between text-slate-200">
          <div className="flex items-center space-x-3">
            <CheckCircle2 className="w-6 h-6 text-emerald-400 flex-shrink-0" />
            <div>
              <h4 className="font-semibold text-emerald-200">{uploadedDataset.filename} Ingested Successfully</h4>
              <p className="text-xs text-slate-400 mt-0.5">
                {uploadedDataset.row_count.toLocaleString()} rows • {uploadedDataset.column_count} columns • {uploadedDataset.source_type.toUpperCase()}
              </p>
            </div>
          </div>
          <Button
            onClick={() => (window.location.href = `/analysis?id=${uploadedDataset.dataset_id}`)}
            variant="primary"
            size="sm"
          >
            <span>Continue to Dataset Analysis</span>
            <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      )}
    </div>
  );
};
