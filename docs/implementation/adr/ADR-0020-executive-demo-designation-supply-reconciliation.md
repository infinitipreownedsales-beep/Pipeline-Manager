# ADR-0020 — Executive Demo designation / retirement supply reconciliation

- **Status:** Accepted (Phase 7)
- **Owning segments:** 09 (Executive Demo), 07 (New Inventory), 11 (Governance/Audit)

## Decision
Executive Demo membership is established and unwound through governed lifecycle transitions that
reconcile New Retail Current Supply atomically:

- **Designation.** Candidate → proposed → approved (committed portfolio state only, no supply effect)
  → **execute**. Execution establishes active membership once and, in the same governed transaction,
  removes the Vehicle Unit from New Retail Current Supply (`current_supply_projection.status =
  'superseded'`) and records an `ACTIVE_DEMO` reconciliation. Idempotent under
  `{unit}:designation.execute`.
- **Retirement.** Eligibility → propose → approve → **execute**. Actual retirement removes active
  membership only at the retirement event (`RETIRED`, reconciliation `RETIRED_AWAITING_DISPOSITION`),
  then disposes via return-to-New-Retail (restores Current Supply exactly once;
  `RETURNED_TO_NEW_RETAIL`, or `ALREADY_RECONCILED` if supply already present) or Used Cars handoff
  (`AWAITING_USED_CARS_RECEIPT → USED_CARS_RECEIVED`; creates no New Retail supply).

Each transition writes a membership-history row + Audit Event atomically, uses optimistic concurrency
(version guard), and is idempotent. One Vehicle Unit counts once across the whole lifecycle.

## Why
A designated demo is no longer sellable New inventory, so leaving it in Current Supply would
double-count it against New Retail Need. Removing it at execution (not at proposal or approval) matches
the point where the commitment is real, and restoring it exactly once at return keeps the supply ledger
conserved. Binding the supply effect, membership change, history, and audit in one transaction makes the
reconciliation all-or-nothing.

## Consequences
- Designation execution is the single point that changes membership and supply; approval alone never
  touches supply (`test_phase7_economics_designation_retirement` items 50, 51).
- Replayed execution removes supply at most once; return restores at most once
  (items 52, 58, 59).
- Supply direction is the mirror image of Service Loaner entry, but the two domains remain separate
  (ADR-0021).
