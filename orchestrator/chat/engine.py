"""Master Evidence-Grounded Dataset Chat Engine (Step 8 / Roadmap #7).

Orchestrates multi-turn dataset chat:
1. Intent classification & dispatch (classifier.py)
2. Structured follow-up resolution & pronoun binding (followup.py)
3. Authoritative NL -> SQL execution via AnalyticalQueryEngine (orchestrator.query_engine)
4. Numerical grounding & hallucination protection (response_generator.py)
5. Specialized handlers for Metadata, Insights, and Dashboard Provenance
6. Complete state isolation per ConversationContext
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ingestion.models import CanonicalDataset
from intelligence.profiler import DataProfile
from intelligence.schema_validator import AnalysisReadiness
from intelligence.semantic_analyzer import DatasetSemanticProfile
from orchestrator.chat.classifier import ChatIntentClassifier
from orchestrator.chat.dashboard_handler import DashboardExplanationHandler
from orchestrator.chat.followup import FollowUpResolver
from orchestrator.chat.insight_handler import InsightChatHandler
from orchestrator.chat.metadata_handler import DatasetMetadataHandler
from orchestrator.chat.response_generator import ChatResponseGenerator
from orchestrator.chat.schemas import (
    ChatIntentType,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ConversationContext,
)
from orchestrator.query_engine import execute_analytical_query
from orchestrator.schemas import AmbiguityStatus, ValidationStatus
from providers.base import LLMClient


class DatasetChatEngine:
    """Coordinator for Evidence-Grounded Dataset Conversations."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.classifier = ChatIntentClassifier()
        self.followup_resolver = FollowUpResolver()
        self.response_generator = ChatResponseGenerator(llm_client)
        self.metadata_handler = DatasetMetadataHandler()
        self.insight_handler = InsightChatHandler()
        self.dashboard_handler = DashboardExplanationHandler()

    def process_chat_turn(
        self,
        dataset: CanonicalDataset,
        semantic_profile: DatasetSemanticProfile,
        message: str,
        context: ConversationContext,
        readiness: Optional[AnalysisReadiness] = None,
        data_profile: Optional[DataProfile] = None,
        use_llm: bool = True,
    ) -> ChatResponse:
        """Process a single conversational turn against an active dataset session."""
        start_time = time.perf_counter()
        msg_clean = (message or "").strip()
        msg_id = str(uuid4())
        dataset_id = dataset.metadata.dataset_id if dataset.metadata else "unknown_dataset"

        # Record user message in history
        context.add_message(ChatMessage(message_id=str(uuid4()), role=ChatRole.USER, content=msg_clean))

        # Handle empty message
        if not msg_clean:
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer="Please enter a question about your dataset (e.g., 'What is the average salary by department?' or 'Show me key insights').",
                intent_type=ChatIntentType.GENERAL_HELP,
                confidence=1.0,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=resp.answer))
            return resp

        # 1. Intent Classification
        intent_type, notice = self.classifier.classify_intent(msg_clean, semantic_profile, context)

        # 2. Handle Unsupported Forecasting / Causal Claims
        if intent_type == ChatIntentType.UNSUPPORTED_OR_CAUSAL:
            answer_text = notice or "I cannot fulfill this speculative request."
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=answer_text,
                intent_type=ChatIntentType.UNSUPPORTED_OR_CAUSAL,
                confidence=1.0,
                warnings=["Predictive forecasting and causal claims are outside current analytical capabilities."],
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=answer_text))
            return resp

        # 3. Handle Provenance / SQL on previous result
        if intent_type == ChatIntentType.PROVENANCE_OR_SQL:
            if context.last_compiled_sql:
                answer_text = (
                    f"**SQL Provenance for Previous Result**:\n\n"
                    f"```sql\n{context.last_compiled_sql}\n```\n\n"
                    f"*Target Metric*: `{context.last_metric}`\n"
                    f"*Target Dimension(s)*: `{', '.join(context.last_dimensions) if context.last_dimensions else 'None'}`"
                )
                resp = ChatResponse(
                    conversation_id=context.conversation_id,
                    message_id=msg_id,
                    dataset_id=dataset_id,
                    question=msg_clean,
                    answer=answer_text,
                    intent_type=ChatIntentType.PROVENANCE_OR_SQL,
                    compiled_sql=context.last_compiled_sql,
                    data=context.last_result_rows,
                    columns=context.last_columns,
                    row_count=len(context.last_result_rows) if context.last_result_rows else 0,
                    confidence=1.0,
                    runtime_seconds=round(time.perf_counter() - start_time, 4),
                )
            else:
                answer_text = "No previous analytical query has been executed yet in this conversation session."
                resp = ChatResponse(
                    conversation_id=context.conversation_id,
                    message_id=msg_id,
                    dataset_id=dataset_id,
                    question=msg_clean,
                    answer=answer_text,
                    intent_type=ChatIntentType.PROVENANCE_OR_SQL,
                    confidence=1.0,
                    runtime_seconds=round(time.perf_counter() - start_time, 4),
                )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=answer_text))
            return resp

        # 4. Handle Dataset Metadata & Understanding
        if intent_type == ChatIntentType.DATASET_METADATA:
            meta_res = self.metadata_handler.handle_metadata_query(
                msg_clean, dataset, data_profile, semantic_profile, readiness
            )
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=meta_res["answer"],
                intent_type=ChatIntentType.DATASET_METADATA,
                data=meta_res.get("data"),
                columns=meta_res.get("columns"),
                row_count=meta_res.get("row_count", 0),
                evidence=meta_res.get("evidence"),
                confidence=1.0,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=resp.answer))
            return resp

        # 5. Handle Insight Questions (Step 6 engine)
        if intent_type == ChatIntentType.INSIGHT_EXPLANATION:
            ins_res = self.insight_handler.handle_insight_query(
                msg_clean, dataset, semantic_profile
            )
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=ins_res["answer"],
                intent_type=ChatIntentType.INSIGHT_EXPLANATION,
                data=ins_res.get("data"),
                columns=ins_res.get("columns"),
                row_count=ins_res.get("row_count", 0),
                compiled_sql=ins_res.get("compiled_sql"),
                evidence=ins_res.get("evidence"),
                confidence=1.0,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=resp.answer))
            return resp

        # 6. Handle Dashboard Explanation Questions (Step 7 engine)
        if intent_type == ChatIntentType.DASHBOARD_EXPLANATION:
            dash_res = self.dashboard_handler.handle_dashboard_query(
                msg_clean, dataset, semantic_profile, readiness, data_profile
            )
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=dash_res["answer"],
                intent_type=ChatIntentType.DASHBOARD_EXPLANATION,
                data=dash_res.get("data"),
                columns=dash_res.get("columns"),
                row_count=dash_res.get("row_count", 0),
                compiled_sql=dash_res.get("compiled_sql"),
                evidence=dash_res.get("evidence"),
                confidence=1.0,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=resp.answer))
            return resp

        # 7. Follow-up Resolution or Analytical Query Execution
        target_question = msg_clean
        compared_entities: Optional[List[str]] = None

        if intent_type == ChatIntentType.COMPARISON:
            # Detect compared entities e.g. "compare ... between Eng and Sales" or "compare Eng and Sales"
            comp_m = re.search(r"\bcompare\s+(?:(?:average|total|avg|mean|sum)\s+)?(?:([a-z0-9_]+)\s+)?(?:between|for|of)?\s*([a-z0-9_\s]+?)\s+and\s+([a-z0-9_\s]+)", msg_clean, re.IGNORECASE)
            if comp_m:
                cand_m = comp_m.group(1)
                e1 = comp_m.group(2).strip().lower()
                e2 = comp_m.group(3).strip().lower()
                e1 = re.sub(r"^(?:the|between|for)\s+", "", e1).strip()
                e2 = re.sub(r"^(?:the)\s+", "", e2).strip()
                compared_entities = [e1, e2]

                # Find candidate measure and dimension
                target_m = cand_m if cand_m and semantic_profile.get_evidence(cand_m) else (context.last_metric or "")
                if not target_m:
                    for c_name, ev in semantic_profile.column_evidences.items():
                        if ev.candidate_role.value == "MEASURE":
                            target_m = c_name
                            break

                dim_cols = [c for c, ev in semantic_profile.column_evidences.items() if ev.candidate_role.value == "DIMENSION"]
                target_d = dim_cols[0] if dim_cols else (context.last_dimensions[0] if context.last_dimensions else "")

                if target_m and target_d:
                    target_question = f"What is the average {target_m} by {target_d}?"

        elif intent_type == ChatIntentType.FOLLOW_UP:
            synth_q, overrides, need_clarify, clarify_opts = self.followup_resolver.resolve_followup(
                msg_clean, context, semantic_profile
            )
            if need_clarify:
                answer_text = "I found multiple possible interpretations for this follow-up. Please clarify:"
                resp = ChatResponse(
                    conversation_id=context.conversation_id,
                    message_id=msg_id,
                    dataset_id=dataset_id,
                    question=msg_clean,
                    answer=answer_text,
                    intent_type=ChatIntentType.AMBIGUOUS_CLARIFICATION,
                    clarification_needed=True,
                    clarification_options=clarify_opts,
                    ambiguity_status="AMBIGUOUS",
                    confidence=0.5,
                    runtime_seconds=round(time.perf_counter() - start_time, 4),
                )
                context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=answer_text))
                return resp
            target_question = synth_q

        # 8. Authoritative Analytical Query Execution (via AnalyticalQueryEngine)
        q_res = execute_analytical_query(
            question=target_question,
            dataset=dataset,
            semantic_profile=semantic_profile,
            readiness=readiness,
        )

        # Filter rows if specific entities were compared
        final_rows = q_res.rows or []
        final_row_count = q_res.row_count if q_res.rows is not None else 0
        if compared_entities and q_res.rows:
            filtered = []
            for r in q_res.rows:
                for v in r.values():
                    if str(v).strip().lower() in compared_entities:
                        filtered.append(r)
                        break
            if len(filtered) >= 2:
                final_rows = filtered
                final_row_count = len(filtered)

        # 9. Handle Ambiguity
        if q_res.ambiguity_status == AmbiguityStatus.AMBIGUOUS:
            options = []
            if q_res.ambiguity_details:
                for a in q_res.ambiguity_details:
                    options.extend(a.alternatives)
            answer_text = q_res.error_message or "Your question is ambiguous. Please select one of the candidate interpretations below:"
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=answer_text,
                intent_type=ChatIntentType.AMBIGUOUS_CLARIFICATION,
                clarification_needed=True,
                clarification_options=options if options else ["Clarify metric", "Clarify dimension"],
                ambiguity_status=q_res.ambiguity_status.value,
                confidence=q_res.confidence,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=answer_text))
            return resp

        # 10. Handle Execution/Validation Failures or Zero Matching Rows
        warnings_list = [i.message for i in q_res.validation_issues if hasattr(i, "message")]
        is_null_eval = any("evaluated to NULL" in str(w) for w in warnings_list)

        if is_null_eval:
            answer_text = "No matching records were found in the dataset for this query."
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=answer_text,
                intent_type=intent_type,
                query_plan=q_res.plan.model_dump() if q_res.plan else None,
                compiled_sql=q_res.compiled_sql,
                data=[],
                columns=q_res.columns,
                row_count=0,
                evidence=q_res.evidence,
                confidence=q_res.confidence,
                warnings=warnings_list,
                ambiguity_status="CLEAR",
                clarification_needed=False,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=answer_text))
            return resp

        if q_res.validation_status == "FAILED" or q_res.ambiguity_status == AmbiguityStatus.UNANSWERABLE:
            err_msg = q_res.error_message or "The analytical engine could not resolve a valid plan for this request."
            answer_text = f"I could not execute this analytical query: {err_msg}"
            resp = ChatResponse(
                conversation_id=context.conversation_id,
                message_id=msg_id,
                dataset_id=dataset_id,
                question=msg_clean,
                answer=answer_text,
                intent_type=intent_type,
                warnings=warnings_list,
                ambiguity_status=q_res.ambiguity_status.value if hasattr(q_res.ambiguity_status, "value") else str(q_res.ambiguity_status),
                confidence=q_res.confidence,
                error=err_msg,
                runtime_seconds=round(time.perf_counter() - start_time, 4),
            )
            context.add_message(ChatMessage(message_id=msg_id, role=ChatRole.ASSISTANT, content=answer_text))
            return resp

        # 11. Grounded Natural Language Response Generation
        answer_text = self.response_generator.generate_answer(
            question=msg_clean,
            plan=q_res.plan,
            rows=final_rows,
            columns=q_res.columns,
            use_llm=use_llm,
        )

        # 12. Update Structured Conversation Context
        context.update_analytical_state(
            question=msg_clean,
            plan=q_res.plan,
            rows=final_rows,
            columns=q_res.columns,
            compiled_sql=q_res.compiled_sql,
            intent_type=intent_type,
        )

        resp = ChatResponse(
            conversation_id=context.conversation_id,
            message_id=msg_id,
            dataset_id=dataset_id,
            question=msg_clean,
            answer=answer_text,
            intent_type=intent_type,
            query_plan=q_res.plan.model_dump() if q_res.plan else None,
            compiled_sql=q_res.compiled_sql,
            data=final_rows,
            columns=q_res.columns,
            row_count=final_row_count,
            evidence=q_res.evidence,
            confidence=q_res.confidence,
            warnings=[i.message for i in q_res.validation_issues if hasattr(i, "message") and i.status != ValidationStatus.PASSED],
            ambiguity_status="CLEAR",
            clarification_needed=False,
            provenance={
                "plan_id": q_res.plan.plan_id if q_res.plan else None,
                "compiled_sql": q_res.compiled_sql,
                "synthesized_question": target_question if target_question != msg_clean else None,
            },
            runtime_seconds=round(time.perf_counter() - start_time, 4),
        )

        context.add_message(ChatMessage(
            message_id=msg_id,
            role=ChatRole.ASSISTANT,
            content=answer_text,
            intent_type=intent_type,
            query_plan=resp.query_plan,
            compiled_sql=resp.compiled_sql,
            data=resp.data,
            columns=resp.columns,
            row_count=resp.row_count,
            evidence=resp.evidence,
        ))

        return resp


default_chat_engine = DatasetChatEngine()


def execute_chat_turn(
    dataset: CanonicalDataset,
    semantic_profile: DatasetSemanticProfile,
    message: str,
    context: ConversationContext,
    readiness: Optional[AnalysisReadiness] = None,
    data_profile: Optional[DataProfile] = None,
    use_llm: bool = True,
) -> ChatResponse:
    """Convenience entry point for processing a chat turn."""
    return default_chat_engine.process_chat_turn(
        dataset=dataset,
        semantic_profile=semantic_profile,
        message=message,
        context=context,
        readiness=readiness,
        data_profile=data_profile,
        use_llm=use_llm,
    )
