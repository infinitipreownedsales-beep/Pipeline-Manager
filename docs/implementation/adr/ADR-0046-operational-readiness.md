# ADR-0046 — Operational readiness + controlled pilot mode

## Status
Accepted (Phase 11).

## Context
The pilot must be visibly non-production, keep the legacy tool as the fallback, block cutover, and expose
honest liveness/readiness — a live app may still be operationally not ready.

## Decision
Add a visible, enforceable pilot mode (`elite/ops/pilot`) that blocks destructive cutover / legacy-
replacement / destructive-migration / production-go-live actions, plus three-way health (liveness /
readiness / operational). Readiness is blocked by migrations behind, integrity failure, a stale/missing
blocking source, a failed uncorrected import, or an unreviewed material discrepancy. Evidence-based
readiness certification records READY / READY_WITH_WARNINGS / NOT_READY. No cutover occurs in Phase 11.

## Consequences
Operators always know the pilot is non-production with a legacy fallback; readiness reflects real evidence,
not a single opaque score.
