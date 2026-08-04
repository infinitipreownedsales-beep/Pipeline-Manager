# IMPLEMENTATION LEDGER

Append-only log of implementation-control actions. Newest phase at the bottom.

## Phase 0 — Preservation and Audit  (branch `elite-pipeline/phase-0`, from `3bf9162`)

Actions taken:
1. Confirmed legacy stable point `3bf9162` (build + 39/39 tests + headless render all green; clean working tree).
2. Preserved legacy:
   - annotated tag `legacy-inventory-tool-1.0` → `3bf9162`;
   - protected branch `legacy/inventory-tool` → `3bf9162` (frozen);
   - recorded artifact SHA-256 `bc8972b4187a6178…` and reproducible build.
3. Created clean restart branch `elite-pipeline/phase-0` from `3bf9162` (legacy line unaltered).
4. Added canonical specification + audit + kickoff prompt under `docs/specification/`.
   - Spec SHA-256 `18b76b9f…`; verified structure: 17 segments (00–16) + ToC, 18 H1 / 1085 H2, 4,523 unique requirement IDs (matches accepted audit).
5. Generated machine-readable `docs/implementation/requirement_index.json` (4,523 IDs, segment + family attribution) and human-readable `REQUIREMENT_INDEX.md`.
6. Authored durable control artifacts: `IMPLEMENTATION_CONTROL.md`, `REPOSITORY_AUDIT.md`,
   `LEGACY_PRESERVATION.md`, `KNOWN_BUG_REGISTRY.md`, `IMPLEMENTATION_LEDGER.md`.
7. Captured known-correct behaviors and confirmed fixes (CPO goalposts / Need
   monotonicity FIXED; C1 pairing, Last Checkout Mileage, snapshot-absence recorded
   with honest Phase-0 status).
8. Verified no secrets in tracked source; env config isolated to git-ignored `config.json`.

Not done (out of Phase 0 scope, by contract): Phase 1 work, redesign, framework
selection, business-logic rewrite, new UI, requirement-ID→code binding, migration
of official truth out of browser-local storage.

Result: **Phase 0 evidence complete → HOLD FOR REVIEW.**
Approved next work unit: **Phase 1 (Preservation-safe implementation start), only after review.**

## Phase 1 — Platform Foundation  (branch `elite-pipeline/phase-0`)

Control-record corrections first: reclassified BUG-CPO-002 from "specification
blocker" to "implementation defect / regression risk" and recorded the canonical
resolution (Demand independent of supply method; CPO a distinct supply workflow;
approved CPO creates a discrete unit-level Commitment counted once; continuous
replenishment must not impersonate a commitment; added qualifying Supply must not
raise Need under unchanged Demand inputs and window). Demand engine NOT redesigned.

Implemented the smallest authoritative platform seed as a NEW `elite/` package
(Python stdlib + SQLite; ADR-0001/0002), touching no legacy file:
- environment identity (explicit; no default), validated config with safe startup
  failure, secret hygiene (env-only, redacted);
- stable IDs, controlled UTC clock + dealership presentation;
- typed errors with correlation IDs;
- repository contracts + durable SQLite persistence; tracked migrations;
  idempotency; optimistic concurrency;
- authentication (identity only) separate from authorization
  (Principal/Capability/Authority/Scope/effective grant), enforced below the UI;
- append-only Audit Events (DB-trigger enforced), distinct from Business/Actual
  facts; governed actions binding business write + audit atomically (no success
  without audit);
- structured logging distinct from audit; deterministic test harness + fixtures.

Evidence executed: platform harness **26/26**; legacy suite **39/39**; legacy
application paths byte-unchanged vs `legacy/inventory-tool` @ `3bf9162`. All 22
mandatory acceptance items pass (see PHASE1_COMPLETION.md).

Docs: PHASE1_COMPLETION.md, PHASE1_TRACEABILITY.md, RUN_INSTRUCTIONS.md,
adr/ADR-0001, adr/ADR-0002; updated IMPLEMENTATION_CONTROL.md and KNOWN_BUG_REGISTRY.md.

Result: **Phase 1 complete → HOLD FOR REVIEW.** Next: Phase 2 only after review.
