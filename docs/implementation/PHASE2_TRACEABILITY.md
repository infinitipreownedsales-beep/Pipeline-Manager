# PHASE 2 TRACEABILITY — data/identity/facts → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs
bind at review against the canonical DOCX / `requirement_index.json`).

| Phase 2 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Source Registry | `data/models`, `data/store` | 04 | DATA, SPEC | 1 |
| Source Contract / Schema Profile | `data/contracts`, `data/models` | 04, 05 | DATA, POL, CAL | 2, 3, 4, 10 |
| Import Batch | `data/ingestion`, `data/store` | 04 | DATA, TRANS | 8, 9, 31, 32 |
| Source Observation + raw preservation | `data/ingestion`, `data/store` | 04 | DATA | 5, 6, 7 |
| Distinct value semantics | `data/normalize` | 04 | DATA, DM | 13, 14, 15, 16 |
| Snapshot classification (full/partial) | `data/contracts`, `data/ingestion` | 04, 07 | DATA, PIPE | 10, 11, 12 |
| Vehicle Unit identity | `data/identity` | 03, 04 | DM, IDRULE, DATA | 17, 18, 19, 24 |
| Production Order identity | `data/identity` | 03, 07 | DM, PIPE | 20, 21, 22 |
| Identity evidence + resolution | `data/identity`, `data/store` | 04 | DM, IDRULE | 17-24 |
| Identity correction | `data/identity` | 04 | DM | 23 |
| Business Fact (append-preserving) | `data/facts`, `data/store` | 03, 11 | DM, GOV, AUDIT | 25-29 |
| Source authority (fact-type + scope) | `data/models`, `data/facts` | 11 | GOV, AUTH | 25, 26 |
| Correction / supersession / reversal | `data/facts` | 03, 11 | DM, GOV | 27, 28, 29 |
| Current-state projection + conflict | `data/facts` | 03 | DM, DEC | 29, 30 |
| Reconciliation outcomes | `data/ingestion`, `data/store` | 04 | DATA | 31, 32 |
| Provenance + data-quality status | `data/models`, `data/ingestion` | 04 | DATA | 5, 16 |
| Migration v2 (versioned, rerun-safe) | `db.py` | 04 | DATA, TRANS | 34 |
| Durable persistence / restart | `data/store`, `db.py` | 04, 13 | DATA, NFR | 33 |
| Fixtures + tests | `data/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Legacy-line invariants | `tests/test_legacy_guard` | 15 | DELIVERY, GATE | 36, 37 |

**Not implemented (guarded, item 38):** Demand, Need, Supply, forecast, CPO, PPO,
CTP, Dealer Trade, Service Loaner, Executive Demo, Prediction, Learning, broad UI,
`pm_*` migration.
