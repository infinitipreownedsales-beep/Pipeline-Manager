# PHASE 10 COMPLETION PACKET — Operator Experience and Presentation Layer

- **Branch:** `elite-pipeline/phase-0`
- **Legacy protected line:** `legacy/inventory-tool` @ `3bf9162` (unchanged)
- **New code:** `elite/ui/` (+ migration v10 in `elite/db.py` — presentation-only). No legacy file changed.
- **Scope:** the first complete operator-facing application, built strictly on the Phase 9 output slices
  and Phase 1-8 authoritative read models. The interface **reads** authoritative records and **never
  recomputes domain logic**; every mutation routes through the governed Phase 1-9 services; browser /
  localStorage state is never authoritative; below-UI authorization + scope are never bypassed.

## Implemented
A server-rendered operator application (stdlib WSGI via `wsgiref`; **no new dependencies**): an
application shell (name/environment, authenticated Principal, current store scope, primary navigation,
attention count, freshness + data-quality indicators, current revision, help, a safe error boundary, and
unauthorized/out-of-scope states); a unified Decision Inbox from the Phase 9 workspace records (counts
reconcile to source; filters; Scenario-only and stale items visually distinct); a consistent
recommendation-detail pattern exposing **Call / Why / Proof / Raw History** (an evidence timeline of
source observations → facts → corrections → versions → prior results → Decisions → approvals → execution
→ Audit Events) that reads authoritative records and never recomputes (missing explanation stays
unknown; official vs Scenario and current vs historical are distinguishable); New Inventory, Production &
Supply, Service Loaner, and Executive Demo workspaces (every number read from the Phase 4-7 stores —
proposal vs committed, membership vs rental, Economic Call vs Execution Status distinct; the zero-mile
question shown verbatim; Used Cars confirmed in one action; Best Overall shows why it wins with visible
tradeoffs and a labeled necessary sacrifice; one physical unit counted once); the governed
Decision-issuance experience (9 dispositions, exact recommendation revision, presented alternatives,
optional rationale, override-with-reason, stale guard, per-render idempotency nonce → double-submit
safe, Scenario-only); approval / execution / acknowledgment queues (separate approval authority + visible
separation-of-duties, approval ≠ execution, execution invokes the real domain service and never shows a
failed run as completed, Scenario Decisions cannot execute officially, idempotent replays); Scenario
administration; Calibration review (over Phase 8 records; approval ≠ activation; scheduled =
future-effective; policy target → review); authority administration (over the Phase 1 grants, with grant
chains and immediate revocation, governed + audited mutations); read-only Audit review (immutable;
correlated traces; missing-event exceptions; scoped + authorized); exception + unresolved queues
(reference source; closing never resolves source; dismissal needs authority + reason); operational-
control summaries (reconcile to source); domain readiness (evidence-based; synthetic-only insufficient;
never deploys); operator search (scope-filtered, links to authoritative detail); and durable
presentation preferences (migration v10 — non-authoritative; deletion changes no business state). Safe
templating with output encoding everywhere, a strict CSP + `HttpOnly`/`SameSite` server-side session,
CSRF tokens on every state-changing action, correlation-ID preservation, and a safe error boundary that
never leaks stack traces or secrets.

**Not built (guarded, item 121):** Phase-11 operational hardening, live-source deployment, broad real-
data migration, cutover, and legacy replacement. New Inventory / production workflows / Service Loaner /
Executive Demo / Learning / Governance stay distinguishable; no universal red/yellow/green score replaces
domain truth.

