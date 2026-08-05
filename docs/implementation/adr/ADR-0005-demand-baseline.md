# ADR-0005 — Demand baseline (supply-independent)

- **Status:** Accepted (Phase 4)
- **Owning segments:** 06 (Demand / forecasting)

## Decision
There is exactly **one** authoritative Demand contract, computed from accepted dealership
history + approved policy under a versioned Calculation Version (`new_inventory_demand`). The
`DemandService.issue(...)` signature takes **no supply parameter** — not current/future/committed
supply, not CPO/PPO/CTP availability, not Dealer Trade feasibility, not Service Loaner / Executive
Demo economics, not a desired acquisition path. A supply-method change therefore cannot move
Demand truth. Demand consumes accepted retail, availability *exposure* (so "no availability" is
never read as "zero demand"), bounded seasonality, trend, approved policy, and — only when an
approved lineage permits — labeled inherited evidence. Direct exact-combination evidence outranks
inherited evidence; low sample size and unresolved gaps reduce confidence; sparse history falls
back to a flat seasonal index rather than an exaggerated coefficient.

## Why
BUG-CPO-002 was rooted in Demand being entangled with a supply/replenishment path. Making Demand
structurally supply-blind (no supply argument exists) is the smallest correct guarantee that
adding an acquisition path cannot change Demand, and is the precondition for monotonic Need.

## Consequences
- Demand is deterministic and reproducible (a reproducibility package pins all inputs + versions;
  `replay` reproduces the identical output).
- Every issued Demand result records its evidence tier, direct/inherited flag, seasonality/trend
  references, confidence, and uncertainty — so a recommendation is always explainable.
- No supply workflow may compute its own Demand; supply may change feasibility/timing/confidence/
  commitment status only.
