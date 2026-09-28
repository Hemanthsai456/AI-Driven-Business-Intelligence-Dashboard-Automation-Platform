'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/Button';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { generateCandidates, listDatasets, runPlan, selectWinner } from '@/lib/api';
import {
  CandidatePlanUI,
  DatasetListItem,
  GenerateCandidatesResponse,
  SelectWinnerResponse,
} from '@/lib/types';
import {
  Sparkles,
  Bot,
  Cpu,
  Search,
  ArrowRight,
  HelpCircle,
  Clock,
  Coins,
  Layers,
  Trophy,
  Award,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';

export default function AskPage() {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [intent, setIntent] = useState<string>('Show total sales by category');
  const [mode, setMode] = useState<string>('both');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [response, setResponse] = useState<GenerateCandidatesResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Stage 6: Winner Selection state
  const [isSelectingWinner, setIsSelectingWinner] = useState<boolean>(false);
  const [winnerResponse, setWinnerResponse] = useState<SelectWinnerResponse | null>(null);
  const [winnerError, setWinnerError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const list = await listDatasets();
        setDatasets(list);
        if (list.length > 0) {
          setSelectedDatasetId(list[0].dataset_id);
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
    setIsLoading(true);
    try {
      const res = await generateCandidates(selectedDatasetId, intent, 3, mode);
      setResponse(res);
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
      // 1. Run each candidate through execution engine
      const execResults: Record<string, any> = {};
      for (const cand of response.candidates) {
        const runRes = await runPlan(cand);
        if (runRes.execution) {
          execResults[cand.plan_id] = runRes.execution;
        }
      }

      // 2. Select winner with Pass 2 Cascade
      const winRes = await selectWinner(
        selectedDatasetId,
        intent,
        response.candidates,
        execResults,
        response.logs || []
      );
      setWinnerResponse(winRes);
    } catch (err: any) {
      setWinnerError(err.message || 'Winner selection failed');
    } finally {
      setIsSelectingWinner(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
          <Sparkles className="w-6 h-6 text-sky-400" />
          Natural Language Analysis (Ask)
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Generate structured analytical candidates using direct LLM generation and external agents with full generator attribution.
        </p>
      </div>

      {errorMsg && <Alert variant="error" title="Generation Error" message={errorMsg} />}

      {/* Query Form */}
      <Card title="Analytical Query & Generator Settings">
        <form onSubmit={handleGenerate} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                Active Dataset
              </label>
              {datasets.length === 0 ? (
                <div className="p-2.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400">
                  No datasets available. Please upload one first.
                </div>
              ) : (
                <select
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  value={selectedDatasetId}
                  onChange={(e) => setSelectedDatasetId(e.target.value)}
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
              <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                Generator Mode
              </label>
              <select
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="both">Both (LLM Direct + External Agent)</option>
                <option value="llm_only">LLM Direct Only</option>
                <option value="agent_only">External Agent Only</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Natural Language Intent
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                placeholder="e.g. Total revenue by category, or monthly sales trend"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
              />
              <Button type="submit" variant="primary" size="md" isLoading={isLoading} disabled={datasets.length === 0}>
                <Search className="w-4 h-4 mr-1.5" />
                Generate Candidates
              </Button>
            </div>
          </div>
        </form>
      </Card>

      {/* Ambiguity Alert */}
      {response?.ambiguity && response.ambiguity.status !== 'CLEAR' && (
        <Alert
          variant="warning"
          title={`Ambiguity Detected (${response.ambiguity.status})`}
          message={response.ambiguity.message || 'The analytical request contains ambiguous elements.'}
        />
      )}

      {/* Winner Selection Error */}
      {winnerError && (
        <Alert variant="error" title="Winner Selection Error" message={winnerError} />
      )}

      {/* Selected Winner Card */}
      {winnerResponse && (
        <Card
          title="Selected Winning Plan (Ranker V1 + Pass 2)"
          headerAction={
            <div className="flex items-center gap-2">
              {winnerResponse.is_tie && (
                <Badge variant="amber" size="sm">
                  Tie (within ε=0.05)
                </Badge>
              )}
              {winnerResponse.cascade_triggered && (
                <Badge variant="amber" size="sm">
                  Cascade (depth {winnerResponse.cascade_depth})
                </Badge>
              )}
              <Badge
                variant={winnerResponse.winner_generator === 'external_agent' ? 'purple' : 'blue'}
                size="sm"
              >
                {winnerResponse.winner_generator}
              </Badge>
              <Badge variant="green" size="sm">
                Score: {winnerResponse.winner_score.toFixed(3)}
              </Badge>
            </div>
          }
        >
          <div className="space-y-4 text-xs">
            {winnerResponse.cascade_triggered && (
              <Alert
                variant="warning"
                title="Pass 2 Cascade Promoted Plan"
                message={`Initial top-ranked candidate failed Pass 2 validation. Promoted from rank #${winnerResponse.winner_rank_before_cascade} to winner after cascade depth ${winnerResponse.cascade_depth}.`}
              />
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Plan ID</span>
                <span className="font-mono text-sky-400 font-semibold">{winnerResponse.winner_plan_id}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Visualization</span>
                <span className="font-semibold text-white uppercase">{winnerResponse.winner_visualization}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Pass 2 Status</span>
                <span className="font-semibold text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {winnerResponse.pass2_passed ? 'Passed' : 'Issues Detected'}
                </span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Spec ID</span>
                <span className="font-mono text-slate-400 truncate block">{winnerResponse.spec_id.slice(0, 16)}...</span>
              </div>
            </div>

            {/* Score Breakdown */}
            <div>
              <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1.5">Score Breakdown</span>
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800/80">
                  <span className="text-slate-400 text-[10px] block">Evidence (40%)</span>
                  <span className="font-mono text-sky-400 font-semibold">{winnerResponse.score_breakdown.evidence.toFixed(3)}</span>
                </div>
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800/80">
                  <span className="text-slate-400 text-[10px] block">Coverage (30%)</span>
                  <span className="font-mono text-indigo-400 font-semibold">{winnerResponse.score_breakdown.coverage.toFixed(3)}</span>
                </div>
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800/80">
                  <span className="text-slate-400 text-[10px] block">Stability (20%)</span>
                  <span className="font-mono text-emerald-400 font-semibold">{winnerResponse.score_breakdown.stability.toFixed(3)}</span>
                </div>
                <div className="bg-slate-900/60 p-2 rounded border border-slate-800/80">
                  <span className="text-slate-400 text-[10px] block">Assumptions (-10%)</span>
                  <span className="font-mono text-amber-400 font-semibold">{winnerResponse.score_breakdown.assumptions.toFixed(3)}</span>
                </div>
              </div>
            </div>

            {/* Alternate Interpretations */}
            {winnerResponse.alternate_interpretations && winnerResponse.alternate_interpretations.length > 0 && (
              <div className="pt-2 border-t border-slate-800/80">
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1.5">
                  Alternate Interpretations ({winnerResponse.alternate_interpretations.length})
                </span>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-slate-300">
                    <thead className="text-[10px] font-mono uppercase bg-slate-950 text-slate-400">
                      <tr>
                        <th className="px-2.5 py-1.5">Plan</th>
                        <th className="px-2.5 py-1.5">Score</th>
                        <th className="px-2.5 py-1.5">Generator</th>
                        <th className="px-2.5 py-1.5">Reason Not Winner</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {winnerResponse.alternate_interpretations.map((alt, aIdx) => (
                        <tr key={aIdx} className="hover:bg-slate-800/20">
                          <td className="px-2.5 py-1.5 font-mono text-sky-400">{alt.plan_id}</td>
                          <td className="px-2.5 py-1.5 font-mono">{alt.score.toFixed(3)}</td>
                          <td className="px-2.5 py-1.5">
                            <Badge variant={alt.generator === 'external_agent' ? 'purple' : 'blue'} size="sm">
                              {alt.generator}
                            </Badge>
                          </td>
                          <td className="px-2.5 py-1.5 text-slate-400 italic">{alt.reason_not_winner}</td>
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

      {/* Generated Candidates */}
      {response && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-indigo-400" />
              Generated Candidates ({response.candidates.length})
            </h2>
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleSelectWinner}
                isLoading={isSelectingWinner}
                disabled={response.candidates.length === 0}
              >
                <Trophy className="w-4 h-4 mr-1.5 text-amber-400" />
                Select Winner (Pass 2 Cascade)
              </Button>
              <span className="text-xs text-slate-400 font-mono hidden md:inline">
                Mode: {mode}
              </span>
            </div>
          </div>

          {response.candidates.length === 0 ? (
            <Card>
              <div className="text-center py-8 text-slate-400 text-sm">
                No valid candidate plans generated.
              </div>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {response.candidates.map((candidate, idx) => (
                <Card
                  key={idx}
                  title={`Candidate #${idx + 1}`}
                  headerAction={
                    <Badge
                      variant={candidate.generator === 'external_agent' ? 'purple' : 'blue'}
                      size="sm"
                    >
                      {candidate.generator === 'external_agent' ? (
                        <span className="flex items-center gap-1">
                          <Bot className="w-3 h-3" />
                          External Agent
                        </span>
                      ) : (
                        <span className="flex items-center gap-1">
                          <Cpu className="w-3 h-3" />
                          LLM Direct
                        </span>
                      )}
                    </Badge>
                  }
                >
                  <div className="space-y-3 text-xs">
                    {/* Metric */}
                    <div className="p-2.5 bg-slate-950 rounded-lg border border-slate-800">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Metric</span>
                      <span className="font-semibold text-sky-400">
                        {candidate.metric.aggregation}({candidate.metric.column})
                      </span>
                    </div>

                    {/* Dimensions */}
                    <div>
                      <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1">Dimensions</span>
                      {candidate.dimensions.length === 0 ? (
                        <span className="text-slate-500 italic">None (Scalar aggregate)</span>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {candidate.dimensions.map((d, dIdx) => (
                            <Badge key={dIdx} variant="slate" size="sm">
                              {d.column} {d.granularity ? `(${d.granularity})` : ''}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Reasoning */}
                    <div className="border-t border-slate-800/80 pt-2.5">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Interpretation</span>
                      <p className="text-slate-300 text-xs italic">
                        &quot;{candidate.reasoning.interpretation}&quot;
                      </p>
                    </div>

                    {/* Action */}
                    <div className="pt-2">
                      <Link
                        href="/plan-runner"
                        className="inline-flex items-center text-xs text-sky-400 hover:text-sky-300 font-medium"
                      >
                        Inspect in Plan Runner <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Link>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* Telemetry Logs */}
          {response.logs && response.logs.length > 0 && (
            <Card title="Generator Telemetry & Cost Logging">
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left text-slate-300">
                  <thead className="bg-slate-950 text-slate-400 uppercase font-mono border-b border-slate-800">
                    <tr>
                      <th className="px-3 py-2">Generator</th>
                      <th className="px-3 py-2">Model</th>
                      <th className="px-3 py-2">Steps</th>
                      <th className="px-3 py-2">Tokens (In / Out)</th>
                      <th className="px-3 py-2">Latency</th>
                      <th className="px-3 py-2">Est. Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {response.logs.map((log, lIdx) => (
                      <tr key={lIdx} className="hover:bg-slate-800/20">
                        <td className="px-3 py-2 font-medium">
                          <Badge variant={log.generator === 'external_agent' ? 'purple' : 'blue'} size="sm">
                            {log.generator}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 font-mono text-slate-400">{log.model}</td>
                        <td className="px-3 py-2">{log.steps}</td>
                        <td className="px-3 py-2 font-mono">{log.input_tokens} / {log.output_tokens}</td>
                        <td className="px-3 py-2 font-mono">{log.latency_seconds}s</td>
                        <td className="px-3 py-2 font-mono text-emerald-400">${log.estimated_cost_usd.toFixed(6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
