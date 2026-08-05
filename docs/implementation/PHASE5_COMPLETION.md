# PHASE 5 COMPLETION PACKET — Production and Supply Workflows

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/workflow/` (+ migration v5 in `elite/db.py`); no legacy file changed.

## Implemented
Governed production + acquisition workflows that convert supply opportunities into proposed /
approved / committed / executed / cancelled / superseded / failed supply actions: production
pipeline projection; ETA + arrival-window interpretation; editability; model-year transition;
Incoming Risk (component-explained); the common workflow lifecycle; **CPO, PPO, Dealer Trade, CTP**;
sequential recomputation; commitment reconciliation (10 outcomes); integrated forecast updates;
execution/outcome capture; and operational workflow slices. Built on the Phase 1 authz/audit,
Phase 3 policy, and Phase 4 Demand/Supply/Need/Excess/forecast/commitment/reproducibility contracts,
with migration v5 appended (v1-v4 unchanged), touching no legacy file. Synthetic fixtures only — no
real manufacturer CPO/PPO policy, incentives, allowances, or windows.

**Every workflow consumes the authoritative Phase 4 Need contract and computes NO separate Demand.**
Supply effects flow through the Phase 4 Supply/commitment records, so count-once and monotonicity
hold end-to-end: an approved commitment credits qualifying Supply exactly once, an already-
represented identity yields ALREADY_REPRESENTED, and added qualifying Supply never increases Need.

**Not built (guarded, item 78):** Service Loaner, Executive Demo, Prediction/Observation Pairing,
Learning, completed Phase-9 Governance, full UX, operational hardening, migration/cutover.

## Acceptance evidence (78 mandatory items, all executed)
| # | Requirement | Test |
|---|---|---|
| 1 | Pipeline projection survives restart | `test_phase5_pipeline_eta.test_01` |
| 2 | Order identity stable through updates | `test_phase5_pipeline_eta.test_02` |
| 3 | Pre-VIN→VIN does not duplicate pipeline | `test_phase5_pipeline_eta.test_03` |
| 4 | Cancelled order excluded from qualifying future supply | `test_phase5_pipeline_eta.test_04` |
| 5 | Conflicting pipeline facts remain explicit | `test_phase5_pipeline_eta.test_05` |
| 6 | ETA precision does not exceed source evidence | `test_phase5_pipeline_eta.test_06` |
| 7 | Revised ETA preserves prior history | `test_phase5_pipeline_eta.test_07` |
| 8 | Cross-month ETA range not silently favorable | `test_phase5_pipeline_eta.test_08` |
| 9 | Unknown ETA not confident qualifying supply | `test_phase5_pipeline_eta.test_09` |
| 10 | Stale ETA reduces confidence / review | `test_phase5_pipeline_eta.test_10` |
| 11 | Editability separately inspectable from Demand | `test_phase5_editability_myt_risk.test_11` |
| 12 | Locked order cannot receive executable CTP | `test_phase5_editability_myt_risk.test_12` |
| 13 | Unknown editability does not become editable | `test_phase5_editability_myt_risk.test_13` |
| 14 | Model-year transition preserves identity | `test_phase5_editability_myt_risk.test_14` |
| 15 | Unsupported lineage does not transfer Demand | `test_phase5_editability_myt_risk.test_15` |
| 16 | Incoming Risk explains component reasons | `test_phase5_editability_myt_risk.test_16` |
| 17 | Risk not only an opaque score | `test_phase5_editability_myt_risk.test_17` |
| 18 | CPO consumes Phase 4 Need | `test_phase5_cpo.test_18` |
| 19 | CPO computes no separate Demand | `test_phase5_cpo.test_19` |
| 20 | CPO proposal has no supply effect | `test_phase5_cpo.test_20` |
| 21 | Approved CPO creates one Commitment | `test_phase5_cpo.test_21` |
| 22 | Replayed CPO approval does not double-count | `test_phase5_cpo.test_22` |
| 23 | CPO already represented does not count twice | `test_phase5_cpo.test_23` |
| 24 | CPO cancellation removes effect, keeps history | `test_phase5_cpo.test_24` |
| 25 | CPO completion reconciles to same/later unit | `test_phase5_cpo.test_25` |
| 26 | PPO distinct from CPO | `test_phase5_ppo_dealer.test_26` |
| 27 | PPO proposal has no supply effect | `test_phase5_ppo_dealer.test_27` |
| 28 | Approved PPO creates at most one Commitment | `test_phase5_ppo_dealer.test_28` |
| 29 | Rejected PPO has no supply effect | `test_phase5_ppo_dealer.test_29` |
| 30 | Dealer Trade proposal has no supply effect | `test_phase5_ppo_dealer.test_30` |
| 31 | Dealer Trade request sent has no supply effect | `test_phase5_ppo_dealer.test_31` |
| 32 | Dealer Trade acceptance per explicit contract | `test_phase5_ppo_dealer.test_32` |
| 33 | Completed Dealer Trade creates one qualifying supply | `test_phase5_ppo_dealer.test_33` |
| 34 | Terminal Dealer Trades do not count | `test_phase5_ppo_dealer.test_34` |
| 35 | Unknown Dealer Trade attempts not invented | `test_phase5_ppo_dealer.test_35` |
| 36 | Received unit reconciles with completed trade | `test_phase5_ppo_dealer.test_36` |
| 37 | CTP modifies one order, no duplicate | `test_phase5_ctp.test_37` |
| 38 | Unaccepted CTP does not replace original future supply | `test_phase5_ctp.test_38` |
| 39 | Accepted CTP preserves original order history | `test_phase5_ctp.test_39` |
| 40 | Rejected CTP leaves order unchanged | `test_phase5_ctp.test_40` |
| 41 | Non-editable CTP is rejected | `test_phase5_ctp.test_41` |
| 42 | CTP consumes Need + Excess, no separate Demand | `test_phase5_ctp.test_42` |
| 43 | CTP recomputes both combinations | `test_phase5_ctp.test_43` |
| 44 | Replayed accepted CTP does not apply twice | `test_phase5_ctp.test_44` |
| 45 | Planner updates committed state after each action | `test_phase5_sequential_reconcile.test_45` |
| 46 | Second recommendation uses updated Need | `test_phase5_sequential_reconcile.test_46` |
| 47 | Now-unnecessary action suppressed | `test_phase5_sequential_reconcile.test_47` |
| 48 | Same unit cannot be selected twice | `test_phase5_sequential_reconcile.test_48` |
| 49 | Demand unchanged when only commitments change | `test_phase5_sequential_reconcile.test_49` |
| 50 | Added commitment does not increase Need | `test_phase5_sequential_reconcile.test_50` |
| 51 | Later workflow supply does not satisfy earlier month | `test_phase5_sequential_reconcile.test_51` |
| 52 | Every transition gets a reconciliation outcome | `test_phase5_sequential_reconcile.test_52` |
| 53 | Duplicate replay → no-effect outcome | `test_phase5_sequential_reconcile.test_53` |
| 54 | Unresolved identity prevents confident commitment | `test_phase5_sequential_reconcile.test_54` |
| 55 | Completion reconciles future/committed → current once | `test_phase5_sequential_reconcile.test_55` |
| 56 | Workflow change issues a new planning result | `test_phase5_integrate_governance.test_56` |
| 57 | Prior issued planning result immutable | `test_phase5_integrate_governance.test_57` |
| 58 | Workflow output identifies the causing action | `test_phase5_integrate_governance.test_58` |
| 59 | Official and Scenario workflow states isolated | `test_phase5_integrate_governance.test_59` |
| 60 | Proposal and approval authorities separate | `test_phase5_integrate_governance.test_60` |
| 61 | Approval and completion authorities separate | `test_phase5_integrate_governance.test_61` |
| 62 | Authorization enforced below the UI | `test_phase5_integrate_governance.test_62` |
| 63 | Scope mismatch rejected | `test_phase5_integrate_governance.test_63` |
| 64 | Revoked authority rejected | `test_phase5_integrate_governance.test_64` |
| 65 | Stale transition rejected | `test_phase5_integrate_governance.test_65` |
| 66 | Idempotent retry, no duplicate effect | `test_phase5_integrate_governance.test_66` |
| 67 | Required Audit Event written atomically | `test_phase5_integrate_governance.test_67` |
| 68 | Audit failure prevents unsafe success | `test_phase5_integrate_governance.test_68` |
| 69 | Output slice uses real domain output | `test_phase5_integrate_governance.test_69` |
| 70 | Migration v5 survives restart | `test_phase5_migration_cross.test_70` |
| 71 | Migration v5 rerun safe | `test_phase5_migration_cross.test_71` |
| 72 | Phase 1 tests remain green | `test_phase5_migration_cross.test_72` |
| 73 | Phase 2 tests remain green | `test_phase5_migration_cross.test_73` |
| 74 | Phase 3 tests remain green | `test_phase5_migration_cross.test_74` |
| 75 | Phase 4 tests remain green | `test_phase5_migration_cross.test_75` |
| 76 | Legacy tests remain 39/39 green | `test_phase5_migration_cross.test_76` (+ `test_legacy_guard`) |
| 77 | Legacy application paths unchanged | `test_phase5_migration_cross.test_77` (+ `test_legacy_guard`) |
| 78 | No Loaner/Demo/Pairing/Learning/UX behavior | `test_phase5_migration_cross.test_78` |

**Fixtures:** 50 dealership-representative scenarios (`workflow/fixtures.build_all_scenarios`,
`SCENARIO_NAMES`), completeness proven by `test_phase5_migration_cross.test_79`.

**Platform harness:** `266/266 passed` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5).
**Legacy:** `39/39` (29 engine + 10 loaner).

## BUG-CPO-002 end-to-end regression (dedicated, 15-point)
`elite/tests/test_phase5_bug_cpo_002_e2e.py` proves the canonical resolution through the REAL
governed CPO workflow: (1) Phase 4 Demand issued; (2) baseline Current/Future/Committed Supply;
(3) baseline Need; (4) one eligible Production Order proposed through CPO; (5) proposal has no supply
effect; (6) authorized approval creates one Commitment; (7) Demand identical; (8) qualifying Supply
+exactly one; (9-10) Need decreases/unchanged, never increases; (11) replayed approval adds no unit;
(12) renamed acquisition path does not alter Demand; (13) cancellation removes the prospective
commitment; (14) approval + cancellation history inspectable; (15) a fresh workflow for the same
order commits at most one active unit for that identity. A monotone ladder confirms Need never rises
as commitments are added.

**With the Phase 4 regression (`test_phase4_bug_cpo_002.py`) also green, BUG-CPO-002 is
`FIXED_END_TO_END` — retained permanently in the regression registry (see KNOWN_BUG_REGISTRY.md).**

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- The Dealer Trade "firm on accept" path is contract-configurable (`firm_on_accept`), defaulting to
  supply-on-completion; a dealership's real firm-offer contract would set it explicitly.
- Operational hardening (retry/durability of the post-transition supply projection), full Governance,
  and outbound-unit Dealer Trade effects are deliberately out of Phase 5 scope.

## Status
**HOLD FOR REVIEW.** Phase 6 not started.
