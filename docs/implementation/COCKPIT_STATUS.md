# Elite Pipeline — Operator Cockpit / Service Loaner status

Base (certified, unchanged): `3f28174`
This increment head: `2467ccc` on `elite-pipeline/real-demand-bridge`

## Fully operational (built + tested this session)
- **Service Loaner ECONOMIC Ideal Mix law** (`elite/loaner/ideal_mix.py`): highest-value
  feasible fleet from IN / HOLD / OUT / WAIT decisions — best-N optimization, never blind
  fill. Stops at the economically defensible count; the target shortfall becomes a
  **future stocking need**, never a forced bad placement. Fleet capped at target →
  stronger IN **displaces** the weakest HOLD (OUT+IN rotation), not blind growth.
- **Monthly placement requirement** (`elite/loaner/placement_settings.py`): temporary,
  month-scoped, **expires and is never inherited**. Forced placements are labelled
  `objective_driven` and chosen to minimise economic sacrifice — kept distinct from the
  economic optimum so learning is not contaminated.
- **Service Loaner cockpit** (`elite/loaner/loaner_cockpit.py`, `/service-loaner`):
  the three fleet counts never conflated — **Current** (authoritative), **Desired**
  (governed operator setting), **Ideal** (economic optimum) — plus the IN/HOLD/OUT
  ranking and future-stocking-need. Desired-fleet + placement requirement persist in the
  governed prefs store (no schema change).
- **Law E honesty**: with no per-unit ICV / Velocity / preowned-DTS economics loaded, the
  mix is reported **ECONOMICALLY UNDETERMINED** — the counts still show, but no ranking is
  fabricated.

## Certified New-Inventory engine — untouched
Schema still v12. No engine mathematics reopened. Certified board unchanged
(28 acquire / 26 combinations / 21 arrived excess / 2 incoming; QX65 8501 QBE/G = ACQUIRE 2;
QX60 8481 XKJ/K = ARRIVED EXCESS 3). UI-bridge regression still green.

## Not yet built (remaining cockpit scope from the productization brief)
These are UI/presentation build-outs; none require reopening certified math:
- Top trust strip (4-source freshness with day thresholds + Update-Data control).
- Home Pipeline Horizon (collapsible model→combination board as the landing screen).
- Ordering CPO (month + per-model allocation ceiling, ranked line workflow) and PPO
  (Firm/Deny simulated supply).
- Service Loaner: Active-Fleet ranked Retire-Now queue, Velocity retail-runway, Calculator
  sandbox (the **economic core and cockpit counts above are done**; the retirement queue and
  sandbox screens are pending, and both need the real ICV/Velocity/preowned inputs to rank).
- Demos user-first roster / call-up board; Wholesale; Dealer Trade Our/Their; CTP page;
  Data control room; dealer exterior/startup polish.

## What actually blocks a full Saturday workflow
1. **Real per-unit Service-Loaner economics are not loaded** (ICV trim-specific $, Velocity
   terms/caps, preowned DTS). Until Kyle imports them, the Ideal Mix ranking stays
   UNDETERMINED (by design — no fabrication). The counts, desired target and placement
   requirement all work today.
2. The remaining cockpit screens listed above are not yet built.
