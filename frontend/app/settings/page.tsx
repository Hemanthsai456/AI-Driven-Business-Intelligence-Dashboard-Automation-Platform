'use client';

import React from 'react';
import { Header } from '../../components/Header';
import { Card } from '../../components/Card';
import { Badge } from '../../components/Badge';
import { Settings, Server, ShieldCheck, Database, Check } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <Header />

      <div className="p-8 max-w-4xl mx-auto w-full space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Settings & Architecture Overview</h1>
          <p className="text-xs text-slate-400 mt-1">
            Environment parameters and development-stage system specifications.
          </p>
        </div>

        {/* API Backend Details */}
        <Card title="Backend API Layer" subtitle="FastAPI HTTP Service Context">
          <div className="space-y-3 text-xs font-mono">
            <div className="flex items-center justify-between p-3 bg-slate-950/80 rounded-lg border border-slate-800">
              <span className="text-slate-400">API Target URL:</span>
              <span className="text-sky-400 font-bold">http://localhost:8000/api</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-950/80 rounded-lg border border-slate-800">
              <span className="text-slate-400">Target Framework:</span>
              <span className="text-slate-200">FastAPI (Python 3.11) + Next.js App Router</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-950/80 rounded-lg border border-slate-800">
              <span className="text-slate-400">Storage Architecture:</span>
              <Badge variant="amber">In-Memory Session Store (Development Stage)</Badge>
            </div>
          </div>
        </Card>

        {/* System Capabilities Matrix */}
        <Card title="Locked Engine Capabilities" subtitle="Source-of-truth Python package exports">
          <ul className="space-y-2 text-xs text-slate-300 font-mono">
            <li className="flex items-center space-x-2 p-2 bg-slate-950/60 rounded border border-slate-800">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Step 1 — Canonical Data Model (CanonicalDataset, ColumnMetadata, DataProfile)</span>
            </li>
            <li className="flex items-center space-x-2 p-2 bg-slate-950/60 rounded border border-slate-800">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Step 2 — Ingestion Loaders (CSVLoader, TSVLoader, ExcelLoader, ParquetLoader)</span>
            </li>
            <li className="flex items-center space-x-2 p-2 bg-slate-950/60 rounded border border-slate-800">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Step 3 — Deterministic Data Profiling Engine (DataProfiler)</span>
            </li>
            <li className="flex items-center space-x-2 p-2 bg-slate-950/60 rounded border border-slate-800">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Step 4 — Rule-Based Semantic Intelligence (SemanticAnalyzer)</span>
            </li>
            <li className="flex items-center space-x-2 p-2 bg-slate-950/60 rounded border border-slate-800">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>Step 4.2 — Schema Validation & Analysis-Readiness (SchemaValidator)</span>
            </li>
          </ul>
        </Card>

        {/* Development Storage Limitations */}
        <Card title="Development-Stage Limitations Notice" subtitle="Phase 1 Architecture Boundary">
          <p className="text-xs text-slate-400 leading-relaxed">
            Uploaded datasets are stored in-memory in the FastAPI application process for the duration of the server session. Storage interfaces are strictly decoupled so persistent storage (PostgreSQL / Object Storage) can be plugged in later without altering frontend API contracts.
          </p>
        </Card>
      </div>
    </div>
  );
}
