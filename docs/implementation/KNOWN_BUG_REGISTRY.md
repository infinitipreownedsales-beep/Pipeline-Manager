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
- **Status:** **OPEN** until the future authoritative implementation proves the
  canonical contracts. Do **not** reopen the product decision. Do **not** redesign
  the Demand engine in Phase 1.
- **Regression fixture (future domain phase):** committing the recommended cycle set
  credits committed units exactly once and does not increase Need for the same
  unchanged window; continuous replenishment does not impersonate a commitment.
- **Release / phase:** future domain implementation (Segments 06/07); tracked as a
  regression risk until proven.

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
