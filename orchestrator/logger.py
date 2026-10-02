"""Structured logging and artifact emission for Orchestrator Stage 7.

Emits:
1. Decision Log (JSONL): Request, context hash, plans, validation errors, latency, token metrics.
2. Explainability Log (JSONL): Ranking rationale, weights used, score breakdown, cascade fallback trace, tie detection.
3. Isolated Candidate Artifacts (JSON): Per-candidate execution results, SQL queries, and validation outcomes.

Architecture references:
- ranker_v1_spec.md §7, §8
- orchestrator_conformance.md §1 ('Decision & Explainability Logs')
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.config import (
    RANK_W1_EVIDENCE,
    RANK_W2_COVERAGE,
    RANK_W3_STABILITY,
    RANK_W4_ASSUMPTIONS,
    RANK_TIE_EPSILON,
)
from orchestrator.schemas import (
    CandidatePlan,
    DashboardSpec,
    ExecutionResult,
    GeneratorCallLog,
    Pass1aResult,
    Pass1bResult,
    Pass2Result,
    RankedCandidate,
    ScoreBreakdown,
)

LOGS_DIR = Path("logs")
ARTIFACTS_DIR = Path("artifacts") / "candidates"


def ensure_directories() -> None:
    """Ensure logs and artifacts directories exist."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def emit_decision_log(
    *,
    request_id: str,
    dataset_id: str,
    intent: str,
    context_hash: str,
    mode: str,
    plans_generated: int,
    plans_valid_pass1a: int,
    plans_valid_pass1b: int,
    winner_plan_id: Optional[str],
    is_tie: bool,
    cascade_depth: int,
    status: str,
    generator_logs: List[GeneratorCallLog],
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Emit a structured entry to the decision JSONL log."""
    ensure_directories()
    target_path = log_path or (LOGS_DIR / "decision_log.jsonl")

    total_tokens = sum(g.input_tokens + g.output_tokens for g in generator_logs)
    total_latency = sum(g.latency_seconds for g in generator_logs)
    total_cost = sum(g.estimated_cost_usd for g in generator_logs)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "dataset_id": dataset_id,
        "intent": intent,
        "context_hash": context_hash,
        "generator_mode": mode,
        "plans_generated": plans_generated,
        "plans_valid_pass1a": plans_valid_pass1a,
        "plans_valid_pass1b": plans_valid_pass1b,
        "winner_plan_id": winner_plan_id,
        "is_tie": is_tie,
        "cascade_depth": cascade_depth,
        "status": status,
        "total_tokens": total_tokens,
        "total_latency_seconds": round(total_latency, 4),
        "estimated_cost_usd": round(total_cost, 6),
        "generator_calls": [g.model_dump() for g in generator_logs],
    }

    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")

    return entry


def emit_explainability_log(
    *,
    spec: DashboardSpec,
    ranked_candidates: List[Tuple[CandidatePlan, ExecutionResult, ScoreBreakdown, int]],
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Emit a structured entry to the explainability JSONL log."""
    ensure_directories()
    target_path = log_path or (LOGS_DIR / "explainability.jsonl")

    ranking_entries = []
    for plan, result, score, rank in ranked_candidates:
        ranking_entries.append({
            "rank": rank,
            "plan_id": plan.plan_id,
            "generator": plan.generator,
            "visualization": plan.visualization.value,
            "metric": f"{plan.metric.aggregation.value}({plan.metric.column})",
            "score_total": round(score.total, 4),
            "score_breakdown": {
                "evidence": round(score.evidence, 4),
                "coverage": round(score.coverage, 4),
                "stability": round(score.stability, 4) if score.stability is not None else None,
                "assumptions": round(score.assumptions, 4),
            },
        })

    alternates = [
        {
            "plan_id": alt.plan.plan_id,
            "score": round(alt.score, 4),
            "reason_not_winner": alt.reason_not_winner,
            "generator": alt.plan.generator,
        }
        for alt in spec.alternate_interpretations
    ]

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spec_id": spec.spec_id,
        "request_id": spec.trace.request_id,
        "dataset_id": spec.dataset_id,
        "intent": spec.intent,
        "winner": {
            "plan_id": spec.winner.plan.plan_id,
            "generator": spec.winner.plan.generator,
            "visualization": spec.winner.plan.visualization.value,
            "score": round(spec.winner.score_breakdown.total, 4),
            "rank_before_cascade": spec.winner.rank,
        },
        "is_tie": spec.is_tie,
        "tie_epsilon": RANK_TIE_EPSILON,
        "cascade_depth": spec.trace.cascade_depth,
        "ranker_weights": {
            "w1_evidence": RANK_W1_EVIDENCE,
            "w2_coverage": RANK_W2_COVERAGE,
            "w3_stability": RANK_W3_STABILITY,
            "w4_assumptions": RANK_W4_ASSUMPTIONS,
        },
        "ranked_candidates": ranking_entries,
        "alternates": alternates,
    }

    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")

    return entry


def save_candidate_artifact(
    *,
    plan: CandidatePlan,
    pass1a: Optional[Pass1aResult] = None,
    execution: Optional[ExecutionResult] = None,
    pass1b: Optional[Pass1bResult] = None,
    score: Optional[ScoreBreakdown] = None,
    pass2: Optional[Pass2Result] = None,
    artifacts_dir: Optional[Path] = None,
) -> Path:
    """Save an isolated JSON artifact for a single analytical candidate."""
    ensure_directories()
    target_dir = artifacts_dir or ARTIFACTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = target_dir / f"{plan.plan_id}.json"

    data = {
        "plan_id": plan.plan_id,
        "dataset_id": plan.dataset_id,
        "intent": plan.intent,
        "generator": plan.generator,
        "plan": plan.model_dump(),
        "pass1a": pass1a.model_dump() if pass1a else None,
        "execution": execution.model_dump() if execution else None,
        "pass1b": pass1b.model_dump() if pass1b else None,
        "score_breakdown": score.model_dump() if score else None,
        "pass2": pass2.model_dump() if pass2 else None,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    return artifact_path
