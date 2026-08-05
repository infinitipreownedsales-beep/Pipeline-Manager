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
- **Phase:** Phase 7 — Executive Demo Domain (**complete; HOLD FOR REVIEW**).
- **Phase 6:** **approved and complete.**
- **Phase 5:** **approved and complete.**
- **Phase 4:** **approved and complete.**
- **Phase 3:** **approved and complete.**
- **Phase 2:** **approved and complete.**
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
- **Phase 3 scope:** Policy Family + immutable/effective-dated Policy Version, taxonomy,
  scope, lifecycle (activation/scheduling/expiration/supersession/revocation/rejection/
  withdrawal/correction), deterministic resolution + precedence + conflict detection,
  declared-only fallback, typed financial assumptions, technical-config separation,
  Calculation Family/Version, Model/Identity-Rule/Comparison-Spec version foundations,
  reproducibility + replay, governed Scenario-override isolation, version activation/rollback
  history, migration v3, fixtures + tests. **No** domain calculation; **no** Demand/Need/
  forecasting/CPO/PPO/Dealer Trade/CTP/Service Loaner/Executive Demo/Prediction/Learning;
  no broad UI. Synthetic values only.
- **Phase 3 result:** new `elite/policy/` package + migration v3 (appended; v1/v2 unchanged),
  touching no legacy file. Platform tests `120/120` (26 P1 + 35 P2 + 59 P3); legacy `39/39`;
  migration v3 rerun-safe; legacy application paths byte-unchanged. All 59 mandatory acceptance
  items pass. See `PHASE3_COMPLETION.md`, `PHASE3_TRACEABILITY.md`, `PHASE3_POLICY_MODEL.md`,
  `adr/ADR-0004`.
- **Phase 4 scope:** authoritative New Inventory planning foundation, in spec order —
  Sellable Combination; Current / Future / Committed Supply; historical retail;
  availability reconstruction; Demand baseline (independent of acquisition/supply method);
  seasonality + trend; evidence hierarchy + lineage; month-by-month forecast; desired
  ending coverage (policy-resolved); Need; Excess; portfolio reconciliation; confidence +
  evidence explanation; first operational output slice. Migration v4 (appended). Proves
  Demand is calculated independently of supply and that qualifying Supply behaves
  monotonically (added qualifying Supply must not increase Need). Uses the Phase 1-3
  platform/fact/identity/policy/calculation-version/reproducibility foundations.
  **No** second Demand calculation inside any supply workflow; **no** Phase-5 production
  workflows, CPO/PPO/Dealer Trade/CTP/Service Loaner/Executive Demo, Learning, full
  Governance, or broad UX. Synthetic dealership-representative fixtures only.
- **Phase 4 result:** new `elite/newinv/` package + migration v4 (appended; v1-v3 unchanged),
  touching no legacy file. Sellable Combination + lineage; Current/Future/Committed Supply with
  count-once qualifying-supply dedup; historical retail; availability reconstruction; supply-blind
  Demand baseline (evidence hierarchy, bounded seasonality/trend, reproducibility+replay);
  month-by-month forecast with combination→model→portfolio reconciliation; policy-resolved desired
  ending coverage; deterministic month-aware Need/Excess (≥0, not both positive, monotone in
  qualifying supply); portfolio aggregation that never recomputes Demand; first operational output
  slice; 40 fixtures. Platform tests `185/185` (26 P1 + 35 P2 + 59 P3 + 65 P4); legacy `39/39`;
  migration v4 rerun-safe; legacy application paths byte-unchanged. All 63 acceptance items pass +
  the dedicated 10-point BUG-CPO-002 regression. See `PHASE4_COMPLETION.md`,
  `PHASE4_TRACEABILITY.md`, `PHASE4_DOMAIN_MODEL.md`, `PHASE4_REGISTRIES.md`, `adr/ADR-0005..0008`.
