# ADR-0033 — Exception + unresolved queues

- **Status:** Accepted (Phase 9)
- **Owning segments:** 11 (Governance), 10 (Views)

## Decision
Seventeen operational exception/unresolved queues (unresolved identity, conflicting/missing/conflicting
policy, stale recommendation, expired approval, failed execution, reconciliation conflict, audit failure,
missing observation, ambiguous pairing, conflicting learning signal, calibration validation regression,
scenario promotion awaiting review, authority conflict, Service Loaner alert, Executive Demo blocked
recommendation) each hold items that REFERENCE the authoritative source record. A resolution action routes
to the owning domain; closing a queue item never silently resolves the source; dismissal requires
authority + a reason. Queue history stays inspectable and priority is explainable.

## Why
Operational triage needs one place to see everything unresolved without duplicating — or accidentally
mutating — the domain truth. Keeping queue items as references, and forbidding a close from touching the
source, ensures the queue is a control view, not a competing state.

## Consequences
- A queue item references its source; closing preserves the source (tests 89-90).
- Dismissal is governed and requires a reason (test 91).
