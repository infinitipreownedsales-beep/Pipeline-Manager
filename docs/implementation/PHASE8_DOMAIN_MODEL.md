# PHASE 8 LEARNING + CALIBRATION DOMAIN MODEL (migration v8)

New tables added by migration v8 `learning_calibration` (appended; v1-v7 unchanged). Payloads are
JSON-in-SQLite behind repository methods (`learning/store.py`). Predictions and Observations are
**immutable** (no-update + no-delete); the calibration activation reference is immutable; everything
else is append-preserving (no-delete). Corrections/reversals/supersessions are recorded as new rows +
lineage, never in-place edits.

## Records (23 tables)
| Table | Purpose | Key invariants |
|---|---|---|
| `prediction` | Immutable issued Prediction | domain-aware payload; all versions pinned; no-update/no-delete |
| `prediction_correction` | Correction/supersession lineage | append-only; original preserved |
| `decision_learning_context` | Learning context on an issued Decision | rationale absence stays unknown; no-delete |
| `observation` | Immutable accepted Observation | accepted facts; missing≠zero; no-update/no-delete |
| `observation_correction` | Correction/reversal lineage | prior-as-known kept; reversal negates effect; no-delete |
| `comparison_specification_runtime` | Executable versioned Comparison Spec | extends Phase 3 registry; new behavior ⇒ new version; no-delete |
| `prediction_observation_pairing` | Deterministic Pairing | 13 outcomes; idempotent (UNIQUE key); never mutates P/O; no-delete |
| `pairing_review` | Human pairing review | append-only |
| `prediction_error` | Versioned Error from a valid Pairing | spec semantics; safe pct; no causation; no-delete |
| `error_correction` | Error correction/supersession lineage | append-only |
| `attribution` | Evidence-based explanation | evidence vs hypothesis; multi-factor; no-delete |
| `attribution_evidence` | Supporting/contradicting evidence | contradiction stays visible; no-delete |
| `attribution_review` | Human review | preserves automated proposal; no-delete |
| `learning_signal` | Domain-aware pattern | min evidence + recurrence; no operational effect; no-delete |
| `learning_signal_source` | Signal → Error/Attribution refs | append-only |
| `calibration_proposal` | Governed proposal (may recommend a versioned change) | never mutates policy/facts directly; lifecycle in review_state; no-delete |
| `calibration_evidence` | Proposal evidence + Learning Signals | append-only |
| `calibration_validation_run` | Backtest run | hypothetical; leakage-checked; no-delete |
| `calibration_validation_result` | Per-cohort result | improved/worsened/unchanged; material flag; no-delete |
| `calibration_transition` | Governed lifecycle history | append-only |
| `calibration_activation` | Immutable activation reference | one per proposal; no-update/no-delete |
| `calibration_rollback` | Rollback record | restores prior version prospectively; no-delete |
| `learning_issued_output` | Issued-output index | append-preserving; no-delete |

## Constitutional separations (enforced)
Prediction ≠ Decision ≠ execution ≠ Observation. Error ≠ Attribution ≠ Learning Signal ≠ Calibration
Proposal ≠ approved Calibration. Learning may PROPOSE change but never activates it. Historical
Predictions/Decisions are immutable after issuance (correction metadata only); a later model/calc
improvement never makes an earlier Prediction appear to have used it. Unknown remains unknown.

## Comparison → Pairing → Error contract
A Comparison Specification must be ACTIVE and applicable (matching Prediction type, Observation type,
subject identity, scope, unit compatibility, and timing window) before Pairing. Pairing outcomes:
`PAIRED, PENDING_OBSERVATION, PARTIAL, LATE_PAIRED, AMBIGUOUS, CONFLICTING, UNIT_MISMATCH,
SCOPE_MISMATCH, IDENTITY_MISMATCH, OUTSIDE_WINDOW, UNRESOLVED, CORRECTED, SUPERSEDED`. An Error is
derived ONLY from a valid Pairing (PAIRED/LATE_PAIRED/PARTIAL); pending/mismatch yields
pending/unresolved with no fabricated numeric error. See `adr/ADR-0022` (Pairing), `adr/ADR-0023`
(Error).

## Calibration lifecycle (governed)
`DRAFT → PROPOSED → UNDER_REVIEW → (VALIDATION_REQUIRED → VALIDATED) → APPROVED → {SCHEDULED →}
ACTIVATED`, plus `REJECTED / WITHDRAWN / ROLLED_BACK / SUPERSEDED / CORRECTED`. Material targets
(calculation/model/parameter/comparison-spec versions) require validation before approval. Activation
is the ONLY step that creates operational change — it creates or references a new approved version, or
a policy-REVIEW recommendation for policy-adjacent targets; it never rewrites prior Predictions.
Authorities (`calibration.propose/validate/approve/activate/rollback`) are separable. See
`adr/ADR-0025` (Calibration governance), `adr/ADR-0026` (backtesting), `adr/ADR-0027` (cross-domain
boundaries).
