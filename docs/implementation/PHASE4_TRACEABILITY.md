# PHASE 4 TRACEABILITY — New Inventory foundation → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at
review against the canonical DOCX / `requirement_index.json`).

| Phase 4 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Sellable Combination identity | `newinv/combination`, `newinv/store` | 03, 07 | DM, INV | 1-4, 6 |
| Combination alias + correction lineage | `newinv/combination`, `newinv/store` | 03 | DM | 5 |
| Combination lineage / comparability | `newinv/combination`, `newinv/store` | 03, 06 | DM, LINEAGE | 26, 29 |
| Current Supply projection | `newinv/supply`, `newinv/store` | 07 | INV, SUPPLY | 7, 8, 9 |
| Future Supply projection | `newinv/supply`, `newinv/store` | 07 | SUPPLY, PIPE | 10, 11, 12 |
| Committed Supply | `newinv/supply`, `newinv/store` | 07, 11 | SUPPLY, GOV | 13, 14, 15, 48 |
| Qualifying supply (count-once) | `newinv/supply` | 07 | SUPPLY, DEC | 46, 47 |
| Historical retail | `newinv/retail`, `newinv/store` | 06 | RETAIL, DM | 16-19 |
| Availability reconstruction | `newinv/availability`, `newinv/store` | 06 | AVAIL, DATA | 20-23 |
| Demand baseline (supply-blind) | `newinv/demand` | 06 | DEMAND, CAL | 24, 25, 49 |
| Evidence hierarchy + lineage | `newinv/demand`, `newinv/combination` | 06 | DEMAND, LINEAGE | 26, 27, 29 |
| Seasonality + trend | `newinv/demand` | 06 | DEMAND | 28, 30, 31, 32 |
| Month-by-month forecast | `newinv/forecast`, `newinv/store` | 06 | FCST | 33, 51, 52, 53 |
| Forecast reconciliation | `newinv/forecast`, `newinv/planning` | 06 | FCST, DEC | 34, 35 |
| Desired ending coverage (policy) | `newinv/coverage`, `policy/resolution` | 05, 06 | POL, INV | 36, 37, 38, 39 |
| Need / Excess (month-aware) | `newinv/planning` | 06, 07 | DEC, INV | 40-45, 48 |
| Reproducibility + replay | `newinv/demand`, `newinv/planning`, `policy/calc` | 06, 13 | CAL, NFR | 50 |
| Portfolio reconciliation | `newinv/planning`, `newinv/store` | 06, 07 | DEC, INV | 35 |
| Operational output slice | `newinv/output` | 10 | VIEW | 54, 55 |
| Migration v4 (versioned, rerun-safe) | `db.py` | 07 | INV, TRANS | 56, 57 |
| Durable persistence / restart | `newinv/store`, `db.py` | 07, 13 | INV, NFR | 1, 56 |
| Fixtures + tests | `newinv/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Cross-phase greens | `tests/` | 15 | GATE | 58, 59, 60 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase4_output_migration` | 15 | DELIVERY, GATE | 61, 62 |
| No-domain / no-Phase-5 guard | `tests/test_phase4_output_migration` | 15 | GATE | 63 |
| BUG-CPO-002 regression | `tests/test_phase4_bug_cpo_002` | 06, 07 | DEMAND, SUPPLY, DEC | dedicated |

**Not implemented (guarded, item 63):** any second Demand calculation inside a supply workflow;
Phase-5 production workflows, CPO, PPO, Dealer Trade, CTP, Service Loaner, Executive Demo,
Prediction pairing, Learning, full Governance, broad UX.
