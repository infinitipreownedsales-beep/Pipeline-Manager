# PHASE 7 COMPLETION PACKET — Executive Demo Domain

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/execdemo/` (+ migration v7 in `elite/db.py`); no legacy file changed.
- **Scope:** Executive Demo **only**, as a bounded governed portfolio domain that is **separate**
  from Service Loaner. The two fleet domains are **not** merged into one shared engine.

## Implemented
The complete Executive Demo bounded domain: portfolio need determination (resolved before any
ranking, from active + committed Executive Demo state only — Service Loaner need never enters, New
Retail Demand is never recalculated); candidate eligibility as an explicit reasoned gate (never
silently admits sold / unresolved / already-demo / active-Service-Loaner / committed units);
candidate construction from accepted facts + New Retail planning references; **Best Overall**
portfolio selection over the full business objective (Executive Demo benefit − New Retail opportunity
cost + portfolio fit + approved model-preference bonus), with per-candidate tradeoffs recorded and
necessary sacrifices labeled — the cheapest unit does not automatically win, nor does the highest
benefit if the New Retail sacrifice is excessive; model preference resolved through Phase 3 only
(never overrides hard eligibility); versioned New Retail opportunity cost that **consumes** the Phase
4 inventory plan (Need position costs more than Excess, proven from the plan; unknown return timing
lowers confidence; a changed demo path never alters Demand); expected Executive Demo lifecycle
projection (versioned; missing inputs → unresolved, never manufactured); designation
propose/approve/execute — approval creates committed portfolio state only, execution establishes
active membership once **and** removes the unit from New Retail Current Supply (count-once
reconciliation); versioned Economic Call kept separate from Execution Status (entry vs retirement
distinguishable, incremental future economics, no sunk designation cost reapplied,
`BLOCKED_NEW_RETAIL_RISK` supported); retirement eligibility / propose / approve / execute (actual
retirement removes active membership only at the event); return-to-New-Retail that restores Current
Supply exactly once (existing supply prevents duplicate restoration); Used Cars handoff as its **own**
immutable, idempotent receipt (a separate record from Service Loaner, creating no New Retail supply,
never preceding retirement); reconciliation outcomes; corrections that preserve prior records;
scenario exploration isolated from official policy/state; resale/outcome foundations for Phase 8; and
operational output slices. Migration v7 appended (v1-v6 unchanged), touching no legacy file. All
policies/assumptions/thresholds resolve through Phase 3; synthetic values only.

Strict domain separation: Executive Demo is distinct from Service Loaner, New Retail inventory,
generic acquisition ranking, CPO/PPO, production pipeline, Service Loaner fleet need, and Used Cars
before confirmed handoff. `elite/execdemo/` imports no Service Loaner package and shares no fleet
engine with it.

**Not built (guarded, item 89):** Prediction/Observation Pairing, Learning, completed Phase-9
Governance, broad Phase-10 UX, operational hardening, migration/cutover.

## Acceptance evidence (90 mandatory items, all executed)
| # | Requirement | Test |
|---|---|---|
| 1 | Executive Demo Unit survives restart | `test_phase7_unit_portfolio.test_01` |
| 2 | Vehicle Unit identity authoritative | `test_phase7_unit_portfolio.test_02_03` |
| 3 | Executive Demo Unit id does not replace Vehicle Unit id | `test_phase7_unit_portfolio.test_02_03` |
| 4 | Executive Demo & Service Loaner are separate domains | `test_phase7_unit_portfolio.test_04_05` |
| 5 | A unit cannot be active in both fleet domains | `test_phase7_unit_portfolio.test_04_05` |
| 6 | Candidate is not membership | `test_phase7_unit_portfolio.test_06` |
| 7 | Approval creates committed state, not membership | `test_phase7_unit_portfolio.test_07` |
| 8 | Execution establishes membership once | `test_phase7_unit_portfolio.test_08` |
| 9 | Replayed approval: no duplicate commitment | `test_phase7_unit_portfolio.test_09` |
| 10 | Replayed execution: no duplicate | `test_phase7_unit_portfolio.test_10` |
| 11 | Cancellation removes committed, preserves history | `test_phase7_unit_portfolio.test_11` |
| 12 | Need resolved independently of ranking | `test_phase7_unit_portfolio.test_12` |
| 13 | Active + committed both reduce need | `test_phase7_unit_portfolio.test_13` |
| 14 | Healthy portfolio → nothing selected | `test_phase7_unit_portfolio.test_14` |
| 15 | Service Loaner need never enters Executive Demo need | `test_phase7_unit_portfolio.test_15_16` |
| 16 | New Retail Demand never recalculated here | `test_phase7_unit_portfolio.test_15_16` |
| 17 | Eligibility separate from ranking, with reasons | `test_phase7_unit_portfolio.test_17` |
| 18 | Active Service Loaner is ineligible | `test_phase7_unit_portfolio.test_18` |
| 19 | Already-active demo is ineligible | `test_phase7_unit_portfolio.test_19` |
| 20 | Sold / unresolved identity not silently eligible | `test_phase7_unit_portfolio.test_20` |
| 21 | Model preference resolves through Policy Versions | `test_phase7_preference_bestoverall.test_21` |
| 22 | Missing preference policy → fallback/unresolved | `test_phase7_preference_bestoverall.test_22` |
| 23 | Conflicting preference → conflict | `test_phase7_preference_bestoverall.test_23` |
| 24 | Preference never overrides ineligibility | `test_phase7_preference_bestoverall.test_24` |
| 25 | Scenario preference stays isolated | `test_phase7_preference_bestoverall.test_25` |
| 26 | Candidate construction uses accepted facts | `test_phase7_preference_bestoverall.test_26_27` |
| 27 | Candidate identifies New Retail planning refs | `test_phase7_preference_bestoverall.test_26_27` |
| 28 | Opportunity cost consumes the Phase 4 plan | `test_phase7_preference_bestoverall.test_28_29` |
| 29 | Opportunity cost calculates no separate Demand | `test_phase7_preference_bestoverall.test_28_29` |
| 30 | Need position costs more than Excess (from plan) | `test_phase7_preference_bestoverall.test_30` |
| 31 | Unknown return timing reduces confidence | `test_phase7_preference_bestoverall.test_31` |
| 32 | Opportunity cost distinct from Executive Demo benefit | `test_phase7_preference_bestoverall.test_32` |
| 33 | Best Overall is explainable (material tradeoffs shown) | `test_phase7_preference_bestoverall.test_33_34_35_36` |
| 34 | Lowest opportunity cost does not automatically win | `test_phase7_preference_bestoverall.test_33_34_35_36` |
| 35 | Highest benefit does not automatically win | `test_phase7_preference_bestoverall.test_33_34_35_36` |
| 36 | Best Overall uses the full objective, no opaque score | `test_phase7_preference_bestoverall.test_33_34_35_36` |
| 37 | Necessary sacrifice labeled | `test_phase7_preference_bestoverall.test_37` |
| 38 | Approval updates committed state | `test_phase7_preference_bestoverall.test_38_39` |
| 39 | Same unit never selected twice within a plan | `test_phase7_preference_bestoverall.test_38_39` |
| 40 | Expected lifecycle projection resolves with inputs | `test_phase7_preference_bestoverall.test_40_41_42` |
| 41 | Missing lifecycle inputs → unresolved (not invented) | `test_phase7_preference_bestoverall.test_40_41_42` |
| 42 | Historical lifecycle projection preserved (append) | `test_phase7_preference_bestoverall.test_40_41_42` |
| 43 | Economic Call versioned; entry vs retirement distinct | `test_phase7_economics_designation_retirement.test_43` |
| 44 | Retirement uses incremental future; no sunk cost | `test_phase7_economics_designation_retirement.test_44` |
| 45 | Missing economic inputs → unresolved | `test_phase7_economics_designation_retirement.test_45` |
| 46 | Alternatives carry their own values (no opaque score) | `test_phase7_economics_designation_retirement.test_46` |
| 47 | Conflicting economic policy → conflict | `test_phase7_economics_designation_retirement.test_47` |
| 48 | Execution Status separate incl. BLOCKED_NEW_RETAIL_RISK | `test_phase7_economics_designation_retirement.test_48` |
| 49 | Designation proposal creates action, not membership | `test_phase7_economics_designation_retirement.test_49` |
| 50 | Approval commits, no supply effect | `test_phase7_economics_designation_retirement.test_50` |
| 51 | Execution establishes membership + removes NR supply once | `test_phase7_economics_designation_retirement.test_51` |
| 52 | Replayed execution: no double supply removal | `test_phase7_economics_designation_retirement.test_52` |
| 53 | Cancellation removes committed, preserves history | `test_phase7_economics_designation_retirement.test_53` |
| 54 | Active Service Loaner cannot be designated | `test_phase7_economics_designation_retirement.test_54` |
| 55 | Retirement eligibility is not retirement | `test_phase7_economics_designation_retirement.test_55` |
| 56 | Retirement approval is not actual retirement | `test_phase7_economics_designation_retirement.test_56` |
| 57 | Actual retirement removes active membership | `test_phase7_economics_designation_retirement.test_57` |
| 58 | Return-to-New-Retail restores Current Supply once | `test_phase7_economics_designation_retirement.test_58` |
| 59 | Existing supply prevents duplicate restoration | `test_phase7_economics_designation_retirement.test_59` |
| 60 | Used Cars handoff is a separate record, no NR supply | `test_phase7_economics_designation_retirement.test_60` |
| 61 | Used Cars receipt idempotent + immutable | `test_phase7_economics_designation_retirement.test_61` |
| 62 | Receipt cannot precede retirement | `test_phase7_economics_designation_retirement.test_62` |
| 63 | Reconciliation outcomes recorded | `test_phase7_economics_designation_retirement.test_63` |
| 64 | One Vehicle Unit counts once across lifecycle | `test_phase7_economics_designation_retirement.test_64` |
| 65 | Correction preserves prior records | `test_phase7_economics_designation_retirement.test_65` |
| 66 | Economic Call not rewritten when execution blocked | `test_phase7_economics_designation_retirement.test_66` |
| 67 | Scenario does not change official policy | `test_phase7_scenario_governance.test_67_68` |
| 68 | Scenario does not change official portfolio state | `test_phase7_scenario_governance.test_67_68` |
| 69 | Scenario identifies overrides; exploring ≠ approval | `test_phase7_scenario_governance.test_69` |
| 70 | Scenario does not activate official policy | `test_phase7_scenario_governance.test_70` |
| 71 | Resale reference is foundation only (no pairing) | `test_phase7_scenario_governance.test_71` |
| 72 | Propose/approve/execute/retire authorities separate | `test_phase7_scenario_governance.test_72` |
| 73 | Authorization enforced below the UI | `test_phase7_scenario_governance.test_73` |
| 74 | Scope mismatch rejected | `test_phase7_scenario_governance.test_74` |
| 75 | Revoked authority rejected | `test_phase7_scenario_governance.test_75` |
| 76 | Stale transition rejected | `test_phase7_scenario_governance.test_76` |
| 77 | Required Audit Event written atomically | `test_phase7_scenario_governance.test_77` |
| 78 | Audit failure blocks unsafe success (rollback) | `test_phase7_scenario_governance.test_77` |
| 79 | Output slices use real domain records | `test_phase7_scenario_governance.test_78` / `test_79` |
| 80 | Migration v7 survives restart | `test_phase7_migration_cross.test_80` |
| 81 | Migration v7 rerun safe | `test_phase7_migration_cross.test_81` |
| 82 | Phase 1 tests remain green | `test_phase7_migration_cross.test_82` |
| 83 | Phase 2 + 3 tests remain green | `test_phase7_migration_cross.test_83` |
| 84 | Phase 4 tests remain green | `test_phase7_migration_cross.test_84` |
| 85 | Phase 5 tests remain green | `test_phase7_migration_cross.test_85` |
| 86 | Phase 6 tests remain green | `test_phase7_migration_cross.test_86` |
| 87 | Legacy tests remain 39/39 green | `test_phase7_migration_cross.test_87` (+ `test_legacy_guard`) |
| 88 | Legacy application paths unchanged | `test_phase7_migration_cross.test_88` (+ `test_legacy_guard`) |
| 89 | No Pairing / Learning / Governance / UX; separate from Service Loaner | `test_phase7_migration_cross.test_89` |
| 90 | All 60 fixtures build | `test_phase7_migration_cross.test_90` |

**Fixtures:** 60 dealership-representative scenarios (`execdemo/fixtures.build_all_scenarios`,
`SCENARIO_NAMES`), completeness proven by `test_phase7_migration_cross.test_90`.

**Platform harness:** `424/424 passed` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 + 79 P7).
**Legacy:** `39/39` (29 engine + 10 loaner).

## Dedicated Best Overall regression (14-point)
`elite/tests/test_phase7_preference_bestoverall.TestBestOverallRegression` proves: (1) portfolio need
known; (2) at least three eligible candidates; (3) a lowest-cost, (4) a highest-benefit, and (5) a
strongest-fit candidate present; (6) Best Overall is chosen from the full objective (the strong-fit
unit, not the cheapest, not the highest-benefit); (7) material tradeoffs (benefit / New Retail
opportunity cost / portfolio fit) shown per candidate; (8) model preference applied only through
approved policy; (9) necessary sacrifices labeled where applicable; (10) approval updates committed
state; (11) the next recommendation uses the updated state; (12) an already-committed unit cannot be
selected again; (13) New Retail Demand is unchanged throughout; (14) a replayed approval creates no
duplicate commitment.

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- The Economic Call, opportunity cost, benefit, and portfolio-fit inputs are caller-supplied resolved
  values (synthetic); wiring real market/residual/fit policy values through Phase 3 resolution is a
  later concern (the contract, versioning, and reproducibility are in place).
- Full Prediction/Observation Pairing and Learning are not implemented; only resale/outcome references
  are preserved for Phase 8 pairing.

## Status
**HOLD FOR REVIEW.** Phase 8 not started.
