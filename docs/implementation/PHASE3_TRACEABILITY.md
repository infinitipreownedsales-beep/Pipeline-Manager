# PHASE 3 TRACEABILITY — policy/versioning → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind
at review against the canonical DOCX / `requirement_index.json`).

| Phase 3 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Policy Family + taxonomy | `policy/models`, `policy/store` | 05 | POL, DM | 1, 3, 23 |
| Immutable Policy Version (triggers) | `policy/store`, `db.py` | 05, 11 | POL, AUDIT | 3, 4 |
| Scope model + dimension validation | `policy/guards`, `policy/models` | 05 | POL, SPEC | 16, 17, 18 |
| Effective dating (UTC + tz boundary) | `policy/resolution`, `policy/fixtures` | 05, 13 | POL, NFR | 7, 8, 9, 10, 28 |
| Lifecycle state machine | `policy/models`, `policy/lifecycle` | 05, 11 | POL, GOV | 5, 6, 7, 8, 11-15 |
| Approval / scheduling / activation | `policy/lifecycle` | 05, 11 | POL, GOV | 7, 8 |
| Supersession / revocation | `policy/lifecycle`, `policy/resolution` | 05 | POL | 11, 12 |
| Rejection / withdrawal | `policy/lifecycle`, `policy/resolution` | 05 | POL | 13, 14 |
| Correction lineage | `policy/lifecycle`, `policy/store` | 05 | POL, DM | 15 |
| Deterministic resolution + precedence | `policy/resolution` | 05, 06 | POL, DEC | 16, 19, 20, 29-31 |
| Conflict detection | `policy/resolution` | 05, 06 | POL, DEC | 20 |
| Approved fallback (declared only) | `policy/resolution` | 05 | POL | 21, 22 |
| Typed financial assumptions | `policy/assumptions`, `policy/guards` | 05 | POL, FIN | 24, 25, 26, 27 |
| Technical config separation | `policy/guards` | 05 | POL, CAL | 23 |
| Calculation Family / Version | `policy/store`, `policy/models`, `policy/calc` | 06 | CAL | 32, 33, 34 |
| Model Version foundation | `policy/store`, `policy/versions` | 06 | MODEL, CAL | 37 |
| Identity-Rule Version foundation | `policy/store` | 04, 06 | IDRULE | 38, 39 |
| Comparison-Specification Version foundation | `policy/store` | 06 | CMP | 40 |
| Reproducibility package + replay | `policy/calc`, `policy/store` | 06, 13 | CAL, NFR | 41, 42 |
| Scenario override isolation (governed) | `policy/scenario`, `policy/resolution` | 05, 11 | POL, GOV | 44-47, 58, 59 |
| Version activation / rollback history | `policy/versions`, `policy/store` | 06, 11 | CAL, AUDIT | 35, 36, 43 |
| Governed action + authz + audit | `policy/lifecycle`, `governance`, `authz`, `audit` | 11 | GOV, AUTH, AUDIT | 48-52 |
| Optimistic concurrency / idempotency | `policy/lifecycle`, `policy/store`, `governance` | 11, 13 | GOV, NFR | 49, 50 |
| Migration v3 (versioned, rerun-safe) | `db.py` | 05 | POL, TRANS | 53, 54 |
| Fixtures + tests | `policy/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase3_scenario_gov` | 15 | DELIVERY, GATE | 55, 57 |

**Not implemented (guarded, items 55/57):** any domain calculation, Demand, Need,
forecasting, CPO, PPO, Dealer Trade, CTP, Service Loaner, Executive Demo, Prediction
pairing, Learning, broad UI. Scenario-override → official-policy promotion is a distinct
governed action deliberately excluded from Phase 3.
