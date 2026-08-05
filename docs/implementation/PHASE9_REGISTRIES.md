# PHASE 9 REGISTRIES — governance + operational control

Living registries for the Phase 9 governed operational surface. Runtime records live in the authoritative
SQLite store (migration v9); this document indexes the contracts. Phase 9 references authoritative Phase
1-8 output and reuses the Phase 1 Governor + Phase 8 Calibration governance.

## Decision Workspace registry
A workspace item references (never copies) a domain recommendation + Prediction / Economic Call /
Execution Status / planning refs, with priority, unresolved classification, assigned reviewer, required
authority, evidence, Raw History, and applicable facts + versions. States: `OPEN, READY_FOR_REVIEW,
UNDER_REVIEW, AWAITING_INFORMATION, UNRESOLVED, RECOMMENDED, DECISION_PENDING, DECIDED, APPROVED,
REJECTED, DEFERRED, AWAITING_EXECUTION, IN_EXECUTION, COMPLETED, FAILED, EXPIRED, STALE, SUPERSEDED,
CORRECTED, CANCELLED`. A changed recommendation creates a new revision; the prior stays historical. See
`adr/ADR-0028`.

## Decision contract registry
An immutable governed Decision references the exact reviewed recommendation + revision, preserves state
known at Decision time, keeps missing rationale unknown, records only presented alternatives, is
idempotent, and writes its Audit Event atomically. Dispositions: `ACCEPT, REJECT, DEFER,
REQUEST_INFORMATION, NO_ACTION, OVERRIDE, CANCEL, CORRECT, SUPERSEDE`. Override requires an explicit
authority + reason; correction preserves the original; supersession links both; cancellation preserves
history; Scenario Decisions stay Scenario-only. See `adr/ADR-0029`.

## Approval registry
Approval is distinct authority, validates current domain state, is rejected when stale / expired /
revoked / over the Decision's scope or quantity, is idempotent, and never implies execution. Conditional
approval stays inspectable.

## Execution-authorization registry
Execution authorization references the Phase 5-7 domain execution service (never duplicates its logic),
requires a valid approval where applicable, records the domain execution ref, and completes only against
an actual domain completion event (a failed execution is never completed). Decision / approval /
execution / completion stay separately inspectable.

## Reconciliation registry
Outcomes: `NO_EXECUTION_REQUIRED, AWAITING_APPROVAL, APPROVED_AWAITING_EXECUTION, EXECUTION_AUTHORIZED,
EXECUTED, COMPLETED, FAILED, CANCELLED, EXPIRED, STALE, ALREADY_RECONCILED, UNRESOLVED_IDENTITY,
CONFLICTING, DOMAIN_REJECTED, AUDIT_BLOCKED`. Every actionable Decision can produce a result; a conflict
yields an unresolved operational state.

## Scenario-administration registry
States: `DRAFT, READY, SHARED, UNDER_REVIEW, APPROVED_FOR_DISCUSSION, PROMOTION_REQUESTED,
POLICY_REVIEW_REQUESTED, REJECTED, EXPIRED, ARCHIVED, SUPERSEDED, CORRECTED`. A Scenario stays isolated
from official state; sharing ≠ approval; approved-for-discussion ≠ official; output identifies overrides
+ baseline; a Scenario can never become an Observation; a Scenario Prediction is excluded from official
learning unless explicitly permitted.

## Promotion-request registry
Targets route to a governed review type: `official_policy_review / portfolio_requirement_review /
monitoring_threshold_review → policy_review`; `calculation_version_review / model_version_review /
comparison_specification_review → calibration` (Phase 8 governance); `operational_decision →
official_decision` (a NEW official Decision from official facts, never a copy of Scenario state). A
promotion request has no direct operational effect; a rejected promotion has no official effect. See
`adr/ADR-0030`.

## Authority + delegation registry
Uses the Phase 1 `capability_grant` store (no second permission store). Delegation cannot exceed the
delegator's capability or scope and records a `delegated_by:<principal>` grant-chain attribution;
temporary authority auto-expires per its contract; a revoked grant is immediately ineffective. Grant /
delegation / expiration / revocation remain historical. See `adr/ADR-0031`.

## Separation-of-duties registry
Rule types: `proposer_not_approver, approver_not_executor, executor_not_completer,
calibration_proposer_not_activator, policy_proposer_not_approver, correction_actor_differs,
self_approval_prohibited_above_materiality`. Conflicts are checked below the UI; a missing required rule
yields UNRESOLVED governance (not permissive behavior); an authorized override needs the explicit
`authority.override_separation` capability + reason + Audit Event and stays visible. See `adr/ADR-0032`.

## Audit-exception registry
Over the immutable Phase 1 Audit Event stream: read-only review filtered by actor / action / target /
correlation / result; correlated multi-step traces; a missing expected event creates a
`missing_expected_event` exception; a failed atomic action is a distinguishable `failed_atomic` exception.

## Operational-exception registry
17 queues: `unresolved_identity, conflicting_facts, missing_policy, conflicting_policy,
stale_recommendation, expired_approval, failed_execution, reconciliation_conflict, audit_failure,
missing_observation, ambiguous_pairing, conflicting_learning_signal, calibration_validation_regression,
scenario_promotion_awaiting_review, authority_conflict, service_loaner_operational_alert,
executive_demo_blocked_recommendation`. Each references the authoritative source; closing a queue item
never resolves the source; dismissal requires authority + reason. See `adr/ADR-0033`.

## Readiness-assessment registry
Domains: `new_inventory, production_workflows, service_loaner, executive_demo, learning_calibration,
governance_foundation`. Classifications: `READY, READY_WITH_WARNINGS, NOT_READY, UNRESOLVED,
CONFLICTING`. Missing required policy or authority blocks readiness; a critical unresolved identity may
block it; passing synthetic tests alone is insufficient; readiness does not deploy or activate; prior
assessments remain historical. See `adr/ADR-0034`.

## Capability / authority registry
`workspace.view/review, decision.issue/approve/reject/defer/override/correct/supersede/acknowledge,
execution.authorize/review, scenario.create/share/review/promote/policy_review_request,
calibration.workspace.review, authority.view/grant/delegate/revoke/override_separation,
audit.view/exception.review, readiness.assess/approve`. Distinct reviewer / decider / approver / executor
/ acknowledger / scenario-owner / scenario-reviewer / authority-admin / auditor / readiness principals
prove separation of authority; every governed action authorizes below the UI, binds an Audit Event
atomically, rejects stale/revoked/out-of-scope actors, and is idempotent under a retry key.
