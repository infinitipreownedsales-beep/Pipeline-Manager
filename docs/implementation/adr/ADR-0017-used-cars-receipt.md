# ADR-0017 — Used Cars receipt

- **Status:** Accepted (Phase 6)
- **Owning segments:** 08 (Service Loaner), 11 (Governance/Audit)

## Decision
After a Service Loaner is retired, the unit enters `AWAITING_USED_CARS_RECEIPT`. Used Cars performs
exactly ONE simple confirmation action (`service_loaner.used_cars_receipt.confirm`). The system
automatically records the confirming Principal, confirmation date/time, Vehicle Unit, retirement
reference, store scope, correlation id, and Audit Event. No checklist and no extra mandatory fields
are required. The confirmation is idempotent (a repeat returns the existing receipt) and the receipt
is immutable and single per unit (enforced by `UNIQUE(service_loaner_unit_id)` + no-update/no-delete
triggers). Receipt is never inferred from retirement and cannot occur before it. A Used Cars receipt
creates NO New Retail Supply — an actual return-to-New-Retail is a separate path that restores Current
Supply exactly once.

## Why
The handoff to Used Cars is a lightweight operational acknowledgement, not a data-entry gate. Making it
a one-click, auto-stamped, idempotent, immutable confirmation matches the real dealership workflow
while preserving an auditable, non-duplicable record — and keeping it distinct from any New Retail
supply effect prevents a retired loaner from silently re-entering New Retail inventory.

## Consequences
- Repeat confirmations never create multiple receipts; the receipt history cannot be ordinarily
  altered or deleted.
- Return-to-retail and Used Cars handoff are separate reconciliation outcomes; one Vehicle Unit counts
  once across them.
