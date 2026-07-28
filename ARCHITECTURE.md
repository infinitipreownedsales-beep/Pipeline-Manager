# Architecture

Authoritative reference for the Pipeline-Manager tool. Describes the **current**
state of the codebase. Update this file as each migration phase completes.

The app is a single offline HTML file (`Pipeline-Manager.html`) built by
`build/gen_pipeline_html.py`, which inlines, in order:
`app_template.html` + `app_engine.js` + `app_render.js` + `app_wiring.js` +
`loaner_engine.js` (as `window.LoanerIntel` / `window.DEPR`), plus an embedded
10-year used-car history CSV and roster/sample data.

`pipeline_manager/` is a Python mirror of the **new-vehicle order engine** used as
the automated validation backbone (39 tests). It is **not** a full mirror — the
loaner financial logic is currently JS-only.

---

## Target layers

| Layer | Responsibility | Depends on |
|-------|----------------|-----------|
| **L0 Adapters** | Parse/normalize raw input (inventory, sales, DMS fleet export, used-sold export, incentives, color map, ledger). | — |
| **L1 Historical Analytics** | Resale history: `compsRange`, `age_curves`, `colorGroup`, `salesRate`. (`window.LoanerIntel`.) | L0 |
| **L2 Financial Kernel** | Domain-agnostic financial **primitives** only: projected resale, write-down, factory incentives, holding cost. Deterministic, side-effect free, no DOM, no globals, unit-testable, Python-portable. Never contains business rules. | L1 |
| **L3 Business Domains** | Each domain composes kernel primitives + its own rules. Business rules never migrate into the kernel. | L2, L4 |
| **L4 Decision Engines** | Generic algorithms — rank, optimize, compare, score, forecast — parameterized by a domain-supplied metric. Never contain business rules. | (pure) |
| **L5 Orchestration** | `runEngine` assembles the `res` object consumed by views. | L3 |
| **L6 Views** | Render prepared data only. No calculations, recommendations, timing, or business rules. | L5 |

---

## Current module ownership

- **L0 Adapters** — `app_engine.js`: `loadInventory`, `loadSales`. `app_wiring.js`:
  `importFleet`, `readSold`, `readFleet`, `readIncentives`, `readColorMap`, ledger
  (`readLedger`/`saveLedger`/`ledgerArray`), `getSettings`.
- **L1 Analytics** — `loaner_engine.js`: `compsRange`, `age_curves`, `colorGroup`,
  `colorGroupAnalytics`, `salesRate`, `predictor` *(legacy — see debt)*.
- **L2 Kernel (primitives, today)** — `_retailAt` (resale), `_writedownAmt`,
  `incentive`/`modelRebate` (entry-month aware), `_interpRet`, comp helpers
  (`_wmedComps`, `_wpctComps`).
- **L3 Domains (today)** —
  - **Service Loaner**: `serviceLoanerEconomics` (cost model + opportunity;
    composes L2 primitives — owns velocity/ICV-at-entry/recon), `_retireTiming`
    (the sole retirement-timing engine), `_fleetCostInfo`, `loanerFleet`,
    `serviceSelection`, `_diversify`, `acquisitionRecs`, `policyExplorer`,
    `loanerOutcomes`.
  - **Retail Ordering** (separate, mature): `buildLines`, `computeMetrics`,
    `computePositions`, `projectAtArrival`, `priority`, `resolveWindows`.
  - **Executive Demo** (partial): `computeDemoReturns`, `executiveDemos`.
- **L4 Decision Engines (today)** — `serviceSelection`/`_diversify` (ranking),
  `_retireTiming` (optimize-over-months), `loanerOutcomes` (scoring). *Not yet
  extracted into generic, domain-agnostic algorithms.*
- **L5 Orchestration** — `runEngine` (`app_engine.js`).
- **L6 Views** — `app_render.js`: `render` and section renderers
  (`serviceSelectionRender`, `fleetFlowRender`, `outcomesRender`, `executiveReport`,
  `loanerRender` *(legacy board — see debt)*, order/overstock/demo/seasonality
  sections).

---

## Data flow

```
raw text ─▶ L0 adapters ─▶ getSettings(s) + window.DEPR (L1)
                              │
                    runEngine(inv, sales, s, today)  (L5)
                              │  builds res:
                              ├─ res.selection      (Service Loaner: rank in-stock)
                              ├─ res.loanerFleetPlan (fleet + per-unit retire timing)
                              ├─ res.loanerOutcomes  (predicted vs actual)
                              ├─ res.acquisitionRecs (what to order)
                              ├─ res.lines / buildSeq (Retail Ordering)
                              └─ res.demo…           (Executive Demo)
                              │
                         render(res)  (L6)  ── reads res.* only
```

