# PHASE 7 EXECUTIVE DEMO DOMAIN MODEL (migration v7)

New tables added by migration v7 `executive_demo` (appended; v1-v6 unchanged). Payloads are
JSON-in-SQLite behind repository methods (`execdemo/store.py`). Units, membership history, portfolio
plans, opportunity-cost / lifecycle / economic results, retirement events, Used Cars receipts,
reconciliation results, and issued outputs are append-preserving (DB triggers block deletes); the Used
Cars receipt is additionally immutable (no-update trigger + `UNIQUE(executive_demo_unit_id)`). This is
a **separate** store and package from Service Loaner — no shared fleet engine.

## Records
| Table | Purpose | Key invariants |
|---|---|---|
| `executive_demo_unit` | A Vehicle Unit's Executive Demo participation | Executive Demo Unit id never replaces Vehicle Unit id; governed `membership_state` separate from designation/economic state; no-delete |
| `executive_demo_membership_history` | Governed lifecycle transitions | append-only; each references reconciliation + audit; no-delete |
| `executive_demo_portfolio_requirement` | Required portfolio size + model representation | policy-resolved; input to need |
| `executive_demo_portfolio_plan` | Best Overall plan | need resolved before ranking; per-candidate tradeoffs + sacrifices recorded; no opaque score; no-delete |
| `executive_demo_candidate` | Constructed candidate | accepted facts + New Retail planning refs; missing facts stay absent |
| `executive_demo_eligibility_result` | Eligibility gate | explicit reasoned outcome; never a ranking; hard ineligibility not overridable |
| `executive_demo_model_preference_resolution` | Model preference | Phase 3 resolution only; resolved/unresolved/conflicting; scenario-isolated |
| `executive_demo_opportunity_cost_result` | New Retail opportunity cost | consumes the Phase 4 plan; Need > Excess; never computes Demand; no-delete |
| `executive_demo_lifecycle_projection` | Expected Executive Demo lifecycle | versioned; missing inputs → unresolved; historical immutable; no-delete |
| `executive_demo_economic_result` | Versioned Economic Call | separate from execution; entry vs retirement; incremental, no sunk cost; reproducibility-pinned; no-delete |
| `executive_demo_execution_status` | Execution Status | explains actionability incl. BLOCKED_NEW_RETAIL_RISK; never rewrites the call |
| `executive_demo_designation_action` | Designation Decision | proposed/approved/cancelled/corrected; approval = committed only |
| `executive_demo_retirement_eligibility` | Retirement eligibility | eligibility ≠ retirement |
| `executive_demo_retirement_action` | Retirement Decision | proposed/approved/cancelled; approval ≠ actual retirement |
| `executive_demo_retirement_event` | Actual retirement | removes active membership at the defined event; no-delete |
| `executive_demo_return_to_retail_event` | Return-to-New-Retail | restores Current Supply once |
| `executive_demo_used_cars_receipt` | Used Cars receipt | one idempotent, immutable confirmation; own record (NOT Service Loaner); UNIQUE per unit; no-update/no-delete |
| `executive_demo_reconciliation_result` | Supply/lifecycle reconciliation | one Vehicle Unit once; 10 outcomes; no-delete |
| `executive_demo_scenario_result` | Isolated scenario exploration | identifies overrides; never changes official policy/portfolio |
| `executive_demo_resale_reference` | Resale/outcome foundation | preserves refs for Phase 8 pairing; predicted/observed unpopulated here |
| `executive_demo_issued_output` | Issued-output index | append-preserving; no-delete |

## Executive Demo lifecycle (governed)
`CANDIDATE → DESIGNATION_PROPOSED → DESIGNATION_APPROVED → (DESIGNATION_PENDING) → ACTIVE` — designation
EXECUTION establishes active membership once **and** removes the unit from New Retail Current Supply.
`ACTIVE` carries `ACTIVE_UNRESOLVED`; the retirement path is `RETIREMENT_ELIGIBLE/PROPOSED/APPROVED →
(RETIREMENT_PENDING) → RETIRED → {RETURNED_TO_NEW_RETAIL | AWAITING_USED_CARS_RECEIPT →
USED_CARS_RECEIVED}`, plus `CANCELLED` and `CORRECTED` (a correction may be recorded from any
non-terminal state; prior history preserved). Legal transitions in `models.TRANSITIONS`. Active
membership (`ACTIVE`, `ACTIVE_UNRESOLVED`, and the four `RETIREMENT_*` in-fleet states) is what counts
as an actual Executive Demo unit for need/count-once.

## Supply direction (opposite of Service Loaner entry, symmetric at retirement)
Designation execution **removes** the Vehicle Unit from New Retail Current Supply (it is now a demo,
not sellable New inventory) and records an `ACTIVE_DEMO` reconciliation once. Return-to-New-Retail
**restores** Current Supply exactly once (`RETURNED_TO_NEW_RETAIL`; existing supply →
`ALREADY_RECONCILED`, no duplicate). A Used Cars handoff creates **no** New Retail supply. New Retail
Demand is never recomputed by any Executive Demo action — it is an input.

## Best Overall objective
`objective = W_BENEFIT·benefit − W_OPP_COST·opportunity_cost + W_FIT·portfolio_fit + preference_bonus`
with `W_BENEFIT=1.0, W_OPP_COST=1.0, W_FIT=2.0, W_PREFERENCE=1.5` (weights recorded in every plan). A
strong complete portfolio fit can outrank both the cheapest and the highest-benefit candidate;
eligibility is a hard pre-filter; already-active/committed/retired units and duplicates are excluded;
per-candidate tradeoffs and necessary sacrifices are always recorded (never an opaque composite).
See `adr/ADR-0018`.
