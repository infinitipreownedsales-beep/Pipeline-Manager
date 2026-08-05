# PHASE 7 REGISTRIES — Executive Demo

Living registries for the Phase 7 Executive Demo domain. Runtime records live in the authoritative
SQLite store (migration v7); this document indexes the contracts. Executive Demo is a **separate**
bounded domain from Service Loaner.

## Executive Demo lifecycle registry
Governed membership states (see `PHASE7_DOMAIN_MODEL.md` for the full transition map). Designation
APPROVAL creates committed portfolio state only; designation EXECUTION establishes membership once and
removes the unit from New Retail Current Supply. Retirement flows eligibility → propose → approve →
execute (actual retirement) → {return-to-New-Retail | Used Cars receipt}. Active membership counts a
Vehicle Unit once.

## Best Overall objective registry
Calculation Version `executive_demo_portfolio` (1.0.0). Objective =
`W_BENEFIT·benefit − W_OPP_COST·opportunity_cost + W_FIT·portfolio_fit + preference_bonus`
(`1.0 / 1.0 / 2.0 / 1.5`). Eligibility is a hard pre-filter; duplicates and already-active/committed/
retired units are excluded; each plan records per-candidate tradeoffs, labeled necessary sacrifices,
the need basis, the objective weights, and the pick — never an opaque composite score. Model
preference contributes only through an approved Phase 3 resolution. See `adr/ADR-0018`.

## New Retail opportunity-cost registry
Calculation Version `executive_demo_opportunity_cost` (1.0.0). CONSUMES a Phase 4 `InventoryPlanResult`
for the candidate's exact Sellable Combination — it identifies the affected combination and months and
derives the cost from the plan position (higher in Need than in Excess, proven from the plan), scaled
by expected months removed from New Retail. It NEVER computes a separate Demand; unknown return timing
lowers confidence (`low`); a changed demo path alone never alters Demand. Reproducibility-pinned. See
`adr/ADR-0019`.

## Expected-lifecycle registry
Calculation Version `executive_demo_lifecycle` (1.0.0). Resolves only when the required inputs
(expected duration, expected mileage, expected retirement timing) are present; otherwise `unresolved`
(never manufactured). Historical projections are immutable/append-preserving; current projections may
change under new facts/policy. Sunk cost is not carried into later retirement decisions.

## Economic Call registry
Calculation Version `executive_demo_economic` (1.0.0). Decision points: `entry` and `retirement`;
retirement uses INCREMENTAL future economics only (no sunk designation cost reapplied). Each result
carries alternatives (each with its own value + basis — never one opaque score), the chosen economic
call, opportunity-cost ref, expected benefit, assumptions, uncertainty, Policy Versions, Calculation
Version, fact refs, and a reproducibility package. Unsupported inputs → unresolved / lower-confidence;
conflicting policy → conflict. The call is never rewritten because execution is blocked.

## Execution Status registry
Separate from the Economic Call: `READY`, `AWAITING_APPROVAL`, `APPROVED_NOT_EXECUTED`,
`BLOCKED_POLICY`, `BLOCKED_IDENTITY`, `BLOCKED_DATA`, `BLOCKED_NEW_RETAIL_RISK`, `BLOCKED_OPERATIONAL`,
`IN_EXECUTION`, `COMPLETED`, `FAILED`, `UNRESOLVED`. Explains whether/why the strongest call can be
acted on now (including excessive New Retail risk); never rewrites the call.

## Eligibility-outcome registry
`ELIGIBLE`, `INELIGIBLE_ACTIVE_SERVICE_LOANER`, `INELIGIBLE_ALREADY_DEMO`, `INELIGIBLE_COMMITTED`,
`INELIGIBLE_SOLD`, `INELIGIBLE_POLICY`, `INELIGIBLE_IDENTITY`, `INELIGIBLE_DATA`, `UNRESOLVED`,
`CONFLICTING`. Reasons are always recorded; hard ineligibility (active Service Loaner, already demo,
sold, unresolved identity) is never overridden by preference or ranking.

## Reconciliation-outcome registry
`REMAINS_ACTIVE_DEMO`, `DESIGNATION_COMMITTED`, `ACTIVE_DEMO`, `RETIRED_AWAITING_DISPOSITION`,
`RETURNED_TO_NEW_RETAIL`, `USED_CARS_RECEIVED`, `ALREADY_RECONCILED`, `UNRESOLVED_IDENTITY`,
`CONFLICTING`, `FAILED_NO_EFFECT`. One Vehicle Unit counts once. See `adr/ADR-0020`.

## Capability / authority registry
`executive_demo.view`, `.designation.propose`, `.designation.approve`, `.designation.execute`,
`.retirement.propose`, `.retirement.approve`, `.retirement.execute`, `.return_to_retail.confirm`,
`.used_cars_receipt.confirm`, `.policy.explore`, `.correct`. Distinct proposer / approver / designator
/ retirer / returner / receiver principals prove separation of authority (fixtures + items 72). All
transitions authorize below the UI, bind an Audit Event atomically, reject stale/revoked/out-of-scope
actors, and are idempotent under a retry key.

## Domain-separation registry
Executive Demo and Service Loaner are separate packages, stores, migrations, capability namespaces, and
lifecycles. A unit that is an active Service Loaner is ineligible/blocked for designation, and vice
versa. No shared fleet engine is introduced. See `adr/ADR-0021`.
