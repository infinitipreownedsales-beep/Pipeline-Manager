# ADR-0047 — Full live-executor integration

## Status
Accepted (Phase 12).

## Context
Phase 11 left a gap: the pilot execution path used a synthetic callback. Phase 12 must invoke the actual
Phase 5-7 domain services behind every governed pilot action, with no synthetic callback in the real path
and no direct domain-table mutation from the UI.

## Decision
Add `elite/release/executors.LiveExecutorRegistry` binding each governed action to the REAL Phase 5-7
governed domain method, and `LiveExecutionService` that (1) invokes the real domain method — its own
Governor.perform produces a real domain event + Audit Event + optimistic-concurrency/idempotency — then
(2) references that real domain ref in the Phase 9 execution authorization/completion/reconciliation. The
Phase 10 UI `/execution/{id}/authorize` uses `app.live_executor` when a Decision is bound (else the prior
reference path, keeping Phase 10/11 green).

## Consequences
The real pilot path invokes the actual service; execution is idempotent, audited, restart-safe, and never
shows a failed run as success; a Scenario Decision cannot enter the official path; the UI performs no direct
domain-table write.
