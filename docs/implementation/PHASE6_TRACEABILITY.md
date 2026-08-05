# PHASE 6 TRACEABILITY — Service Loaner domain → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review
against the canonical DOCX / `requirement_index.json`).

| Phase 6 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Active-fleet Full Snapshot contract | `loaner/snapshot`, `data/ingestion` | 08, 04 | LOANER, DATA | 4-8 |
| Membership reconciliation by VIN | `loaner/snapshot`, `loaner/store` | 08 | LOANER, DM | 1, 4, 9, 10 |
| Service Loaner Unit + lifecycle | `loaner/unit`, `loaner/lifecycle`, `loaner/models` | 08 | LOANER, GOV | 2, 3, 11-14 |
| In-service-date authority | `loaner/dating` | 08 | LOANER, DM | 15-18 |
| Last Checkout Mileage | `loaner/dating` | 08 | LOANER, DATA | 19-23 |
| Zero-mile-rented monitoring | `loaner/monitoring` | 08 | LOANER, NOACT | 24-30 |
| Economic Call (versioned) | `loaner/economics`, `policy/calc` | 08, 06 | LOANER, CAL | 31-37, 39, 66 |
| Execution Status | `loaner/execution` | 08 | LOANER, DEC | 38, 66 |
| Entry selection + portfolio | `loaner/portfolio` | 08 | LOANER, DEC | 40-46 |
| Retirement / provisional / return / final | `loaner/retirement`, `loaner/lifecycle` | 08 | LOANER, GOV | 47-54 |
| Used Cars handoff (idempotent, immutable) | `loaner/retirement`, `loaner/store` | 08 | LOANER, AUDIT | 55-61 |
| Return-to-retail reconciliation | `loaner/retirement`, `newinv/store` | 08, 07 | LOANER, SUPPLY | 62-65 |
| Scenario / policy exploration | `loaner/scenario` | 08, 05 | LOANER, POL | 67-70 |
| Governance + audit | `loaner/lifecycle`, `governance`, `authz`, `audit` | 11 | GOV, AUTH, AUDIT | 71-78 |
| Operational output slices | `loaner/output` | 10 | VIEW | 79 |
| Resale / outcome foundations | `loaner/resale` | 08, 12 | LOANER, LEARN(ref) | (Phase 8 pairing refs) |
| Migration v6 (versioned, rerun-safe) | `db.py` | 08 | LOANER, TRANS | 80, 81 |
| Durable persistence / restart | `loaner/store`, `db.py` | 08, 13 | LOANER, NFR | 1, 80 |
| Fixtures + tests | `loaner/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Cross-phase greens | `tests/` | 15 | GATE | 82-86 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase6_migration_cross` | 15 | DELIVERY, GATE | 87, 88 |
| No-out-of-scope-behavior guard | `tests/test_phase6_migration_cross` | 15 | GATE | 89 |

**Not implemented (guarded, item 89):** Executive Demo (Phase 7), Prediction/Observation Pairing,
Learning, completed Phase-9 Governance, broad Phase-10 UX, operational hardening, migration/cutover.
