# PHASE 9 GOVERNANCE + OPERATIONAL-CONTROL DOMAIN MODEL (migration v9)

New tables added by migration v9 `governance_operational_control` (appended; v1-v8 unchanged). Payloads
are JSON-in-SQLite behind repositories (`govern/store.py`). Governed Decisions, acknowledgments, and
readiness assessments are **immutable** (no-update + no-delete); everything else is append-preserving
(no-delete). Every table REFERENCES authoritative Phase 1-8 records by id — Phase 9 never copies domain
calculations into a second source of truth, and never redefines Phase 4-8 domain mathematics.

## Records (24 tables)
| Table | Purpose | Key invariants |
|---|---|---|
| `decision_workspace_item` | Operational-control summary referencing domain output | references only; mutable state via version guard; no-delete |
| `decision_workspace_revision` | Snapshot per recommendation revision | append-only; prior remains historical |
| `governed_decision` | Immutable issued Decision | references exact recommendation; no-update/no-delete; UNIQUE idempotency |
| `decision_alternative` | Actually-presented alternatives | only what was presented; no-delete |
| `decision_approval` | Approval where the domain requires it | scope/quantity-bounded; idempotent; no-delete |
| `execution_authorization` | References the Phase 5-7 domain executor | never duplicates domain logic; idempotent; no-delete |
| `decision_execution_reconciliation` | 15 deterministic outcomes | append-only |
| `decision_acknowledgment` | Operational receipt/awareness | idempotent + immutable (no-update/no-delete) |
| `governance_expiration` | Expiry of rec/decision/approval/exec/scenario | append-only |
| `governance_staleness_result` | Staleness markers | append-only; stale never deletes |
| `scenario_administration` | Governed Scenario (isolated) | 12 states; version-guarded; no-delete |
| `scenario_share` | Sharing record | sharing ≠ approval; no-delete |
| `scenario_review` | Review record | approved-for-discussion ≠ official; no-delete |
| `scenario_promotion_request` | Promotion routing | no operational effect; routes to review type; no-delete |
| `policy_review_request` | Policy-review item | a review, not a policy change; no-delete |
| `authority_delegation` | Delegation over Phase 1 grants | ≤ delegator capability + scope; grant chain; no-delete |
| `authority_temporary_grant` | Temporary authority | auto-expires per contract; no-delete |
| `separation_of_duties_rule` | Versioned SoD rules | policy-resolvable; no-delete |
| `separation_of_duties_exception` | Conflicts + authorized overrides | override visible + audited; no-delete |
| `audit_exception` | Missing/failed Audit events | append-only |
| `operational_exception_item` | Exception/unresolved queue item | references source; closing ≠ resolving source; no-delete |
| `operational_control_summary` | Structured counts + refs | reconciles to source; no-delete |
| `domain_readiness_assessment` | Evidence-based readiness | immutable after issuance; does not deploy; no-update/no-delete |
| `governance_issued_output` | Issued-output index | append-preserving; no-delete |

## Workspace states (operational-control summary only)
`OPEN, READY_FOR_REVIEW, UNDER_REVIEW, AWAITING_INFORMATION, UNRESOLVED, RECOMMENDED, DECISION_PENDING,
DECIDED, APPROVED, REJECTED, DEFERRED, AWAITING_EXECUTION, IN_EXECUTION, COMPLETED, FAILED, EXPIRED,
STALE, SUPERSEDED, CORRECTED, CANCELLED`. Domain records keep their own lifecycle; the workspace state
summarizes control and never replaces it.

## Constitutional separations (enforced)
Recommendation ≠ Decision ≠ approval ≠ execution ≠ completion. Scenario ≠ official state; shared Scenario
≠ approval; Calibration Proposal ≠ activation; policy-review request ≠ policy change. Authorization +
scope enforced below the UI; governed state change + Audit Event atomic; audit failure blocks unsafe
success; stale Decisions/approvals rejected; idempotent retries never duplicate; correction/supersession
preserve original history; unknown rationale stays unknown; absence of approval ≠ rejection; absence of
execution ≠ failure unless the contract says so. See `adr/ADR-0028` (Decision Workspace), `ADR-0029`
(Decision issuance), `ADR-0030` (Scenario promotion), `ADR-0031` (authority delegation), `ADR-0032`
(separation of duties), `ADR-0033` (exception queues), `ADR-0034` (readiness).

## Dispositions + reconciliation
Dispositions: `ACCEPT, REJECT, DEFER, REQUEST_INFORMATION, NO_ACTION, OVERRIDE, CANCEL, CORRECT,
SUPERSEDE`. Reconciliation outcomes: `NO_EXECUTION_REQUIRED, AWAITING_APPROVAL, APPROVED_AWAITING_EXECUTION,
EXECUTION_AUTHORIZED, EXECUTED, COMPLETED, FAILED, CANCELLED, EXPIRED, STALE, ALREADY_RECONCILED,
UNRESOLVED_IDENTITY, CONFLICTING, DOMAIN_REJECTED, AUDIT_BLOCKED`. Every actionable Decision can produce a
reconciliation result.
