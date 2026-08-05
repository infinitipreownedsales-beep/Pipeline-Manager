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
- **Status:** **OPEN — Phase 4 regression GREEN, kept open pending review.** The New
  Inventory foundation (Phase 4) proves the canonical contracts under a synthetic CPO-like
  commitment (Committed Supply only; the real CPO workflow is NOT implemented). The dedicated
  regression `elite/tests/test_phase4_bug_cpo_002.py` passes: Demand is independent of
  acquisition path; an approved commitment is credited to Committed Supply exactly once; added
  qualifying Supply never increases Need under unchanged Demand inputs and window (monotone
  non-increasing ladder). Kept OPEN as a risk until reviewed AND until the real Phase-5 CPO
  workflow is shown to preserve these contracts. Do **not** reopen the product decision.
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