## Acceptance evidence (121 mandatory items, all executed)
| # | Group | Test module |
|---|---|---|
| 1-8 | Shell, identity, scope, unauthorized/out-of-scope/revoked, freshness, stale | `test_phase10_shell_inbox` |
| 9-12 | Decision Inbox — counts reconcile, filters, Scenario/stale distinct | `test_phase10_shell_inbox` |
| 13-19 | Recommendation detail — Call/Why/Proof/Raw History, unknown, historical/official distinct | `test_phase10_shell_inbox` |
| 20-23 | New Inventory — totals/monthly match Phase 4, supply kinds distinct, no UI recompute | `test_phase10_domains` |
| 24-28 | Production & Supply — proposal vs committed, ETA preserved, reconciliation | `test_phase10_domains` |
| 29-34 | Service Loaner — membership/rental distinct, exact zero-mile question, provisional≠complete, one-action receipt, Call≠Status | `test_phase10_domains` |
| 35-40 | Executive Demo — Best Overall why, tradeoffs, sacrifice, cost≠benefit, designation≠active, separate from loaner | `test_phase10_domains` |
| 41-48 | Decision issuance — revision, blank rationale, override reason, stale guard, invokes service, no-duplicate, audit-failure, scenario-can't-execute | `test_phase10_decision_queues` |
| 49-52 | Approval — separate authority, SoD visible+enforced, ≠ execution, expired can't proceed | `test_phase10_decision_queues` |
| 53-57 | Execution — uses domain service, failed≠completed, stages inspectable, conflict unresolved, no-duplicate | `test_phase10_decision_queues` |
| 58-60 | Acknowledgment — ≠ approval/execution, idempotent | `test_phase10_decision_queues` |
| 61-66 | Scenario admin — hypothetical, sharing≠approval, discussion≠official, promotion no effect, overrides shown, scoped | `test_phase10_govern` |
| 67-70 | Calibration — approval≠activation, scheduled future-effective, policy→review, prior Predictions unchanged | `test_phase10_govern` |
| 71-76 | Authority — Phase 1 records, grant chain, expired/revoked inactive, governed mutation, audit-failure | `test_phase10_govern` |
| 77-79 | Audit — read-only, correlated trace, missing-event exception | `test_phase10_govern` |
| 80-82 | Exceptions — link source, close preserves source, dismissal needs authority+reason | `test_phase10_govern` |
| 83 | Summaries reconcile to source | `test_phase10_govern` |
| 84-88 | Readiness — evidence-based, synthetic-insufficient, missing policy/authority block, no deploy | `test_phase10_govern` |
| 89-90 | Search — scope-filtered, links authoritative detail | `test_phase10_govern` |
| 91-95 | Security — no localStorage authoritative, pref deletion inert, CSRF, double-submit, no trace/secret | `test_phase10_security_a11y` |
| 96-100 | Accessibility — keyboard actions, non-color status, form labels, empty + failure states | `test_phase10_security_a11y` |
| 101-107 | End-to-end operator workflows through real services | `test_phase10_workflows_cross` |
| 108-109 | Presentation persistence survives restart; migration v10 rerun-safe | `test_phase10_workflows_cross` |
| 110-118 | Phase 1-9 tests remain green | `test_phase10_workflows_cross` |
| 119-120 | Legacy 39/39; legacy paths unchanged | `test_phase10_workflows_cross` (+ `test_legacy_guard`) |
| 121 | No Phase-11 hardening/deploy/migration/cutover; UI recomputes no domain math | `test_phase10_workflows_cross` |

**Fixtures:** 40 operator-facing scenarios (`ui/fixtures.build_all_scenarios`, `SCENARIO_NAMES`),
completeness proven by `test_phase10_workflows_cross.test_121b`.

**Platform harness:** `717/717 passed` (26 P1 + 35 P2 + 59 P3 + 65 P4 + 81 P5 + 79 P6 + 79 P7 + 91 P8 +
104 P9 + 98 P10). **Legacy:** `39/39` (29 engine + 10 loaner).

## Dedicated operator-workflow regression (20-point)
`elite/tests/test_phase10_operator_workflow_regression.TestOperatorWorkflowRegression` drives the full
loop through the UI routes and real services: open inbox → open an authoritative recommendation →
Call/Why/Proof/Raw History visible → issue Decision (audited) → separate approver approves under an
enforced separation-of-duties rule → approval does not execute → authorized executor initiates the real
domain service returning an actual event → completion + reconciliation shown → repeated submission does
not duplicate → a new fact makes the recommendation stale → stale cannot execute → an authorized override
requires a reason → a Scenario recommendation cannot execute officially → the correlation ID is preserved
→ no domain calculation happens in the UI → prior recommendation + Decision remain historical → an audit
failure produces a visible safe failure → the legacy application remains untouched.

## Dedicated presentation-integrity regression (15-point)
`elite/tests/test_phase10_presentation_integrity_regression.TestPresentationIntegrityRegression` proves
the UI is a faithful window: displayed Demand/Supply/Need match the stored plan; Economic Call vs
Execution Status vs Decision vs approval vs execution are shown from stored records; the UI contains no
alternative Demand/Need/economic formula; presentation state cannot alter authoritative values; refresh
reproduces the same display; historical vs current are separable; and a Scenario result cannot replace an
official one.

## Local startup instructions
```
export ELITE_ENV=development
export ELITE_DB_PATH=/path/to/elite.db
PYTHONPATH=. python3 -m elite.ui.serve            # serves the operator app on 127.0.0.1:8010
# then open http://127.0.0.1:8010/login  (sign in with an operator id + password + store scope)
```
`elite/ui/app.make_server(app)` wraps the stdlib `wsgiref.simple_server`; the app is a standard WSGI
callable and is fully driveable in-process (no socket) via `elite.ui.fixtures.Client`.

## Legacy-line verification
`git diff legacy/inventory-tool -- build Pipeline-Manager.html pipeline_manager` is empty;
`legacy/inventory-tool` remains at `3bf9162`.

## Remaining risks
- Execution authorization references the domain execution service through a caller-supplied
  ref/`domain_execute_fn` (synthetic in fixtures); wiring each real Phase 5-7 executor call behind the UI
  action is a later integration concern (the reference contract, idempotency, and completion/
  reconciliation guarantees are in place).
- The presentation layer is intentionally minimal (semantic HTML + inline CSS, no client JS); richer
  interaction and full visual design are deferred (Phase-11+), out of Phase 10 scope by contract.

## Status
**HOLD FOR REVIEW.** Phase 11 not started.
