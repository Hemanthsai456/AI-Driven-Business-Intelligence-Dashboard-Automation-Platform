'use client';

import React, { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/Button';
import { listDatasets, runPlan, validatePlan } from '@/lib/api';
import { DatasetListItem, Pass1aResult, PlanRunResponse } from '@/lib/types';
import {
  Play,
  CheckCircle2,
  XCircle,
  Code,
  Terminal,
  ShieldCheck,
} from 'lucide-react';

export default function PlanRunnerPage() {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [planJson, setPlanJson] = useState<string>('');
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [validationResult, setValidationResult] = useState<Pass1aResult | null>(null);
  const [runResponse, setRunResponse] = useState<PlanRunResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const list = await listDatasets();
        setDatasets(list);
        if (list.length > 0) {
          setSelectedDatasetId(list[0].dataset_id);
          populateSamplePlan(list[0].dataset_id);
        }
      } catch (err: any) {
        console.error('Failed to load datasets:', err);
      }
    }
    loadData();
  }, []);

  const populateSamplePlan = (dsId: string) => {
    const sample = {
      dataset_id: dsId,
      intent: 'Total metric summary by dimension',
      metric: {
        column: 'Revenue',
        aggregation: 'SUM',
      },
      dimensions: [
        {
          column: 'Category',
        },
      ],
      filters: [],
      visualization: 'BAR',
      reasoning: {
        interpretation: 'Aggregated revenue broken down by categorical dimension',
        evidence: ['Standard dimension aggregation plan'],
      },
    };
    setPlanJson(JSON.stringify(sample, null, 2));
  };

  const handleDatasetChange = (newId: string) => {
    setSelectedDatasetId(newId);
    try {
      const parsed = JSON.parse(planJson);
      parsed.dataset_id = newId;
      setPlanJson(JSON.stringify(parsed, null, 2));
    } catch {
      populateSamplePlan(newId);
    }
  };

  const handleValidate = async () => {
    setErrorMsg(null);
    setValidationResult(null);
    setIsValidating(true);
    try {
      const parsedPlan = JSON.parse(planJson);
      const res = await validatePlan(parsedPlan);
      setValidationResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'JSON parse error or validation request failed');
    } finally {
      setIsValidating(false);
    }
  };

  const handleRun = async () => {
    setErrorMsg(null);
    setRunResponse(null);
    setIsRunning(true);
    try {
      const parsedPlan = JSON.parse(planJson);
      const res = await runPlan(parsedPlan);
      setRunResponse(res);
      setValidationResult(res.pass1a);
    } catch (err: any) {
      setErrorMsg(err.message || 'Plan execution request failed');
    } finally {
      setIsRunning(false);
    }
  };

  const pass1aPassed = validationResult?.passed ?? runResponse?.pass1a?.passed;
  const executionSuccess = runResponse?.execution?.status === 'SUCCESS';
  const pass1bPassed = runResponse?.pass1b?.passed;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="pb-2 border-b border-border">
        <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <Terminal className="w-5 h-5 text-[#EA6928]" />
          Plan Runner
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Execute candidate plan schemas through Pass 1a validation, DuckDB SQL compilation, and Pass 1b result verification.
        </p>
      </div>

      {errorMsg && <Alert variant="error" title="Execution Error" message={errorMsg} />}

      {/* Main Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: JSON Editor (5 Cols) */}
        <div className="lg:col-span-5 space-y-4">
          <Card
            title="CandidatePlan Editor"
            subtitle="Strict schema adherence: schemas/candidate_plan.schema.json"
            headerAction={
              <Button
                size="xs"
                variant="outline"
                onClick={() => {
                  try {
                    setPlanJson(JSON.stringify(JSON.parse(planJson), null, 2));
                  } catch {}
                }}
              >
                Format JSON
              </Button>
            }
          >
            <div className="space-y-3">
              <div>
                <label className="block text-2xs font-semibold text-muted-foreground uppercase font-mono mb-1">
                  Target Dataset
                </label>
                <select
                  value={selectedDatasetId}
                  onChange={(e) => handleDatasetChange(e.target.value)}
                  className="w-full text-xs bg-surface border border-border rounded px-2.5 py-1.5 text-foreground font-mono focus:outline-none focus:border-[#EA6928]"
                >
                  {datasets.map((d) => (
                    <option key={d.dataset_id} value={d.dataset_id}>
                      {d.filename} ({d.row_count} rows)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-2xs font-semibold text-muted-foreground uppercase font-mono mb-1">
                  Plan Schema Definition
                </label>
                <textarea
                  value={planJson}
                  onChange={(e) => setPlanJson(e.target.value)}
                  rows={13}
                  className="w-full text-xs font-mono bg-surface border border-border rounded p-2.5 text-foreground focus:outline-none focus:border-[#EA6928] leading-relaxed"
                  spellCheck={false}
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleValidate}
                  isLoading={isValidating}
                  disabled={isRunning}
                  leftIcon={<ShieldCheck className="w-3.5 h-3.5" />}
                >
                  Validate (Pass 1a)
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRun}
                  isLoading={isRunning}
                  disabled={isValidating}
                  leftIcon={<Play className="w-3.5 h-3.5" />}
                >
                  Run Plan
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Right: Steps Timeline & Execution Result (7 Cols) */}
        <div className="lg:col-span-7 space-y-4">
          <Card title="Execution Validation Stages" subtitle="Pass 1 deterministic execution lifecycle">
            <div className="space-y-4 pt-1 font-mono text-xs">
              {/* Step 1: Pass 1a */}
              <div className="flex items-start gap-3">
                <div
                  className={`w-6 h-6 rounded flex items-center justify-center shrink-0 text-xs font-bold ${
                    pass1aPassed === true
                      ? 'bg-emerald-600 text-white'
                      : pass1aPassed === false
                      ? 'bg-rose-600 text-white'
                      : 'bg-[#E6D4B8] text-muted-foreground'
                  }`}
                >
                  {pass1aPassed === true ? '✓' : pass1aPassed === false ? '✕' : '1'}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">Pass 1a: Static Schema Validation</span>
                    <Badge
                      variant={pass1aPassed === true ? 'green' : pass1aPassed === false ? 'red' : 'slate'}
                      size="xs"
                    >
                      {pass1aPassed === true ? 'PASSED' : pass1aPassed === false ? 'FAILED' : 'WAITING'}
                    </Badge>
                  </div>
                  <p className="text-2xs text-muted-foreground mt-0.5">
                    Validates schema structure, column presence, aggregation compatibility, and null rules.
                  </p>
                </div>
              </div>

              <div className="h-4 w-px bg-border ml-3 -my-2" />

              {/* Step 2: DuckDB Execution */}
              <div className="flex items-start gap-3">
                <div
                  className={`w-6 h-6 rounded flex items-center justify-center shrink-0 text-xs font-bold ${
                    executionSuccess === true
                      ? 'bg-emerald-600 text-white'
                      : runResponse?.execution?.status && runResponse.execution.status !== 'SUCCESS'
                      ? 'bg-rose-600 text-white'
                      : 'bg-[#E6D4B8] text-muted-foreground'
                  }`}
                >
                  {executionSuccess === true ? '✓' : runResponse?.execution?.status ? '✕' : '2'}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">DuckDB Sandboxed Execution</span>
                    <Badge
                      variant={
                        executionSuccess
                          ? 'green'
                          : runResponse?.execution?.status
                          ? 'red'
                          : 'slate'
                      }
                      size="xs"
                    >
                      {runResponse?.execution?.status || 'PENDING'}
                    </Badge>
                  </div>
                  <p className="text-2xs text-muted-foreground mt-0.5">
                    Executes with sandbox limits: 256MB RAM cap, 1 worker thread, 30s timeout.
                  </p>
                  {runResponse?.execution?.runtime_seconds !== undefined && (
                    <div className="text-2xs text-[#EA6928] mt-1 font-semibold">
                      Runtime: {(runResponse.execution.runtime_seconds * 1000).toFixed(1)}ms
                    </div>
                  )}
                </div>
              </div>

              <div className="h-4 w-px bg-border ml-3 -my-2" />

              {/* Step 3: Pass 1b */}
              <div className="flex items-start gap-3">
                <div
                  className={`w-6 h-6 rounded flex items-center justify-center shrink-0 text-xs font-bold ${
                    pass1bPassed === true
                      ? 'bg-emerald-600 text-white'
                      : pass1bPassed === false
                      ? 'bg-rose-600 text-white'
                      : 'bg-[#E6D4B8] text-muted-foreground'
                  }`}
                >
                  {pass1bPassed === true ? '✓' : pass1bPassed === false ? '✕' : '3'}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">Pass 1b: Result Set Verification</span>
                    <Badge
                      variant={pass1bPassed === true ? 'green' : pass1bPassed === false ? 'red' : 'slate'}
                      size="xs"
                    >
                      {pass1bPassed === true ? 'PASSED' : pass1bPassed === false ? 'FAILED' : 'PENDING'}
                    </Badge>
                  </div>
                  <p className="text-2xs text-muted-foreground mt-0.5">
                    Enforces 50,000 row cap and max 50% failed datetime cast rate.
                  </p>
                </div>
              </div>
            </div>
          </Card>

          {/* Compiled SQL Query */}
          {runResponse?.execution?.compiled_sql && (
            <Card title="Compiled SQL" subtitle="Generated DuckDB query">
              <pre className="p-3 bg-[#E6D4B8]/30 rounded text-2xs font-mono text-foreground overflow-x-auto border border-border">
                <code>{runResponse.execution.compiled_sql}</code>
              </pre>
            </Card>
          )}

          {/* Result Data Rows */}
          {runResponse?.execution?.rows && (
            <Card
              title="Execution Output Preview"
              subtitle={`${runResponse.execution.row_count} rows returned`}
              padding="none"
            >
              <div className="overflow-x-auto max-h-60">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border bg-[#E6D4B8]/40 text-2xs uppercase text-muted-foreground">
                      {runResponse.execution.columns.map((c) => (
                        <th key={c} className="py-2 px-3 font-semibold text-foreground">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {runResponse.execution.rows.slice(0, 8).map((r, i) => (
                      <tr key={i} className="hover:bg-[#E6D4B8]/20">
                        {runResponse.execution!.columns.map((c) => (
                          <td key={c} className="py-1.5 px-3 text-muted-foreground whitespace-nowrap">
                            {r[c] !== null && r[c] !== undefined ? String(r[c]) : <span className="text-rose-600 italic">null</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
