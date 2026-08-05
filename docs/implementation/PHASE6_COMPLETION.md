# PHASE 6 COMPLETION PACKET — Service Loaner Domain

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/loaner/` (+ migration v6 in `elite/db.py`); no legacy file changed.
- **Scope:** Service Loaner **only**. Executive Demo is **not** built (deferred to Phase 7).

## Implemented
The complete Service Loaner bounded domain: authoritative active-fleet Full Snapshot contract +
membership reconciliation by VIN (via Phase 2 ingestion, raw preserved); Service Loaner Unit +
lifecycle (Vehicle Unit identity never replaced); in-service-date authority; Last Checkout Mileage
(distinct zero/blank/missing/invalid); zero-mile-rented monitoring; versioned Economic Call (separate
from Execution Status; incremental exit economics, no sunk-cost reapplication); entry selection +
fleet portfolio optimization; retirement / provisional retirement / return confirmation / final
retirement; Used Cars handoff (one idempotent, immutable confirmation); return-to-retail
reconciliation (restores Current Supply once; receipt creates none); scenario/policy exploration;
resale/outcome foundations; operational output slices. Migration v6 appended (v1-v5 unchanged),
touching no legacy file. All policies/assumptions/thresholds resolve through Phase 3; synthetic values
only.

Strict domain separation: Service Loaner is distinct from Executive Demo, New Retail Demand, generic
acquisition ranking, production workflow, CPO/PPO, and Used Cars inventory before confirmed handoff.

**Not built (guarded, item 89):** Executive Demo, Prediction/Observation Pairing, Learning, completed
Phase-9 Governance, broad Phase-10 UX, operational hardening, migration/cutover.

## Acceptance evidence (89 mandatory items, all executed)
| # | Requirement | Test |
|---|---|---|
| 1 | Service Loaner Unit survives restart | `test_phase6_snapshot_membership.test_01` |
| 2 | Vehicle Unit identity authoritative | `test_phase6_snapshot_membership.test_02_03` |
| 3 | SL Unit id does not replace Vehicle Unit id | `test_phase6_snapshot_membership.test_02_03` |
| 4 | Valid Full Snapshot reconciles by VIN | `test_phase6_snapshot_membership.test_04` |
| 5 | Partial Snapshot absence: no removal | `test_phase6_snapshot_membership.test_05` |
| 6 | Invalid Full Snapshot claim cannot remove | `test_phase6_snapshot_membership.test_06` |
| 7 | Full Snapshot absence → review, not retirement | `test_phase6_snapshot_membership.test_07` |
| 8 | Invalid/unresolved VIN not silently entered | `test_phase6_snapshot_membership.test_08` |
| 9 | Duplicate VIN explicit | `test_phase6_snapshot_membership.test_09` |
| 10 | Conflicting rental status explicit | `test_phase6_snapshot_membership.test_10` |
| 11 | Entry approval does not establish membership | `test_phase6_lifecycle_dating_mileage.test_11` |
| 12 | Entry execution establishes membership once | `test_phase6_lifecycle_dating_mileage.test_12` |
| 13 | Replayed entry execution: no duplicate | `test_phase6_lifecycle_dating_mileage.test_13` |
| 14 | Rental state separate from membership | `test_phase6_lifecycle_dating_mileage.test_14` |
| 15 | Verified in-service date controls tenure | `test_phase6_lifecycle_dating_mileage.test_15` |
| 16 | Import date does not substitute | `test_phase6_lifecycle_dating_mileage.test_16` |
| 17 | Conflicting in-service dates → unresolved | `test_phase6_lifecycle_dating_mileage.test_17` |
| 18 | In-service correction preserves history | `test_phase6_lifecycle_dating_mileage.test_18` |
| 19 | Explicit zero checkout mileage stays zero | `test_phase6_lifecycle_dating_mileage.test_19_20_21` |
| 20 | Blank distinct from zero | `test_phase6_lifecycle_dating_mileage.test_19_20_21` |
| 21 | Missing distinct from zero | `test_phase6_lifecycle_dating_mileage.test_19_20_21` |
| 22 | Invalid mileage not authoritative | `test_phase6_lifecycle_dating_mileage.test_22` |
| 23 | Checkout ≠ odometer; supersede preserves | `test_phase6_lifecycle_dating_mileage.test_23` |
| 24 | Rented+zero+elapsed → review alert | `test_phase6_monitoring.test_24` |
| 25 | Rented+zero before threshold → no alert | `test_phase6_monitoring.test_25` |
| 26 | Rented+nonzero → no alert | `test_phase6_monitoring.test_26` |
| 27 | No longer rented clears alert | `test_phase6_monitoring.test_27` |
| 28 | Prior alert history preserved | `test_phase6_monitoring.test_28` |
| 29 | No invented customer-vehicle location | `test_phase6_monitoring.test_29_30` |
| 30 | No invented actual mileage | `test_phase6_monitoring.test_29_30` |
| 31 | Economic Call resolves through Policy Versions | `test_phase6_economics_portfolio.test_31` |
| 32 | Missing required economic policy → unresolved | `test_phase6_economics_portfolio.test_32` |
| 33 | Exact policy overrides broad | `test_phase6_economics_portfolio.test_33` |
| 34 | Conflicting policy → conflict | `test_phase6_economics_portfolio.test_34` |
| 35 | Exit timing uses incremental future economics | `test_phase6_economics_portfolio.test_35` |
| 36 | Sunk placement cost not reapplied | `test_phase6_economics_portfolio.test_36` |
| 37 | Economic Call unchanged when execution blocked | `test_phase6_economics_portfolio.test_37` |
| 38 | Execution Status can block preferred call | `test_phase6_economics_portfolio.test_38` |
| 39 | Economic result preserves references | `test_phase6_economics_portfolio.test_39` |
| 40 | Fleet need resolved independently of ranking | `test_phase6_economics_portfolio.test_40` |
| 41 | Portfolio entry selection updates committed state | `test_phase6_economics_portfolio.test_41_42_43_44` |
| 42 | Next recommendation uses updated state | `test_phase6_economics_portfolio.test_41_42_43_44` |
| 43 | Same candidate not selected twice | `test_phase6_economics_portfolio.test_41_42_43_44` |
| 44 | Already-active candidate not recommended | `test_phase6_economics_portfolio.test_41_42_43_44` |
| 45 | Placement does not change New Retail Demand | `test_phase6_economics_portfolio.test_45_46` |
| 46 | New-Retail opportunity cost is an input | `test_phase6_economics_portfolio.test_45_46` |
| 47 | Eligibility distinct from retirement | `test_phase6_retirement_handoff.test_47` |
| 48 | Retirement approval distinct from return | `test_phase6_retirement_handoff.test_48` |
| 49 | Rented provisional remains active/rented | `test_phase6_retirement_handoff.test_49` |
| 50 | Provisional prevents duplicate recommendation | `test_phase6_retirement_handoff.test_50` |
| 51 | Return confirmation is a separate event | `test_phase6_retirement_handoff.test_51` |
| 52 | Final retirement changes membership | `test_phase6_retirement_handoff.test_52` |
| 53 | Cancellation preserves history, restores state | `test_phase6_retirement_handoff.test_53` |
| 54 | Corrected retirement preserves prior | `test_phase6_retirement_handoff.test_54` |
| 55 | Retired → awaiting-used-cars-receipt | `test_phase6_retirement_handoff.test_55` |
| 56 | Receipt one confirmation action only | `test_phase6_retirement_handoff.test_56_58` |
| 57 | Receipt auto-records date/time + Principal | `test_phase6_retirement_handoff.test_57` |
| 58 | Receipt: no checklist/mandatory fields | `test_phase6_retirement_handoff.test_56_58` |
| 59 | Duplicate receipt idempotent | `test_phase6_retirement_handoff.test_59` |
| 60 | Receipt cannot occur before retirement | `test_phase6_retirement_handoff.test_60` |
| 61 | Retirement does not imply receipt | `test_phase6_retirement_handoff.test_61` |
| 62 | Used Cars receipt creates no New Retail Supply | `test_phase6_retirement_handoff.test_62` |
| 63 | Return-to-New-Retail restores supply once | `test_phase6_retirement_handoff.test_63_64` |
| 64 | Existing supply prevents duplicate restoration | `test_phase6_retirement_handoff.test_63_64` |
| 65 | Return-to-retail preserves historical membership | `test_phase6_retirement_handoff.test_65` |
| 66 | Economic Call + Execution Status separate | `test_phase6_economics_portfolio.test_66` |
| 67 | Scenario does not change official policy | `test_phase6_scenario_governance.test_67_68` |
| 68 | Scenario does not change official fleet state | `test_phase6_scenario_governance.test_67_68` |
| 69 | Shared Scenario does not imply approval | `test_phase6_scenario_governance.test_69_70` |
| 70 | Scenario output identifies overrides | `test_phase6_scenario_governance.test_69_70` |
| 71 | Proposal/approval/exec/return/complete/receipt authorities separate | `test_phase6_scenario_governance.test_71` |
| 72 | Authorization enforced below the UI | `test_phase6_scenario_governance.test_72` |
| 73 | Scope mismatch rejected | `test_phase6_scenario_governance.test_73` |
| 74 | Revoked authority rejected | `test_phase6_scenario_governance.test_74` |
| 75 | Stale transition rejected | `test_phase6_scenario_governance.test_75` |
| 76 | Idempotent retry: no duplicate effect | `test_phase6_scenario_governance.test_76` |
| 77 | Required Audit Event written atomically | `test_phase6_scenario_governance.test_77` |
| 78 | Audit failure blocks unsafe success | `test_phase6_scenario_governance.test_78` |
| 79 | Output slices use real domain records | `test_phase6_scenario_governance.test_79` |
| 80 | Migration v6 survives restart | `test_phase6_migration_cross.test_80` |
| 81 | Migration v6 rerun safe | `test_phase6_migration_cross.test_81` |
| 82 | Phase 1 tests remain green | `test_phase6_migration_cross.test_82` |
| 83 | Phase 2 tests remain green | `test_phase6_migration_cross.test_83` |
| 84 | Phase 3 tests remain green | `test_phase6_migration_cross.test_84` |
| 85 | Phase 4 tests remain green | `test_phase6_migration_cross.test_85` |
| 86 | Phase 5 tests remain green | `test_phase6_migration_cross.test_86` |
| 87 | Legacy tests remain 39/39 green | `test_phase6_migration_cross.test_87` (+ `test_legacy_guard`) |
| 88 | Legacy application paths unchanged | `test_phase6_migration_cross.test_88` (+ `test_legacy_guard`) |
| 89 | No Executive Demo / Pairing / Learning / UX | `test_phase6_migration_cross.test_89` |

**Fixtures:** 60 dealership-representative scenarios (`loaner/fixtures.build_all_scenarios`,
`SCENARIO_NAMES`), completeness proven by `test_phase6_migration_cross.test_90`.

**Platform harness:** `345/345 passed` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6).
**Legacy:** `39/39` (29 engine + 10 loaner).

## Dedicated zero-mile-rented regression (14-point)
`elite/tests/test_phase6_monitoring.TestZeroMileRegression` proves: authoritative in-service date
known; current snapshot shows rented; accepted Last Checkout Mileage == 0; elapsed exceeds the active
review threshold; alert created with the approved question ("Where is this customer's vehicle, and
let's check the miles on the loaner?"); no rental-history table required; repeated evaluation
idempotent; a later nonzero checkout mileage clears the active alert; prior alert remains historical;
a later not-rented snapshot clears the alert; blank/missing/invalid mileage never trigger the rule; no
customer-vehicle location or actual loaner mileage is invented.

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- The Economic Call uses caller-supplied resolved alternatives (synthetic); wiring real market/residual
  policy values through Phase 3 resolution is a later concern (the contract + reproducibility are in place).
- Full Prediction/Observation Pairing and Learning are not implemented; only resale/outcome references
  are preserved for Phase 8 pairing.

## Status
**HOLD FOR REVIEW.** Phase 7 (Executive Demo) not started.
