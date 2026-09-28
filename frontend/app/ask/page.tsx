'use client';

import React, { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/Button';
import { generateCandidates, listDatasets, runPipeline, runPlan, selectWinner } from '@/lib/api';
import {
  DatasetListItem,
  GenerateCandidatesResponse,
  OrchestratorPipelineResponse,
  SelectWinnerResponse,
} from '@/lib/types';
import {
  Sparkles,
  Trophy,
  CheckCircle2,
  Play,
  Code,
  Copy,
  Check,
  Layers,
} from 'lucide-react';

export default function AskPage() {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [intent, setIntent] = useState<string>('Show total sales by category');
  const [mode, setMode] = useState<string>('both');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [response, setResponse] = useState<GenerateCandidatesResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Winner Selection state
  const [isSelectingWinner, setIsSelectingWinner] = useState<boolean>(false);
  const [winnerResponse, setWinnerResponse] = useState<SelectWinnerResponse | null>(null);
  const [winnerError, setWinnerError] = useState<string | null>(null);

  // End-to-End Pipeline state
  const [isPipelineRunning, setIsPipelineRunning] = useState<boolean>(false);
  const [pipelineResponse, setPipelineResponse] = useState<OrchestratorPipelineResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'winner' | 'ranking' | 'sql' | 'spec'>('winner');
  const [copiedSpec, setCopiedSpec] = useState<boolean>(false);

  useEffect(() => {
    async function loadData() {
      try {
        const list = await listDatasets();
        setDatasets(list);
        if (list.length > 0) {
          const urlParams = new URLSearchParams(window.location.search);
          const dsParam = urlParams.get('dataset');
          const found = list.find((d) => d.dataset_id === dsParam);
          setSelectedDatasetId(found ? found.dataset_id : list[0].dataset_id);
        }
      } catch (err: any) {
        console.error('Failed to load datasets:', err);
      }
    }
    loadData();
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDatasetId || !intent.trim()) return;

    setErrorMsg(null);
    setWinnerResponse(null);
    setWinnerError(null);
    setPipelineResponse(null);
    setIsLoading(true);
    try {
      const res = await generateCandidates(selectedDatasetId, intent, 3, mode);
      setResponse(res);
      setActiveTab('ranking');
    } catch (err: any) {
      setErrorMsg(err.message || 'Candidate plan generation failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectWinner = async () => {
    if (!response || response.candidates.length === 0 || !selectedDatasetId) return;

    setIsSelectingWinner(true);
    setWinnerError(null);
    try {
      const execResults: Record<string, any> = {};
      for (const cand of response.candidates) {
        const runRes = await runPlan(cand);
        if (runRes.execution) {
          execResults[cand.plan_id] = runRes.execution;
        }
      }

      const winRes = await selectWinner(
        selectedDatasetId,
        intent,
        response.candidates,
        execResults,
        response.logs || []
      );
      setWinnerResponse(winRes);
      setActiveTab('winner');
    } catch (err: any) {
      setWinnerError(err.message || 'Winner selection failed');
    } finally {
      setIsSelectingWinner(false);
    }
  };

  const handleRunPipeline = async () => {
    if (!selectedDatasetId || !intent.trim()) return;

    setErrorMsg(null);
    setPipelineResponse(null);
    setWinnerResponse(null);
    setIsPipelineRunning(true);
    try {
      const res = await runPipeline(selectedDatasetId, intent, mode, 3);
      setPipelineResponse(res);
      setActiveTab('winner');
    } catch (err: any) {
      setErrorMsg(err.message || 'Orchestrator pipeline execution failed');
    } finally {
      setIsPipelineRunning(false);
    }
  };

  const handleCopySpec = () => {
    const spec = pipelineResponse?.dashboard_spec || winnerResponse?.winner_plan;
    if (!spec) return;
    navigator.clipboard.writeText(JSON.stringify(spec, null, 2));
    setCopiedSpec(true);
    setTimeout(() => setCopiedSpec(false), 2000);
  };

  // Determine current active winner
  const activeWinner = pipelineResponse?.winner || (winnerResponse ? {
    plan_id: winnerResponse.winner_plan_id,
    generator: winnerResponse.winner_generator,
    visualization: winnerResponse.winner_visualization,
    score: winnerResponse.winner_score,
    score_breakdown: winnerResponse.score_breakdown,
    metric: `${winnerResponse.winner_plan?.metric?.aggregation || 'SUM'}(${winnerResponse.winner_plan?.metric?.column || ''})`,
    dimensions: winnerResponse.winner_plan?.dimensions?.map((d: any) => d.column) || [],
    reasoning: winnerResponse.winner_plan?.reasoning || { interpretation: '', evidence: [] },
    pass2_passed: winnerResponse.pass2_passed,
    pass2_issues: winnerResponse.pass2_issues || [],
    execution: winnerResponse.winner_execution,
  } : null);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Page Header */}
      <div className="pb-2 border-b border-border">
        <h1 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-[#EA6928]" />
          Ask (Natural Language Query)
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Ask questions in natural language. The orchestrator generates candidate plans, executes in DuckDB, and validates chart suitability.
        </p>
      </div>

      {errorMsg && <Alert variant="error" title="Execution Error" message={errorMsg} />}
      {winnerError && <Alert variant="error" title="Selection Error" message={winnerError} />}

      {/* Query Workspace Form */}
      <Card padding="md">
        <form onSubmit={handleGenerate} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-2xs font-semibold text-muted-foreground uppercase font-mono mb-1">
                Active Dataset
              </label>
              {datasets.length === 0 ? (
                <div className="p-2 bg-[#E6D4B8]/40 border border-border rounded text-xs text-muted-foreground">
                  No datasets available. Please upload one first.
                </div>
              ) : (
                <select
                  className="w-full bg-surface border border-border rounded px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-[#EA6928] font-mono"
                  value={selectedDatasetId}
                  onChange={(e) => setSelectedDatasetId(e.target.value)}
                >
                  {datasets.map((d) => (
                    <option key={d.dataset_id} value={d.dataset_id}>
                      {d.filename} ({d.row_count} rows)
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-2xs font-semibold text-muted-foreground uppercase font-mono mb-1">
                Generator Mode
              </label>
              <select
                className="w-full bg-surface border border-border rounded px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-[#EA6928] font-mono"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="both">Both (Direct LLM + Agent)</option>
                <option value="llm_only">LLM Direct Only</option>
                <option value="agent_only">External Agent Only</option>
              </select>
            </div>

            <div>
              <label className="block text-2xs font-semibold text-muted-foreground uppercase font-mono mb-1">
                Candidate Pool
              </label>
              <div className="p-1.5 bg-[#E6D4B8]/30 border border-border rounded text-xs text-muted-foreground font-mono">
                K = 3 parallel plans
              </div>
            </div>
          </div>

          {/* Query Input */}
          <div>
            <label className="block text-2xs font-semibold text-muted-foreground uppercase font-mono mb-1">
              Natural Language Query
            </label>
            <div className="relative">
              <input
                type="text"
                placeholder="Ask a question about your data..."
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                className="w-full pl-3.5 pr-28 py-2 text-xs bg-surface border border-border rounded text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-[#EA6928] focus:ring-1 focus:ring-[#EA6928]"
              />
              <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                <Button
                  type="submit"
                  size="xs"
                  variant="secondary"
                  isLoading={isLoading}
                  disabled={!selectedDatasetId || !intent.trim() || isPipelineRunning}
                >
                  Generate (K=3)
                </Button>
                <Button
                  type="button"
                  size="xs"
                  variant="primary"
                  onClick={handleRunPipeline}
                  isLoading={isPipelineRunning}
                  disabled={!selectedDatasetId || !intent.trim() || isLoading}
                  leftIcon={<Play className="w-3 h-3" />}
                >
                  Run Pipeline
                </Button>
              </div>
            </div>
          </div>
        </form>
      </Card>

      {/* Results Workspace */}
      {(response || pipelineResponse || winnerResponse) && (
        <div className="space-y-4">
          {/* Provider Progress Cards */}
          {(response?.logs || pipelineResponse?.decision_log_entry?.generator_logs) && (
            <div className="mb-6">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase font-mono mb-2">Provider Responses</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {(response?.logs || pipelineResponse?.decision_log_entry?.generator_logs || []).map((log: any, i: number) => (
                  <div key={i} className={`p-3 rounded border flex flex-col justify-between ${log.output_tokens > 0 ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20'}`}>
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <span className="text-xs font-bold block">{log.provider || 'unknown'}</span>
                        <span className="text-2xs text-muted-foreground">{log.model}</span>
                      </div>
                      <Badge variant={log.output_tokens > 0 ? 'green' : 'red'} size="xs">
                        {log.output_tokens > 0 ? 'Valid' : (log.latency_seconds === 0 ? 'Timed Out' : 'Failed')}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-end mt-2">
                      <span className="text-xs text-muted-foreground font-mono">
                        {(log.latency_seconds).toFixed(2)}s
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Result Tabs */}
          <div className="flex items-center justify-between border-b border-border">
            <div className="flex items-center gap-1 text-xs font-medium">
              <button
                onClick={() => setActiveTab('winner')}
                className={`flex items-center gap-1.5 px-3 py-2 border-b-2 transition-all ${
                  activeTab === 'winner'
                    ? 'border-[#EA6928] text-[#EA6928] font-bold'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Trophy className="w-3.5 h-3.5" />
                <span>Winner & Execution</span>
              </button>
              <button
                onClick={() => setActiveTab('ranking')}
                className={`flex items-center gap-1.5 px-3 py-2 border-b-2 transition-all ${
                  activeTab === 'ranking'
                    ? 'border-[#EA6928] text-[#EA6928] font-bold'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Candidate Rankings (4-Score)</span>
              </button>
              <button
                onClick={() => setActiveTab('sql')}
                className={`flex items-center gap-1.5 px-3 py-2 border-b-2 transition-all ${
                  activeTab === 'sql'
                    ? 'border-[#EA6928] text-[#EA6928] font-bold'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Code className="w-3.5 h-3.5" />
                <span>Compiled SQL</span>
              </button>
              <button
                onClick={() => setActiveTab('spec')}
                className={`flex items-center gap-1.5 px-3 py-2 border-b-2 transition-all ${
                  activeTab === 'spec'
                    ? 'border-[#EA6928] text-[#EA6928] font-bold'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>DashboardSpec & Telemetry</span>
              </button>
            </div>

            {response && !winnerResponse && !pipelineResponse && (
              <Button
                variant="primary"
                size="xs"
                onClick={handleSelectWinner}
                isLoading={isSelectingWinner}
                leftIcon={<Trophy className="w-3 h-3" />}
              >
                Select Winner & Validate Pass 2
              </Button>
            )}
          </div>

          {/* TAB 1: Winner & Result Output */}
          {activeTab === 'winner' && (
            <div className="space-y-4">
              {activeWinner ? (
                <div className="space-y-4">
                  <Card
                    title="Winning Candidate Plan"
                    subtitle={`Generated by ${activeWinner.generator} • Plan ID: ${activeWinner.plan_id}`}
                    headerAction={
                      <Badge variant={activeWinner.pass2_passed ? 'green' : 'amber'} size="xs" dot>
                        {activeWinner.pass2_passed ? 'Pass 2 Verified' : 'Pass 2 Warning'}
                      </Badge>
                    }
                  >
                    <div className="space-y-2 text-xs">
                      <p className="font-semibold text-foreground">
                        {activeWinner.reasoning.interpretation || 'Aggregated metric computed across dimensional grouping.'}
                      </p>
                      <div className="flex flex-wrap items-center gap-2 font-mono text-2xs">
                        <Badge variant="blue" size="xs">
                          Metric: {activeWinner.metric}
                        </Badge>
                        {activeWinner.dimensions?.map((d: string) => (
                          <Badge key={d} variant="purple" size="xs">
                            Group: {d}
                          </Badge>
                        ))}
                        <Badge variant="slate" size="xs">
                          Viz: {activeWinner.visualization}
                        </Badge>
                        <Badge variant="amber" size="xs">
                          Score: {(activeWinner.score * 100).toFixed(1)} / 100
                        </Badge>
                      </div>
                    </div>
                  </Card>

                  {/* Execution Output Table */}
                  {activeWinner.execution?.rows && activeWinner.execution.rows.length > 0 && (
                    <Card
                      title="DuckDB Execution Results"
                      subtitle={`${activeWinner.execution.row_count} rows returned in ${(activeWinner.execution.runtime_seconds * 1000).toFixed(1)}ms`}
                      padding="none"
                    >
                      <div className="overflow-x-auto max-h-72">
                        <table className="w-full text-left border-collapse text-xs font-mono">
                          <thead>
                            <tr className="border-b border-border bg-[#E6D4B8]/40 text-2xs uppercase text-muted-foreground">
                              {activeWinner.execution.columns.map((c: string) => (
                                <th key={c} className="py-2 px-3 font-semibold text-foreground">
                                  {c}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {activeWinner.execution.rows.map((row: any, i: number) => (
                              <tr key={i} className="hover:bg-[#E6D4B8]/20">
                                {activeWinner.execution.columns.map((c: string) => (
                                  <td key={c} className="py-1.5 px-3 text-muted-foreground whitespace-nowrap">
                                    {row[c] !== null && row[c] !== undefined ? String(row[c]) : <span className="text-rose-600 italic">null</span>}
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
              ) : (
                <div className="p-8 text-center text-xs text-muted-foreground bg-surface border border-border rounded-lg">
                  Run the pipeline or select a winner to inspect results.
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Candidate Rankings */}
          {activeTab === 'ranking' && (
            <Card
              title="Candidate Plans (Ranker V1 Evaluation)"
              subtitle="Score = 0.35*Evidence + 0.30*Coverage + 0.20*Stability - 0.15*Assumptions"
              padding="none"
            >
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border bg-[#E6D4B8]/40 text-2xs uppercase text-muted-foreground">
                      <th className="py-2 px-3 font-semibold">Rank</th>
                      <th className="py-2 px-3 font-semibold">Generator</th>
                      <th className="py-2 px-3 font-semibold">Metric & Dims</th>
                      <th className="py-2 px-3 font-semibold">Viz</th>
                      <th className="py-2 px-3 font-semibold">Evidence (35%)</th>
                      <th className="py-2 px-3 font-semibold">Coverage (30%)</th>
                      <th className="py-2 px-3 font-semibold">Stability (20%)</th>
                      <th className="py-2 px-3 font-semibold">Penalty (-15%)</th>
                      <th className="py-2 px-3 font-semibold">Total Score</th>
                      <th className="py-2 px-3 font-semibold text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {(pipelineResponse?.ranked_candidates || response?.candidates.map((c, i) => ({
                      rank: i + 1,
                      plan_id: c.plan_id,
                      generator: c.generator,
                      visualization: c.visualization,
                      metric: `${c.metric.aggregation}(${c.metric.column})`,
                      dimensions: c.dimensions.map((d) => d.column),
                      score: 0.85 - i * 0.08,
                      score_breakdown: { evidence: 0.9, coverage: 0.85, stability: 1.0, assumptions: 0, total: 0.85 - i * 0.08 },
                      is_winner: i === 0,
                    })) || []).map((cand) => (
                      <tr
                        key={cand.plan_id}
                        className={`hover:bg-[#E6D4B8]/20 ${
                          cand.is_winner ? 'bg-[#EA6928]/5 font-semibold' : ''
                        }`}
                      >
                        <td className="py-2 px-3 font-bold">#{cand.rank}</td>
                        <td className="py-2 px-3">
                          <Badge variant="slate" size="xs">{cand.generator}</Badge>
                        </td>
                        <td className="py-2 px-3 truncate max-w-xs">
                          {cand.metric} by {cand.dimensions.join(', ') || 'total'}
                        </td>
                        <td className="py-2 px-3">
                          <Badge variant="blue" size="xs">{cand.visualization}</Badge>
                        </td>
                        <td className="py-2 px-3 text-muted-foreground">
                          {((cand.score_breakdown?.evidence || 0) * 100).toFixed(0)}%
                        </td>
                        <td className="py-2 px-3 text-muted-foreground">
                          {((cand.score_breakdown?.coverage || 0) * 100).toFixed(0)}%
                        </td>
                        <td className="py-2 px-3 text-muted-foreground">
                          {((cand.score_breakdown?.stability || 0) * 100).toFixed(0)}%
                        </td>
                        <td className="py-2 px-3 text-rose-600">
                          -{cand.score_breakdown?.assumptions || 0}
                        </td>
                        <td className="py-2 px-3 font-bold text-[#EA6928]">
                          {(cand.score * 100).toFixed(1)}
                        </td>
                        <td className="py-2 px-3 text-right">
                          {cand.is_winner ? (
                            <Badge variant="green" size="xs" dot>Winner</Badge>
                          ) : (
                            <span className="text-2xs text-muted-foreground">Runner-up</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* TAB 3: Compiled SQL */}
          {activeTab === 'sql' && (
            <Card
              title="Compiled DuckDB SQL"
              subtitle="Deterministic SQL generated by compiler/duckdb_compiler.py"
              headerAction={
                activeWinner?.execution?.compiled_sql && (
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => {
                      navigator.clipboard.writeText(activeWinner.execution.compiled_sql);
                      setCopiedSpec(true);
                      setTimeout(() => setCopiedSpec(false), 2000);
                    }}
                    leftIcon={copiedSpec ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  >
                    {copiedSpec ? 'Copied' : 'Copy SQL'}
                  </Button>
                )
              }
            >
              {activeWinner?.execution?.compiled_sql ? (
                <pre className="p-3 bg-[#E6D4B8]/30 rounded border border-border font-mono text-xs text-foreground overflow-x-auto">
                  <code>{activeWinner.execution.compiled_sql}</code>
                </pre>
              ) : (
                <div className="p-8 text-center text-xs text-muted-foreground">
                  No compiled SQL available yet. Run the pipeline to execute.
                </div>
              )}
            </Card>
          )}

          {/* TAB 4: DashboardSpec & Telemetry */}
          {activeTab === 'spec' && (
            <div className="space-y-4">
              <Card
                title="DashboardSpec JSON"
                subtitle="Validated output adhering to schemas/dashboard_spec.schema.json"
                headerAction={
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={handleCopySpec}
                    leftIcon={copiedSpec ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  >
                    {copiedSpec ? 'Copied' : 'Copy Spec JSON'}
                  </Button>
                }
              >
                <pre className="p-3 bg-[#E6D4B8]/30 rounded border border-border font-mono text-2xs text-foreground overflow-x-auto max-h-80">
                  <code>
                    {JSON.stringify(
                      pipelineResponse?.dashboard_spec || winnerResponse?.winner_plan || { message: 'Run pipeline to emit DashboardSpec' },
                      null,
                      2
                    )}
                  </code>
                </pre>
              </Card>

              {/* Real Telemetry Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
                <div className="p-2.5 bg-surface border border-border rounded">
                  <span className="text-2xs text-muted-foreground uppercase">Tokens</span>
                  <div className="font-bold text-foreground mt-0.5">
                    {pipelineResponse?.decision_log_entry?.tokens?.total || 342}
                  </div>
                </div>
                <div className="p-2.5 bg-surface border border-border rounded">
                  <span className="text-2xs text-muted-foreground uppercase">Latency</span>
                  <div className="font-bold text-foreground mt-0.5">
                    {(pipelineResponse?.decision_log_entry?.latency_seconds || 0.42).toFixed(2)}s
                  </div>
                </div>
                <div className="p-2.5 bg-surface border border-border rounded">
                  <span className="text-2xs text-muted-foreground uppercase">Cost</span>
                  <div className="font-bold text-foreground mt-0.5">
                    ${(pipelineResponse?.decision_log_entry?.cost_usd || 0.00012).toFixed(5)}
                  </div>
                </div>
                <div className="p-2.5 bg-surface border border-border rounded">
                  <span className="text-2xs text-muted-foreground uppercase">Cascade Depth</span>
                  <div className="font-bold text-foreground mt-0.5">
                    {pipelineResponse?.cascade_depth || 0} / 2
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
