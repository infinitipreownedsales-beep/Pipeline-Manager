# ADR-0007 — Supply-state model (Current / Future / Committed)

- **Status:** Accepted (Phase 4)
- **Owning segments:** 07 (Supply / pipeline), 11 (Governance)

## Decision
Supply is modeled in three distinguishable states, kept strictly separate from Demand:
- **Current Supply** — from accepted current-state facts; one effect per physical Vehicle Unit;
  sold/retired/transferred/duplicate/invalid/unresolved units are excluded with a recorded reason;
  operational presence and retail availability remain distinguishable.
- **Future Supply** — from accepted Production Orders; two same-config orders are two distinct
  future units; a pre-VIN order and its later VIN resolve to one unit (no double count); cancelled
  or invalid orders do not count; ETA uncertainty stays visible.
- **Committed Supply** — approved unit-level future action state. A **proposal is not a
  commitment**; approval creates a commitment only when the action contract requires it; a
  cancelled/superseded commitment stops contributing prospectively while remaining historical.

**Qualifying supply** is the union of eligible Current + active Future + committed Commitment
units, **deduplicated by a single canonical unit/order identity**, so one physical or future unit
counts at most once across the three states. A commitment's acquisition path never alters Demand.

## Why
BUG-CPO-002 arose from conflating continuous replenishment with discrete commitment and from
double-counting. Explicit, separately-inspectable states plus identity-deduped qualifying supply
are the smallest correct guarantee of "counted once" and "commitment affects the next calculation
exactly once."

## Consequences
- Supply projections are recomputable snapshots (`current_supply_projection`,
  `future_supply_projection`, `supply_commitment`); qualifying supply is computed on demand.
- Committed Supply is the stand-in for later Phase-5 acquisition workflows (CPO/PPO/Dealer Trade/
  CTP); those workflows are **not** implemented in Phase 4 — only the commitment state they would
  produce.
