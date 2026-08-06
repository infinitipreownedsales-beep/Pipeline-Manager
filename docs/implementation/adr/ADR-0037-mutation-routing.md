# ADR-0037 — Mutation routing through governed services

- **Status:** Accepted (Phase 10)
- **Owning segments:** 10 (User Experience), 11 (Governance)

## Decision
Every state-changing operator action routes through exactly one Phase 1-9 governed service — Decision
issuance, approval, execution authorization/completion, acknowledgment, Used Cars receipt, authority
delegation, exception dismissal — and never mutates a domain record directly. Each mutation is a POST
carrying a CSRF token and a per-render idempotency nonce (threaded as the service idempotency key so a
double submit replays instead of duplicating). Below-UI authorization and scope are enforced by the
Phase 1 authorizer inside every handler; the correlation ID is preserved across the call chain; audit
failure surfaces as a safe failure with nothing committed.

## Why
The governance guarantees of Phases 1-9 (atomic audit, separation of duties, stale/idempotency
protection, immutability) are only real if the UI cannot bypass them. Forcing every mutation through the
governed services — and never letting a route write a domain table — makes the interface incapable of
weakening those guarantees.

## Consequences
- CSRF failures are rejected (403); double submissions do not duplicate (idempotency nonce); audit
  failures render a safe error and commit nothing (tests 46, 47, 93, 94).
- Approval cannot execute, a Scenario Decision cannot execute officially, and a stale recommendation
  cannot be decided ordinarily — all because the routes call the governed services.
