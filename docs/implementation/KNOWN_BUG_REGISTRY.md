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
- **Existing fix location:** none. Requires the two-stage model (Stage 1: discrete
  production reconciliation crediting committed units 1:1; Stage 2: forward retail
  projection on the residual). This is a **specification-owned business-model decision**,
  not a legacy patch.
- **Status:** **OPEN — MATERIAL (Phase 1 blocker).** Do not patch in Phase 0.
- **Regression fixture (required in Phase 1):** committing the recommended cycle set
  must drive that cycle's Need to ~0 for those configs; committed units credited 1:1;
  no re-recommendation of the same window.
- **Release / phase:** Target Phase 1 under Segments 06/07.

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
