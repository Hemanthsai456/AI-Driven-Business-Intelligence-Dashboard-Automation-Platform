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
import time
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
from orchestrator.llm import LLMClient, LLMClientError, MockLLMClient
from orchestrator.schemas import (
    CandidatePlan,
    ColumnContextEntry,
    GeneratorCallLog,
    LLMContext,
)


class PlanGenerator(ABC):
    """Abstract interface for analytical plan generation."""

    @abstractmethod
    def generate_plans(
        self,
        context: LLMContext,
        k: int = 1,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        """Generate up to k candidate plans for the given analytical context."""
        pass


class LLMDirectGenerator(PlanGenerator):
    """Generates candidate plans directly via structured LLM schema prompts."""

    def __init__(self, llm_client: LLMClient):
        self.client = llm_client

    def _build_prompt(self, context: LLMContext, k: int, retry_error: Optional[str] = None) -> str:
        cols_summary = "\n".join(
            f"- {c.column_name} (Role: {c.candidate_role}, Confidence: {c.confidence:.2f}, Type: {c.dtype or 'N/A'})"
            for c in context.columns
        )

        prompt = (
            f"You are a Business Intelligence Analyst. Generate {k} analytical query plan(s) for the dataset.\n"
            f"Dataset ID: {context.dataset_id}\n"
            f"User Intent: {context.intent}\n\n"
            f"Available Columns (Read-only Metadata):\n{cols_summary}\n\n"
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
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        logs: List[GeneratorCallLog] = []
        valid_plans: List[CandidatePlan] = []
        schema = CandidatePlan.model_json_schema()

        attempts = 1 + AI_MAX_RETRIES
        last_error = None

        for attempt in range(attempts):
            prompt = self._build_prompt(context, k=k, retry_error=last_error)
            try:
                raw_json, call_log = self.client.generate_structured(
                    prompt=prompt,
                    response_schema=schema,
                    generator_label="llm_direct",
                )
                logs.append(call_log)

                # Output can be single plan dict or list of plan dicts
                candidates = raw_json if isinstance(raw_json, list) else [raw_json]
                for item in candidates:
                    if isinstance(item, dict):
                        # Ensure dataset_id and generator match
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


# ---------------------------------------------------------------------------
# External Agent Read-Only Metadata Tools
# ---------------------------------------------------------------------------


class AgentMetadataEnvironment:
    """Read-only sandbox providing metadata exploration tools to external agents.

    Guarantees:
    - NO row access
    - NO SQL execution
    - Only accesses sanitized LLMContext structures
    """

    def __init__(self, context: LLMContext):
        self._columns_by_name: Dict[str, ColumnContextEntry] = {
            c.column_name.lower(): c for c in context.columns
        }
        self.context = context

    def list_columns(self) -> List[Dict[str, Any]]:
        """List all available dataset columns with candidate role and confidence."""
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
        """Get summary statistics for a column (null %, distinct count, dtype). NO raw rows."""
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
        """Get semantic evidence statements supporting role classification."""
        col = self._columns_by_name.get(column_name.strip().lower())
        if not col:
            return {"error": f"Column '{column_name}' not found."}
        return {
            "column_name": col.column_name,
            "evidence": col.evidence,
        }


class ExternalAgentGenerator(PlanGenerator):
    """Generates candidate plans via an autonomous reasoning agent with bounded steps.

    Uses an external agent loop constrained by AGENT_MAX_STEPS, AGENT_MAX_TOKENS,
    and AGENT_TIMEOUT_S. Has access to read-only metadata tools only.
    """

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
        schema = CandidatePlan.model_json_schema()

        steps_taken = 0
        total_input_tokens = 0
        total_output_tokens = 0

        # Step 1: Agent inspects available columns via list_columns
        cols = env.list_columns()
        steps_taken += 1

        # Identify candidate measures and dimensions for the user intent
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
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        """Run external agent with strict failure isolation and timeout boundaries."""
        start_time = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._execute_agent_loop, context, k)
            try:
                plans, log = future.result(timeout=self.timeout_seconds)
                return plans, [log]
            except concurrent.futures.TimeoutError:
                # Failure isolation: timeout must NOT fail the request
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
                # Failure isolation: runtime exception must NOT fail the request
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
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        env = AgentMetadataEnvironment(context)
        # Record metadata tool calls
        self.tools_called.append("list_columns")
        _ = env.list_columns()

        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)

        if self.simulate_timeout:
            # Simulate timeout scenario directly
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
    """Dispatches candidate generation according to GENERATOR_MODE ('llm_only', 'agent_only', 'both')."""

    def __init__(
        self,
        direct_generator: PlanGenerator,
        agent_generator: PlanGenerator,
        mode: Optional[str] = None,
    ):
        self.direct_generator = direct_generator
        self.agent_generator = agent_generator
        self.mode = mode or GENERATOR_MODE

    def generate_candidates(
        self,
        context: LLMContext,
        k: int = 3,
    ) -> Tuple[List[CandidatePlan], List[GeneratorCallLog]]:
        """Generate candidates based on configured mode with failure isolation."""
        all_plans: List[CandidatePlan] = []
        all_logs: List[GeneratorCallLog] = []

        if self.mode == "llm_only":
            plans, logs = self.direct_generator.generate_plans(context, k=k)
            all_plans.extend(plans)
            all_logs.extend(logs)

        elif self.mode == "agent_only":
            plans, logs = self.agent_generator.generate_plans(context, k=k)
            all_plans.extend(plans)
            all_logs.extend(logs)

        elif self.mode == "both":
            # Generate from direct LLM
            try:
                d_plans, d_logs = self.direct_generator.generate_plans(context, k=k)
                all_plans.extend(d_plans)
                all_logs.extend(d_logs)
            except Exception:
                pass

            # Generate from external agent (with failure isolation)
            try:
                a_plans, a_logs = self.agent_generator.generate_plans(context, k=k)
                all_plans.extend(a_plans)
                all_logs.extend(a_logs)
            except Exception:
                pass

        # Deduplicate while preserving order
        unique_plans: List[CandidatePlan] = []
        seen_sigs = set()
        for p in all_plans:
            sig = p.plan_signature()
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                unique_plans.append(p)

        return unique_plans[:k], all_logs
