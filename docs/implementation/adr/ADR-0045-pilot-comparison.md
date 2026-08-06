# ADR-0045 — Non-authoritative parallel-run comparison

## Status
Accepted (Phase 11).

## Context
The pilot runs alongside the legacy tool. Disagreement must be reviewable evidence, never an automatic
change to either tool.

## Decision
Add a comparison layer (`elite/ops/pilot.PilotService.compare`) that captures a snapshot of the Elite result
and the legacy result and classifies the difference (MATCH / DATA / TIMING / IDENTITY / POLICY / CALCULATION
/ LEGACY_LIMITATION / ELITE_LIMITATION / UNRESOLVED). It mutates NEITHER result — only the review fields are
written, via a governed review. Legacy is not authoritative because it is legacy; Elite is not authoritative
because it is new; an unknown cause stays UNRESOLVED; reviewer rationale is stored only as supplied; a
material unresolved difference blocks readiness until reviewed.

## Consequences
Comparison is safe to run continuously; it never silently synchronizes one tool to the other; readiness is
evidence-based.
