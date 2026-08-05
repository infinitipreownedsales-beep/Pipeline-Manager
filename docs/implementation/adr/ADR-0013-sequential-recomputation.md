# ADR-0013 — Sequential recomputation

- **Status:** Accepted (Phase 5)
- **Owning segments:** 06 (Demand/forecast), 07 (Supply/pipeline planning)

## Decision
The sequential planner starts from one accepted portfolio state and applies one approved Commitment
effect at a time, recomputing qualifying Supply / Need / Excess against the UPDATED committed state
before producing the next recommendation. Every intermediate issued plan is preserved
(`sequential_planning_step`, append-preserving); the step records which action caused each state
change (need before/after). The same unit/order can never be selected twice (DUPLICATE_SELECTION),
and an action whose combination's Need is already met is suppressed (SUPPRESSED_NO_NEED). Demand is
never recomputed here — it is an input owned by Phase 4 and unchanged unless its own accepted inputs
or active versions change.

## Why
Batch ranking that assumes all proposed actions can occur simultaneously would double-satisfy Need
and re-select units. Recomputing after each accepted action — against the real updated committed
state — is the smallest correct way to make a sequence of supply actions deterministic, traceable,
and non-double-counting.

## Consequences
- Each step is attributable to its causing action; the run and every intermediate plan are preserved.
- The planner returns unresolved / stops if identity or commitment reconciliation fails.
- Monotonicity holds across the sequence: added qualifying Supply never raises Need.
