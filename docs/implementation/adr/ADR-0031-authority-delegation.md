# ADR-0031 — Authority administration + delegation

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance/Authorization)

## Decision
Authority administration operates over the Phase 1 `capability_grant` store — there is no second
permission store. A delegation cannot exceed the delegator's own capability or scope, and the backing
grant records a `delegated_by:<principal>` chain so a delegated action stays attributable. Temporary
authority carries an expiration and is swept to inactive automatically per its contract; a revoked grant
is immediately ineffective. Every authority mutation is a governed action (authorized + atomically
audited); an audit failure leaves authority unchanged. Grant / delegation / expiration / revocation
records remain historical.

## Why
Reusing the Phase 1 authorization primitive keeps a single authoritative access-decision path (enforced
below the UI) and avoids a divergent shadow permission model. Bounding delegation to the delegator's own
authority, auto-expiring temporary grants, and auditing every change keep the authority surface safe and
inspectable.

## Consequences
- Over-capability and over-scope delegations are rejected (tests 76, 77; regression 5, 6).
- Temporary authority expires and revoked authority is denied by the Phase 1 authorizer (tests 74, 75).
- An audit failure blocks the grant mutation entirely (test 84; regression 12-13).
