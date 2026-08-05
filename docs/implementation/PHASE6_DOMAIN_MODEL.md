# PHASE 6 SERVICE LOANER DOMAIN MODEL (migration v6)

New tables added by migration v6 `service_loaner` (appended; v1-v5 unchanged). Payloads are
JSON-in-SQLite behind repository methods (`loaner/store.py`). Units, membership history, economic
results, retirement events, Used Cars receipts, reconciliation results, monitoring alerts, and issued
outputs are append-preserving (DB triggers block deletes); the Used Cars receipt is additionally
immutable (no-update trigger + `UNIQUE(service_loaner_unit_id)`).

## Records
| Table | Purpose | Key invariants |
|---|---|---|
| `service_loaner_unit` | A Vehicle Unit's Service Loaner participation | SL Unit id never replaces Vehicle Unit id; membership_state (governed) separate from current_rental_state; no-delete |
| `service_loaner_membership_history` | Governed lifecycle transitions | append-only; each references reconciliation + audit; no-delete |
| `service_loaner_snapshot_reconciliation` | Per-VIN snapshot outcomes | MEMBER_CONFIRMED/ADDED, ABSENT_REVIEW/NO_CHANGE, INVALID_VIN_EXCLUDED, DUPLICATE_VIN, CONFLICTING_STATE |
| `service_loaner_operational_state` | Rental/availability per snapshot | rental change never changes membership |
| `service_loaner_in_service_date_resolution` | In-service-date authority | verified controls tenure; import date never substitutes; conflicts unresolved; corrections preserved |
| `service_loaner_checkout_mileage_fact` | Last Checkout Mileage | zero≠blank≠missing≠invalid; supersede preserves history; not the odometer |
| `service_loaner_monitoring_alert` | Zero-mile-rented alerts | approved prompt; cleared not deleted; history preserved; no-delete |
| `service_loaner_entry_candidate` | Entry candidates | eligibility + availability + NR opportunity cost (input) |
| `service_loaner_portfolio_plan` | Fleet portfolio plan | need resolved separately; explainable selection; sacrifices flagged; no-delete |
| `service_loaner_economic_result` | Versioned Economic Call | separate from execution; incremental exit economics; reproducibility-pinned; no-delete |
| `service_loaner_execution_status` | Execution Status | explains why a call can/can't be acted on; never rewrites the call |
| `service_loaner_retirement_eligibility` | Eligibility | eligibility ≠ retirement |
| `service_loaner_retirement_action` | Retirement Decision | proposed/approved/provisional/cancelled; approval ≠ return |
| `service_loaner_return_confirmation` | Actual return event | separate operational event |
| `service_loaner_retirement_event` | Final retirement | reconciles membership at the defined event; no-delete |
| `used_cars_receipt` | Used Cars receipt | one idempotent, immutable confirmation; auto Principal+timestamp; UNIQUE per unit; no-update/no-delete |
| `service_loaner_reconciliation_result` | Return-to-retail reconciliation | one Vehicle Unit once; 10 outcomes; no-delete |
| `service_loaner_scenario_result` | Isolated scenario exploration | identifies overrides; never changes official policy/fleet |
| `service_loaner_resale_reference` | Resale/outcome foundation | preserves refs for Phase 8 pairing |
| `service_loaner_issued_output` | Issued-output index | append-preserving; no-delete |

## Service Loaner lifecycle (governed)
`CANDIDATE → ENTRY_PROPOSED → ENTRY_APPROVED → (ENTRY_PENDING) → ACTIVE_AVAILABLE` (entry EXECUTION
establishes membership once), with `ACTIVE_RENTED / ACTIVE_UNRESOLVED`, retirement path
`RETIREMENT_ELIGIBLE/PROPOSED/APPROVED → PROVISIONAL_RETIREMENT → AWAITING_RETURN → RETURN_CONFIRMED →
RETIRED → AWAITING_USED_CARS_RECEIPT → USED_CARS_RECEIVED`, plus `RETURNED_TO_NEW_RETAIL`, `CANCELLED`,
`CORRECTED`. Legal transitions in `models.TRANSITIONS`; a retirement cancellation restores an
ACTIVE_* state (history preserved). Rental state is a separate operational fact and never changes
membership by itself.

## Snapshot → membership contract
The fleet file is ingested through Phase 2 (`src_loaner`, Full-Snapshot-capable; raw preserved). Only
a valid, compatible Full Snapshot supports absence reconciliation (absence → ABSENT_REVIEW signal,
never a removal/invented retirement); a Partial Snapshot absence → ABSENT_NO_CHANGE; an invalid Full
claim (`src_loaner_feed`, non-capable) validates as partial and cannot remove membership. Invalid/
unresolved VINs are excluded; duplicate VINs and conflicting operational states are explicit.

## Used Cars handoff + return-to-retail
Retirement completion queues the unit to AWAITING_USED_CARS_RECEIPT. The Used Cars receipt is a single
idempotent, immutable confirmation (auto-records the confirming Principal + timestamp + correlation +
audit; no checklist), cannot occur before retirement, and creates NO New Retail Supply. An actual
return-to-New-Retail (a distinct path) restores Current Supply exactly once through the Phase 4 store
(existing supply → ALREADY_RECONCILED, no duplication); historical membership + the retirement event
remain inspectable.
