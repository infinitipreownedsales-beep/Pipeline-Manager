# ADR-0052 — Release package + explicit release-authorization gate

## Status
Accepted (Phase 12).

## Context
Go-live must be an explicit, governed, human Decision — never an automatic consequence of passing tests —
and must not itself perform cutover.

## Decision
Issue an immutable release package (once issued). Provide a governed final readiness certification (ten
dimensions) and an explicit governed release-authorization Decision (AUTHORIZE_GO_LIVE / LIMITED_DOMAIN /
CONTINUE_PARALLEL_RUN / DEFER / REJECT / ROLLBACK_REQUIRED). GO_LIVE_AUTHORIZED can only be set by an
authorized Principal's explicit Decision; the Decision is atomic with its Audit Event, supports expiration +
separation of duties, and performs no cutover.

## Consequences
Readiness and authorization are separate; no authorization leaves the system in parallel pilot mode; an
expired authorization cannot be used; production-primary activation requires a distinct explicit release
authorization after review; no irreversible cutover occurs in Phase 12.
