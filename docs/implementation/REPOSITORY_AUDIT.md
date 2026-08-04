# REPOSITORY AUDIT — Phase 0

Inventory of the repository at legacy commit `3bf9162`. Classification per the
Phase 0 kickoff contract. No assets were altered, moved, or deleted.

## Runtime entry points
| Entry point | Role |
|---|---|
| `Pipeline-Manager.html` | The legacy Inventory Tool — generated single-file offline app (open in browser). **The product.** |
| `build/gen_pipeline_html.py` | Build: inlines template + JS + data → `Pipeline-Manager.html`. |
| `pipeline_manager/` (Python) | Validation backbone mirroring the new-vehicle order engine; source of the test suite. |

## Storage & browser-local state
Official working state currently lives in **browser `localStorage`** (19 keys):
`pm_inv, pm_sales, pm_pre, pm_set, pm_inc, pm_fleet, pm_fleetimport, pm_sold,
pm_loaner_ledger, pm_loaners, pm_colormap, pm_loancfg, pm_suppress, pm_adds,
pm_demos, pm_trades, pm_collapsed, pm_dcollapsed, pm_print`.
- Finding: there is no server-side system of record; imports and settings persist
  only in the browser. The specification prohibits official truth living in
  browser-local storage — **recorded as a Phase-1 migration item, not changed in Phase 0.**

## Source files & contracts
| File | Contract |
|---|---|
| `build/app_template.html` | DOM + CSS shell; input controls; localStorage keys. |
| `build/app_engine.js` | L2 kernel primitives + L3 domain logic + orchestration (`runEngine`). |
| `build/app_render.js` | Views (render only). |
| `build/app_wiring.js` | Adapters: parse inputs, `getSettings`, persistence, importers. |
| `build/loaner_engine.js` | Loaner history analytics (`window.LoanerIntel`). |
| `pipeline_manager/engine.py`, `loaner_intel.py`, `keys.py`, … | Python mirror (order engine) + tests. |
| `pipeline_manager/roster_default.json`, `sample_data/` | Roster + sample imports/fixtures. |

## Tests & commands
- `pipeline_manager/tests/test_engine.py` (29) and `test_loaner_intel.py` (10) — **39 total, verified green in Phase 0.**
- Commands: see `IMPLEMENTATION_CONTROL.md`.

## Branches
| Branch / ref | Classification |
|---|---|
| `legacy-inventory-tool-1.0` (tag → 3bf9162) | Immutable legacy preservation. |
| `legacy/inventory-tool` (→ 3bf9162) | Protected legacy line (frozen). |
| `claude/recompute-on-run-program-fy9lnf` (→ 3bf9162) | Prior active line; retained at legacy point. |
| `elite-pipeline/phase-0` | Clean restart (Phase 0 artifacts only). |
| `claude/golf-app-audit-upload-nnuxut` | Unrelated project (see UNKNOWN assets). |

## Asset classification
| Asset | Class |
|---|---|
| `Pipeline-Manager.html` | **GENERATED / WORKING** (build output = the product). |
| `build/app_template.html`, `app_engine.js`, `app_render.js`, `app_wiring.js`, `loaner_engine.js`, `gen_pipeline_html.py` | **WORKING** (product source). |
| `pipeline_manager/**` (engine + tests + roster + sample_data) | **WORKING** (validation backbone / fixtures). |
| `ARCHITECTURE.md`, `AUDIT.md`, `README.md` | **WORKING** (docs). |
| `Loaner-Intelligence.html`, `build/loaner_render.js`, `build/loaner_template.html`, `build/gen_loaner_html.py` | **OBSOLETE / LEGACY-ONLY** (superseded standalone loaner build). |
| `caddie.html`, `src/CaddieOS.jsx`, `build/entry.jsx`, `build/gen-artifact.mjs`, `build/gen-html.mjs`, `artifact.html` | **UNKNOWN** (a separate "caddie/golf" project sharing the repo; not part of Elite Pipeline / Inventory Tool). |
| `config.json` (git-ignored) | **NONCOMPLIANT-adjacent** (env config; not tracked; no secrets in source). |

## Business rules → owning specification segment
Owning segment inferred from spec Heading-1 titles; requirement IDs to be bound in Phase 1.
| Business rule (legacy location) | Meaning | Owning segment | Phase-0 status |
|---|---|---|---|
| `loadInventory`, `loadSales`, `buildKey`/`normalizeCode`/`normalizeInt` (`app_engine.js`) | Ingestion + config identity/keying | **04** Data/Identity/Ingestion | known-correct; identity-normalization is a Phase-1 review target |
| `getSettings`, `incentive`, effective incentive table (`app_wiring.js`/`app_engine.js`) | Policy/config, incentives | **05** Policy/Config/Versioning | known-correct |
| `buildLines` → `need = orderTarget − proj − agedBrake` | New-inventory demand/need | **06** New Inventory Demand/Supply/Forecasting | partially defective — see BUG-CPO-002 |
| `computeArrivalWindows`, `resolveWindows`, `projChain`, `projectAtArrival` | CPO/PPO production window + projection | **07** Production Pipeline / CPO / PPO / CTP | goalposts FIXED (`3bf9162`); model conflation OPEN |
| `serviceLoanerEconomics`, `_writedownAmt`, `_retailAt`, `loanerFleet`, `_retireTiming`, `serviceSelection`, `_diversify`, `loanerOutcomes` | Service Loaner economics, retirement timing, forecast-vs-actual | **08** Service Loaner | known-correct (this session); L2/L3 separated |
| `computeDemoReturns`, `executiveDemos`, `demoDashboard` | Executive Demo | **09** Executive Demo | unverified against spec |
| `loanerOutcomes` (predicted vs actual) | Prediction/observation/error/learning signal | **10** Prediction/Decision/Observation/Learning | known-correct (this session) |
| render layer (`app_render.js`) | UX / interaction | **12** UX | reusable after contract review |
| `pipeline_manager/tests/**` | Verification/fixtures | **14** Verification/Fixtures/Gates | working |

## Secrets / environment-specific configuration
- No API keys, tokens, passwords, or private keys found in tracked source.
- Environment config uses `config.json` (git-ignored). Values are **not** copied
  into documentation or source control.
