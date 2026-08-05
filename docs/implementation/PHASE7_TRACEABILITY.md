# PHASE 7 TRACEABILITY — Executive Demo domain → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review
against the canonical DOCX / `requirement_index.json`).

| Phase 7 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Executive Demo Unit + lifecycle | `execdemo/unit`, `execdemo/lifecycle`, `execdemo/models` | 09 | DEMO, GOV | 1-3, 6-11 |
| Domain separation from Service Loaner | `execdemo/unit`, `execdemo/portfolio` | 09 | DEMO, LOANER | 4, 5, 18, 89 |
| Portfolio need (before ranking) | `execdemo/portfolio` | 09 | DEMO, DEC | 12-16 |
| Candidate eligibility (reasoned gate) | `execdemo/eligibility` | 09 | DEMO, DEC | 17-20 |
| Model preference (approved policy) | `execdemo/preference`, `policy/resolution` | 09, 05 | DEMO, POL | 21-25 |
| Candidate construction | `execdemo/portfolio` | 09 | DEMO, DM | 26, 27 |
| New Retail opportunity cost (consumes plan) | `execdemo/opportunity`, `newinv/*` | 09, 07 | DEMO, SUPPLY, CAL | 28-32 |
| Best Overall selection | `execdemo/portfolio` | 09 | DEMO, DEC | 33-39 |
| Expected lifecycle projection | `execdemo/projection` | 09 | DEMO, CAL | 40-42 |
| Economic Call (versioned) | `execdemo/economics`, `policy/calc` | 09, 06 | DEMO, CAL | 43-47, 66 |
| Execution Status | `execdemo/economics` | 09 | DEMO, DEC | 48, 66 |
| Designation propose/approve/execute | `execdemo/unit`, `execdemo/lifecycle` | 09 | DEMO, GOV, SUPPLY | 49-54 |
| Retirement / return / final | `execdemo/retirement`, `execdemo/lifecycle` | 09 | DEMO, GOV | 55-59, 63, 64 |
| Used Cars handoff (idempotent, immutable) | `execdemo/retirement`, `execdemo/store` | 09 | DEMO, AUDIT | 60-62 |
| Corrections preserve history | `execdemo/unit`, `execdemo/retirement` | 09 | DEMO, DM | 65 |
| Scenario / policy exploration | `execdemo/scenario`, `execdemo/preference` | 09, 05 | DEMO, POL | 67-70 |
| Resale / outcome foundations | `execdemo/resale` | 09, 12 | DEMO, LEARN(ref) | 71 (Phase 8 pairing refs) |
| Governance + audit | `execdemo/lifecycle`, `governance`, `authz`, `audit` | 11 | GOV, AUTH, AUDIT | 72-78 |
| Operational output slices | `execdemo/output` | 10 | VIEW | 79 |
| Migration v7 (versioned, rerun-safe) | `db.py` | 09 | DEMO, TRANS | 80, 81 |
| Durable persistence / restart | `execdemo/store`, `db.py` | 09, 13 | DEMO, NFR | 1, 80 |
| Fixtures + tests | `execdemo/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Cross-phase greens | `tests/` | 15 | GATE | 82-86 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase7_migration_cross` | 15 | DELIVERY, GATE | 87, 88 |
| No-out-of-scope-behavior guard | `tests/test_phase7_migration_cross` | 15 | GATE | 89 |

## Dedicated regression
Best Overall (14-point): `tests/test_phase7_preference_bestoverall.TestBestOverallRegression`.

## Permanent prior-phase regressions retained
BUG-CPO-002 (`tests/test_phase4_bug_cpo_002`, `tests/test_phase5_bug_cpo_002_e2e`) and the Service
Loaner zero-mile-rented regression (`tests/test_phase6_monitoring.TestZeroMileRegression`) continue to
pass unchanged under migration v7 (acceptance items 84-86).