- **Phase 5 scope:** governed production + acquisition workflows that convert supply opportunities
  into proposed/approved/committed/executed/cancelled/superseded/failed supply actions —
  production-pipeline state; ETA + arrival-window interpretation; editability; model-year
  transition; Incoming Risk; CPO; PPO; Dealer Trade; CTP; sequential recomputation; commitment
  reconciliation; integrated forecast updates; execution/outcome capture foundations; focused
  operational workflow slices. Migration v5 (appended). All workflows **consume the authoritative
  Phase 4 Need contract** and define **no** separate Demand. Reuses Phase 1 authz/audit, Phase 3
  policy, and Phase 4 Demand/Supply/Need/Excess/forecast/commitment/reproducibility contracts
  without redefining them. **No** Service Loaner, Executive Demo, Prediction/Observation Pairing,
  Learning, completed Phase-9 Governance, full UX, operational hardening, or migration/cutover.
- **Phase 5 result:** new `elite/workflow/` package + migration v5 (appended; v1-v4 unchanged),
  touching no legacy file. Production-pipeline projection + ETA/editability/model-year transition +
  component-explained Incoming Risk; the common governed workflow lifecycle; CPO/PPO/Dealer Trade/CTP
  workflows (all consume Phase 4 Need, none compute Demand; discrete count-once commitments; CTP
  moves one future unit without a duplicate order); commitment reconciliation (10 outcomes);
  sequential recomputation; integrated forecast updates; operational workflow slices; 50 fixtures.
  Platform tests `266/266` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5); legacy `39/39`; migration v5
  rerun-safe; legacy application paths byte-unchanged. All 78 acceptance items pass + the 15-point
  end-to-end BUG-CPO-002 regression → **BUG-CPO-002 FIXED_END_TO_END**. See `PHASE5_COMPLETION.md`,
  `PHASE5_TRACEABILITY.md`, `PHASE5_DOMAIN_MODEL.md`, `PHASE5_REGISTRIES.md`, `adr/ADR-0009..0013`.
- **Phase 6 scope:** the complete **Service Loaner** domain **only** (Executive Demo is Phase 7 and
  is NOT built here) as an independent governed portfolio domain — authoritative active-fleet Full
  Snapshot contract + membership reconciliation by VIN; Service Loaner Unit + lifecycle; in-service-
  date authority; Last Checkout Mileage; zero-mile-rented monitoring; versioned Economic Call
  (separate from Execution Status; incremental exit timing, no sunk-cost reapplication); entry
  selection + fleet portfolio optimization; retirement / provisional retirement / return
  confirmation / final retirement; Used Cars handoff (one idempotent confirmation); return-to-retail
  reconciliation; scenario/policy exploration; resale/outcome foundations; operational output slices.
  Migration v6 (appended). Strict domain separation: Service Loaner is distinct from Executive Demo,
  New Retail Demand, generic acquisition ranking, production workflow, CPO/PPO, and Used Cars before
  confirmed handoff. All policy/assumptions/thresholds resolve through Phase 3; reuses Phase 1-5
  identity/facts/policy/supply/planning/commitment/workflow/governance/audit foundations. **No**
  Executive Demo, Prediction/Observation Pairing, Learning, completed Phase-9 Governance, full UX,
  operational hardening, or migration/cutover.
- **Phase 6 result:** new `elite/loaner/` package + migration v6 (appended; v1-v5 unchanged), touching
  no legacy file. Active-fleet Full Snapshot + membership reconciliation by VIN; Service Loaner Unit +
  governed lifecycle; in-service-date authority; Last Checkout Mileage; zero-mile-rented monitoring;
  versioned Economic Call separate from Execution Status; entry portfolio optimization; retirement /
  provisional / return / final; Used Cars idempotent immutable receipt; return-to-retail
  reconciliation; scenario exploration; resale foundations; output slices; 60 fixtures. Platform tests
  `345/345` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6); legacy `39/39`; migration v6 rerun-safe;
  legacy application paths byte-unchanged. All 89 acceptance items pass + the 14-point zero-mile-rented
  regression. See `PHASE6_COMPLETION.md`, `PHASE6_TRACEABILITY.md`, `PHASE6_DOMAIN_MODEL.md`,
  `PHASE6_REGISTRIES.md`, `adr/ADR-0014..0017`.
