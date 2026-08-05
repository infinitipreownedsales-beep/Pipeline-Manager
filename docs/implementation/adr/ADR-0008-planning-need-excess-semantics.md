# ADR-0008 — Planning semantics (Need / Excess / portfolio)

- **Status:** Accepted (Phase 4)
- **Owning segments:** 06 (Demand/forecast), 07 (Supply/pipeline planning)

## Decision
Need and Excess are deterministic and month-aware, computed under Calculation Version
`new_inventory_plan`:
- `requirement = Σ(monthly Demand over horizon) + desired ending coverage`. Desired ending
  coverage is **resolved through Phase 3 policy**, never hardcoded; an unresolved/conflicting
  coverage policy leaves the plan `unresolved` — it never invents a target.
- `Need = max(0, requirement − qualifying_supply)` and `Excess = max(0, qualifying_supply −
  requirement)`, so both are non-negative and never simultaneously positive.
- Qualifying supply is identity-deduped (counted once across Current/Future/Committed) and
  restricted to units available within the horizon.
- Per month, `cumulative_supply[m]` counts only units available on/before month m — a later-
  arriving unit cannot satisfy an earlier month, and continued unsold inventory is explicitly
  carried forward through time.
- Portfolio aggregation **sums** issued combination results into model / model-year / portfolio
  summaries and never independently recomputes Demand; combination-level results remain traceable
  via `plan_refs`. Healthy / leave-alone states are valid outputs.

By construction, adding qualifying Supply cannot increase Need and removing it cannot decrease
Need (monotonicity); an approved commitment credits exactly one unit and updates the next
calculation.

## Why
These invariants are the binding fix for BUG-CPO-002 and the core trust guarantees of the tool.
Encoding them in a deterministic, reproducible calculation (with a per-month roll-forward) is the
smallest correct way to make Need explainable, monotone, and non-double-counting.

## Consequences
- Plans are issued append-preserving with a reproducibility package; `replay` reproduces the
  identical Need/Excess.
- The first operational output slice (`newinv/output`) renders real issued plan/demand output —
  Call / Why / Proof / evidence refs / month-by-month / supply / Demand / Need / Excess /
  confidence / unresolved state / versions — not mocked recommendation text.
