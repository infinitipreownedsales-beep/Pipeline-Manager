# ADR-0053 — Single-operator pilot approval exception + Executive Demo disposition routes

## Status
Accepted (Phase 12 first-use workflow repair). No migration. No domain-logic change.

## Context
The controlled pilot begins with a **single real operator** (the sole user). Two first-use workflow
blockers were found by a route-level capability audit:

1. **Self-approval is blocked in the operator UI.** The Approvals screen hides the Approve button when the
   Decision maker equals the approver (`ui/views/queues.py`), so a sole operator cannot complete
   propose → approve → execute through the UI. Creating a second fake operator, or approving outside the UI,
   were both rejected as dishonest workarounds.
2. **Two Executive Demo disposition actions had no operator route.** Return-to-New-Retail and Used Cars
   receipt confirmation existed as authoritative Phase 7 services (`execdemo/retirement.py`) but were not
   reachable from the UI, so the Executive Demo lifecycle could not be completed by an operator.

## Decision
1. **Explicit, reversible single-operator pilot exception.** `App.single_operator_pilot` (default `False`,
   set from `ELITE_SINGLE_OPERATOR_PILOT` in `ui/serve.py`) gates a **clearly-labelled** self-approval path.
   When enabled:
   - the Approvals screen shows an *"Approve under single-operator pilot exception"* button with a
     *"separation of duties NOT satisfied"* badge — it never claims normal SoD was met;
   - the approval is recorded with `conditions.single_operator_pilot_exception = True` and
     `separation_of_duties = "NOT_SATISFIED_SINGLE_OPERATOR_PILOT"` (persisted on the existing
     `approval.conditions` JSON column — **no migration**), and is audited through the normal governed
     `decision.approve` path;
   - the Execution screen shows a persistent *"Approved under single-operator pilot exception"* badge.
   The exception is enforced at the **POST layer** too: without it, a self-proposed Decision returns HTTP 403.
   Setting `single_operator_pilot = False` (multi-user rollout) **removes the exception and re-enforces
   separation of duties** — a self-proposed Decision can no longer be self-approved.
2. **Two governed Executive Demo disposition routes** (`ui/views/domains.py`):
   `POST /executive-demo/{unit_id}/return-to-retail` → `retirement.return_to_new_retail`, and
   `POST /executive-demo/{unit_id}/used-cars` → `retirement.confirm_used_cars_receipt` (a single
   confirmation, no checklist). Both call the **existing authoritative Phase 7 services** — no direct table
   mutation — preserving below-UI authorization, store scope, idempotency, the Audit Event, correlation IDs,
   failure handling (a governed error renders a safe page), and reconciliation. The Executive Demo screen
   surfaces the state-appropriate confirmation for `RETIRED` and `AWAITING_USED_CARS_RECEIPT` units.

## Consequences
- The sole operator can complete propose → approve (under the visible exception) → execute → confirm
  disposition entirely in the UI, with the exception truthfully recorded and audited.
- Multi-user rollout is a config flip (`ELITE_SINGLE_OPERATOR_PILOT` unset) that restores enforced SoD; no
  data or schema change is required to move off the exception.
- Proven by `tests/test_phase12_single_operator_execdemo.py` (12-point regression).

## Not changed
No Phase 1–11 domain logic, no migration (schema stays at v12), and no auto-disposition change to
`retirement.execute`. The permanent operator database is untouched.
