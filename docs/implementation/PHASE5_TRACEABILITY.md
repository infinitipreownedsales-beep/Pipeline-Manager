# PHASE 5 TRACEABILITY — production/supply workflows → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review
against the canonical DOCX / `requirement_index.json`).

| Phase 5 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Production pipeline projection | `workflow/pipeline`, `workflow/store` | 07 | PIPE, SUPPLY | 1-5 |
| ETA / arrival windows | `workflow/pipeline` | 07 | PIPE, NFR | 6-10 |
| Editability | `workflow/pipeline`, `workflow/store` | 07 | PIPE | 11-13 |
| Model-year transition | `workflow/pipeline` | 06, 07 | LINEAGE, PIPE | 14, 15 |
| Incoming Risk (component) | `workflow/risk` | 07 | RISK, DEC | 16, 17 |
| Common workflow lifecycle | `workflow/lifecycle`, `workflow/models` | 07, 11 | WORKFLOW, GOV | 60-68 |
| CPO workflow | `workflow/cpo`, `workflow/reconcile` | 07 | CPO, SUPPLY | 18-25 |
| PPO workflow | `workflow/ppo`, `workflow/reconcile` | 07 | PPO, SUPPLY | 26-29 |
| Dealer Trade workflow | `workflow/dealer_trade`, `workflow/reconcile` | 07 | DEALER_TRADE | 30-36 |
| CTP workflow | `workflow/ctp`, `workflow/reconcile` | 07 | CTP, PIPE | 37-44 |
| Sequential recomputation | `workflow/sequential` | 06, 07 | DEC, PLAN | 45-48 |
| Commitment reconciliation | `workflow/reconcile`, `workflow/store` | 07 | SUPPLY, DEC | 52-55 |
| Integrated forecast updates | `workflow/integrate` | 06, 07 | FCST, PLAN | 56-59 |
| Monotonic / count-once supply | `workflow/reconcile`, `newinv/supply` | 07 | SUPPLY | 49-51 |
| Governance + audit | `workflow/lifecycle`, `governance`, `authz`, `audit` | 11 | GOV, AUTH, AUDIT | 60-68 |
| Operational workflow slices | `workflow/output` | 10 | VIEW | 69 |
| Migration v5 (versioned, rerun-safe) | `db.py` | 07 | WORKFLOW, TRANS | 70, 71 |
| Durable persistence / restart | `workflow/store`, `db.py` | 07, 13 | WORKFLOW, NFR | 1, 70 |
| Fixtures + tests | `workflow/fixtures`, `tests/` | 14 | TEST, GATE | all |
| Cross-phase greens | `tests/` | 15 | GATE | 72-75 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase5_migration_cross` | 15 | DELIVERY, GATE | 76, 77 |
| No out-of-scope behavior guard | `tests/test_phase5_migration_cross` | 15 | GATE | 78 |
| BUG-CPO-002 end-to-end regression | `tests/test_phase5_bug_cpo_002_e2e` | 06, 07 | CPO, SUPPLY, DEC | dedicated |

**Not implemented (guarded, item 78):** Service Loaner, Executive Demo, Prediction/Observation
Pairing, Learning, completed Phase-9 Governance, full UX, operational hardening, migration/cutover.
