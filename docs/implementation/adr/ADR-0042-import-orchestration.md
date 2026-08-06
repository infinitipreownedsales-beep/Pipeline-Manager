# ADR-0042 — Import-run orchestration

## Status
Accepted (Phase 11).

## Context
The pilot needs an authoritative, restart-safe record of every import attempt, with idempotency, retry
linkage, and failure that never corrupts the last valid state.

## Decision
Add `elite/ops/imports.ImportOrchestrator` driving the state machine RECEIVED → VALIDATING → VALIDATED →
INGESTING → INGESTED → RECONCILING → COMPLETED/COMPLETED_WITH_WARNINGS (with REJECTED/FAILED/CANCELLED/
SUPERSEDED). Same content is idempotent; a failed import preserves the prior accepted state (Phase 2
ingestion is atomic); partial ingestion never reaches COMPLETED; a retry links via `retry_of`; errors are
recorded as safe messages only. Import success is not acceptance; acceptance is not reconciliation;
reconciliation is not automatic business action.

## Consequences
Operators see safe, actionable failures; restart never replays a completed effect; the import record
references — but never copies — the raw Phase 2 evidence.
