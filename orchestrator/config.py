"""Orchestrator configuration constants.

All values are project decisions (configurable defaults, not spec requirements).
They are intentional hypotheses and are logged alongside all decisions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Candidate Worker Pool
# ---------------------------------------------------------------------------

# Maximum number of parallel K-way candidate plans to generate and execute.
MAX_K: int = 3

# ---------------------------------------------------------------------------
# LLM Generation and Retry Caps  (Project Decisions)
# ---------------------------------------------------------------------------

# Maximum attempts for the initial LLM JSON-schema generation call.
# Capped at 1 retry: 1 initial attempt + 1 automatic retry = 2 total calls max.
AI_MAX_RETRIES: int = 1

# Maximum number of re-prompts allowed when a DuckDB execution error is
# returned to the LLM (error-informed re-prompt loop in Pass 1).
PASS1_REPROMPT_MAX: int = 2

# Maximum depth of the runner-up cascade triggered by Pass 2 failure.
# After this many rollback steps, the orchestrator returns a UNANSWERABLE result.
MAX_CASCADE_DEPTH: int = 2

# ---------------------------------------------------------------------------
# Ranker V1 — Tie Threshold  (Project Decision / Configurable Hypothesis)
# ---------------------------------------------------------------------------

# Score differential below which two ranked candidates are considered tied.
# Ties trigger a clarification prompt rather than arbitrary winner selection.
RANK_TIE_EPSILON: float = 0.05

# ---------------------------------------------------------------------------
# Ranker V1 — Score Weights  (Project Decisions / Configurable Hypotheses)
# ---------------------------------------------------------------------------
# score = w1*evidence + w2*coverage + w3*stability - w4*assumptions
# These weights are hypotheses; they are configurable and logged with every ranking.

RANK_W1_EVIDENCE: float = 0.35    # mean role confidence of columns used
RANK_W2_COVERAGE: float = 0.30    # fraction of request terms mapped to plan fields
RANK_W3_STABILITY: float = 0.20   # result agreement under small perturbations
RANK_W4_ASSUMPTIONS: float = 0.15 # count of defaults filled without request support
RANK_W5_AGREEMENT: float = 0.10   # supporting_count / providers_responded

# ---------------------------------------------------------------------------
# DuckDB Worker Resource Limits  (Project Decisions)
# ---------------------------------------------------------------------------

# Per-worker DuckDB thread count limit (single-threaded for predictability).
DUCKDB_THREAD_LIMIT: int = 1

# Per-worker DuckDB memory limit (string format accepted by DuckDB PRAGMA).
DUCKDB_MEMORY_LIMIT: str = "256MB"

# Per-worker execution timeout in seconds before thread interrupt is raised.
DUCKDB_TIMEOUT_SECONDS: float = 30.0

# ---------------------------------------------------------------------------
# Result Limits
# ---------------------------------------------------------------------------

# Maximum number of rows allowed in an ExecutionResult before Pass 1b rejects.
RESULT_ROW_CAP: int = 50_000

# Maximum fraction of failed datetime TRY_CAST operations before Pass 1b rejects.
FAILED_CAST_RATE_THRESHOLD: float = 0.50

# ---------------------------------------------------------------------------
# Generator Configuration & Modes
# ---------------------------------------------------------------------------

# Generator mode: "llm_only" | "agent_only" | "both" (default "llm_only")
GENERATOR_MODE: str = "llm_only"

# ---------------------------------------------------------------------------
# External Agent Resource Limits (Project Decisions)
# ---------------------------------------------------------------------------

# Maximum reasoning/tool execution steps an external agent can perform per request.
AGENT_MAX_STEPS: int = 5

# Maximum context/output token budget for agent execution.
AGENT_MAX_TOKENS: int = 4096

# Agent execution timeout in seconds.
AGENT_TIMEOUT_S: float = 30.0

# ---------------------------------------------------------------------------
# Gemini LLM Client Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY_ENV: str = "GEMINI_API_KEY"
GEMINI_MODEL_ENV: str = "GEMINI_MODEL"
DEFAULT_GEMINI_MODEL: str = "gemini-2.5-flash"

GROQ_API_KEY_ENV: str = "GROQ_API_KEY"
GROQ_MODEL_ENV: str = "GROQ_MODEL"
DEFAULT_GROQ_MODEL: str = "llama3-70b-8192"

OLLAMA_HOST_ENV: str = "OLLAMA_HOST"
OLLAMA_MODEL_ENV: str = "OLLAMA_MODEL"
DEFAULT_OLLAMA_MODEL: str = "llama3"
DEFAULT_OLLAMA_HOST: str = "http://localhost:11434"

PROVIDER_ENV: str = "PROVIDER"
DEFAULT_PROVIDER: str = "gemini"

EVAL_MODE_ENV: str = "EVAL_MODE"
RUN_LIVE_TESTS_ENV: str = "RUN_LIVE_TESTS"

# Cost estimation constants ($ per 1M tokens, gemini-2.5-flash baseline)
ESTIMATED_INPUT_COST_PER_M: float = 0.075
ESTIMATED_OUTPUT_COST_PER_M: float = 0.30
