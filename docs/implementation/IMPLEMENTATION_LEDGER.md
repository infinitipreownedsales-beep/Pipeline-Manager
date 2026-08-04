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

## Phase 2 — Data, Identity, and Accepted Facts  (branch `elite-pipeline/phase-0`)

Control records: Phase 1 recorded approved; Phase 2 set active then complete.
BUG-CPO-002 kept open only as a later-domain implementation/regression risk.

Implemented a NEW `elite/data/` package + migration v2 (appended; v1 unchanged),
touching no legacy file:
- Source Registry, Source Contract/Schema Profile (shape+meaning only), Import Batch;
- Source Observation with raw preservation + separate normalization; distinct value
  sentinels (missing/blank/zero/false/na/unknown/invalid/unresolved/conflicting);
- Full/Partial snapshot classification (contract-driven; absence = scoped signal only);
- Vehicle Unit + Production Order identity (VIN-only unit identity; order-id-only order
  identity; pre-VIN→single-unit link; scope isolation; corrections preserve prior);
- Identity Evidence + resolution outcomes;
- Business Facts under source authority (fact-type + scope), append-preserving with
  correction/supersession/reversal; deterministic current-state projection + conflict;
- Reconciliation (one outcome per row; counts balance; absence signals);
- deterministic fixtures (21 source cases, 14 identity cases) + tests.

Evidence executed: platform harness **61/61** (26 Phase 1 + 35 Phase 2); legacy suite
**39/39**; migration v2 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 38 mandatory acceptance items pass
(PHASE2_COMPLETION.md).

Docs: PHASE2_COMPLETION, PHASE2_TRACEABILITY, PHASE2_DATA_MODEL, adr/ADR-0003;
updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note).

Result: **Phase 2 complete → HOLD FOR REVIEW.** Next: Phase 3 only after review.

## Phase 3 — Policy, Configuration, Effective Dating, and Calculation Versioning  (branch `elite-pipeline/phase-0`)

Control records: Phase 2 recorded approved; Phase 3 set active then complete. BUG-CPO-002
kept open only as a later New-Inventory implementation/regression risk.

Implemented a NEW `elite/policy/` package + migration v3 (appended; v1/v2 unchanged),
touching no legacy file:
- Policy Family + immutable, effective-dated Policy Version (DB triggers enforce
  value-immutability + no-delete; optimistic concurrency on lifecycle);
- taxonomy (8 categories, technical config kept distinct from business policy);
- scope model with declared allowed dimensions (unsupported dimensions rejected);
- lifecycle state machine (DRAFT→PROPOSED→UNDER_REVIEW→APPROVED→SCHEDULED→ACTIVE plus
  EXPIRED/SUPERSEDED/REVOKED/REJECTED/WITHDRAWN/CORRECTED) with legal-transition enforcement;
  approval never auto-activates a future version; activation refused before effective time;
- supersession/revocation/rejection/withdrawal + correction lineage (append-preserving);
- deterministic resolution (scenario-vs-official → active lifecycle → effective time → scope
  → specificity → approved precedence → conflict); newest-recorded never auto-wins; explicit
  CONFLICTING; declared-only fallback (never invents a value);
- typed financial assumptions (unit/denominator; zero valid; blank ≠ zero);
- Calculation Family/Version + Model/Identity-Rule/Comparison-Spec version foundations
  (registered-until-activated; behavior change requires a distinct version);
- reproducibility package pinning all refs + replay (identical output); current recompute
  does not rewrite a prior issued result;
- governed Scenario-override isolation (`scenario.override`; resolves only in scenario; never
  changes official; never activates by existing/sharing; audited);
- version activation/rollback history (append-preserving; rollback marks prior `rolled_back`);
- deterministic fixtures + 59 acceptance tests.

Evidence executed: platform harness **120/120** (26 P1 + 35 P2 + 59 P3); legacy suite
**39/39**; migration v3 rerun-safe; legacy application paths byte-unchanged vs
`legacy/inventory-tool` @ `3bf9162`. All 59 mandatory acceptance items pass
(PHASE3_COMPLETION.md).

Docs: PHASE3_COMPLETION, PHASE3_TRACEABILITY, PHASE3_POLICY_MODEL, adr/ADR-0004;
updated IMPLEMENTATION_CONTROL, RUN_INSTRUCTIONS, REQUIREMENT_INDEX (note).

Result: **Phase 3 complete → HOLD FOR REVIEW.** Next: Phase 4 only after review.
