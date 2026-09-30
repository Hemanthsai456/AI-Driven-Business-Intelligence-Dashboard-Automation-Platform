# Ranker V1 Specification

**Status:** Implemented in `orchestrator/utils.py`
**Implementation:** Deterministic, Zero-LLM

---

## 1. Purpose

The Ranker V1 selects the best analytical plan from a set of surviving candidates
that have passed Pass 1a (pre-dispatch) and Pass 1b (post-execution) validation.
It operates without any LLM calls and uses only structured, deterministic scoring.

---

## 2. Score Formula

```
agreement_contribution = w5 * agreement * coverage
score = w1 * evidence + w2 * coverage + w3 * stability + agreement_contribution - w4 * assumptions
```

All weights and caps are **project decisions (configurable hypotheses)** logged alongside
every ranking decision. They are not derived from data or optimized; they are
initial design choices subject to revision.

### Default Weights and Caps (from `orchestrator/config.py`)

| Parameter | Symbol | Default | Meaning |
| :--- | :--- | ---: | :--- |
| `RANK_W1_EVIDENCE` | w1 | 0.35 | Mean role confidence of columns used |
| `RANK_W2_COVERAGE` | w2 | 0.30 | Fraction of request terms mapped to plan fields |
| `RANK_W3_STABILITY` | w3 | 0.20 | Result agreement under small perturbations (V1 proxy) |
| `RANK_W4_ASSUMPTIONS` | w4 | 0.15 | Penalty for defaults filled without request support |
| `RANK_W5_AGREEMENT` | w5 | 0.10 | Multi-provider agreement weight (gated by coverage) |
| `LOW_COVERAGE_CONFIDENCE_CAP` | - | 0.40 | **PROVISIONAL**: Score cap & tie threshold when coverage is low |

Final score is clamped to **[0.0, 1.0]**. Furthermore, if `coverage < LOW_COVERAGE_CONFIDENCE_CAP`,
the candidate's final score is capped at `LOW_COVERAGE_CONFIDENCE_CAP` to prevent low-coverage plans
from dominating on agreement alone, and `is_tie` is forced to trigger clarification.

---

## 3. Score Components

### 3.1 Evidence Score

**Formula:** Mean confidence of all columns used in the plan (metric + dimensions + filters).

```
evidence = mean({ confidence(col) for col in used_columns })
```

- Confidence values come from `DatasetSemanticProfile.column_evidences` (C4: sole authority).
- Missing columns (not in semantic profile) contribute 0.0 confidence.
- Range: [0.0, 1.0]. HIGH confidence columns score 0.85–0.95.

### 3.2 Coverage Score

**Formula:** Fraction of intent word tokens that appear in plan field values.

```
coverage = count(tokens in intent that appear in plan_text) / total_tokens
```

- `plan_text` = concatenation of metric column, aggregation, intent, dimension columns, filter columns.
- Coverage is capped at 1.0.
- Empty intent tokens → coverage = 0.0.

### 3.3 Stability Score (V1 Proxy)

True perturbation stability (running adjacent granularity variants) is deferred to Stage 7.

V1 proxy uses execution quality signals:
- **Base:** 1.0 for SUCCESS status.
- **Penalty 1:** Subtract `failed_cast_rate` (high cast failure → less stable).
- **Penalty 2:** Subtract 0.2 if `row_count < 2` (near-empty results have low signal stability).
- **Timeout/Error:** Stability = 0.0.
- Clamped to [0.0, 1.0].

### 3.4 Assumption Penalty

**Formula:** Normalised count of fields set to default values without explicit request support.

| Assumption | Condition |
| :--- | :--- |
| Visualization defaulted to TABLE | `plan.visualization == TABLE` |
| No dimensions specified | `len(plan.dimensions) == 0` |
| No filters specified | `len(plan.filters) == 0` |
| No comparison specified | `plan.comparison is None` |

```
assumptions = assumption_count / 4.0  (normalised over max 4)
```

### 3.5 Agreement Score (Multi-Provider)

**Formula:** Ratio of supporting providers to total responding providers.

```
agreement = supporting_count / providers_responded
```

- When multiple providers return the exact same plan (deduped by `plan_signature`), `supporting_count` increases.
- High agreement across different models indicates high confidence.

---

## 4. Tie Handling

When the top-2 candidates score within `RANK_TIE_EPSILON` of each other:

```
abs(score_1 - score_2) < RANK_TIE_EPSILON (default: 0.05)
```

The orchestrator sets `DashboardSpec.is_tie = True` and routes to a
**clarification fallback prompt** (UI component: Stage 6). The user selects
their preferred interpretation rather than the system picking arbitrarily.

`RANK_TIE_EPSILON` is a **project decision (configurable hypothesis)**.

---

## 5. Candidate Output Consistency Check

Before ranking, all surviving candidates are checked for semantic consistency:

| Check | Criteria |
| :--- | :--- |
| Metric column | All candidates use the same metric column |
| Time basis | All candidates use the same granularity |
| Output schema | All candidates produce the same output column set |

