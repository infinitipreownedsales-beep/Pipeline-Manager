# ADR-0027 — Cross-domain learning boundaries

- **Status:** Accepted (Phase 8)
- **Owning segments:** 12 (Learning)

## Decision
Learning records are domain-owned. A Learning Signal owned by one domain cannot mutate another domain's
behavior automatically: New Inventory forecast Error must not alter Service Loaner economics; a Service
Loaner resale outcome must not alter New Inventory Demand; an Executive Demo outcome must not redefine
Service Loaner rules. Cross-domain evidence may support a Calibration Proposal only when the
relationship is explicit and approved. No universal ranker or single global learning score is
introduced, and shared platform records never erase domain meaning.

## Why
The domains answer different business questions with different economics and identity rules. A universal
scorer or automatic cross-domain influence would recreate the model-conflation class of defects
(BUG-CPO-002) at the learning layer and couple independently-evolving domains. Domain ownership with an
explicit, approved exception path keeps learning meaningful and safe.

## Consequences
- `boundaries.assert_same_domain` rejects an unapproved cross-domain application (tests 51-53).
- Learning Signals, Errors, and Predictions all carry an owning domain; cross-domain influence is a
  deliberate, approved act, never an emergent side effect.