- **Phase 7 scope:** the complete **Executive Demo** domain as an independent governed portfolio
  domain — current portfolio + need determination; candidate eligibility + construction; **Best
  Overall** portfolio-selection (not cheapest/most-eligible); model preference (approved policy);
  versioned New Retail opportunity cost (consumes Phase 4 planning, never recalculates Demand);
  expected Executive Demo lifecycle; designation propose/approve/execute; active membership; versioned
  Economic Call (separate from Execution Status; incremental exit economics, no sunk-cost reapplied);
  retirement eligibility/propose/approve/execute; actual retirement; return-to-New-Retail
  reconciliation (restore Current Supply once); Used Cars handoff (idempotent, immutable; own record —
  NOT merged with Service Loaner); committed portfolio updates; scenario exploration; resale/outcome
  foundations; operational output slices. Migration v7 (appended). Strict domain separation: Executive
  Demo is distinct from Service Loaner, New Retail inventory, generic acquisition ranking, CPO/PPO,
  production pipeline, Service Loaner fleet need, and Used Cars before confirmed handoff — the two
  fleet domains are NOT merged into one shared engine. Reuses Phase 1-6 identity/facts/policy/planning/
  commitment/governance/audit/lifecycle-history/reconciliation foundations. **No** Prediction/
  Observation Pairing, Learning, completed Phase-9 Governance, full UX, operational hardening, or
  migration/cutover.
- **Phase 7 result:** new `elite/execdemo/` package + migration v7 (appended; v1-v6 unchanged), touching
  no legacy file. Executive Demo Unit + governed lifecycle (Vehicle Unit identity never replaced);
  portfolio need resolved before ranking (Service Loaner need excluded, New Retail Demand never
  recomputed); reasoned eligibility gate; candidate construction from accepted facts + New Retail
  planning refs; versioned New Retail opportunity cost consuming the Phase 4 plan (Need > Excess, never
  a separate Demand); **Best Overall** portfolio selection over the full objective with recorded
  tradeoffs + labeled sacrifices (not cheapest/most-eligible, no opaque score); model preference via
  Phase 3 only; expected lifecycle projection; versioned Economic Call separate from Execution Status
  (entry vs retirement, incremental, no sunk cost, `BLOCKED_NEW_RETAIL_RISK`); designation
  propose/approve/execute (execution establishes membership once and removes New Retail Current Supply);
  retirement propose/approve/execute; return-to-New-Retail restoring Current Supply exactly once; Used
  Cars idempotent immutable receipt as its **own** record (NOT merged with Service Loaner); corrections
  preserving history; scenario exploration; resale foundations; output slices; 60 fixtures. Platform
  tests `424/424` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 + 79 P7); legacy `39/39`; migration v7
  rerun-safe; legacy application paths byte-unchanged. All 90 acceptance items pass + the 14-point Best
  Overall regression. Executive Demo and Service Loaner remain **separate** bounded domains (no shared
  fleet engine). See `PHASE7_COMPLETION.md`, `PHASE7_TRACEABILITY.md`, `PHASE7_DOMAIN_MODEL.md`,
  `PHASE7_REGISTRIES.md`, `adr/ADR-0018..0021`.
- **Approved next phase:** Phase 8 — **only after review**.

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
**Phase 7 complete — HOLD FOR REVIEW.** Executive Demo Domain on `elite-pipeline/phase-0` (Phase 6
approved). New `elite/execdemo/` package + migration v7; platform tests `424/424`; legacy `39/39`; all
90 acceptance items + the 14-point Best Overall regression pass; legacy application paths byte-
unchanged. Phase 6 (Service Loaner) remains complete, approved, and a **separate** bounded domain —
Executive Demo is a distinct package and is NOT merged with Service Loaner (no shared fleet engine).
Legacy line preserved at `3bf9162`. **BUG-CPO-002 = FIXED_END_TO_END**, retained permanently in
regression coverage. Phase 8 not started.
