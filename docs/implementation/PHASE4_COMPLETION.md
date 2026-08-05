# PHASE 4 COMPLETION PACKET — New Inventory Foundation

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/newinv/` (+ migration v4 in `elite/db.py`); no legacy file changed.

## Implemented (specification order)
Sellable Combination → Current / Future / Committed Supply → historical retail → availability
reconstruction → Demand baseline → seasonality + trend → evidence hierarchy + lineage →
month-by-month forecast → desired ending coverage → Need → Excess → portfolio reconciliation →
confidence + evidence explanation → first operational output slice. Built on the Phase 1-3
platform / fact / identity / policy / calculation-version / reproducibility foundations, with
migration v4 appended (v1-v3 unchanged), touching no legacy file. Synthetic dealership fixtures
only — no real incentives / allowances / write-downs / windows.

**Demand is calculated independently of acquisition or supply method** (the Demand contract
takes no supply input at all), and **qualifying Supply behaves monotonically** (added qualifying
Supply never increases Need under unchanged Demand inputs and window).

**Not built (guarded):** any second Demand calculation inside a supply workflow; Phase-5
production workflows, CPO / PPO / Dealer Trade / CTP / Service Loaner / Executive Demo,
Prediction pairing, Learning, full Governance, or broad UX.

## Acceptance evidence (63 mandatory items, all executed)
| # | Requirement | Test |
|---|---|---|
| 1 | Sellable Combination survives restart | `test_phase4_combination.test_01` |
| 2 | Exact combinations distinguish exterior + interior | `test_phase4_combination.test_02` |
| 3 | Drivetrain distinct where variable | `test_phase4_combination.test_03` |
| 4 | Standard trim content creates no artificial identity | `test_phase4_combination.test_04` |
| 5 | Combination correction preserves prior identity | `test_phase4_combination.test_05` |
| 6 | Cross-store combinations remain scoped | `test_phase4_combination.test_06` |
| 7 | Current Supply counts one Vehicle Unit once | `test_phase4_supply.test_07` |
| 8 | Sold / ineligible units excluded | `test_phase4_supply.test_08` |
| 9 | Unresolved identity does not silently count | `test_phase4_supply.test_09` |
| 10 | Future Supply counts distinct Production Orders | `test_phase4_supply.test_10` |
| 11 | Pre-VIN→VIN does not double-count | `test_phase4_supply.test_11` |
| 12 | Cancelled future orders excluded | `test_phase4_supply.test_12` |
| 13 | Proposed action is not Committed Supply | `test_phase4_supply.test_13` |
| 14 | Approved commitment contributes exactly once | `test_phase4_supply.test_14` |
| 15 | Cancelled commitment stops contributing prospectively | `test_phase4_supply.test_15` |
| 16 | Historical retail uses accepted facts only | `test_phase4_retail_availability.test_16` |
| 17 | Duplicate observations do not duplicate retail | `test_phase4_retail_availability.test_17` |
| 18 | Retail correction updates current use, keeps history | `test_phase4_retail_availability.test_18` |
| 19 | Retail reversal preserves history | `test_phase4_retail_availability.test_19` |
| 20 | Available-no-sales ≠ unavailable-no-sales | `test_phase4_retail_availability.test_20` |
| 21 | Partial snapshot invents no continuous availability | `test_phase4_retail_availability.test_21` |
| 22 | Stockout fabricates no exact lost sales | `test_phase4_retail_availability.test_22` |
| 23 | Availability gaps reduce confidence | `test_phase4_retail_availability.test_23` |
| 24 | Demand independently callable, no supply inputs | `test_phase4_demand.test_24` |
| 25 | Demand unchanged when only acquisition path changes | `test_phase4_demand.test_25` |
| 26 | Exact evidence outranks inherited | `test_phase4_demand.test_26` |
| 27 | Inherited evidence remains labeled | `test_phase4_demand.test_27` |
| 28 | Low sample size reduces confidence | `test_phase4_demand.test_28` |
| 29 | Unsupported lineage does not silently transfer | `test_phase4_demand.test_29` |
| 30 | Seasonality bounded and explainable | `test_phase4_demand.test_30` |
| 31 | Sparse history does not exaggerate seasonality | `test_phase4_demand.test_31` |
| 32 | Trend is traceable | `test_phase4_demand.test_32` |
| 33 | Monthly forecast reconciles to horizon total | `test_phase4_forecast_planning.test_33` |
| 34 | Combination totals reconcile to model | `test_phase4_forecast_planning.test_34` |
| 35 | Model totals reconcile to portfolio | `test_phase4_forecast_planning.test_35` |
| 36 | Missing coverage policy → unresolved | `test_phase4_forecast_planning.test_36` |
| 37 | Approved broad fallback resolves only when permitted | `test_phase4_forecast_planning.test_37` |
| 38 | More specific coverage overrides broader | `test_phase4_forecast_planning.test_38` |
| 39 | Conflicting coverage → conflict | `test_phase4_forecast_planning.test_39` |
| 40 | Need never negative | `test_phase4_forecast_planning.test_40_41_42` |
| 41 | Excess never negative | `test_phase4_forecast_planning.test_40_41_42` |
| 42 | Need and Excess not simultaneously positive | `test_phase4_forecast_planning.test_40_41_42` |
| 43 | Added qualifying Supply does not increase Need | `test_phase4_forecast_planning.test_43` |
| 44 | Removed qualifying Supply does not decrease Need | `test_phase4_forecast_planning.test_44` |
| 45 | Later-arriving Supply does not satisfy an earlier month | `test_phase4_forecast_planning.test_45` |
| 46 | Current/Future/Committed separately inspectable | `test_phase4_supply.test_46` |
| 47 | One physical/future unit is not counted twice | `test_phase4_supply.test_47` |
| 48 | Commitment updates the next calculation | `test_phase4_forecast_planning.test_48` |
| 49 | Supply-method change alone does not alter Demand | `test_phase4_forecast_planning.test_49` |
| 50 | Repeating the same package reproduces the result | `test_phase4_forecast_planning.test_50` |
| 51 | New accepted facts may produce a new current forecast | `test_phase4_forecast_planning.test_51` |
| 52 | New current forecast does not rewrite history | `test_phase4_forecast_planning.test_52` |
| 53 | Official and Scenario results isolated | `test_phase4_forecast_planning.test_53` |
| 54 | Output identifies facts/policies/version/confidence/uncertainty | `test_phase4_output_migration.test_54` |
| 55 | First operational slice uses real domain output | `test_phase4_output_migration.test_55` |
| 56 | Migration v4 survives restart | `test_phase4_output_migration.test_56` |
| 57 | Migration v4 rerun is safe | `test_phase4_output_migration.test_57` |
| 58 | Phase 1 tests remain green | `test_phase4_output_migration.test_58` |
| 59 | Phase 2 tests remain green | `test_phase4_output_migration.test_59` |
| 60 | Phase 3 tests remain green | `test_phase4_output_migration.test_60` |
| 61 | Legacy tests remain 39/39 green | `test_phase4_output_migration.test_61` (+ `test_legacy_guard`) |
| 62 | Legacy application paths unchanged | `test_phase4_output_migration.test_62` (+ `test_legacy_guard`) |
| 63 | No Phase-5 / Loaner / Demo / Pairing / Learning behavior | `test_phase4_output_migration.test_63` |

**Fixtures:** 40 dealership-representative scenarios (`newinv/fixtures.build_all_scenarios`,
`SCENARIO_NAMES`), completeness proven by `test_phase4_output_migration.test_64`.

**Platform harness:** `185/185 passed` (26 Phase 1 + 35 Phase 2 + 59 Phase 3 + 65 Phase 4).
**Legacy:** `39/39` (29 engine + 10 loaner).

## BUG-CPO-002 regression (dedicated, 10-point)
`elite/tests/test_phase4_bug_cpo_002.py` proves, with a synthetic CPO-like commitment standing
in as Committed Supply only (no CPO workflow implemented):
1. baseline Demand computed; 2. baseline qualifying Supply computed; 3. Need computed;
4. approved synthetic CPO-like commitment added only as Committed Supply (not current/future);
5. Demand unchanged; 6. qualifying Supply increases by exactly the committed quantity;
7. Need decreases or unchanged; 8. Need never increases; 9. replaying the same commitment does
not count twice; 10. changing the commitment label / acquisition path yields the same Demand.
A monotonicity ladder (`test_bug_cpo_002_ladder_is_monotone`) adds units one at a time and
confirms Need is monotone non-increasing.

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- BUG-CPO-002 stays **open** as a risk until reviewed; the Phase 4 regression proves the
  contracts under synthetic Committed Supply — the real CPO workflow (Phase 5) must preserve them.
- The Demand/plan calculations are deliberately the smallest correct deterministic model that
  proves the invariants (availability-adjusted rate + bounded seasonality/trend; roll-forward
  Need/Excess). Richer estimators are a later concern; none is introduced.

## Status
**HOLD FOR REVIEW.** Phase 5 not started.
