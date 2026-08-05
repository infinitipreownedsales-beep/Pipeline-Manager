# PHASE 8 COMPLETION PACKET — Prediction, Observation, Error, Attribution, Learning, Calibration

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/learning/` (+ migration v8 in `elite/db.py`); no legacy file changed.
- **Scope:** the institutional-memory + learning foundation. **Learning may propose change but never
  activates it — no approved Calibration means no operational change.**

## Implemented
The complete learning + calibration foundation that preserves and connects what was known, predicted,
recommended, chosen, executed, and what actually happened — and why prediction differed from outcome —
without collapsing domains: immutable issued Predictions (domain-aware payloads; every applicable
version pinned; corrections preserve the original; reissuing creates a new Prediction; no-prediction /
unresolved permitted; Scenario Predictions distinct); Decision learning context (never invents
rationale — absence stays unknown); immutable accepted Observations (accepted facts only; missing ≠
zero; correction/reversal preserve prior-as-known; conflicting → unresolved; scenario output can never
become an Observation); an **executable versioned Comparison Specification** extending the Phase 3
registry; deterministic **Prediction-to-Observation Pairing** (13 outcomes; identity/scope/unit/timing
enforced; idempotent; pending until window close; late contract; ambiguous → unresolved; never mutates
the Prediction/Observation; aggregation only when the spec permits); versioned **Error** derived only
from a valid Pairing (spec semantics; safe percentage; zero/ missing/partial explicit; materiality via
policy; reproducibility-pinned; no causation); evidence-based **Attribution** (evidence vs hypothesis;
multi-factor; unknown stays unknown; stockout supports constrained demand but no exact missed sales;
human review preserves the automated proposal); domain-aware **Learning Signal** (minimum evidence +
recurrence + sample size visible; conflicting stays visible; weak data lowers confidence; no
operational effect; escalation explicit); governed **Calibration** (propose → validate → approve →
activate/schedule → rollback; separated authorities; validation required for material change; approval
distinct from activation; activation creates/references a NEW approved version or a policy-REVIEW
recommendation; never rewrites prior Predictions; rollback restores prospectively; rejected/withdrawn
inert); deterministic **backtesting/validation** (preserved historical inputs; hypothetical; no
leakage; cohort improve/degrade; aggregate cannot hide material degradation); **cross-domain
boundaries** (no universal scorer; a domain signal cannot mutate another domain automatically);
operational output slices. Migration v8 appended (v1-v7 unchanged), touching no legacy file. All
policies/assumptions/thresholds resolve through Phase 3; synthetic values only. All Phase 1-7 issued
results are immutable historical inputs.

**Not built (guarded, item 90):** completed Phase-9 Governance, full Decision workspace, broad
Scenario administration, Phase-10 UX, operational hardening, migration/cutover. Learning/Calibration
never automatically mutate active policy, calculations, thresholds, valuation, permissions, or business
behavior.

## Acceptance evidence (90 mandatory items, all executed)
| # | Requirement | Test |
|---|---|---|
| 1 | Prediction survives restart | `test_phase8_prediction_observation.test_01` |
| 2 | Prediction immutable after issuance | `..test_02` |
| 3 | Prediction correction preserves original | `..test_03` |
| 4 | New facts create a new Prediction | `..test_04` |
| 5 | Prediction preserves facts + versions + Observation contract | `..test_05` |
| 6 | Scenario Prediction distinct; no-prediction permitted | `..test_06` / `test_06b` |
| 7 | Decision context does not invent rationale | `..test_07` |
| 8 | Decision context survives restart | `..test_08` |
| 9 | Observation uses accepted Business Facts | `..test_09` |
| 10 | Missing Observation does not become zero | `..test_10` |
| 11 | Observation correction preserves original | `..test_11` |
| 12 | Reversal preserves Observation history | `..test_12` |
| 13 | Conflicting facts → conflicting/unresolved; scenario output ≠ Observation | `..test_13` / `test_13b` |
| 14 | Comparison Specification Version survives restart | `test_phase8_comparison_pairing_error.test_14` |
| 15 | Inactive Comparison Specification cannot Pair | `..test_15` |
| 16 | Prediction/Observation type mismatch rejected | `..test_16` |
| 17 | Subject identity mismatch rejected | `..test_17` |
| 18 | Store/scope mismatch rejected | `..test_18` |
| 19 | Unit mismatch rejected | `..test_19` |
| 20 | Observation-window rules enforced | `..test_20` |
| 21 | Valid exact Pairing succeeds | `..test_21` |
| 22 | Replayed Pairing idempotent | `..test_22` |
| 23 | Ambiguous Pairing unresolved | `..test_23` |
| 24 | Partial Pairing follows the specification | `..test_24` |
| 25 | Late Pairing labeled late; pending until window; aggregation only when permitted | `..test_25` / `25b` / `25c` |
| 26 | Pairing does not mutate Prediction/Observation | `..test_26` |
| 27 | Error requires a valid Pairing | `..test_27` |
| 28 | Signed Error correct | `..test_28_29` |
| 29 | Absolute Error correct | `..test_28_29` |
| 30 | Percentage Error handles zero denominator safely | `..test_30` |
| 31 | Missing Observation → no fabricated Error | `..test_31` |
| 32 | Partial Observation → permitted partial Error | `..test_32` |
| 33 | Materiality threshold resolves through policy | `..test_33` |
| 34 | Error preserves Comparison + Calculation Versions | `..test_34` |
| 35 | Corrected Observation → corrected/superseding Error | `..test_35` |
| 36 | Error does not establish causation | `..test_36` |
| 37 | Attribution identifies supporting evidence | `test_phase8_attribution_signal.test_37` |
| 38 | Contradicting evidence stays visible | `..test_38` |
| 39 | Unsupported Attribution stays proposed/unresolved | `..test_39` |
| 40 | Unknown customer intent stays unknown | `..test_40` |
| 41 | Stockout Attribution invents no exact missed sales | `..test_41` |
| 42 | Multiple contributing factors coexist | `..test_42` |
| 43 | Human review preserves the automated proposal | `..test_43` |
| 44 | One isolated Error → no supported Signal | `..test_44` |
| 45 | Minimum evidence requirement enforced | `..test_45_46_47` |
| 46 | Sample size visible | `..test_45_46_47` |
| 47 | Recurrence demonstrated before support | `..test_45_46_47` |
| 48 | Conflicting evidence → conflicting Signal | `..test_48` |
| 49 | Data-quality weakness reduces confidence | `..test_49` |
| 50 | Learning Signal has no operational effect | `..test_50` |
| 51 | New Inventory Signal cannot mutate Service Loaner | `..test_51` |
| 52 | Service Loaner Signal cannot mutate New Inventory | `..test_52` |
| 53 | Executive Demo Signal cannot mutate Service Loaner | `..test_53` |
| 54 | Calibration Proposal has no operational effect | `test_phase8_calibration_validation.test_54` |
| 55 | Validation uses preserved historical inputs | `..test_55_56` |
| 56 | Backtest does not rewrite historical Prediction | `..test_55_56` |
| 57 | Future Observation leakage prohibited | `..test_57` |
| 58 | Validation identifies improved + worsened cohorts | `..test_58` |
| 59 | Aggregate improvement cannot hide material degradation | `..test_59` |
| 60 | Approval distinct from activation | `..test_60` |
| 61 | Future-effective Calibration stays scheduled | `..test_61` |
| 62 | Activation creates/references a new approved version | `..test_62` |
| 63 | Activation does not rewrite prior Predictions | `..test_63` |
| 64 | Rejected Calibration has no effect | `..test_64` |
| 65 | Withdrawn Calibration has no effect | `..test_65` |
| 66 | Rollback preserves history | `..test_66_67` |
| 67 | Rollback restores prior approved version prospectively | `..test_66_67` |
| 68 | Policy-targeted Calibration → policy-review recommendation | `..test_68` |
| 69 | No approved Calibration → no operational change | `..test_69` |
| 70 | Proposal/validation/approval/activation/rollback authorities distinct (validation gate) | `..test_70` / `test_71` |
| 71 | Authorization enforced below the UI | `..test_71` |
| 72 | Scope mismatch rejected | `..test_72` |
| 73 | Revoked authority rejected | `..test_73` |
| 74 | Stale transition rejected | `..test_74` |
| 75 | Idempotent activation retry — no duplicate | `..test_75` |
| 76 | Required Audit Event written atomically | `..test_76` |
| 77 | Audit failure blocks unsafe activation | `..test_77` |
| 78 | Output slices use real stored records | `..test_78` |
| 79 | Migration v8 survives restart | `test_phase8_migration_cross.test_79` |
| 80 | Migration v8 rerun safe | `..test_80` |
| 81 | Phase 1 tests remain green | `..test_81` |
| 82 | Phase 2 tests remain green | `..test_82` |
| 83 | Phase 3 tests remain green | `..test_83` |
| 84 | Phase 4 tests remain green | `..test_84` |
| 85 | Phase 5 tests remain green | `..test_85` |
| 86 | Phase 6 tests remain green | `..test_86` |
| 87 | Phase 7 tests remain green | `..test_87` |
| 88 | Legacy tests remain 39/39 green | `..test_88` (+ `test_legacy_guard`) |
| 89 | Legacy application paths unchanged | `..test_89` (+ `test_legacy_guard`) |
| 90 | No Phase-9 Governance / Decision workspace / Scenario admin / UX / hardening / cutover | `..test_90` |

**Fixtures:** 60 synthetic scenarios (`learning/fixtures.build_all_scenarios`, `SCENARIO_NAMES`),
completeness proven by `test_phase8_migration_cross.test_90b`.

**Platform harness:** `515/515 passed` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 + 79 P7 + 91 P8).
**Legacy:** `39/39` (29 engine + 10 loaner).

## Dedicated learning-governance regression (20-point)
`elite/tests/test_phase8_learning_governance_regression.TestLearningGovernanceRegression` proves the
full loop: an official Prediction is issued; an Observation arrives; the applicable Comparison
Specification pairs them; Error is calculated; evidence-supported Attribution is recorded; repeated
evidence creates a SUPPORTED Learning Signal; the Signal alone changes nothing; a Calibration Proposal
is created; the Proposal alone changes nothing; validation compares current vs proposed on preserved
historical inputs; approval alone does not activate; authorized activation creates/references a new
version; future Predictions may use it; prior Predictions retain the old version; rollback restores the
prior approved version prospectively; no historical Prediction is rewritten; audit failure prevents
activation; replayed activation duplicates nothing; a policy-targeted proposal does not mutate policy;
and no approved Calibration means no operational change.

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- Comparison Specification runtime evaluation uses caller-supplied timing/lateness signals (synthetic);
  wiring real calendar/window arithmetic is a later concern (the versioned contract + outcomes are in
  place).
- Backtesting compares caller-supplied cohort error measures (synthetic); a real recompute harness over
  preserved inputs is deferred — the no-leakage / hypothetical / cohort-degradation guarantees are in
  place. No machine learning is implemented merely to satisfy Phase 8.

## Status
**HOLD FOR REVIEW.** Phase 9 not started.
