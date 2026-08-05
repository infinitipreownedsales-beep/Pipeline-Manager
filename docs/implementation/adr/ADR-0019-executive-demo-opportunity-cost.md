# ADR-0019 — Executive Demo New Retail opportunity cost consumes the Phase 4 plan

- **Status:** Accepted (Phase 7)
- **Owning segments:** 09 (Executive Demo), 07 (New Inventory)

## Decision
The New Retail opportunity cost of designating a Vehicle Unit as an Executive Demo is a versioned
result (`executive_demo_opportunity_cost`) that **consumes** the authoritative Phase 4 inventory plan
(`InventoryPlanResult`) for the candidate's exact Sellable Combination. It reads the plan's Need/Excess
position and affected months and derives a deterministic cost — higher when the combination is in Need,
lower when in Excess, scaled by the expected number of months the unit is removed from New Retail. It
**never** computes a separate Demand. Unknown return timing lowers confidence to `low`. Each result is
reproducibility-pinned and stays distinguishable from Executive Demo benefit.

## Why
New Retail Demand is a single authoritative baseline (Phase 4, supply-blind). Any domain that recomputed
it would reintroduce the BUG-CPO-002 class of model conflation and double-counting. Consuming the plan —
rather than recalculating demand — keeps Demand an input and makes the opportunity cost a direct,
explainable function of the real New Retail position the demo displaces.

## Consequences
- A candidate whose combination is in Need has a strictly higher opportunity cost than one in Excess,
  proven from the plan, not assumed (`test_phase7_preference_bestoverall.test_30`).
- A changed Executive Demo assignment path alone never alters New Retail Demand (regression item 13).
- The opportunity cost is a distinct result table from Executive Demo benefit; the two never collapse
  into one score.
