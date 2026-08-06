# PHASE 10 APPLICATION ARCHITECTURE + REGISTRIES

The operator application (`elite/ui/`) is a server-rendered Python app built on the **stdlib only**
(`wsgiref`, `html`, `http.cookies`, `secrets`, `urllib.parse`) — no third-party web framework and no new
dependencies. It is a thin presentation layer over the Phase 1-9 services: it reads authoritative records
and never recomputes domain logic, routes every mutation through the governed services, and holds no
authoritative state in the browser.

## Architecture
- **`http.py`** — `Request`, `Response`, `Router` (path patterns with `{name}` segments). Responses set a
  strict `Content-Security-Policy` (`default-src 'self'`), `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, and `HttpOnly; SameSite=Strict` session cookies.
- **`app.py`** — `App` is a WSGI callable. It owns the router, an in-memory server-side session map (an
  opaque cookie token → Principal + scope + CSRF token), a safe dispatch/error boundary, and `handle()`
  for in-process testing (no socket). `App.require(session, capability)` enforces below-UI authorization
  via the Phase 1 authorizer.
- **`render.py`** — safe HTML helpers (`esc` for attributes, `esc_text` for verbatim prose), the shell
  layout, tables, key/value lists, forms (CSRF + idempotency nonce), status badges (text glyph + label,
  never color-only), and the safe error page. All CSS is inline and self-hosted; no external assets.
- **`prefs.py`** — presentation-state persistence (migration v10; non-authoritative).
- **`views/`** — one module per screen area (`auth`, `inbox`, `decision`, `queues`, `domains`, `govern`,
  `search`); `views.register(app)` wires all routes.
- **`serve.py`** — the local launcher (`python3 -m elite.ui.serve`) over `wsgiref.simple_server`.

## Route registry
| Method + path | Screen / action | Capability (below UI) |
|---|---|---|
| GET `/login`, POST `/login`, GET `/logout` | authenticated operator context | public |
| GET `/healthz`, GET `/help`, POST `/scope` | health / help / scope switch | session (scope switch checks a grant) |
| GET `/` | Today / Decision Inbox | `workspace.view` |
| GET `/item/{id}` | recommendation detail (Call/Why/Proof/Raw History) | `workspace.view` |
| GET+POST `/item/{id}/decide` | Decision issuance | `workspace.review` + `decision.issue`/`.override` |
| GET `/approvals`, POST `/approval/{id}/approve` | approval queue | `workspace.view` + `decision.approve` |
| GET `/execution`, POST `/execution/{id}/authorize|complete` | execution queue | `workspace.view` + `execution.authorize` |
| GET `/acknowledgments`, POST `/ack/{id}` | acknowledgment queue | `workspace.view` + `decision.acknowledge` |
| GET `/new-inventory` `/production` `/service-loaner` `/executive-demo` | domain workspaces | `workspace.view` |
| POST `/service-loaner/{id}/used-cars` | one-action Used Cars receipt | `service_loaner.used_cars_receipt.confirm` |
| GET `/scenarios` `/scenario/{id}` | Scenario administration + comparison | `workspace.view` |
| GET `/calibration` `/calibration/{id}` | Calibration review | `workspace.view` (activation via Phase 8) |
| GET `/authority`, POST `/authority/delegate` | authority administration | `authority.view` + `authority.delegate` |
| GET `/audit` | Audit review (read-only) | `audit.view` |
| GET `/exceptions`, POST `/exception/{id}/dismiss` | exception queues | `workspace.view` + `audit.exception.review` |
| GET `/summaries` | operational-control summaries | `workspace.view` |
| GET `/readiness` | domain readiness | `workspace.view` |
| GET `/search` | operator search (scope-filtered) | `workspace.view` |

## Navigation registry
Primary nav (capability-aware visibility, but visibility never replaces authorization — every screen
enforces its capability below the UI): Today / Decision Inbox, New Inventory, Production & Supply, Service
Loaners, Executive Demos, Scenarios, Learning & Calibration, Approvals, Execution, Exceptions, Audit,
Authority, Readiness.

## Decision Inbox contract
Rows are Phase 9 workspace items in the operator's scope. Each row shows Call, subject, domain, status
(text badge), priority, owner, and next governed action; Scenario-only and stale items carry a distinct
badge. The reconciling totals line prints every workspace-state count, which equals the store counts.
Filters (`domain`, `status`, `priority`) narrow the table without inventing authority or priority.

## Recommendation-detail contract
Four sections read from authoritative records: **Call** (the current recommended action / leave-alone
state), **Why** (business reasoning; absent reasoning shows *unknown*, never invented), **Proof**
(recommendation / Economic Call / Execution Status refs + accepted facts + applicable versions), and
**Raw History** (an evidence timeline: item opened → recommendation revisions → Decisions → approvals →
executions → reconciliations). Official vs Scenario and current vs historical are labeled distinctly. The
detail never recomputes domain logic.

## Domain workspace contracts
New Inventory reads `inventory_plan_result` (Demand / Current / Future / Committed / Need / Excess /
state) — no client recompute, one unit counted once. Production & Supply reads `supply_commitment` +
`commitment_reconciliation_result` (proposal vs committed distinct). Service Loaner reads
`service_loaner_unit` + `service_loaner_monitoring_alert` (membership vs rental distinct; the zero-mile
question verbatim; the Used Cars receipt is one action). Executive Demo reads
`executive_demo_portfolio_plan` (Best Overall pick + why, tradeoffs, labeled sacrifice; opportunity cost
separate from benefit).

## Mutation-action registry
Every state-changing route carries a CSRF token and a per-render idempotency nonce and calls exactly one
Phase 1-9 service: Decision issuance → `p9.decisions.issue`; approval → `p9.approvals.approve`; execution
→ `p9.execution.authorize`/`.complete`/`.reconcile`; acknowledgment → `p9.ack.acknowledge`; Used Cars →
`p6.retirement.confirm_used_cars_receipt`; delegation → `p9.authority.delegate`; exception dismissal →
`p9.queues.dismiss`; scope switch → `App.switch_scope`. No route mutates a domain record directly.

## Presentation-state registry (migration v10 — non-authoritative)
`operator_view_preference` (key/value), `saved_filter`, `saved_workspace_view`, `instructional_hint_state`,
`recent_operator_context`. These hold no business state; deleting any of them changes no Decision,
approval, execution, policy, identity, supply, Demand, Need, Economic Call, or governance state, and they
are freely deletable (no immutability triggers). No authoritative state is ever stored in browser
localStorage.

## Security + CSRF contract
Server-side sessions (opaque `HttpOnly; SameSite=Strict` cookie token). Every non-public POST requires a
`_csrf` field equal to the session token (mismatch → 403). Double submission is prevented by a per-render
`_idem` nonce threaded as the service idempotency key. Correlation IDs are preserved across the governed
call chain. A strict CSP and `X-Frame-Options: DENY` are set on every response. Below-UI authorization +
scope are enforced by the Phase 1 authorizer inside every handler.

## Error-handling contract
`App.handle` wraps every handler: `AuthorizationError` → a safe 403 ("Not permitted"); `ValidationError`/
`ConcurrencyError` → 409 with the user-facing message only; `PersistenceError` → 409 ("not applied,
nothing changed"); any other exception → a generic safe 500. No stack trace, technical detail, or secret
is ever rendered to an operator.

## Accessibility checklist
Semantic landmarks (`banner`, `navigation`, `main`) and headings; every form control has an associated
`<label>`; primary actions are real `<button>` elements (keyboard-focusable) with a visible `:focus`
outline; status is conveyed by a text glyph + label, never color alone; layouts are responsive
(`max-width` + a mobile media query); validation/permission errors render as clear `role="alert"`
messages; empty states and failure states are usable (with a way back).
