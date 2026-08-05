# ADR-0029 — Governed Decision issuance

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance/Audit)

## Decision
An issued Decision references the exact reviewed recommendation and its revision, preserves the state
known at Decision time, keeps missing rationale unknown, and records only the alternatives actually
presented. Issuance is a Phase 1 governed action: authorized below the UI, idempotent under a retry key,
and bound to its Audit Event atomically (audit failure rolls the whole issuance back). A stale/superseded
recommendation is rejected for an ordinary disposition; only an explicit OVERRIDE authority + reason may
proceed. Scenario Decisions stay Scenario-only, and a private Scenario output can never be issued as an
official Decision. Dispositions (`ACCEPT, REJECT, DEFER, REQUEST_INFORMATION, NO_ACTION, OVERRIDE, CANCEL,
CORRECT, SUPERSEDE`) never rewrite the recommendation; correction preserves the original Decision,
supersession links both, cancellation preserves history.

## Why
Recommendation is not Decision. Making issuance a governed, idempotent, atomically-audited act — with
stale protection and an explicit, reasoned override path — guarantees that every operational decision is
attributable, reversible in record, and never silently made against outdated or scenario-only evidence.

## Consequences
- Replayed issuance returns the same Decision (test 11); audit failure commits nothing (test 13).
- Stale issuance is rejected; override requires a reason and is audited (tests 14, 15, 23).
- A scenario recommendation cannot be executed as official state (tests 16-17; regression 19).
