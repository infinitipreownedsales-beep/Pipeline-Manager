# PHASE 8 TRACEABILITY — learning + calibration → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review
against the canonical DOCX / `requirement_index.json`).

| Phase 8 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Immutable Prediction issuance | `learning/prediction`, `policy/calc` | 12 | PRED, CAL, REPRO | 1-6 |
| Decision learning context | `learning/prediction` | 12 | PRED, DEC | 7, 8 |
| Immutable Observation | `learning/observation` | 12 | OBS, DATA | 9-13 |
| Comparison Specification runtime | `learning/comparison`, `policy` | 12, 06 | CMP, POL | 14, 15 |
| Prediction-to-Observation Pairing | `learning/pairing` | 12 | PAIR | 16-26 |
| Error | `learning/error`, `policy/calc` | 12 | ERR, CAL | 27-36 |
| Attribution | `learning/attribution` | 12 | ATTR | 37-43 |
| Learning Signal | `learning/signal` | 12 | LEARN | 44-50 |
| Cross-domain boundaries | `learning/boundaries` | 12 | LEARN, DOMAIN | 51-53, 90 |
| Backtesting / validation | `learning/validation` | 12 | CALIB, VALID | 54-59 |
| Calibration governance | `learning/calibration`, `governance`, `authz`, `audit` | 12, 11 | CALIB, GOV, AUTH, AUDIT | 60-77 |
| Activation / rollback (versioned) | `learning/calibration`, `policy/store` | 12, 06 | CALIB, VER | 62, 63, 66, 67, 75 |
| Operational output slices | `learning/output` | 10 | VIEW | 78 |
| Migration v8 (versioned, rerun-safe) | `db.py` | 12 | LEARN, TRANS | 79, 80 |
| Durable persistence / restart | `learning/store`, `db.py` | 12, 13 | LEARN, NFR | 1, 8, 14, 79 |
| Fixtures + tests | `learning/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Cross-phase greens | `tests/` | 15 | GATE | 81-87 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase8_migration_cross` | 15 | DELIVERY, GATE | 88, 89 |
| No-out-of-scope-behavior guard | `tests/test_phase8_migration_cross` | 15 | GATE | 90 |

## Dedicated regression
Learning-governance (20-point):
`tests/test_phase8_learning_governance_regression.TestLearningGovernanceRegression`.

## Permanent prior-phase regressions retained
BUG-CPO-002 (`tests/test_phase4_bug_cpo_002`, `tests/test_phase5_bug_cpo_002_e2e`), the Service Loaner
zero-mile-rented regression (`tests/test_phase6_monitoring`), and the Executive Demo Best Overall
regression (`tests/test_phase7_preference_bestoverall`) continue to pass unchanged under migration v8
(acceptance items 84-87).
