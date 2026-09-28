# Multi-Agentic Candidate Plan Generator Architecture

**Status:** Implemented in `orchestrator/generator.py`, `orchestrator/llm.py`, and `orchestrator/capabilities.py`  
**Current Commit:** `b5032e0` / Stage 8 Multi-Agent Generator Overhaul

---

## 1. Overview

The Multi-Agentic Generator layer produces schema-valid analytical `CandidatePlan` objects in response to natural-language user queries. It combines:
- **Multi-Provider LLM Clients**: Unified integration across Google Gemini (`google-genai`), Groq Cloud API, and local Ollama instances.
- **Parallel Dispatch**: Concurrent generation from multiple distinct models/providers.
- **Isolated Reasoning Agents**: Autonomous agents equipped with sandboxed, read-only metadata exploration tools.
- **Deterministic Schema Enforcement**: Strict JSON schema adherence (`additionalProperties: false`, all properties required).
- **Consensus & Agreement Scoring**: Cross-provider agreement tracking (`ScoreBreakdown.agreement` and `RankerWeights.w5_agreement`).

---

## 2. Provider Support Matrix

| Provider | Client Class | Transport | Authentication | Default Model | Strict Schema Support |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** | `GeminiClient` | `google-genai` SDK | `GEMINI_API_KEY` | `gemini-2.5-flash` | Native via SDK `response_schema` |
| **Groq Cloud** | `GroqClient` | Direct HTTP (`urllib.request`) | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | Schema-prompt injection + `json_object` |
| **Local Ollama** | `OllamaClient` | Direct HTTP (`urllib.request`) | **None (Localhost)** | `llama3` | Schema-prompt injection + `format: json` |

### Provider Configuration via Environment Variables

All settings are configured through `.env` (template in `.env.example`):
- `PROVIDER`: Active provider (`gemini`, `groq`, `ollama`)
- `GEMINI_API_KEY`, `GEMINI_MODEL`: Gemini authentication and model tag
- `GROQ_API_KEY`, `GROQ_MODEL`: Groq API key and model identifier
- `OLLAMA_HOST`, `OLLAMA_MODEL`: Local Ollama HTTP endpoint (`http://localhost:11434`) and model tag
- `GENERATOR_MODE`: Generation mode (`llm_only`, `agent_only`, `both`)
- `AGENT_LOOP`: Enable autonomous multi-step reasoning agent (`true` / `false`)
- `EVAL_MODE`: Enable offline response caching for regression benchmarking

---

## 3. Generator Implementations

### 3.1 `MultiProviderGenerator`
Queries enabled providers (Gemini, Groq, Ollama) concurrently using `concurrent.futures.ThreadPoolExecutor`.
- Deduplicates plans by structural `plan_signature()`.
- Calculates provider agreement count (how many models agreed on the same candidate structure).
- Records per-provider call telemetry (`input_tokens`, `output_tokens`, `latency_seconds`, `estimated_cost_usd`).

### 3.2 `LLMDirectGenerator`
Single-client direct generator providing structured prompt generation with 1-shot retry on schema decoding error. Backward-compatible with standalone tests and single-model deployments.

### 3.3 `ExternalAgentGenerator`
Runs an autonomous reasoning agent within a sandboxed `AgentMetadataEnvironment`:
- **Read-Only Invariant**: Agent has access **only** to metadata methods: `list_columns()`, `get_column_stats()`, and `get_column_evidence()`.
- **Zero Raw Data Access**: Raw dataframe rows and arbitrary SQL execution are strictly prohibited.
- **Resource Bounds**: Bounded by `AGENT_MAX_STEPS` (default: 5), `AGENT_MAX_TOKENS` (default: 4096), and `AGENT_TIMEOUT_S` (default: 30.0s).
- **Failure Isolation**: Agent timeouts or crashes fail gracefully without terminating the user's HTTP request.

---

## 4. Telemetry and Explainability

Every generator call produces a `GeneratorCallLog`:
```python
GeneratorCallLog(
    model="gemini-2.5-flash",
    provider="gemini",
    generator="llm_direct",
    steps=1,
    input_tokens=420,
    output_tokens=180,
    latency_seconds=1.24,
    estimated_cost_usd=0.000085,
)
```
Logs are preserved in `OrchestratorTrace.candidate_artifacts` and emitted in explainability audit trails under `artifacts/candidate_plans/`.
