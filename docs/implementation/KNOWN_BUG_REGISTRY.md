# KNOWN BUG REGISTRY — Phase 0

Confirmed and material defects at legacy `3bf9162`. Entries follow the Phase 0
contract fields. New defects append here with a stable ID.

---

### BUG-CPO-001 — CPO Need "moving goalposts" (non-monotonic in Supply)
- **Symptoms:** Adding confirmed production units could *increase* the remaining
  September CPO Need for the same window.
- **Affected requirements:** Segment 06 (Demand/Need), Segment 07 (CPO window).
  Bind exact requirement IDs in Phase 1 (INV-DEMAND / CPO families).
- **Root cause (verified):** `computeArrivalWindows` measured the production→arrival
  lead from *all* inventory, recency-weighted by production date; newly-added
  inbound units dominated the lead, shifting the seasonal target.
- **Existing fix location:** `build/app_engine.js` `computeArrivalWindows`;
  mirror `pipeline_manager/engine.py` `compute_arrival_windows`. Commit `3bf9162`.
- **Status:** **FIXED / CONFIRMED.** Window now measured from arrived (on-lot) units only.
- **Regression fixture:** `test_auto_window_is_data_driven_and_continuous`,
  `test_projection_credits_residual_inbound` (both green); plus documented ladder
  `+0/+4/+8/+16 → 12/9/9/9` proving monotonicity.
- **Release / phase:** Fixed at `3bf9162` (preserved legacy). Re-verify under spec in Phase 1.

---

### BUG-CPO-002 — Continuous-replenishment vs. discrete-CPO-commitment model conflation
- **Symptoms:** After committing the exact units the engine recommended for a
  September CPO cycle, the engine still recommends ~13 more for the same cycle
  ("double-ordering the month").
- **Affected requirements:** Segment 06 (Demand/Need semantics), Segment 07
  (CPO/PPO/CTP production commitment). Bind IDs in Phase 1.
- **Root cause (verified by trace):** `need` is computed as replenishment-to-target
  at the arrival horizon. `projChain` runs current *and committed* inventory through
  a retail sell-down (`Math.max(held, proj[k-1] − rate·sm)`), so committed units are
  consumed by projected retail sales before the horizon. The engine has **no concept
  of "committed for this production cycle"** — no commitment attribution (e.g., order
  number / production cycle), so committed supply cannot be banked against the Need it
  fulfilled. Configs that sell faster than the production lead regenerate Need
  indefinitely.
- **Canonical resolution (specification — NOT an open product decision):**
  - Demand remains independent of supply method.
  - CPO is a distinct supply workflow.
  - An approved CPO action creates a discrete unit-level Commitment.
  - That Commitment affects Future/Committed Supply exactly once.
  - Continuous replenishment logic must not substitute for discrete commitment state.
  - Added qualifying Supply must not increase Need when Demand inputs and the
    evaluated window are unchanged.
- **Existing fix location:** none in the legacy engine. The legacy demand path
  conflates continuous replenishment with discrete commitment; the authoritative
  implementation must honor the canonical contracts above.
- **Classification:** **implementation defect / regression risk** (NOT a
  specification-owned model-decision blocker — the spec already resolves it).
