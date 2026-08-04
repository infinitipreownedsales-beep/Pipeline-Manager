# ADR-0003 — Data, Identity, and Accepted-Facts model

- **Status:** Accepted (Phase 2)
- **Owning segments:** 03 (Domain model), 04 (Data/identity/ingestion), 11 (Governance)

## Decisions
1. **Raw preservation + separate normalization.** Every Source Observation stores
   `raw_values` verbatim and `normalized_values` alongside. Distinct value semantics
   (missing / blank / zero / false / N/A / unknown / invalid / unresolved /
   conflicting) are kept as distinct sentinels (`normalize.Special`) that never
   collapse — encoded so `0`/`False` are never confused with blank/missing.
2. **Observation ≠ Fact.** Upload and parse never create Business Facts. Only an
   accepted observation under valid **source authority** (fact-type + scope specific)
   produces a Business Fact.
3. **VIN-only unit identity.** A Vehicle Unit's identity is established only by a
   valid, accepted VIN, scoped to a store. Stock numbers, configuration similarity,
   and source row ids never establish physical-unit identity; scope prevents
   cross-store merging. Production Orders are distinguished by manufacturer order id,
   never configuration; a pre-VIN order may later link to exactly one canonical unit.
4. **Append-preserving facts.** Corrections, supersessions, and reversals create new
   records with explicit relationships; the original is never overwritten or deleted
   (DB trigger blocks deletes). Current-state projection deterministically selects the
   applicable current fact; multiple conflicting authorities yield an explicit
   conflict unless an approved precedence rule resolves it.
5. **Contract-driven snapshots.** Full-Snapshot status requires active-contract
   support; it is never inferred from row count. Full-Snapshot absence yields only a
   scoped reconciliation signal — never a removal or an invented lifecycle fact.
   Partial-Snapshot absence has no removal effect.
6. **Every row reconciles.** Each source row receives exactly one reconciliation
   outcome; the outcome counts balance to the Import Batch row total.

## Why
These are the binding Phase 2 invariants. Modeling them explicitly (distinct
sentinels, source authority, VIN-only identity, append-preserving history,
contract-driven snapshots) is the smallest correct way to guarantee trustworthy
source/identity handling before any recommendation is built.

## Consequences
- Storage is JSON-in-SQLite behind repository methods (replaceable).
- No domain business rule is implied by any of these records.
