# PHASE 4 NEW INVENTORY DOMAIN MODEL (migration v4)

New tables added by migration v4 `new_inventory` (appended; v1-v3 unchanged). All payloads are
JSON-in-SQLite behind repository methods (`newinv/store.py`). Issued results are append-
preserving (DB triggers block deletes); supply/retail projections are recomputable snapshots.

## Records
| Table | Purpose | Key invariants |
|---|---|---|
| `sellable_combination` | Canonical orderable + sellable configuration | `canonical_identity` from demand-material dims only; scoped; no-delete trigger; corrections preserve prior |
| `sellable_combination_alias` | Source / correction aliases | append; history preserved |
| `combination_lineage` | Explicit, versioned comparability relationships | generation change needs approved rule to inherit |
| `current_supply_projection` | Current Supply from accepted current-state facts | one effect per Vehicle Unit; eligibility + exclusion reason; presence ≠ availability |
| `future_supply_projection` | Future Supply from Production Orders | distinct orders distinct; pre-VIN→VIN one unit; cancelled excluded; ETA visible |
| `supply_commitment` | Approved unit-level future action state | proposal ≠ commitment; committed once; cancel stops prospectively, stays historical |
| `retail_history_projection` | Accepted retail, deduped | facts only; no duplicate retail; correction/reversal preserve history |
| `availability_interval` | Month-bucketed availability + exposure | available≠unavailable; partial invents no continuity; stockout fabricates no lost sales; gaps reduce confidence |
| `demand_result` | Issued Demand baseline | supply-blind; evidence tier + direct flag; reproducibility-pinned; no-delete |
| `forecast_result` / `forecast_month` | Month-by-month forecast | monthly reconciles to total; issued history immutable; no-delete |
| `desired_coverage_resolution` | Policy-resolved ending coverage | resolved/unresolved/conflicting; never invented |
| `inventory_plan_result` / `inventory_plan_month` | Need / Excess | Need,Excess ≥ 0, not both positive; monotone in qualifying supply; per-month cumulative; no-delete |
| `portfolio_plan_result` | Model / model-year / portfolio aggregation | sums combination results; never recomputes Demand; no-delete |
| `issued_planning_output` | Issued-output reference index | append-preserving; pins calc version + reproducibility package |

## Demand contract (supply-blind)
`DemandService.issue(...)` takes accepted retail, availability exposure, seasonality, trend,
lineage/inheritance, and policy versions — **no supply parameter exists**. Expected retail per
month = availability-adjusted baseline rate × bounded seasonal index × trend, under Calculation
Version `new_inventory_demand`. Direct exact-combination evidence outranks inherited lineage
evidence; inherited evidence is labeled; low sample / gaps reduce confidence; sparse history
falls back to a flat seasonal index. A reproducibility package pins all inputs + versions so
`replay` reproduces the identical output.

## Need / Excess contract (month-aware, monotone)
Under Calculation Version `new_inventory_plan`:
- `total_demand` = Σ monthly Demand over the horizon (Demand is an input, never recomputed).
- `qualifying_supply` = eligible Current + active Future + committed Commitment units, **deduped
  by one canonical unit/order identity** (counted once across the three states), restricted to
  units available within the horizon.
- `requirement` = total_demand + desired ending coverage (policy-resolved; unresolved ⇒ the plan
  is `unresolved`, never an invented target).
- `Need = max(0, requirement − qualifying_supply)`; `Excess = max(0, qualifying_supply −
  requirement)` ⇒ both ≥ 0 and never both positive.
- Per month: `cumulative_supply[m]` counts only units available on/before month m, so a later-
  arriving unit cannot satisfy an earlier month; continued unsold inventory is explicitly carried
  forward. Adding qualifying Supply cannot raise Need; removing it cannot lower Need.