- **Status:** **FIXED_END_TO_END (Phase 5) — retained permanently in the regression registry.**
  Phase 4 proves the canonical contracts under a synthetic CPO-like commitment
  (`elite/tests/test_phase4_bug_cpo_002.py`, green). Phase 5 implements the REAL governed CPO
  workflow and the dedicated 15-point end-to-end regression
  `elite/tests/test_phase5_bug_cpo_002_e2e.py` passes together with it: Phase 4 Demand issued;
  baseline Current/Future/Committed Supply + Need; one eligible Production Order proposed through CPO
  (no supply effect); authorized approval creates exactly one Commitment; Demand identical;
  qualifying Supply +exactly one; Need decreases/unchanged and never increases; replayed approval
  adds no unit; renamed acquisition path does not alter Demand; cancellation removes the prospective
  commitment while approval + cancellation history remain inspectable; a fresh workflow for the same
  order commits at most one active unit for that identity (monotone ladder confirms Need never
  rises). Both regressions are permanent; the product decision remains closed. Any future workflow
  (e.g. real allocation feeds) must keep both regressions green. Verified still green under migration
  v7 / Phase 7 (Executive Demo): designating a unit as a demo removes it from New Retail Current Supply
  and never recomputes Demand, and its versioned New Retail opportunity cost consumes the Phase 4 plan
  rather than recalculating Demand (`elite/tests/test_phase7_migration_cross.py` items 84-86; regression
  item 13 asserts Demand unchanged). Verified still green under migration v8 / Phase 8 (Learning): a
  New Inventory forecast Error/Signal cannot mutate any domain automatically, and no Calibration changes
  Demand behavior without an approved, activated version — Learning only proposes
  (`elite/tests/test_phase8_migration_cross.py` items 84-87; the 20-point learning-governance regression
  proves no operational change without approved Calibration). Verified still green under migration v9 /
  Phase 9 (Governance): the governed operational surface references authoritative domain output and never
  redefines Phase 4-8 domain mathematics — no Decision, approval, execution, promotion, or override
  rewrites an issued recommendation, Prediction, planning result, or Demand
  (`elite/tests/test_phase9_migration_cross.py` items 106-110; the governed-decision regression proves the
  recommendation stays historical through the whole Decision→execution loop). Verified still green under
  migration v10 / Phase 10 (Operator Experience and Presentation Layer): the operator UI is a faithful
  read-only window — it displays the stored Demand / Supply / Need / Economic Call / Execution Status and
  recomputes no domain math, contains no alternative Demand or Need formula, and every mutation routes
  through the governed Phase 1-9 services, so no screen, filter, presentation preference, or browser state
  can raise Need or rewrite an issued recommendation, Prediction, planning result, or Demand
  (`elite/tests/test_phase10_domains.py` test_23; `test_phase10_presentation_integrity_regression.py`;
  `test_phase10_workflows_cross.py` test_121). Migration v10 adds presentation-only tables with no
  immutability triggers and does not touch any Phase 4-9 domain record.
- **Regression fixture (Phase 4):** `elite/tests/test_phase4_bug_cpo_002.py` — baseline
  Demand + qualifying Supply + Need; add an approved synthetic CPO-like commitment only as
  Committed Supply; Demand unchanged; qualifying Supply increases by exactly the committed
  quantity; Need decreases or is unchanged and never increases; replaying the commitment does
  not double-count; changing the commitment label / acquisition path yields the same Demand.
- **Release / phase:** Phase 4 New Inventory foundation (Segments 05/06/07 planning
  semantics); tracked as a regression risk until the Phase 4 regression suite proves it and
  is reviewed.

---

### BUG-LOANER-003 — Obsolete standalone Loaner-Intelligence build superseded
- **Symptoms:** Duplicate loaner tooling (`Loaner-Intelligence.html` + `build/loaner_*`)
  parallel to the integrated Service Loaner module.
- **Affected requirements:** Segment 08 (Service Loaner). 
- **Root cause:** Pre-integration standalone tool retained after integration.
- **Existing fix location:** integrated module lives in `build/app_*`.
- **Status:** **OPEN — LOW (cleanup).** Classified OBSOLETE in REPOSITORY_AUDIT; do not
  delete in Phase 0 (preservation).
- **Regression fixture:** n/a (removal only).
- **Release / phase:** Phase 1+ cleanup after contract review.

---

## Deferred / documented behaviors (not defects, tracked for Phase 1 verification)
- C1 unit-pairing rule (Segment 08): related caps present; exact rule unverified.
- Service Loaner Last Checkout Mileage (Segment 08): partial; exact semantic unverified.
- Snapshot-absence rule (must not invent retirement facts): not present; honest absence.
