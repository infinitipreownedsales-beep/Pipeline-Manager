# PHASE 6 REGISTRIES — Service Loaner

Living registries for the Phase 6 Service Loaner domain. Runtime records live in the authoritative
SQLite store (migration v6); this document indexes the contracts.

## Service Loaner source-contract registry
| Source | Profile | Snapshot-capable | Authoritative fact | Use |
|---|---|---|---|---|
| `src_loaner` | `prof_loaner_v1` (vin, rental_status, in_service_date, checkout_mileage) | yes | `loaner_present` | authoritative Full Snapshot; supports absence reconciliation |
| `src_loaner_feed` | `prof_loaner_feed_v1` | no | — | non-authoritative; a full claim validates as partial (cannot remove membership) |

Raw source values are preserved through Phase 2 (`import_batch` + `source_observation`). Membership
reconciles by accepted VIN into `service_loaner_snapshot_reconciliation`.

## Service Loaner lifecycle registry
Governed membership states (see `PHASE6_DOMAIN_MODEL.md` for the full transition map). Entry APPROVAL
does not establish membership; entry EXECUTION does (once). Rental state is a separate operational
fact. Retirement flows through provisional → return-confirmed → retired → used-cars-receipt, with an
alternative return-to-New-Retail path.

## Economic Call registry
Calculation Version `service_loaner_economic` (1.0.0). Decision points: `placement` and `exit`; exit
uses INCREMENTAL future economics only (no sunk placement cost). Each result carries alternatives
(each with its own value + basis — never one opaque score), the chosen economic call, assumptions,
uncertainty, Policy Versions, Calculation Version, fact refs, and a reproducibility package.
Unsupported inputs → unresolved / lower-confidence. The call is never rewritten because execution is
blocked.

## Execution Status registry
Separate from the Economic Call: `READY`, `BLOCKED_RENTED`, `BLOCKED_RETURN_NOT_CONFIRMED`,
`BLOCKED_POLICY`, `BLOCKED_IDENTITY`, `BLOCKED_DATA`, `BLOCKED_OPERATIONAL`, `AWAITING_APPROVAL`,
`APPROVED_NOT_EXECUTED`, `IN_EXECUTION`, `COMPLETED`, `FAILED`, `UNRESOLVED`. Explains why the
financially strongest call can or cannot be acted on now; operational infeasibility blocks execution
but never rewrites the call.

## Monitoring-rule registry
`zero_mile_rented` — when a unit is presently rented, its accepted Last Checkout Mileage is an explicit
zero, and elapsed time since the authoritative in-service date exceeds a configurable, effective-dated
threshold, an alert is raised with the prompt: *"Where is this customer's vehicle, and let's check the
miles on the loaner?"*. Evaluated on the current accepted snapshot only (no rental-history
reconstruction); idempotent; cleared when no longer rented or when checkout mileage changes from zero;
prior alerts preserved. Blank/missing/invalid mileage never trigger it; no location or actual mileage
is invented.

## Portfolio-plan registry
`service_loaner_portfolio_plan` — fleet NEED (required − current active) is resolved separately from
candidate ranking; selection is explainable (eligibility + availability + New-Retail opportunity cost
as an INPUT), lowest opportunity cost first, never one generic acquisition score; necessary sacrifices
are flagged explicitly. Approved entries update committed fleet state; the next plan uses it; the same
unit is never selected twice; already-active/approved/retired/committed units are excluded.

## Used Cars handoff contract
After retirement the unit is AWAITING_USED_CARS_RECEIPT. Used Cars performs ONE simple confirmation
(`service_loaner.used_cars_receipt.confirm`). The system auto-records the confirming Principal,
timestamp, Vehicle Unit, retirement reference, store scope, correlation id, and Audit Event. No
checklist or extra mandatory fields. The confirmation is idempotent (a repeat returns the existing
receipt; `UNIQUE(service_loaner_unit_id)` + immutability trigger enforce single, unchangeable receipt).
Receipt is never inferred from retirement and cannot occur before it; receipt history is preserved.

## Return-to-retail reconciliation contract
Outcomes: `REMAINS_ACTIVE`, `PROVISIONAL_ONLY`, `RETURN_CONFIRMED`, `RETIRED_AWAITING_HANDOFF`,
`USED_CARS_RECEIVED`, `RETURNED_TO_NEW_RETAIL`, `ALREADY_RECONCILED`, `UNRESOLVED_IDENTITY`,
`CONFLICTING`, `FAILED_NO_EFFECT`. One Vehicle Unit counts once; membership contribution stops at the
correct actual event; New Retail Current Supply is restored only under an allowed actual
return-to-retail event (once; existing supply → ALREADY_RECONCILED); a Used Cars receipt creates no
New Retail Supply; historical Service Loaner membership remains inspectable.
