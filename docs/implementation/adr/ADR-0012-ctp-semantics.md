# ADR-0012 — CTP (Change The Production) semantics

- **Status:** Accepted (Phase 5)
- **Owning segments:** 07 (Supply/pipeline)

## Decision
CTP is a governed modification of an EXISTING Production Order — it never creates a second order. A
CTP carries the original and proposed Sellable Combinations and respects editability: a proposal is
rejected up front unless the order is executably editable (editable / conditionally-editable; unknown
/ locked / past-cutoff / conflicting cannot execute). Approval records the change intent WITHOUT
moving supply — the original Future Supply remains authoritative (no double-count of original +
proposed). Accepted execution moves the one future unit from the original to the proposed
combination: the original projection is superseded (history preserved) and a new projection is added
under the proposed combination with the SAME order identity, so the unit counts once and BOTH
combinations recompute. CTP consumes Phase 4 Need and Excess, computes no separate Demand, and a
replayed accepted CTP does not apply twice (idempotent).

## Why
CTP re-associates an already-committed production slot rather than adding supply. Deferring the supply
move to accepted execution (with approval as intent only) is the smallest correct way to avoid
double-counting original and proposed combinations while preserving the order's history.

## Consequences
- Rejected/failed CTP leaves the original order unchanged.
- A CTP from an Excess combination to a Need combination recomputes both, moving one unit of supply.
- The change details and superseded/new projection references are preserved for audit.
