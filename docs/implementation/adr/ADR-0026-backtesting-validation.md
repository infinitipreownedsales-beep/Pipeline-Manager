# ADR-0026 — Backtesting and validation

- **Status:** Accepted (Phase 8)
- **Owning segments:** 12 (Learning)

## Decision
Calibration validation compares a current version and a proposed version over PRESERVED historical
inputs and outcomes, per material cohort. Backtest results are labeled hypothetical and never rewrite
historical issued Predictions; training and evaluation windows stay distinguishable; leakage of future
Observation into historical Prediction inputs is prohibited (rejected). Validation identifies cohorts
improved / worsened / unchanged and explicitly flags when an aggregate improvement hides material
cohort degradation. Synthetic fixtures prove the foundation — no machine learning is implemented merely
to satisfy the phase.

## Why
A proposed change must be justified against real history without contaminating that history or hiding
who it hurts. Labeling results hypothetical, forbidding leakage, and surfacing material cohort
degradation behind an aggregate win are the guardrails that make validation evidence trustworthy input
to an approval decision.

## Consequences
- A leakage attempt is rejected (test 57); historical Predictions are unchanged after any backtest
  (test 56).
- Aggregate improvement with a degraded material cohort is flagged, not silently accepted (test 59).
