# ADR-0024 — Attribution as an evidence layer

- **Status:** Accepted (Phase 8)
- **Owning segments:** 12 (Learning)

## Decision
Attribution explains an Error as an evidence-based layer, never as asserted fact. Each Attribution
proposes a contributing factor in a defined category and accrues supporting AND contradicting evidence;
its status is derived from the recorded evidence (`SUPPORTED` with support and no contradiction,
`PARTIALLY_SUPPORTED` when mixed, `CONTRADICTED` when only contradiction, else `PROPOSED`). One outcome
may have multiple contributing factors; no weights/shares are stored, to avoid false precision.
Unrecorded customer intent and Dealer Trade attempts remain UNKNOWN; a stockout may support a
constrained-demand Attribution but never an exact missed-sales quantity. Human review preserves the
original automated proposal (a review row + a new human Attribution referencing the original).

## Why
Outcomes rarely have a single provable cause, and much of the relevant context (customer motivation,
un-attempted trades) is simply unrecorded. Presenting hypotheses as facts, or fabricating exact
counterfactual quantities, would corrupt the institutional memory. Distinguishing evidence from
hypothesis and keeping contradiction visible makes the explanation honest and auditable.

## Consequences
- Learning Signals build on Attribution + Error evidence, never on asserted causation.
- Human-reviewed conclusions never overwrite the automated proposal.
