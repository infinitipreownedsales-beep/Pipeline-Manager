# ADR-0010 — Commitment reconciliation

- **Status:** Accepted (Phase 5)
- **Owning segments:** 07 (Supply/pipeline)

## Decision
Every governed workflow transition produces or references a deterministic
`commitment_reconciliation_result` drawn from a fixed outcome set: `NO_SUPPLY_EFFECT`,
`COMMITMENT_CREATED`, `ALREADY_REPRESENTED`, `COMMITMENT_UPDATED`, `COMMITMENT_CANCELLED`,
`COMPLETED_TO_CURRENT`, `FAILED_NO_EFFECT`, `UNRESOLVED_IDENTITY`, `CONFLICTING`, `DUPLICATE_REPLAY`.
Supply effects are applied through the Phase 4 Supply/commitment records (Committed Supply on
approval, Current Supply on completion), so the Phase 4 qualifying-supply dedup — keyed on one
canonical unit/order identity — is the single source of count-once truth. Reconciliation records the
prior and new qualifying-supply counts so the effect is explicit and auditable.

## Why
BUG-CPO-002 was a double-counting / model-conflation defect. Making the *workflow* defer entirely to
the Phase 4 dedup for counting — rather than maintaining its own supply tally — guarantees that an
already-represented order yields ALREADY_REPRESENTED (no new unit), a replay yields DUPLICATE_REPLAY
(no effect), and a completion moves a unit to Current Supply exactly once.

## Consequences
- Reconciliation results are append-preserving and every transition carries one.
- Count-once and monotonicity hold end-to-end without duplicated supply accounting in the workflow.
- Unresolved identity blocks a confident commitment (UNRESOLVED_IDENTITY), never a silent count.
