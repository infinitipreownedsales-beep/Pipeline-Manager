# PHASE 9 TRACEABILITY — governance + operational control → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review against
the canonical DOCX / `requirement_index.json`).

| Phase 9 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Consolidated Decision Workspace | `govern/workspace` | 11 | GOV, VIEW | 1-6 |
| Recommendation review | `govern/workspace` | 11, 10 | GOV, VIEW | 5, 6, 100 |
| Governed Decision issuance + dispositions | `govern/decision`, `governance`, `authz`, `audit` | 11 | GOV, AUTH, AUDIT | 7-26 |
| Approval | `govern/approval` | 11 | GOV, AUTH | 27-35 |
| Execution authorization (references domain) | `govern/execution`, `workflow`/`loaner`/`execdemo` | 11 | GOV | 36-43 |
| Decision-to-execution reconciliation | `govern/execution` | 11 | GOV | 44, 54 |
| Acknowledgment | `govern/acknowledge` | 11 | GOV | 45-48 |
| Expiration + staleness | `govern/expiration` | 11 | GOV, POL | 49-53 |
| Scenario administration | `govern/scenario_admin`, `policy/scenario` | 11, 05 | GOV, POL | 55-57, 63-67 |
| Promotion + policy-review requests | `govern/scenario_admin` | 11, 05 | GOV, POL | 58-62 |
| Calibration review workspace | `govern/calibration_workspace`, `learning/calibration` | 11, 12 | GOV, CALIB | 68-72 |
| Authority administration | `govern/authority`, `authz` | 11 | AUTH, GOV | 73-78, 83-84 |
| Delegation + temporary authority | `govern/authority` | 11 | AUTH | 74-78 |
| Separation of duties | `govern/sod` | 11 | AUTH, GOV | 79-82 |
| Audit administration | `govern/audit_admin`, `audit` | 11 | AUDIT | 85-88 |
| Exception + unresolved queues | `govern/queues` | 11, 10 | GOV | 89-91 |
| Operational-control summaries | `govern/summaries` | 10 | VIEW | 92 |
| Domain readiness assessment | `govern/readiness` | 11, 15 | GOV, DELIVERY | 93-99 |
| Operational output slices | `govern/output` | 10 | VIEW | 100 |
| Migration v9 (versioned, rerun-safe) | `db.py` | 11 | GOV, TRANS | 101, 102 |
| Cross-phase greens | `tests/` | 15 | GATE | 103-110 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase9_migration_cross` | 15 | DELIVERY, GATE | 111, 112 |
| No-out-of-scope-behavior guard | `tests/test_phase9_migration_cross` | 15 | GATE | 113 |

## Dedicated regressions
Governed-decision (20-point): `tests/test_phase9_governed_decision_regression`.
Authority-administration (14-point): `tests/test_phase9_authority_admin_regression`.

## Permanent prior-phase regressions retained
BUG-CPO-002 (`tests/test_phase4_bug_cpo_002`, `tests/test_phase5_bug_cpo_002_e2e`), the Service Loaner
zero-mile-rented regression (`tests/test_phase6_monitoring`), the Executive Demo Best Overall regression
(`tests/test_phase7_preference_bestoverall`), and the Phase 8 learning-governance regression
(`tests/test_phase8_learning_governance_regression`) all remain green under migration v9 (items 106-110).
