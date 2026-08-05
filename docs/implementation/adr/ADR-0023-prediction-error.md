# ADR-0023 — Prediction Error

- **Status:** Accepted (Phase 8)
- **Owning segments:** 12 (Learning), 06 (Calculation Versioning)

## Decision
A versioned Error is derived ONLY from a valid Pairing (`PAIRED`/`LATE_PAIRED`/`PARTIAL`), using the
Comparison Specification's error semantics. It records signed and absolute error always; percentage
error only when the denominator is valid and semantically meaningful (a zero/meaningless expected value
yields no percentage, never a division error); zero predicted/actual and partial/missing observations
follow explicit semantics (missing → pending, partial → the permitted partial error, never fabricated).
Materiality resolves through policy. Each Error pins the Comparison + Calculation Versions and a
reproducibility package. An Error establishes no causation. A corrected Observation produces a
corrected/superseding Error via `error_correction` without deleting history.

## Why
The size and sign of a miss must be computed under an explicit, versioned rule, and must degrade
gracefully when inputs are absent or units are incompatible rather than inventing a number.
Reproducibility pinning lets a historical Error be recomputed exactly, and keeping causation out of the
Error keeps "what happened" separate from "why it may have happened" (Attribution).

## Consequences
- Percentage error is null for a zero denominator; tests assert no ZeroDivision.
- Materiality is a policy-resolved classification, not a hardcoded constant.
- Correcting an Observation never rewrites the prior Error; it supersedes it with lineage.