---

## Single sources of truth

| Calculation | Established SoT | Status |
|-------------|-----------------|--------|
| Projected resale | `_retailAt` (comps × continuous age curve × color premium) | **Partial** — legacy `deprResale`/`predictor` still feed the legacy loaner board. Convergence pending. |
| Write-down | `_writedownAmt` | ✅ Single. |
| Factory incentive | `incentive` (entry-month aware) | ✅ Single (legacy per-model fallback kept for simple-mode entry). |
| Retirement timing | `_retireTiming` | ✅ Single. Legacy `loanerTiming` removed (Phase 1); the legacy board now consumes `_retireTiming`. |
| Recommendation ranking | `serviceSelection` / `_diversify` | **Partial** — `acquisitionRecs` and legacy `allCandidates` scoring overlap. |
| Fleet flow / cadence | `loanerFleet` | ✅ Single. |
| Predicted-vs-actual | `loanerOutcomes` | ✅ Single. |

---

## Current business domains

- **Service Loaner** — built (hero workflow). Places units, times retirement,
  recommends acquisition, scores forecast against actuals.
- **Retail Ordering** — built, mature, mirrored in Python (39 tests).
- **Executive Demo** — partial (returns + report).
- **Wholesale / Used / CPO / CTP / Acquisition** — not yet distinct domains.

---

## Migration status

Target = one financial kernel of pure primitives; Service Loaner economics live in
the Service Loaner domain; generic decision engines; one loaner screen.

- **Phase 0 — ✅ complete.** Removed the dead "hero recommendation / optimization
  mode" subsystem (`serviceLoanerRecs`, `serviceRecReason`, `optimizeStrategy`,
  `deMoney`, `heroRecommendation`, `detailPanel`, `fbRow`/`fbRows`/`srcBadge`,
  `outMoney`) — unreferenced by any live render path.
- **Phase 1 — ✅ complete.** Established the L2/L3 boundary: `unitDifference` →
  `serviceLoanerEconomics` (L3, composes L2 primitives `_retailAt`/`_writedownAmt`/
  `incentive`); layer banners added. Deleted `loanerTiming`; `_retireTiming` is now
  the sole retirement-timing engine and the legacy board consumes it. All Service
  Loaner outputs verified byte-identical before/after.
- **Phase 2 — ✅ complete (no code change).** Evaluated extracting generic
  decision engines (`rankBy`/`optimizeMonth`). None met the extraction bar: the
  month-optimizer (`_retireTiming`) and rank-assignment (`serviceSelection`) each
  have a single consumer, and the three rankers use *different* metrics
  (`difference` vs `acquisitionRecs`' history score), so a shared ranker can't
  reduce duplication until the metric is unified — which changes outputs and is
  therefore **deferred into Phase 3**. The prior real duplicate (`optimizeStrategy`)
  was already removed in Phase 0. Extraction would have been a framework over
  single consumers, so it was correctly declined.
- **Phases 3–5 — pending.** (3) Unify the acquisition/ideal-to-order ranking metric
  onto the kernel and extract a generic ranker *at that point* (real 2nd consumer);
  delete the legacy loaner board (`loanerRender`); rewire `buildSequence` loaner
  intake. (4) Slim `allCandidates`; delete `loanerEconomics`/`deprResale`.
  (5) Migrate the depreciation explorer off `predictor`; delete `predictor`/`getComps`.

## Noted micro-duplicates (not decision logic; addressed opportunistically)

- Identical trim-head helpers: `_trimHead` (engine) and an inline `firstWord` in
  `acquisitionRecs`. Zero-risk to merge but outside Phase 2's decision-engine
  scope; fold into whichever phase next edits `acquisitionRecs` (Phase 3).
- Two different `median` implementations (`_fleetCostInfo.med`,
  `idealOrderRender.med`) — reconcile only when a phase already changes those
  outputs, since they compute differently.

## Known technical debt (live duplicates awaiting the phases above)

- Two resale paths: `_retailAt` (new) vs `deprResale`/`predictor` (legacy board).
- Multiple acquisition rankings: `serviceSelection`-derived vs `acquisitionRecs`
  vs legacy `buildSeq.fleetUnits`.
- Some math still executes in views (`unitStackInner` recomputes comps;
  `fleetFlowRender` does date math) — to move into L5 output.
- Standalone `Loaner-Intelligence.html` build (`loaner_render.js`,
  `loaner_template.html`, `gen_loaner_html.py`) is superseded by the integrated
  module.
