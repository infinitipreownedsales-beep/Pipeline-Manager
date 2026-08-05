# PHASE 5 PRODUCTION / WORKFLOW DOMAIN MODEL (migration v5)

New tables added by migration v5 `production_supply_workflows` (appended; v1-v4 unchanged). All
payloads are JSON-in-SQLite behind repository methods (`workflow/store.py`). Governed workflow /
transition / reconciliation / issued records are append-preserving (DB triggers block deletes);
projections (pipeline / ETA) may be superseded but prior-as-known remains inspectable.

## Records
| Table | Purpose | Key invariants |
|---|---|---|
| `production_pipeline_projection` | Pipeline state from accepted orders + facts | order identity stable; pre-VIN→VIN one unit; conflicts explicit; cancelled/superseded emit no qualifying future supply; no-delete |
| `eta_history` | Revised ETA history | precision never exceeds evidence; revisions preserved; no-delete |
| `editability_result` | Production editability | operational truth; unknown≠editable; never changes Demand |
| `model_year_transition_result` | Model-year transition intel | preserves separate model-year identity; approved lineage governs inheritance |
| `incoming_risk_result` | Component-explained risk | lists reasons; classification derived; never one opaque score; no-delete |
| `supply_workflow` | Governed workflow (common lifecycle) | subject identity, combination, need ref, lifecycle; append-preserving; no-delete |
| `supply_workflow_transition` | Lifecycle transitions | append-only; each references a reconciliation + audit; no-delete |
| `supply_workflow_evidence` | Workflow evidence links | append |
| `cpo_action` / `ppo_action` | Discrete allocation detail | discrete unit/order identity |
| `dealer_trade_action` / `dealer_trade_status_history` | Trade detail + status trail | proposal→request→accept→complete/terminal |
| `ctp_action` / `ctp_change_detail` | Change-the-production detail | one order modified, not duplicated; original + proposed combos |
| `commitment_reconciliation_result` | Deterministic reconciliation | one of 10 outcomes; prior/new qualifying recorded; no-delete |
| `sequential_planning_run` / `sequential_planning_step` | Sequential recomputation | each intermediate state preserved; causing action recorded; no-delete on steps |
| `workflow_issued_output_reference` | Workflow-triggered issued outputs | identifies causing action; append; no-delete |
| `execution_confirmation` | Execution/outcome capture | received-unit reconciliation |

## Common workflow lifecycle
`DRAFT → PROPOSED → UNDER_REVIEW → APPROVED → COMMITTED → IN_EXECUTION → COMPLETED`, plus
`REJECTED / WITHDRAWN / CANCELLED / FAILED / SUPERSEDED / EXPIRED / UNRESOLVED`. Each domain
restricts the legal subset (`models.TRANSITIONS`): CPO/PPO approval commits directly
(`PROPOSED→COMMITTED`); Dealer Trade adds `EXPIRED` and `APPROVED→COMPLETED/FAILED`; CTP executes
`APPROVED→COMPLETED`. Illegal transitions and stale versions are rejected; every transition binds a
transition row + reconciliation result + any supply effect atomically with an Audit Event (Phase 1
Governor).

## Commitment reconciliation outcomes
`NO_SUPPLY_EFFECT`, `COMMITMENT_CREATED`, `ALREADY_REPRESENTED`, `COMMITMENT_UPDATED`,
`COMMITMENT_CANCELLED`, `COMPLETED_TO_CURRENT`, `FAILED_NO_EFFECT`, `UNRESOLVED_IDENTITY`,
`CONFLICTING`, `DUPLICATE_REPLAY`. Supply effects run through the Phase 4 Supply/commitment records
via raw inserts inside the governed transaction, so the Phase 4 qualifying-supply dedup guarantees
count-once and monotonicity: a commit for an already-represented identity is `ALREADY_REPRESENTED`
(no new unit); a completion moves a committed/future unit to Current Supply once; a replay is
`DUPLICATE_REPLAY` with no effect.

## Supply-effect atomicity
`newinv/store` exposes raw `insert_commitment` / `insert_current_supply` / `insert_future_supply`
that run on the governed connection, so a workflow's business write + supply effect + Audit Event
commit together. On idempotent replay the Governor short-circuits before the effect, and on audit
failure the whole transaction rolls back — a workflow can never be reported successful without its
audit, and never double-applies a supply effect.
