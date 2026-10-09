# Dataset Chat & Evidence Grounding Specification

**Status:** IMPLEMENTED & AUDITED  
**Audience:** AI Engineers, Backend Developers, Frontend Developers  

---

## 1. Overview & Objectives

**Dataset Chat** (`POST /api/chat`, frontend component `frontend/components/DatasetChatView.tsx`) enables analysts to hold natural-language conversations with any uploaded tabular dataset.

### Core Objectives
1. **Conversational NL-to-SQL Analytics**: Translate ad-hoc questions into structured queries executed deterministically against DuckDB.
2. **Zero Hallucination Numbers**: Numerical values returned in conversational responses are grounded directly in engine execution results.
3. **Multi-Turn Context & Pronoun Binding**: Maintain thread memory to interpret follow-up questions (e.g., *"What about for 2025?"* or *"Break that down by category"*).
4. **Transparent Evidence & SQL Provenance**: Every response includes an inspection drawer showing the exact compiled SQL query, execution time, and row count.

---

## 2. Conversational Architecture

```
User Message
     │
     ▼
┌────────────────────────────────────────────────────────┐
│ 1. Chat Intent Classifier (orchestrator/chat/classifier)│
│    [ANALYTICAL_QUERY, FOLLOW_UP, COMPARISON, METADATA, │
│     INSIGHT_EXPLANATION, PROVENANCE_OR_SQL, etc.]      │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ 2. Follow-Up & Context Resolver (followup.py)          │
│    (Resolve pronouns, inherit filters, maintain state) │
└───────────────────────────┬────────────────────────────┘
                            │ Resolved Analytical Intent
┌───────────────────────────▼────────────────────────────┐
│ 3. Analytical Query Engine (orchestrator/query_engine) │
│    - Intent formulation & metric/dimension binding     │
│    - Query Compiler (compiler.py -> DuckDB SQL)        │
│    - Isolated Execution (engine/duckdb_executor.py)    │
└───────────────────────────┬────────────────────────────┘
                            │ Tabular Result Rows
┌───────────────────────────▼────────────────────────────┐
│ 4. Grounded Response Generator (response_generator.py) │
│    - Grounding Guard: Validate numbers match output    │
│    - Formulate human-readable analytical explanation   │
│    - Generate 2-3 contextual follow-up suggestions     │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ 5. API Response with Embedded Provenance & Chart Data  │
└────────────────────────────────────────────────────────┘
```

---

## 3. Intent Classification & Routing (`ChatIntentClassifier`)

User queries are categorized into structured intent types:

| Intent Type | Trigger Pattern | Handler Action |
| :--- | :--- | :--- |
| `ANALYTICAL_QUERY` | *"What is total sales by region?"*, *"Average order value in Q1"* | Dispatches to `AnalyticalQueryEngine` for SQL compilation and DuckDB execution. |
| `FOLLOW_UP` | *"Break that down by customer"*, *"What about in Europe?"* | Resolves context from prior conversation turns, merges filters/groupings. |
| `COMPARISON` | *"Compare 2024 to 2025"*, *"Which category grew faster?"* | Evaluates relative deltas and ratio disparities. |
| `DATASET_METADATA` | *"What columns are in this dataset?"*, *"How many rows?"* | Serves directly from cached profile and schema metadata without query execution. |
| `INSIGHT_EXPLANATION` | *"Why is store 101 an outlier?"*, *"Explain this trend"* | Summarizes statistical factors (variance, IQR, ANOVA effect size). |
| `PROVENANCE_OR_SQL` | *"Show me the query"*, *"How was this calculated?"* | Returns the exact parameterized DuckDB SQL query string and execution metrics. |
| `UNSUPPORTED_OR_CAUSAL` | *"Why did customers leave?"*, *"Will sales increase next year?"* | Explains that observational data cannot prove causal mechanisms or predict future events without predictive modeling. |
| `AMBIGUOUS_CLARIFICATION`| *"Show performance"* (unspecified metric/dimension) | Returns clarification prompt offering valid measure choices. |
| `GENERAL_HELP` | *"What can you do?"*, *"Help me get started"* | Outlines supported query types and suggests initial exploratory prompts. |

---

## 4. Multi-Turn State Management (`ConversationContext`)

Conversational state is tracked in `api/store.py` inside `DatasetSessionRecord`:

```python
class ConversationContext:
    conversation_id: str
    dataset_id: str
    messages: List[ChatMessage]
    active_filters: List[FilterSpec]
    last_query_plan: Optional[CandidatePlan]
    last_metric: Optional[str]
    last_dimension: Optional[str]
    last_granularity: Optional[str]
```

### Resetting Conversation
Analysts can clear the conversation thread at any time via:
`POST /api/chat/conversation/{dataset_id}/{conversation_id}/clear`

---

## 5. Evidence Inspector & SQL Provenance (`EvidenceInspector.tsx`)

Every analytical answer in Dataset Chat and every tile on the dashboard exposes an **Evidence Inspector** drawer:

```
┌──────────────────────────────────────────────────────────────────┐
│                      EVIDENCE & SQL PROVENANCE                   │
├──────────────────────────────────────────────────────────────────┤
│ Execution Status: SUCCESS (Execution Time: 3.4ms | 12 rows)      │
├──────────────────────────────────────────────────────────────────┤
│ Compiled DuckDB SQL:                                             │
│   SELECT Region, SUM(TotalSales) AS TotalRevenue                 │
│   FROM dataset                                                   │
│   WHERE Date >= '2024-01-01' AND Date <= '2024-12-31'            │
│   GROUP BY Region                                                │
│   ORDER BY TotalRevenue DESC;                                    │
├──────────────────────────────────────────────────────────────────┤
│ Grounding Guard Verification:                                    │
│   ✓ Stat 'Total Revenue' (4,219,500.00) verified against engine  │
│   ✓ Group 'North America' (1,842,100.00) verified against engine │
├──────────────────────────────────────────────────────────────────┤
│ Statistical Evidence:                                            │
│   • Share of Total: 43.7%                                        │
│   • Effect Size (η²): 0.38 (Substantial Disparity)               │
│   • Stability (Bootstrap): 0.94 (High Stability)                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Number Grounding Guard

To prevent generative hallucinations:
1. When generating narrative explanations, the LLM or template engine is supplied with the exact execution output table.
2. The `GroundingGuard` scans the generated response text for numeric patterns (integers, floats, percentages, currency).
3. Every detected number must match an engine-computed value within a tight tolerance ($10^{-2}$).
4. If an unsupported number is detected, the narrative is rejected and replaced with the verified deterministic engine statement.
