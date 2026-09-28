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
score = w1 * evidence + w2 * coverage + w3 * stability - w4 * assumptions
```

All weights are **project decisions (configurable hypotheses)** logged alongside
every ranking decision. They are not derived from data or optimized; they are
initial design choices subject to revision.

### Default Weights (from `orchestrator/config.py`)

| Weight | Symbol | Default | Meaning |
| :--- | :--- | ---: | :--- |
| `RANK_W1_EVIDENCE` | w1 | 0.35 | Mean role confidence of columns used |
| `RANK_W2_COVERAGE` | w2 | 0.30 | Fraction of request terms mapped to plan fields |
| `RANK_W3_STABILITY` | w3 | 0.20 | Result agreement under small perturbations (V1 proxy) |
| `RANK_W4_ASSUMPTIONS` | w4 | 0.15 | Penalty for defaults filled without request support |

Final score is clamped to **[0.0, 1.0]**.

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
