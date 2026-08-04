# IMPLEMENTATION CONTROL — Elite Pipeline

Single source of control for the Elite Pipeline implementation. Governs which
specification is authoritative, what is preserved, and what work is permitted.

## Canonical specification
- **Path:** `docs/specification/ELITE_PIPELINE_Canonical_Master_Implementation_Specification_FINAL.docx`
- **Version:** 1.0.0  · **Architecture:** RC1
- **Disposition:** Accepted for Implementation Control (see `docs/specification/ELITE_PIPELINE_Final_Cross_Document_Audit.md`)
- **Segments:** 00–16 complete (17 segments + Table of Contents)
- **Requirement IDs:** 4,523 unique (4,532 occurrences) — verified against the accepted audit
- **SHA-256 (docx):** `18b76b9fd4f9113e4dfbc4250eea0e1cfa6c0c702581e58d6422f3ab33bf6e05`
- The specification is the sole product authority. Prior chats, remembered
  direction, and legacy behavior do **not** override it where they conflict.

## Protected legacy reference (Product A — do not alter)
- **Tag (immutable):** `legacy-inventory-tool-1.0` → commit `3bf9162`
- **Protected branch (frozen):** `legacy/inventory-tool` → `3bf9162`
- **Designated working branch retained at:** `claude/recompute-on-run-program-fy9lnf` → `3bf9162`
- **Artifact SHA-256:** `bc8972b4187a6178a50fb778ea79e8c3c291faf11c3975f74713ed7abfc81de3` (`Pipeline-Manager.html`)

## Clean restart branch (Phase 0 artifacts)
- **Branch:** `elite-pipeline/phase-0` (created from `3bf9162`; does not modify the legacy line)

## Current phase / work unit
- **Phase:** Phase 2 — Data, Identity, and Accepted Facts (**complete; HOLD FOR REVIEW**).
- **Phase 0:** approved and complete.
- **Phase 1:** **approved and complete.** New `elite/` platform package (Python
  stdlib + SQLite); environment/config, ids/clock, typed errors, repositories +
  durable persistence, migrations, authn, authz, append-only audit, governed
  actions, structured logging, deterministic test harness. Platform tests `26/26`.
  See `PHASE1_COMPLETION.md`, `PHASE1_TRACEABILITY.md`, `adr/`.
- **Phase 2 scope:** source registry, source contracts/schema profiles, import
  batches, source observations (raw + normalized), snapshot classification,
  vehicle-unit and production-order identity, identity evidence/resolution, business
  facts with correction/supersession/reversal, reconciliation, provenance, current-
  state projection, fixtures + tests. **No** Demand/Need/Supply/CPO/PPO/CTP/Loaner/
  Demo/Prediction/Learning; no broad UI; no `pm_*` migration.
- **Phase 2 result:** new `elite/data/` package + migration v2; source registry &
  contracts, import batches, source observations (raw + normalized), snapshot rules,
  vehicle-unit/production-order identity, evidence/resolution, append-preserving
  business facts with correction/supersession/reversal, reconciliation, provenance,
  current-state projection. Platform tests `61/61`; legacy `39/39`; no legacy file
  changed. See `PHASE2_COMPLETION.md`, `PHASE2_TRACEABILITY.md`, `PHASE2_DATA_MODEL.md`,
  `adr/ADR-0003`.
- **Approved next phase:** Phase 3 — **only after review**.

## Required commands (legacy launch / inspect)
```
# Build the single-file legacy app
python3 build/gen_pipeline_html.py            # -> Pipeline-Manager.html

# Launch: open Pipeline-Manager.html in any modern browser (offline, single file)
#   then paste inventory + speed-to-sell exports; state persists in localStorage

# Validation suite (must be actually executed to claim green)
python3 pipeline_manager/tests/test_engine.py
PYTHONPATH=. python3 pipeline_manager/tests/test_loaner_intel.py
```

## Environment setup
- Offline single-file HTML tool; no server, no network at runtime.
- Build requires Python 3 only. Tests require Python 3 (stdlib).
- Optional dev-only render check uses a preinstalled headless Chromium + Node.
- Env-specific config is read from `config.json` (git-ignored; **not** committed).

## Open blockers
- **None.** BUG-CPO-002 is **not** a specification blocker: the canonical spec
  already resolves it (Demand independent of supply method; CPO is a distinct
  supply workflow creating a discrete unit-level Commitment counted once in
  Future/Committed Supply; continuous replenishment must not impersonate a
  commitment; added qualifying Supply must not raise Need under unchanged Demand
  inputs and window). It is tracked as an **implementation defect / regression
  risk** until the future authoritative implementation proves those contracts. The
  Demand engine is **not** redesigned in Phase 1.

## Known defects
- See `KNOWN_BUG_REGISTRY.md`. Confirmed-fixed: CPO moving-goalposts / Need
  monotonicity (`3bf9162`). Open: BUG-CPO-002 (model conflation).

## Review owner
- Product owner / General Sales Manager (dealership). Implementation review pending.

## Status
**HOLD FOR REVIEW.** Phase 0 evidence complete. Do not proceed to Phase 1 until reviewed and approved.
