# ADR-0050 — Parallel validation + discrepancy governance

## Status
Accepted (Phase 12).

## Context
The pilot runs alongside legacy; disagreement must be reviewable evidence with a governed burn-down, never a
silent change to either tool.

## Decision
Record dated parallel-validation runs/results (both outputs preserved, classified, neither mutated) and a
governed discrepancy burn-down with an immutable transition log. Classification requires evidence; a
confirmed Elite defect enters the defect registry; closing a discrepancy alters neither historical result; a
material unresolved discrepancy blocks affected-domain readiness.

## Consequences
A difference is never hidden for parity; legacy and Elite disagreement both require evidence-based review;
burn-down metrics reconcile to the discrepancy records.
