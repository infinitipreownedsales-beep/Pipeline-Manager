# PHASE 10 TRACEABILITY — operator experience → specification

Owning segments per spec Heading-1 titles; requirement families named (exact IDs bind at review against
the canonical DOCX / `requirement_index.json`).

| Phase 10 capability | Module(s) | Segment | Families | Acceptance |
|---|---|---|---|---|
| Application shell + authenticated context | `ui/app`, `ui/render`, `ui/views/auth` | 10, 11 | VIEW, AUTH | 1-8 |
| Navigation | `ui/render` (NAV) | 10 | VIEW | 1 |
| Decision Inbox | `ui/views/inbox`, `govern/store` | 10 | VIEW, GOV | 9-12 |
| Recommendation detail + Raw History | `ui/views/inbox`, `govern/workspace` | 10 | VIEW, GOV | 13-19 |
| New Inventory workspace | `ui/views/domains`, `newinv` | 10, 07 | VIEW, PLAN | 20-23 |
| Production & Supply workspace | `ui/views/domains`, `workflow` | 10, 08 | VIEW, SUPPLY | 24-28 |
| Service Loaner workspace | `ui/views/domains`, `loaner` | 10, 08 | VIEW, LOANER | 29-34 |
| Executive Demo workspace | `ui/views/domains`, `execdemo` | 10, 09 | VIEW, DEMO | 35-40 |
| Decision-issuance experience | `ui/views/decision`, `govern/decision` | 10, 11 | VIEW, GOV, AUTH | 41-48 |
| Approval / execution / acknowledgment queues | `ui/views/queues`, `govern/{approval,execution,acknowledge}` | 10, 11 | VIEW, GOV | 49-60 |
| Scenario administration | `ui/views/govern`, `govern/scenario_admin` | 10, 11 | VIEW, GOV, POL | 61-66 |
| Calibration review | `ui/views/govern`, `govern/calibration_workspace`, `learning/calibration` | 10, 12 | VIEW, CALIB | 67-70 |
| Authority administration | `ui/views/govern`, `govern/authority`, `authz` | 10, 11 | VIEW, AUTH | 71-76 |
| Audit review | `ui/views/govern`, `govern/audit_admin`, `audit` | 10, 11 | VIEW, AUDIT | 77-79 |
| Exception + unresolved queues | `ui/views/govern`, `govern/queues` | 10, 11 | VIEW, GOV | 80-82 |
| Operational-control summaries | `ui/views/govern`, `govern/summaries` | 10 | VIEW | 83 |
| Domain readiness | `ui/views/govern`, `govern/readiness` | 10, 11 | VIEW, DELIVERY | 84-88 |
| Operator search | `ui/views/search` | 10 | VIEW | 89-90 |
| Security / CSRF / sessions | `ui/app`, `ui/http`, `ui/render` | 10, 11 | SEC, AUTH | 91-95 |
| Accessibility / usability | `ui/render` | 10 | VIEW, A11Y | 96-100 |
| Presentation-state persistence | `ui/prefs`, `db.py` (v10) | 10 | VIEW, TRANS | 91, 92, 108, 109 |
| End-to-end operator workflows | `ui/*`, `govern/*`, domain services | 10, 11 | VIEW, GOV | 101-107 |
| Cross-phase greens | `tests/` | 15 | GATE | 110-118 |
| Legacy-line invariants | `tests/test_legacy_guard`, `tests/test_phase10_workflows_cross` | 15 | DELIVERY, GATE | 119, 120 |
| No-out-of-scope-behavior guard | `tests/test_phase10_workflows_cross` | 15 | GATE | 121 |

## Dedicated regressions
Operator-workflow (20-point): `tests/test_phase10_operator_workflow_regression`.
Presentation-integrity (15-point): `tests/test_phase10_presentation_integrity_regression`.

## Authoritative-read discipline
The UI reads authoritative Phase 1-9 records and defines no domain formula. The presentation-integrity
regression asserts displayed Demand/Supply/Need/Economic-Call/Execution-Status/Decision/approval/execution
equal the stored values and that the UI source contains no alternative Demand/Need/economic formula
(`test_phase10_presentation_integrity_regression`; `test_phase10_domains.test_23`;
`test_phase10_workflows_cross.test_121`). See `adr/ADR-0036`.

## Permanent prior-phase regressions retained
BUG-CPO-002 (`test_phase4_bug_cpo_002`, `test_phase5_bug_cpo_002_e2e`), the Service Loaner zero-mile
regression (`test_phase6_monitoring`), the Executive Demo Best Overall regression
(`test_phase7_preference_bestoverall`), the Phase 8 learning-governance regression, and the Phase 9
governed-decision + authority-administration regressions all remain green under migration v10
(items 110-118).
