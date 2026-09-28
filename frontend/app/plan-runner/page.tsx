'use client';

import React, { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/Button';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { listDatasets, runPlan, validatePlan } from '@/lib/api';
import { DatasetListItem, Pass1aResult, PlanRunResponse } from '@/lib/types';
import { Play, CheckCircle2, XCircle, Code, Clock, Table, Database } from 'lucide-react';

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <Play className="w-6 h-6 text-sky-400" />
            Deterministic Plan Runner
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Validate candidate analytical plans via Pass 1a, compile safe DuckDB SQL, execute, and verify via Pass 1b.
          </p>
        </div>
      </div>

      {errorMsg && <Alert variant="error" title="Operation Failed" message={errorMsg} />}

      {/* Dataset Selection & Plan Editor */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 space-y-4">
          <Card title="Dataset & Plan Configuration">
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                  Select Active Dataset
                </label>
                {datasets.length === 0 ? (
                  <div className="p-3 bg-slate-800/50 border border-slate-700/60 rounded-lg text-xs text-slate-400">
                    No active datasets found. Please upload a dataset first.
                  </div>
                ) : (
                  <select
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    value={selectedDatasetId}
                    onChange={(e) => handleDatasetChange(e.target.value)}
                  >
                    {datasets.map((d) => (
                      <option key={d.dataset_id} value={d.dataset_id}>
                        {d.filename} ({d.row_count} rows, {d.readiness_status})
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Candidate Plan JSON
                  </label>
                  <button
                    type="button"
                    onClick={() => populateSamplePlan(selectedDatasetId || 'dataset-id')}
                    className="text-xs text-sky-400 hover:text-sky-300"
                  >
                    Reset Sample Plan
                  </button>
                </div>
                <textarea
                  className="w-full h-80 bg-slate-950 font-mono text-xs text-slate-300 p-3 rounded-lg border border-slate-800 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  value={planJson}
                  onChange={(e) => setPlanJson(e.target.value)}
                  placeholder="Paste CandidatePlan JSON..."
                />
              </div>

              <div className="flex items-center gap-3 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleValidate}
                  isLoading={isValidating}
                  className="flex-1"
                >
                  <CheckCircle2 className="w-4 h-4 mr-1.5 text-sky-400" />
                  Validate Pass 1a
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRun}
                  isLoading={isRunning}
                  className="flex-1"
                >
                  <Play className="w-4 h-4 mr-1.5 text-white" />
                  Execute on DuckDB
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Validation & Execution Results */}
        <div className="lg:col-span-7 space-y-6">
          {/* Pass 1a Status */}
          {validationResult && (
            <Card
              title="Pass 1a Pre-Dispatch Validation"
              headerAction={
                validationResult.passed ? (
                  <Badge variant="green">PASSED</Badge>
                ) : (
                  <Badge variant="red">REJECTED</Badge>
                )
              }
            >
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span className="font-mono">Plan ID: {validationResult.plan_id}</span>
                </div>
                {validationResult.issues.length === 0 ? (
                  <p className="text-xs text-emerald-400">All pre-dispatch checks passed cleanly.</p>
                ) : (
                  <div className="space-y-2">
                    {validationResult.issues.map((issue, idx) => (
                      <div
                        key={idx}
                        className={`p-2.5 rounded-lg border text-xs flex items-start justify-between gap-3 ${
                          issue.status === 'FAILED'
                            ? 'bg-rose-500/10 border-rose-500/20 text-rose-300'
                            : issue.status === 'WARNING'
                            ? 'bg-amber-500/10 border-amber-500/20 text-amber-300'
                            : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
                        }`}
                      >
                        <div>
                          <span className="font-semibold uppercase tracking-wider text-[10px] block opacity-80">
                            {issue.check} {issue.column ? `(${issue.column})` : ''}
                          </span>
                          <span className="mt-0.5 block">{issue.message}</span>
                        </div>
                        <Badge
                          variant={
                            issue.status === 'FAILED'
                              ? 'red'
                              : issue.status === 'WARNING'
                              ? 'amber'
                              : 'green'
                          }
                          size="sm"
                        >
                          {issue.status}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* DuckDB Execution Result */}
          {runResponse?.execution && (
            <Card
              title="DuckDB Execution Results"
              headerAction={
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400 flex items-center gap-1 font-mono">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    {runResponse.execution.runtime_seconds}s
                  </span>
                  <Badge
                    variant={
                      runResponse.execution.status === 'SUCCESS' ? 'green' : 'red'
                    }
                  >
                    {runResponse.execution.status}
                  </Badge>
                </div>
              }
            >
              <div className="space-y-4">
                {/* Metrics / Cast stats */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg">
                    <span className="text-[10px] text-slate-400 uppercase font-mono block">Returned Rows</span>
                    <span className="text-lg font-bold text-slate-100">{runResponse.execution.row_count}</span>
                  </div>
                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg">
                    <span className="text-[10px] text-slate-400 uppercase font-mono block">Failed Datetime Casts</span>
                    <span className="text-lg font-bold text-slate-100">
                      {runResponse.execution.failed_cast_count}{' '}
                      <span className="text-xs font-normal text-slate-400">
                        ({(runResponse.execution.failed_cast_rate * 100).toFixed(1)}%)
                      </span>
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg">
                    <span className="text-[10px] text-slate-400 uppercase font-mono block">Pass 1b Status</span>
                    <span className="text-lg font-bold text-slate-100">
                      {runResponse.pass1b?.passed ? (
                        <span className="text-emerald-400 text-sm">VERIFIED</span>
                      ) : (
                        <span className="text-rose-400 text-sm">FAILED</span>
                      )}
                    </span>
                  </div>
                </div>

                {/* Compiled SQL */}
                {runResponse.execution.compiled_sql && (
                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 mb-1.5">
                      <Code className="w-3.5 h-3.5 text-sky-400" />
                      Compiled DuckDB SQL
                    </div>
                    <pre className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-sky-300 overflow-x-auto">
                      {runResponse.execution.compiled_sql}
                    </pre>
                  </div>
                )}

                {/* Result Table Preview */}
                {runResponse.execution.rows && runResponse.execution.rows.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 mb-2">
                      <Table className="w-3.5 h-3.5 text-indigo-400" />
                      Query Output Preview
                    </div>
                    <div className="border border-slate-800 rounded-lg overflow-x-auto max-h-60">
                      <table className="w-full text-xs text-left text-slate-300">
                        <thead className="bg-slate-950 text-slate-400 uppercase font-mono border-b border-slate-800 sticky top-0">
                          <tr>
                            {runResponse.execution.columns.map((col, idx) => (
                              <th key={idx} className="px-3 py-2 font-medium">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {runResponse.execution.rows.slice(0, 10).map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-slate-800/30">
                              {runResponse.execution!.columns.map((col, cIdx) => (
                                <td key={cIdx} className="px-3 py-2 whitespace-nowrap">
                                  {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-slate-600">null</span>}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {!validationResult && !runResponse && (
            <div className="h-64 border border-dashed border-slate-800 rounded-xl flex flex-col items-center justify-center text-slate-500 space-y-2 p-6 text-center">
              <Database className="w-8 h-8 text-slate-600 mb-1" />
              <p className="text-sm font-medium text-slate-400">Ready to execute plan</p>
              <p className="text-xs text-slate-500 max-w-sm">
                Select a dataset, customize or keep the sample CandidatePlan, and click Validate or Execute.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
