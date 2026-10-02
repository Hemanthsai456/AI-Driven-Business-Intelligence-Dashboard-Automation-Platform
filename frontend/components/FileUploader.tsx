'use client';

import React, { useState, useRef } from 'react';
import { UploadCloud, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react';
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
        className={`border-2 border-dashed rounded-card p-10 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-primary bg-primary-soft/50 scale-[1.01]'
            : 'border-border bg-surface hover:border-primary hover:bg-surface-muted'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.parquet"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center space-y-3">
          <div className="p-3 bg-primary-soft rounded-full text-primary border border-primary/20">
            {isUploading ? (
              <svg className="animate-spin w-6 h-6 text-primary" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <UploadCloud className="w-6 h-6" />
            )}
          </div>

          <div>
            <h3 className="text-sm font-semibold text-foreground">
              {isUploading ? 'Ingesting & Profiling Dataset...' : 'Upload Dataset'}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">
              Drag and drop your file here, or click to browse from disk
            </p>
          </div>

          <div className="flex items-center space-x-2 text-2xs text-muted-foreground font-mono">
            <span>CSV, TSV, XLSX, Parquet</span>
            <span>•</span>
            <span>Up to 100 MB</span>
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-3 bg-error-soft border border-error/30 rounded-card flex items-start gap-2.5 text-xs text-error">
          <AlertCircle className="w-4 h-4 text-error shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">Ingestion Error</div>
            <p className="mt-0.5 opacity-90">{error}</p>
          </div>
        </div>
      )}

      {/* Success Notification */}
      {uploadedDataset && (
        <div className="p-4 bg-success-soft border border-success/30 rounded-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
            <div>
              <div className="font-semibold text-foreground">
                {uploadedDataset.filename} Ingested Successfully
              </div>
              <p className="text-2xs text-muted-foreground font-mono mt-0.5">
                {uploadedDataset.row_count.toLocaleString()} rows • {uploadedDataset.column_count} columns • {uploadedDataset.source_type.toUpperCase()}
              </p>
            </div>
          </div>
          <Button
            onClick={() => (window.location.href = `/analysis?id=${uploadedDataset.dataset_id}`)}
            variant="primary"
            size="sm"
            rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
          >
            Continue to Analysis
          </Button>
        </div>
      )}
    </div>
  );
};
