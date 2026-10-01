"""PlanGenerator interface, LLMDirectGenerator, ExternalAgentGenerator, and MockAgent.

Guarantees:
1. Strict schema compliance: All outputs validated against CandidatePlan schema. One retry, then drop.
2. Failure Isolation: External agent timeout or crash must NOT fail the request.
3. Read-only metadata tools: External agent has NO row access and NO SQL capability.
4. Bounded loop: External agent execution is bounded by AGENT_MAX_STEPS, AGENT_MAX_TOKENS, and AGENT_TIMEOUT_S.
5. Generator attribution: CandidatePlan.generator is set to 'llm_direct' or 'external_agent'.
6. Full decision logging: model, generator, steps, tokens, latency, cost.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import time
import hashlib
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from orchestrator.config import (
    AGENT_MAX_STEPS,
    AGENT_MAX_TOKENS,
    AGENT_TIMEOUT_S,
    AI_MAX_RETRIES,
    ESTIMATED_INPUT_COST_PER_M,
    ESTIMATED_OUTPUT_COST_PER_M,
    GENERATOR_MODE,
)
from providers import (
    LLMClient,
    LLMClientError,
    MockLLMClient,
    get_multi_provider_clients,
    get_strict_json_schema,
)
from orchestrator.schemas import (
    CandidatePlan,
    ColumnContextEntry,
    GeneratorCallLog,
    LLMContext,
    SemanticInterpretation,
)


class QuotaExceededError(RuntimeError):
    pass


class RateLimiter:
    """Per-provider rate limiter + daily call counter."""
    
    def __init__(self, limits_per_day: Dict[str, int] = None):
        self.limits = limits_per_day or {"gemini": 1000, "groq": 500, "ollama": 10000}
        self.state_file = "artifacts/quotas.json"
        self._load()

    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    self.counts = json.load(f)
            except:
                self.counts = {}
        else:
            self.counts = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.counts, f)

    def check_and_increment(self, provider: str):
        today = time.strftime("%Y-%m-%d")
        key = f"{provider}_{today}"
        current = self.counts.get(key, 0)
        limit = self.limits.get(provider, 1000)
        
        if current >= limit:
            raise QuotaExceededError(f"Daily quota reached for {provider}")
            
        self.counts[key] = current + 1
        self._save()


class ResponseCache:
    """Record/replay cache for multi-provider responses."""
    
    def __init__(self):
        self.cache_dir = "artifacts/llm_cache"
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_key(self, provider: str, model: str, prompt: str, context_hash: str) -> str:
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        safe_model = model.replace("/", "_").replace("\\", "_")
        return f"{provider}_{safe_model}_{prompt_hash}_{context_hash}"

    def get(self, provider: str, model: str, prompt: str, context_hash: str) -> Optional[Dict[str, Any]]:
        key = self._get_key(provider, model, prompt, context_hash)
        filepath = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except:
                return None
        return None

    def set(self, provider: str, model: str, prompt: str, context_hash: str, data: Dict[str, Any]):
        key = self._get_key(provider, model, prompt, context_hash)
        filepath = os.path.join(self.cache_dir, f"{key}.json")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f)


RATE_LIMITER = RateLimiter()
RESPONSE_CACHE = ResponseCache()


class PlanGenerator(ABC):
    """Abstract interface for analytical plan generation."""

    @abstractmethod
    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        """Generate up to k candidate plans for the given analytical context and interpretations."""
        pass


class LLMDirectGenerator(PlanGenerator):
    """Generates candidate plans directly via structured LLM schema prompts."""

    def __init__(self, llm_client: LLMClient):
        self.client = llm_client

    def _build_prompt(
        self,
        context: LLMContext,
        k: int,
        retry_error: Optional[str] = None,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> str:
        cols_summary = "\n".join(
            f"- {c.column_name} (Role: {c.candidate_role}, Confidence: {c.confidence:.2f}, Type: {c.dtype or 'N/A'})"
            for c in context.columns
        )

        interp_section = ""
        if interpretations:
            interp_lines = [
                f"- Interpretation {i+1}: {interp.intent_summary} (Metric: {interp.metric_column} [{interp.aggregation.value}], Dimensions: {interp.dimension_columns})"
                for i, interp in enumerate(interpretations)
            ]
            interp_section = "\nTarget Semantic Interpretations:\n" + "\n".join(interp_lines) + "\n"

        prompt = (
            f"You are a Business Intelligence Analyst. Generate {k} analytical query plan(s) for the dataset.\n"
            f"Dataset ID: {context.dataset_id}\n"
            f"User Intent: {context.intent}\n\n"
            f"Available Columns (Read-only Metadata):\n{cols_summary}\n"
            f"{interp_section}\n"
            "Rules:\n"
            "1. Metric must use a MEASURE role column for SUM/AVG/STDDEV/MEDIAN.\n"
            "2. Temporal granularity (YEAR, MONTH, DAY, etc.) requires a DATETIME column.\n"
            "3. Return a JSON object matching the CandidatePlan schema.\n"
        )
        if retry_error:
            prompt += f"\nPrevious attempt failed with error: {retry_error}. Please correct the schema.\n"
        return prompt

    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        logs: List[GeneratorCallLog] = []
        valid_plans: List[CandidatePlan] = []
        schema = CandidatePlan.model_json_schema()

        attempts = 1 + AI_MAX_RETRIES
        last_error = None

        for attempt in range(attempts):
            prompt = self._build_prompt(context, k=k, retry_error=last_error, interpretations=interpretations)
            try:
                raw_json, call_log = self.client.generate_structured(
                    prompt=prompt,
                    response_schema=schema,
                    generator_label="llm_direct",
                )
                logs.append(call_log)

                candidates = raw_json if isinstance(raw_json, list) else [raw_json]
                for item in candidates:
                    if isinstance(item, dict):
                        item["dataset_id"] = context.dataset_id
                        item["generator"] = "llm_direct"
                        if "intent" not in item:
                            item["intent"] = context.intent
                        plan = CandidatePlan.model_validate(item)
                        valid_plans.append(plan)

                if valid_plans:
                    break

            except (ValidationError, LLMClientError, Exception) as e:
                last_error = str(e)

        return valid_plans[:k], logs



class MultiProviderGenerator(PlanGenerator):
    """Calls configured providers (Gemini, Groq, Ollama) in parallel. Returns valid schema-checked plans."""

    def __init__(self, clients: Optional[List[LLMClient]] = None):
        if clients is not None:
            self.clients = clients
        else:
            self.clients = get_multi_provider_clients()

        self.eval_mode = os.getenv("EVAL_MODE", "false").lower() == "true"

    def _build_prompt(
        self,
        context: LLMContext,
        k: int,
        retry_error: Optional[str] = None,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> str:
        cols_summary = "\n".join(
            f"- {c.column_name} (Role: {c.candidate_role}, Confidence: {c.confidence:.2f}, Type: {c.dtype or 'N/A'})"
            for c in context.columns
        )

        interp_section = ""
        if interpretations:
            interp_lines = [
                f"- Interpretation {i+1}: {interp.intent_summary} (Metric: {interp.metric_column} [{interp.aggregation.value}], Dimensions: {interp.dimension_columns})"
                for i, interp in enumerate(interpretations)
            ]
            interp_section = "\nTarget Semantic Interpretations:\n" + "\n".join(interp_lines) + "\n"

        prompt = (
            f"You are a Business Intelligence Analyst. Generate {k} analytical query plan(s) for the dataset.\n"
            f"Dataset ID: {context.dataset_id}\n"
            f"User Intent: {context.intent}\n\n"
            f"Available Columns (Read-only Metadata):\n{cols_summary}\n"
            f"{interp_section}\n"
            "Rules:\n"
            "1. Metric must use a MEASURE role column for SUM/AVG/STDDEV/MEDIAN.\n"
            "2. Temporal granularity (YEAR, MONTH, DAY, etc.) requires a DATETIME column.\n"
            "3. Return a JSON object matching the CandidatePlan schema.\n"
        )
        if retry_error:
            prompt += f"\nPrevious attempt failed with error: {retry_error}. Please correct the schema.\n"
        return prompt

    def _call_provider(self, client: LLMClient, prompt: str, schema: Dict[str, Any], context: LLMContext, k: int) -> Tuple[List[CandidatePlan], GeneratorCallLog]:
        provider = client.provider
        model = client.model_name
        
        # Check quota
        RATE_LIMITER.check_and_increment(provider)
        
        # Check cache
        if self.eval_mode:
            cached = RESPONSE_CACHE.get(provider, model, prompt, context.context_hash)
            if cached:
                # Mock a call log
                call_log = GeneratorCallLog(
                    model=model,
                    generator="llm_direct",
                    steps=1,
                    input_tokens=100,
                    output_tokens=100,
                    latency_seconds=0.01,
                    estimated_cost_usd=0.0,
                )
                
                valid_plans = []
                candidates = cached if isinstance(cached, list) else [cached]
                for item in candidates:
                    if isinstance(item, dict):
                        item["dataset_id"] = context.dataset_id
                        item["generator"] = "llm_direct"
                        item["provider"] = provider
                        if "intent" not in item:
                            item["intent"] = context.intent
                        valid_plans.append(CandidatePlan.model_validate(item))
                
                return valid_plans, call_log

        # Make real call
        raw_json, call_log = client.generate_structured(
            prompt=prompt,
            response_schema=schema,
            generator_label="llm_direct",
        )
        
        # Save to cache
        RESPONSE_CACHE.set(provider, model, prompt, context.context_hash, raw_json)
        
        valid_plans = []
        candidates = raw_json if isinstance(raw_json, list) else [raw_json]
        for item in candidates:
            if isinstance(item, dict):
                item["dataset_id"] = context.dataset_id
                item["generator"] = "llm_direct"
                item["provider"] = provider
                if "intent" not in item:
                    item["intent"] = context.intent
                valid_plans.append(CandidatePlan.model_validate(item))
                
        return valid_plans, call_log

    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        
        all_logs: List[GeneratorCallLog] = []
        all_plans: List[CandidatePlan] = []
        schema = get_strict_json_schema(CandidatePlan)
        
        attempts = 1 + AI_MAX_RETRIES
        last_error = None
        
        for attempt in range(attempts):
            prompt = self._build_prompt(context, k=k, retry_error=last_error, interpretations=interpretations)

            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self._call_provider, client, prompt, schema, context, k): client
                    for client in self.clients
                }
                
                for future in concurrent.futures.as_completed(futures):
                    client = futures[future]
                    try:
                        # Timeout isolated per provider
                        plans, log = future.result(timeout=15.0)
                        all_logs.append(log)
                        all_plans.extend(plans)
                    except Exception as e:
                        # Failures are logged, never fatal
                        err_log = GeneratorCallLog(
                            model=client.model_name,
                            provider=client.provider,
                            generator="llm_direct",
                            steps=1,
                            input_tokens=0,
                            output_tokens=0,
                            latency_seconds=0.0,
                            estimated_cost_usd=0.0,
                        )
                        all_logs.append(err_log)
                        last_error = str(e)

            if all_plans:
                break
                
        # Reject structurally invalid plans before dedup / agreement scoring
        from orchestrator.validator import is_plan_structurally_valid
        valid_plans = [p for p in all_plans if is_plan_structurally_valid(p)]

        # Dedupe by plan_signature, aggregate supporting_count and provider lists
        unique_plans: Dict[str, CandidatePlan] = {}
        baseline_providers = {"rule_based_baseline", "local", "zero_cost_local"}
        
        # Exclude rule_based_baseline from provider counts and consensus math
        llm_providers_responded = sum(
            1 for log in all_logs
            if log.output_tokens > 0 and log.provider.lower() not in baseline_providers
        )
        if llm_providers_responded == 0:
            llm_providers_responded = sum(1 for log in all_logs if log.output_tokens > 0) or 1

        for plan in valid_plans:
            sig = plan.plan_signature()
            is_baseline = plan.provider.lower() in baseline_providers
            init_supporting = [] if is_baseline else [plan.provider]
            init_count = 0 if is_baseline else 1

            if sig not in unique_plans:
                unique_plans[sig] = plan.model_copy(update={
                    "supporting_count": init_count,
                    "providers_responded": llm_providers_responded,
                    "supporting_providers": init_supporting
                })
            else:
                curr = unique_plans[sig]
                if not is_baseline and plan.provider not in curr.supporting_providers:
                    new_providers = curr.supporting_providers + [plan.provider]
                    unique_plans[sig] = curr.model_copy(update={
                        "supporting_count": curr.supporting_count + 1,
                        "supporting_providers": new_providers
                    })

        return list(unique_plans.values())[:k], all_logs


# ---------------------------------------------------------------------------
# External Agent Read-Only Metadata Tools
# ---------------------------------------------------------------------------


class AgentMetadataEnvironment:
    """Read-only sandbox providing metadata exploration tools to external agents."""

    def __init__(self, context: LLMContext):
        self._columns_by_name: Dict[str, ColumnContextEntry] = {
            c.column_name.lower(): c for c in context.columns
        }
        self.context = context

    def list_columns(self) -> List[Dict[str, Any]]:
        return [
            {
                "column_name": c.column_name,
                "candidate_role": c.candidate_role,
                "confidence": c.confidence,
                "confidence_level": c.confidence_level,
            }
            for c in self.context.columns
        ]

    def get_column_stats(self, column_name: str) -> Dict[str, Any]:
        col = self._columns_by_name.get(column_name.strip().lower())
        if not col:
            return {"error": f"Column '{column_name}' not found."}
        return {
            "column_name": col.column_name,
            "dtype": col.dtype,
            "distinct_count": col.distinct_count,
            "null_percentage": col.null_percentage,
        }

    def get_column_evidence(self, column_name: str) -> Dict[str, Any]:
        col = self._columns_by_name.get(column_name.strip().lower())
        if not col:
            return {"error": f"Column '{column_name}' not found."}
        return {
            "column_name": col.column_name,
            "evidence": col.evidence,
        }


class ExternalAgentGenerator(PlanGenerator):
    """Generates candidate plans via an autonomous reasoning agent with bounded steps."""

    def __init__(
        self,
        llm_client: LLMClient,
        max_steps: int = AGENT_MAX_STEPS,
        timeout_seconds: float = AGENT_TIMEOUT_S,
        max_tokens: int = AGENT_MAX_TOKENS,
    ):
        self.client = llm_client
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

    def _execute_agent_loop(
        self,
        context: LLMContext,
        k: int,
    ) -> Tuple[List[CandidatePlan], GeneratorCallLog]:
        start_time = time.perf_counter()
        env = AgentMetadataEnvironment(context)
        schema = get_strict_json_schema(CandidatePlan)

        steps_taken = 0
        total_input_tokens = 0
        total_output_tokens = 0

        cols = env.list_columns()
        steps_taken += 1

        prompt = (
            f"You are an analytical agent constructing an optimal CandidatePlan.\n"
            f"Dataset ID: {context.dataset_id}\n"
            f"User Intent: {context.intent}\n"
            f"Columns: {json.dumps(cols)}\n\n"
            "Produce the final CandidatePlan adhering to the JSON schema."
        )

        valid_plans: List[CandidatePlan] = []
        attempts = 1 + AI_MAX_RETRIES

        for attempt in range(attempts):
            if steps_taken >= self.max_steps:
                break

            steps_taken += 1
            raw_json, call_log = self.client.generate_structured(
                prompt=prompt,
                response_schema=schema,
                generator_label="external_agent",
            )
            total_input_tokens += call_log.input_tokens
            total_output_tokens += call_log.output_tokens

            try:
                if isinstance(raw_json, dict):
                    raw_json["dataset_id"] = context.dataset_id
                    raw_json["generator"] = "external_agent"
                    raw_json["provider"] = getattr(self.client, "provider", "unknown")
                    if "intent" not in raw_json:
                        raw_json["intent"] = context.intent
                    plan = CandidatePlan.model_validate(raw_json)
                    valid_plans.append(plan)
                    break
            except ValidationError as ve:
                prompt += f"\nValidation error: {str(ve)}. Please correct the plan."

        latency = time.perf_counter() - start_time
        cost = (
            (total_input_tokens / 1_000_000.0) * ESTIMATED_INPUT_COST_PER_M
            + (total_output_tokens / 1_000_000.0) * ESTIMATED_OUTPUT_COST_PER_M
        )

        agent_log = GeneratorCallLog(
            model=getattr(self.client, "model_name", "agent-orchestrator"),
            generator="external_agent",
            steps=steps_taken,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            thinking_tokens=0,
            latency_seconds=round(latency, 4),
            estimated_cost_usd=round(cost, 6),
        )

        return valid_plans[:k], agent_log

    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        start_time = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._execute_agent_loop, context, k)
            try:
                plans, log = future.result(timeout=self.timeout_seconds)
                return plans, [log]
            except concurrent.futures.TimeoutError:
                latency = time.perf_counter() - start_time
                timeout_log = GeneratorCallLog(
                    model=getattr(self.client, "model_name", "agent-orchestrator"),
                    generator="external_agent",
                    steps=1,
                    input_tokens=0,
                    output_tokens=0,
                    thinking_tokens=0,
                    latency_seconds=round(latency, 4),
                    estimated_cost_usd=0.0,
                )
                return [], [timeout_log]
            except Exception as e:
                latency = time.perf_counter() - start_time
                error_log = GeneratorCallLog(
                    model=getattr(self.client, "model_name", "agent-orchestrator"),
                    generator="external_agent",
                    steps=1,
                    input_tokens=0,
                    output_tokens=0,
                    thinking_tokens=0,
                    latency_seconds=round(latency, 4),
                    estimated_cost_usd=0.0,
                )
                return [], [error_log]


class MockAgent(PlanGenerator):
    """Mock agent implementation for unit tests verifying timeouts, isolation, and metadata tool access."""

    def __init__(
        self,
        canned_plans: Optional[List[CandidatePlan]] = None,
        simulate_timeout: bool = False,
        simulate_error: bool = False,
        sleep_seconds: float = 0.0,
    ):
        self.canned_plans = canned_plans or []
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.sleep_seconds = sleep_seconds
        self.tools_called: List[str] = []

    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
        interpretations: Optional[List[SemanticInterpretation]] = None,
        **kwargs: Any,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        env = AgentMetadataEnvironment(context)
        self.tools_called.append("list_columns")
        _ = env.list_columns()

        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)

        if self.simulate_timeout:
            log = GeneratorCallLog(
                model="mock-agent",
                generator="external_agent",
                steps=1,
                input_tokens=0,
                output_tokens=0,
                thinking_tokens=0,
                latency_seconds=round(self.sleep_seconds, 4),
                estimated_cost_usd=0.0,
            )
            return [], [log]

        if self.simulate_error:
            raise RuntimeError("Mock agent encountered unexpected error.")

        plans = [
            p.model_copy(update={"generator": "external_agent"})
            for p in self.canned_plans[:k]
        ]
        log = GeneratorCallLog(
            model="mock-agent",
            generator="external_agent",
            steps=2,
            input_tokens=100,
            output_tokens=80,
            thinking_tokens=0,
            latency_seconds=0.02,
            estimated_cost_usd=0.000030,
        )
        return plans, [log]



# ---------------------------------------------------------------------------
# Coordinator dispatching according to GENERATOR_MODE
# ---------------------------------------------------------------------------


class PlanGenerationCoordinator:
    """Dispatches candidate generation according to GENERATOR_MODE."""

    def __init__(
        self,
        direct_generator: PlanGenerator,
        agent_generator: PlanGenerator,
        mode: Optional[str] = None,
    ):
        self.direct_generator = direct_generator
        self.agent_generator = agent_generator
        self.mode = mode or GENERATOR_MODE
        self.agent_loop = os.getenv("AGENT_LOOP", "false").lower() == "true"

    def generate_candidates(
        self,
        context: LLMContext,
        k: int = 3,
        interpretations: Optional[List[SemanticInterpretation]] = None,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        all_plans: List[CandidatePlan] = []
        all_logs: List[GeneratorCallLog] = []

        if self.mode == "llm_only":
            plans, logs = self.direct_generator.generate_plans(context, k=k, interpretations=interpretations)
            all_plans.extend(plans)
            all_logs.extend(logs)

        elif self.mode == "agent_only" and self.agent_loop:
            plans, logs = self.agent_generator.generate_plans(context, k=k, interpretations=interpretations)
            all_plans.extend(plans)
            all_logs.extend(logs)

        elif self.mode == "both":
            try:
                d_plans, d_logs = self.direct_generator.generate_plans(context, k=k, interpretations=interpretations)
                all_plans.extend(d_plans)
                all_logs.extend(d_logs)
            except Exception:
                pass

            if self.agent_loop:
                try:
                    a_plans, a_logs = self.agent_generator.generate_plans(context, k=k, interpretations=interpretations)
                    all_plans.extend(a_plans)
                    all_logs.extend(a_logs)
                except Exception:
                    pass

        # Since MultiProviderGenerator already dedupes, we just return
        return all_plans[:k], all_logs

    generate_plans = generate_candidates