Inconsistent candidates are flagged in `CandidateConsistencyCheck.mismatches`.
Inconsistency is logged but does **not** automatically disqualify candidates in V1.

**Implementation:** `orchestrator/utils.py::check_candidate_output_consistency()`

---

## 6. Pass 2 — Winner-Only Validation

After ranking, Pass 2 validates the **winner only**:

1. **Plan-vs-result consistency:** Metric column appears in `ExecutionResult.columns`.
2. **Visualization suitability:**
   - `KPI` requires `row_count == 1`.
   - `LINE` / `AREA` requires at least one DATETIME dimension.
   - `PIE` requires `row_count <= 20` (categorical breakdown).
3. **Failure:** Triggers runner-up cascade (promoting rank-2 to winner).
4. **Cascade depth:** Capped at `MAX_CASCADE_DEPTH` (default: 2). After exhausting cascade, DashboardSpec is not produced; UNANSWERABLE is returned.

**Implementation:** Stage 7 (cascade + Pass 2 logic).
**Schema:** `orchestrator/schemas.py::Pass2Result` (defined in Stage 3).

---

## 7. ScoreBreakdown — Explainability

Every `RankedCandidate` carries a `ScoreBreakdown` with:

| Field | Description |
| :--- | :--- |
| `evidence` | Raw evidence component (pre-weight) |
| `coverage` | Raw coverage component (pre-weight) |
| `stability` | Raw stability component (pre-weight) |
| `assumptions` | Raw assumption penalty (pre-weight) |
| `agreement` | Multi-provider agreement component (pre-weight) |
| `total` | Weighted final score, clamped [0, 1] |

The `OrchestratorTrace.ranker_weights` field records which weights were used,
enabling full audit of ranking decisions.

---

## 8. Deferred Work (Stage 7)

| Feature | Status |
| :--- | :--- |
| True perturbation stability (adjacent granularity runs) | Stage 7 |
| Pass 2 visualization suitability full implementation | Stage 7 |
| Runner-up cascade execution | Stage 7 |
| Explainability JSONL log emission | Stage 7 |
| DashboardSpec trace emission | Stage 7 |

---

## 9. Known Limitations: Agreement-on-Wrong-Answer Risk (Consensus Failure Mode)

If Gemini, Groq, and Ollama all independently propose the same WRONG plan (e.g., all three assume the wrong aggregation for an ambiguous request or select the wrong metric column):
- **Nothing in the current runtime ranker catches this**:
  - The plan passes **Pass 1a** because the column and aggregation are syntactically and structurally valid against the schema (e.g. `UnitPrice` is a `MEASURE`, `AVG` is a whitelisted aggregation). Pass 1a does not know business semantic ground truth.
  - The plan passes **Pass 1b** because DuckDB executes the query cleanly, generates non-empty rows, produces non-null metric values, and has no failed casts.
  - The plan receives maximum agreement bonus: `agreement = supporting_count / providers_responded = 3 / 3 = 1.0` (scaled by `w5_agreement = 0.10`), which actively boosts the wrong plan to rank 1.
  - The plan passes **Pass 2** because the metric is present in the result columns and visualization cardinalities match.
- **Ground Truth Invariance**: There is currently no runtime check that compares a candidate plan's query or result against ground truth. Agreement is purely consensus-based among generator outputs. If all generators share the same bias or hallucination, that erroneous plan wins uncontested.
- **Measurement Mechanism**:
  - **Correction Note**: `tests/eval/run_eval.py` (which produced `tests/eval/results.md`) was previously mislabeled as an evaluation of the system; it is in fact a fast, deterministic **`SyntheticRankerRegressionHarness`** that tests ranker/validation logic against scripted candidate sets and does not measure real LLM provider behavior.
  - **Empirical Evidence**: The actual empirical evaluation is performed by `tests/eval/run_real_eval.py` with live Gemini and Groq model calls, and its empirical findings are documented in [`tests/eval/real_results.md`](../tests/eval/real_results.md). Real evaluation confirms natural divergence, generative variance, and empirical agreement-on-wrong-answer rates under live production conditions.

---

## 10. Mitigation: Gating Agreement on Coverage (PROVISIONAL)

change ranker scoring from purely additive to gate agreement by coverage:
```
agreement_contribution = w5 * agreement * coverage
score = w1*evidence + w2*coverage + w3*stability + agreement_contribution - w4*assumptions
```

Two candidates with identical scores except one has agreement=1.0/coverage=0.2 and the other has agreement=0.33/coverage=0.9 — the second must NOT be dominated by the first purely on agreement.

Add `LOW_COVERAGE_CONFIDENCE_CAP` config constant. Mark it PROVISIONAL in a code comment and in docs/ranker_v1_spec.md until derived from eval data. If a candidate's coverage falls below it, cap the candidate's final score below a threshold that forces ties/clarification rather than an outright automatic win, even at agreement=1.0.
