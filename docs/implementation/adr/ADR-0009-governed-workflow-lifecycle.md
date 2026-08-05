# ADR-0009 — Governed workflow lifecycle

- **Status:** Accepted (Phase 5)
- **Owning segments:** 07 (Supply/pipeline workflows), 11 (Governance)

## Decision
Production/acquisition workflows share one common lifecycle (`DRAFT → PROPOSED → UNDER_REVIEW →
APPROVED → COMMITTED → IN_EXECUTION → COMPLETED` plus REJECTED/WITHDRAWN/CANCELLED/FAILED/SUPERSEDED/
EXPIRED/UNRESOLVED); each workflow type restricts the legal subset. Every proposal and transition is
a governed action (Phase 1 Governor): authorized below the UI, legal-transition + optimistic-
concurrency checked, and persisted atomically with a transition row, a commitment-reconciliation
result, any supply effect, and the required Audit Event. A proposal is never Supply; approval creates
Committed Supply only where the workflow contract requires it; execution/completion is distinct from
approval, and proposal/approval/completion are distinct capabilities. Idempotent retries short-
circuit in the Governor (recorded as DUPLICATE_REPLAY, no effect re-applied); an audit-write failure
rolls the whole action back.

## Why
The workflows must produce trustworthy, auditable supply state without ever bypassing authorization
or double-applying effects. Reusing the Phase 1 governed-action primitive (business write + audit
atomic) and running supply effects via raw inserts on the governed connection is the smallest correct
way to guarantee "no success without audit" and "no duplicate effect."

## Consequences
- Workflow / transition / reconciliation records are append-preserving (no-delete triggers).
- Separation of authority (proposal vs approval vs completion) is enforced by distinct capabilities.
- The supply effect is atomic with its audit; on replay or audit failure no supply is created.
