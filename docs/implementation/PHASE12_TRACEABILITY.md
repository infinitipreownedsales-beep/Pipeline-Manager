# PHASE 12 TRACEABILITY — live integration + migration + validation + release → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review against the
canonical DOCX / `requirement_index.json`). Phase 12 is the FINAL engineering + validation phase. It adds no
new business rule and redefines no Phase 1-11 mathematics; it wires the real executors, migrates real data,
validates against legacy, rehearses migration/rollback/recovery, and gates an explicit release authorization
— with no irreversible production cutover.

| Phase 12 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Live-source inventory | `release/migration`, `release/store` | 02, 14, 16 | SOURCE, DELIVERY | 1-2 |
| Real adapter configuration | `release/migration` | 02 | SOURCE, DATA | 3-5 |
| Controlled real-source ingestion | `release/migration`, `ops/*` | 02, 14 | DATA, GATE | 6-11 |
| Identity migration | `release/migration` | 02 | DATA | 12-16 |
| Historical migration | `release/migration` | 02 | DATA | 17-20 |
| Policy migration | `release/migration`, `policy/*` | 03 | POL | 21-24 |
| Authority migration | `release/migration`, `authz` | 11 | AUTH | 25-28 |
| Domain-state reconstruction | `release/migration`, domain services | 05-09 | PLAN, GATE | 29-34 |
| Full execution-service wiring | `release/executors`, `ui/views/queues` | 10, 11, 16 | GOV, GATE | 35-40 |
| Shadow mode | `release/shadow` | 14, 16 | DELIVERY | 41-44 |
| Sustained parallel validation | `release/validation` | 14, 16 | DELIVERY | 45-52 |
| Discrepancy burn-down | `release/validation` | 14, 16 | GOV, DELIVERY | 53 |
| Operator acceptance testing | `release/uat` | 16 | DELIVERY | 54-58 |
| Migration rehearsal | `release/rehearsal` | 14, 16 | DELIVERY | 59-65 |
| Rollback rehearsal | `release/rehearsal` | 16 | DELIVERY, GATE | 66-70 |
| Recovery rehearsal | `release/rehearsal` | 14 | DELIVERY | 71-72 |
| Cutover runbook | `release/release` | 16 | DELIVERY | 73-75 |
| Release package | `release/release` | 16 | DELIVERY | 76-80 |
| Final readiness certification | `release/release` | 16 | GATE | 81-90 |
| Release authorization | `release/release` | 16 | GATE, AUTH | 91-98 |
| Restart durability | `release/store`, `db` | 14 | DELIVERY | 99 |
| Phase 11 pilot usable | `ops/*`, `ui/*` | 10, 14 | VIEW | 100 |
| Cross-phase greens | `tests/` | 15 | GATE | 101-111 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase12_readiness_authorization` | 15 | GATE | 112-113 |
| No irreversible cutover | `release/*`, `ops/pilot` | 15, 16 | GATE | 114 |

## Acceptance modules
- `test_phase12_migration` (1-34)
- `test_phase12_execution_validation` (35-80)
- `test_phase12_readiness_authorization` (81-114 + 64-fixture completeness)

## Dedicated regressions
- Live-execution (20-point): `tests/test_phase12_live_execution_regression`.
- Final-readiness (25-point): `tests/test_phase12_final_readiness_regression`.

## Final-phase discipline
Migration v12 holds NO business truth: real domain state lives in the Phase 2-9 records this layer
REFERENCES. Migration is not cutover; import success is not migration acceptance; migration acceptance is
not operational readiness; operational readiness is not go-live authorization; go-live authorization is not
automatic activation. GO_LIVE_AUTHORIZED can only be set by an authorized Principal's explicit governed
Decision — never by automated tests — and authorization performs no cutover. The legacy tool remains
available throughout; no irreversible production cutover or legacy retirement occurs. See
`adr/ADR-0047..0052`.

## Permanent prior-phase regressions retained
BUG-CPO-002 (FIXED_END_TO_END), the Service Loaner zero-mile, Executive Demo Best Overall, Phase 8 learning-
governance, Phase 9 governed-decision + authority-administration, Phase 10 operator-workflow + presentation-
integrity, and Phase 11 import-recovery + controlled-pilot regressions all remain green under migration v12
(items 101-111). The real live executors write real domain records through the real governed methods, so no
migration/reconstruction/validation/execution can raise Need or rewrite an issued result.
