# ADR-0032 — Separation of duties

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance/Authorization)

## Decision
Separation-of-duties rules are versioned / policy-resolvable (`proposer_not_approver, approver_not_executor,
executor_not_completer, calibration_proposer_not_activator, policy_proposer_not_approver,
correction_actor_differs, self_approval_prohibited_above_materiality`). Conflicts are checked below the
UI; a conflict is a hard block that records an exception. A missing REQUIRED rule yields UNRESOLVED
governance rather than permissive behavior. An authorized override requires the explicit
`authority.override_separation` capability + a reason + an Audit Event, and the override stays visible.

## Why
Governance integrity depends on the same person not holding both sides of a separated pair. Defaulting a
missing rule to "unresolved" (not "allowed") avoids silent permissiveness, while an explicit, reasoned,
audited override supports real single-staff dealership situations without hiding them.

## Consequences
- A proposer cannot approve; self-approval above materiality is blocked (tests 79, 80; regression 9).
- An override needs capability + reason and is recorded; an unauthorized override is rejected (tests 81,
  82; regression 10, 11).
