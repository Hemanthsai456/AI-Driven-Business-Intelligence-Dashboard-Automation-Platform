'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Alert } from '@/components/Alert';
import { Button } from '@/components/Button';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { generateCandidates, listDatasets, runPipeline, runPlan, selectWinner } from '@/lib/api';
import {
  CandidatePlanUI,
  DatasetListItem,
  GenerateCandidatesResponse,
  OrchestratorPipelineResponse,
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
  Play,
  Code,
  Copy,
  Check,
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

  // Stage 7: End-to-End Pipeline & Spec Viewer state
  const [isPipelineRunning, setIsPipelineRunning] = useState<boolean>(false);
  const [pipelineResponse, setPipelineResponse] = useState<OrchestratorPipelineResponse | null>(null);
  const [showSpecJson, setShowSpecJson] = useState<boolean>(false);
  const [copiedSpec, setCopiedSpec] = useState<boolean>(false);

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

  const handleRunPipeline = async () => {
    if (!selectedDatasetId || !intent.trim()) return;

    setErrorMsg(null);
    setPipelineResponse(null);
    setIsPipelineRunning(true);
    try {
      const res = await runPipeline(selectedDatasetId, intent, mode, 3);
      setPipelineResponse(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Orchestrator pipeline execution failed');
    } finally {
      setIsPipelineRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
          <Sparkles className="w-6 h-6 text-sky-400" />
          Natural Language Analysis (Ask & Orchestrator Pipeline)
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Full-lifecycle orchestrator: ambiguity detection, candidate generation, DuckDB execution, Pass 1/2 validation, Ranker V1, and DashboardSpec emission.
        </p>
      </div>

      {errorMsg && <Alert variant="error" title="Execution Error" message={errorMsg} />}

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
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                placeholder="e.g. Total revenue by category, or monthly sales trend"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
              />
              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={handleRunPipeline}
                isLoading={isPipelineRunning}
                disabled={datasets.length === 0}
              >
                <Play className="w-4 h-4 mr-1.5" />
                Run Pipeline
              </Button>
              <Button
                type="submit"
                variant="secondary"
                size="md"
                isLoading={isLoading}
                disabled={datasets.length === 0}
              >
                <Search className="w-4 h-4 mr-1.5" />
                Generate Candidates
              </Button>
            </div>
          </div>
        </form>
      </Card>

      {/* Pipeline Tie / Clarification Alert */}
      {pipelineResponse && (pipelineResponse.is_tie || pipelineResponse.clarification_needed) && (
        <Alert
          variant="warning"
          title="Clarification Needed (Candidate Tie Detected)"
          message={
            pipelineResponse.ambiguity_message ||
            `Multiple valid interpretations exist within the ε=0.05 tie threshold for "${intent}". Please review the ranked candidates below and confirm your desired interpretation.`
          }
        />
      )}

      {/* Pipeline Error / Refusal Alert */}
      {pipelineResponse && pipelineResponse.status !== 'SUCCESS' && (
        <Alert
          variant={pipelineResponse.status === 'REFUSED' ? 'error' : 'warning'}
          title={`Pipeline Status: ${pipelineResponse.status}`}
          message={pipelineResponse.message}
        />
      )}

      {/* Stage 7: Candidate Ranking Table with Full Score Breakdown */}
      {pipelineResponse && pipelineResponse.ranked_candidates.length > 0 && (
        <Card
          title="Ranker V1 Scoring & Candidate Evaluation"
          headerAction={
            <div className="flex items-center gap-2">
              {pipelineResponse.is_tie && (
                <Badge variant="amber" size="sm">
                  Tie (within ε=0.05)
                </Badge>
              )}
              {pipelineResponse.cascade_depth > 0 && (
                <Badge variant="amber" size="sm">
                  Cascade (depth {pipelineResponse.cascade_depth})
                </Badge>
              )}
              <Badge variant="blue" size="sm">
                {pipelineResponse.ranked_candidates.length} Evaluated
              </Badge>
            </div>
          }
        >
          <div className="space-y-4">
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left text-slate-300">
                <thead className="bg-slate-950 text-slate-400 uppercase font-mono border-b border-slate-800 text-[10px]">
                  <tr>
                    <th className="px-3 py-2">Rank</th>
                    <th className="px-3 py-2">Plan ID</th>
                    <th className="px-3 py-2">Generator</th>
                    <th className="px-3 py-2">Vis</th>
                    <th className="px-3 py-2">Metric</th>
                    <th className="px-3 py-2">Dimensions</th>
                    <th className="px-3 py-2 text-right">Evidence (35%)</th>
                    <th className="px-3 py-2 text-right">Coverage (30%)</th>
                    <th className="px-3 py-2 text-right">Stability (20%)</th>
                    <th className="px-3 py-2 text-right">Assumptions (-15%)</th>
                    <th className="px-3 py-2 text-right">Total Score</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                  {pipelineResponse.ranked_candidates.map((cand) => (
                    <tr
                      key={cand.plan_id}
                      className={`hover:bg-slate-800/30 ${cand.is_winner ? 'bg-sky-950/20' : ''}`}
                    >
                      <td className="px-3 py-2 font-bold text-white">#{cand.rank}</td>
                      <td className="px-3 py-2 text-sky-400 font-semibold">{cand.plan_id}</td>
                      <td className="px-3 py-2">
                        <Badge
                          variant={cand.generator === 'external_agent' ? 'purple' : 'blue'}
                          size="sm"
                        >
                          {cand.generator === 'external_agent' ? 'Agent' : 'LLM'}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 uppercase text-slate-200">{cand.visualization}</td>
                      <td className="px-3 py-2 text-slate-300">{cand.metric}</td>
                      <td className="px-3 py-2 text-slate-400">{cand.dimensions.join(', ') || 'None'}</td>
                      <td className="px-3 py-2 text-right text-sky-300">
                        {cand.score_breakdown.evidence.toFixed(3)}
                      </td>
                      <td className="px-3 py-2 text-right text-indigo-300">
                        {cand.score_breakdown.coverage.toFixed(3)}
                      </td>
                      <td className="px-3 py-2 text-right text-emerald-300">
                        {cand.score_breakdown.stability.toFixed(3)}
                      </td>
                      <td className="px-3 py-2 text-right text-amber-300">
                        {cand.score_breakdown.assumptions.toFixed(3)}
                      </td>
                      <td className="px-3 py-2 text-right font-bold text-emerald-400">
                        {cand.score.toFixed(4)}
                      </td>
                      <td className="px-3 py-2">
                        {cand.is_winner ? (
                          <Badge variant="green" size="sm">WINNER</Badge>
                        ) : (
                          <Badge variant="slate" size="sm">Alternate</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      )}

      {/* Stage 7: Pipeline Winner Card */}
      {pipelineResponse?.winner && (
        <Card
          title="Pipeline Winner (Validated Dashboard Spec)"
          headerAction={
            <div className="flex items-center gap-2">
              {pipelineResponse.cascade_depth > 0 && (
                <Badge variant="amber" size="sm">
                  Cascade Depth {pipelineResponse.cascade_depth}
                </Badge>
              )}
              <Badge
                variant={pipelineResponse.winner.generator === 'external_agent' ? 'purple' : 'blue'}
                size="sm"
              >
                {pipelineResponse.winner.generator}
              </Badge>
              <Badge variant="green" size="sm">
                Score: {pipelineResponse.winner.score.toFixed(4)}
              </Badge>
            </div>
          }
        >
          <div className="space-y-4 text-xs">
            {pipelineResponse.cascade_depth > 0 && (
              <Alert
                variant="warning"
                title="Pass 2 Runner-Up Cascade Triggered"
                message={`The initial rank-1 proposal failed Pass 2 visualization suitability. Runner-up promoted to winner after ${pipelineResponse.cascade_depth} cascade step(s).`}
              />
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Plan ID</span>
                <span className="font-mono text-sky-400 font-semibold">{pipelineResponse.winner.plan_id}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Visualization</span>
                <span className="font-semibold text-white uppercase">{pipelineResponse.winner.visualization}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Pass 2 Status</span>
                <span className="font-semibold text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {pipelineResponse.winner.pass2_passed ? 'Passed (Suitability Verified)' : 'Issues Detected'}
                </span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Spec ID</span>
                <span className="font-mono text-slate-400 truncate block">
                  {pipelineResponse.spec_id ? `${pipelineResponse.spec_id.slice(0, 16)}...` : 'N/A'}
                </span>
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
              <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1">Interpretation</span>
              <p className="text-slate-300 italic">
                &quot;{pipelineResponse.winner.reasoning.interpretation}&quot;
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Stage 7: DashboardSpec JSON Viewer */}
      {pipelineResponse?.dashboard_spec && (
        <Card
          title="DashboardSpec JSON Artifact"
          headerAction={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(
                    JSON.stringify(pipelineResponse.dashboard_spec, null, 2)
                  );
                  setCopiedSpec(true);
                  setTimeout(() => setCopiedSpec(false), 2000);
                }}
              >
                {copiedSpec ? (
                  <Check className="w-3.5 h-3.5 mr-1 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5 mr-1" />
                )}
                {copiedSpec ? 'Copied!' : 'Copy Spec JSON'}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowSpecJson(!showSpecJson)}
              >
                <Code className="w-3.5 h-3.5 mr-1" />
                {showSpecJson ? 'Hide JSON' : 'View Spec JSON'}
              </Button>
            </div>
          }
        >
          {showSpecJson ? (
            <pre className="p-4 bg-slate-950 text-slate-300 rounded-lg text-xs font-mono overflow-x-auto max-h-96 border border-slate-800">
              {JSON.stringify(pipelineResponse.dashboard_spec, null, 2)}
            </pre>
          ) : (
            <p className="text-xs text-slate-400">
              Canonical DashboardSpec emitted with full trace, alternate interpretations, and isolated candidate artifacts. Click &quot;View Spec JSON&quot; to inspect payload.
            </p>
          )}
        </Card>
      )}

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
