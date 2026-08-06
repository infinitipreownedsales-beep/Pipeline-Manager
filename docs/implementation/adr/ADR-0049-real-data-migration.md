# ADR-0049 — Real-data migration + governed readiness

## Status
Accepted (Phase 12).

## Context
Real identity, history, policy, and authority must migrate into a dedicated database without inventing data
or moving business truth into the migration layer, and readiness must be evidence-based and multi-dimensional.

## Decision
Migrate into a DEDICATED migration/pilot database via the real adapters/orchestrator; record identity + fact
reconciliation, governed policy resolution (confirmed values only), and governed authority configuration
(explicit scope, no overgrant). Assess readiness across ten separate dimensions; OPERATIONALLY_READY is
derived from the eight prerequisites; GO_LIVE_AUTHORIZED is never set by certification.

## Consequences
Unknown stays unknown; unresolved identity stays unresolved; synthetic values cannot become official policy;
missing policy/authority blocks readiness; readiness and authorization stay separately inspectable.
