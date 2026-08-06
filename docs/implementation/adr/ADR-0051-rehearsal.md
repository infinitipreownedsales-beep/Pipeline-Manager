# ADR-0051 — Migration / rollback / recovery rehearsals

## Status
Accepted (Phase 12).

## Context
Readiness cannot be declared on tests alone; migration, rollback, and recovery must be PROVEN, repeatable,
and non-destructive.

## Decision
Add immutable rehearsal records: a migration rehearsal from a clean database through v1-v12 + backup +
restart + count reconciliation; a rollback rehearsal proving control returns to legacy (history preserved,
legacy available, in-flight identified, no replay into legacy); a recovery rehearsal preserving committed
truth. A failed rehearsal blocks readiness.

## Consequences
Rollback is proven, not merely documented; rehearsals do not affect operational legacy state; failures are
preserved and block readiness.
