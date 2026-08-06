# PHASE 11 TRACEABILITY — operational hardening + controlled pilot readiness → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review against the
canonical DOCX / `requirement_index.json`). Phase 11 adds NO business rule and redefines NO Phase 1-10
domain mathematics — it hardens operation and prepares a controlled pilot alongside the legacy tool.

| Phase 11 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Source-contract registry | `ops/contracts` | 02, 13, 14 | SOURCE, DATA | (registry) |
| Source adapters | `ops/adapters` | 02 | SOURCE, DATA | 1-6 |
| Import orchestration | `ops/imports`, `ops/store` | 02, 14 | DATA, GATE | 7-11 |
| Controlled file intake | `ops/intake` | 02, 11 | SEC, DATA | 65-68 |
| Snapshot semantics | `ops/adapters`, `data/*` | 02 | DATA | 12-13 |
| Data freshness | `ops/freshness` | 02, 14 | DATA, DELIVERY | 14-16 |
| Reconciliation / drift | `ops/reconcile` | 02, 14 | DATA | 17-21 |
| Scheduling | `ops/scheduler` | 14 | DELIVERY | 22-25 |
| Restart / recovery | `ops/recovery`, `ops/imports` | 14 | GATE, DELIVERY | 26-30 |
| Concurrency hardening | `governance`, `ui/app`, `authz` | 11, 14 | GATE | 31-35 |
| SQLite durability | `ops/durability`, `db` | 14 | DELIVERY | 36-39 |
| Backup / restore | `ops/backup` | 14 | DELIVERY | 40-44 |
| Health checks | `ops/health` | 14 | DELIVERY | 45-50 |
| Observability / logging | `ops/observability`, `logging_` | 14 | SEC, DELIVERY | 51-56 |
| Performance baselines | `ops/performance` | 14 | DELIVERY | 57-62 |
| Security hardening | `ops/security`, `ui/*` | 11 | SEC, AUTH | 63-64, 69-77 |
| Configuration management | `ops/opsconfig`, `config` | 01 | DELIVERY, SEC | 75-77 |
| Controlled pilot mode | `ops/pilot` | 14, 16 | DELIVERY | 78-80 |
| Parallel-run comparison | `ops/pilot` | 14, 16 | DELIVERY | 81-85 |
| Operator feedback | `ops/pilot`, `ops/store` | 14, 16 | DELIVERY | 86-88 |
| Pilot packaging | `ops/cli` | 14, 16 | DELIVERY | 89-92 |
| Phase 10 usability | `ui/*` | 10 | VIEW | 93 |
| Cross-phase greens | `tests/` | 15 | GATE | 94-103 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase11_pilot_cross` | 15 | DELIVERY, GATE | 104-105 |
| No-cutover guard | `ops/pilot`, `tests/test_phase11_pilot_cross` | 15, 16 | GATE | 106 |

## Acceptance modules
- `test_phase11_adapters_intake` (1-11, 65-68)
- `test_phase11_freshness_reconcile` (12-21)
- `test_phase11_scheduling_recovery` (22-35)
- `test_phase11_durability_backup_health` (36-50)
- `test_phase11_observability_security` (51-64, 69-77)
- `test_phase11_pilot_cross` (78-106 + 60-fixture completeness)

## Dedicated regressions
- Import-recovery (15-point): `tests/test_phase11_import_recovery_regression`.
- Controlled-pilot (20-point): `tests/test_phase11_controlled_pilot_regression`.

## Operational-record discipline
Migration v11 holds NO business truth: no Demand, Need, Supply, Economic Call, Decision, approval,
execution, policy, or identity value lives in the operational layer. Raw source evidence stays in the Phase
2 records; the operational tables only REFERENCE it. Point-in-time evidence is immutable; lifecycle/registry
rows are append-preserving. See `adr/ADR-0041..0046`.

## Permanent prior-phase regressions retained
BUG-CPO-002 (`test_phase4_bug_cpo_002`, `test_phase5_bug_cpo_002_e2e`), the Service Loaner zero-mile
regression, the Executive Demo Best Overall regression, the Phase 8 learning-governance regression, the
Phase 9 governed-decision + authority-administration regressions, and the Phase 10 operator-workflow +
presentation-integrity regressions all remain green under migration v11 (items 94-103). BUG-CPO-002 remains
FIXED_END_TO_END: the operational layer imports source data as evidence and recomputes no domain math, so no
import, reconciliation, freshness, comparison, or pilot action can raise Need or rewrite an issued result.
