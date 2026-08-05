# PHASE 8 REGISTRIES — learning + calibration

Living registries for the Phase 8 learning + calibration foundation. Runtime records live in the
authoritative SQLite store (migration v8); this document indexes the contracts.

## Prediction registry
Immutable issued Predictions. Foundational types: `new_inventory_monthly_demand`,
`combination_retail_expectation`, `need_or_excess`, `arrival_timing_or_incoming_risk`,
`workflow_outcome_expectation`, `service_loaner_economic_call_expectation`,
`service_loaner_retirement_expectation`, `executive_demo_opportunity_or_lifecycle_expectation`,
`executive_demo_retirement_expectation`. Each carries a domain payload, unit contract, confidence,
uncertainty, evidence classification, accepted-fact + source-state refs, and every applicable version
(Policy / Calculation / Model / Identity-Rule / Comparison-Spec) plus a reproducibility package. Each
type declares its expected Observation contract (`models.OBSERVATION_CONTRACT`). A no-prediction /
unresolved result is permitted; a correction preserves the original; reissuing creates a new
Prediction; Scenario Predictions stay distinct from official ones.

## Observation registry
Immutable accepted Observations. Types: `actual_monthly_retail`, `actual_unit_retail`,
`actual_availability`, `actual_arrival_timing`, `actual_workflow_completion`, `actual_workflow_failure`,
`actual_service_loaner_retirement`, `actual_used_cars_receipt`, `actual_service_loaner_resale_reference`,
`actual_executive_demo_activation`, `actual_executive_demo_retirement`, `actual_return_path`,
`actual_resale_or_new_retail_outcome`. Missing stays missing (never zero); observation-time and
recorded-time are distinct; corrections/reversals preserve prior-as-known; scenario output can never
be accepted as an Observation.

## Comparison Specification registry
Executable versioned contracts (`comparison_specification_runtime`) extending the Phase 3
`comparison_specification_version` registry (`registry_ref`). Each version pins scope/matching/timing/
window/lateness/unit/transformation/aggregation rules and explicit partial/conflicting/missing/late
behavior + error semantics + directionality + materiality-threshold ref. A spec must be ACTIVE and
applicable before Pairing; a behavior change requires a NEW version; historical Pairings retain the
version they used.

## Pairing registry
Outcomes: `PAIRED, PENDING_OBSERVATION, PARTIAL, LATE_PAIRED, AMBIGUOUS, CONFLICTING, UNIT_MISMATCH,
SCOPE_MISMATCH, IDENTITY_MISMATCH, OUTSIDE_WINDOW, UNRESOLVED, CORRECTED, SUPERSEDED`. Idempotent under
`{prediction}:{observation}:{comparison_version}`; aggregation only when the spec permits; never
mutates the Prediction/Observation. See `adr/ADR-0022`.

## Error registry
Calculation Version `learning_error` (1.0.0). Derived only from a valid Pairing; semantics from the
Comparison Spec. Signed/absolute always; percentage skipped for a zero/meaningless denominator; zero/
missing/partial explicit; materiality resolves through policy; reproducibility-pinned; no causation.
See `adr/ADR-0023`.

## Attribution registry
Categories: `availability_constraint, stockout, source_data_quality, timing_shift, eta_variance,
policy_change, calculation_limitation, model_year_transition, unapproved_lineage,
operational_execution_failure, cancelled_or_failed_workflow, service_loaner_operational_block,
executive_demo_operational_block, market_or_customer_factor, unknown`. Statuses: `PROPOSED, SUPPORTED,
PARTIALLY_SUPPORTED, CONTRADICTED, REJECTED, UNRESOLVED, CORRECTED, SUPERSEDED`. Evidence vs
hypothesis; multi-factor; unknown stays unknown; human review preserves the automated proposal. See
`adr/ADR-0024`.

## Learning Signal registry
Statuses: `CANDIDATE, MONITORING, SUPPORTED, INSUFFICIENT_EVIDENCE, CONFLICTING, REJECTED,
ESCALATED_TO_CALIBRATION, CORRECTED, SUPERSEDED`. Support requires a minimum sample + demonstrated
recurrence + non-conflicting evidence + acceptable data quality (thresholds policy-resolvable). Signals
stay domain-specific; sample size is visible; a Signal has NO operational effect; escalation is
explicit. Append-preserving.

## Calibration registry
Targets: `calculation_version, model_version, calculation_parameter, confidence_classification,
lineage_or_comparability_rule, materiality_threshold, monitoring_threshold, policy_review_recommendation,
source_quality_rule_review, comparison_specification_version`. Lifecycle: `DRAFT → PROPOSED →
UNDER_REVIEW → (VALIDATION_REQUIRED → VALIDATED) → APPROVED → {SCHEDULED →} ACTIVATED`, plus `REJECTED /
WITHDRAWN / ROLLED_BACK / SUPERSEDED / CORRECTED`. Material targets require validation before approval;
approval ≠ activation; activation creates/references a new approved version or a policy-REVIEW
recommendation and never rewrites prior Predictions; rollback restores prospectively. **No approved
Calibration means no operational change.** See `adr/ADR-0025`.

## Backtesting / validation contract
Calculation Version `learning_backtest` (1.0.0). Compares current vs proposed versions over preserved
historical inputs + outcomes per material cohort; results labeled hypothetical; leakage prohibited;
training/evaluation windows distinguishable; identifies improved/worsened/unchanged cohorts and flags
when an aggregate improvement hides material cohort degradation. See `adr/ADR-0026`.

## Cross-domain learning-boundary registry
Domains: `new_inventory_forecasting, production_workflow_timing, cpo_ppo, dealer_trade, ctp,
service_loaner, executive_demo`. A domain's Learning Signal cannot mutate another domain automatically;
cross-domain evidence may support a Calibration Proposal only under an explicit approved relationship;
no universal ranker / single global learning score exists. See `adr/ADR-0027`.

## Capability / authority registry
`prediction.view, prediction.issue, prediction.correct, observation.accept, observation.correct,
comparison_spec.register, comparison_spec.approve, pairing.review, attribution.review,
learning_signal.review, calibration.propose, calibration.validate, calibration.approve,
calibration.activate, calibration.rollback`. Distinct predictor / observer / registrar / spec-approver
/ proposer / validator / approver / activator / rollbacker principals prove separation of authority.
Every governed action authorizes below the UI, binds an Audit Event atomically, rejects stale/revoked/
out-of-scope actors, and is idempotent under a retry key.
