# PHASE 12 ARCHITECTURE + CONTRACTS/REGISTRIES

Phase 12 (`elite/release/`) is the **final engineering + validation** layer. It wires every required real
Phase 5-7 executor behind the governed pilot actions, migrates real data into a **dedicated migration
database**, runs shadow mode + a sustained parallel run with governed discrepancy burn-down, conducts
operator acceptance testing, performs proven migration/rollback/recovery rehearsals, issues an immutable
release package, and produces a governed final readiness certification + an explicit release-authorization
gate. Python **stdlib only — no new dependency**. **No irreversible production cutover occurs.**

## Package map
| Module | Responsibility |
|---|---|
| `models.py` | constants (outcomes, statuses, dimensions, dispositions, shadow modes) + capabilities |
| `store.py` | repositories for the migration-v12 records |
| `executors.py` | `LiveExecutorRegistry` + `LiveExecutionService` (real Phase 5-7 wiring) |
| `migration.py` | live-source inventory, adapters, ingestion, identity/fact/policy/authority migration, reconstruction |
| `shadow.py` | domain shadow mode (governed, event-logged) |
| `validation.py` | sustained parallel validation + governed discrepancy burn-down |
| `uat.py` | operator acceptance testing on the real application |
| `rehearsal.py` | migration / rollback / recovery rehearsals |
| `release.py` | release package, final readiness certification, release-authorization gate, cutover runbook |
| `fixtures.py` | Phase 12 stack + 64 fixtures |

## Live-execution wiring (ADR-0047) — resolving the Phase 11 limitation
The Phase 11 pilot execution path used a synthetic callback. Phase 12 replaces it: a `LiveExecutorRegistry`
binds each governed action to the **actual Phase 5-7 governed domain method** (e.g. `execdemo.retirement.
execute`, `loaner.units.execute_entry`). `LiveExecutionService.execute(...)` (1) invokes the real domain
method — its own `Governor.perform` produces a real domain event + Audit Event + optimistic-concurrency/
idempotency — then (2) references that real domain reference in the Phase 9 execution authorization /
completion / reconciliation (Phase 9 references domain execution, never duplicates it). The Phase 10 UI
`/execution/{id}/authorize` handler uses `app.live_executor` when a Decision is bound (else the prior
reference path, keeping Phase 10/11 green). Guarantees: no synthetic callback in the real path; no direct
domain-table mutation from the UI; the actual result is displayed; a failed execution is never shown as
success (a domain not in an execution-enabled shadow mode is refused); execution is idempotent; the audit +
correlation chain is linked; state survives restart; concurrent replay does not duplicate; a Scenario
Decision can never enter the official path.

## Live-source connection inventory
`live_source_connection` records, per source family: actual system, owner, access method, availability,
authentication/delivery, environment, cadence, expected timing, Full/Partial snapshot capability, actual
schema, schema-drift risk, real identity fields, effective-time behavior, correction behavior, absence
semantics, operational dependency, fallback procedure, integration status, and any unresolved access
blocker. Every source carries a classification: `MANUAL_GOVERNED / FILE_EXPORT / API_AVAILABLE /
ACCESS_PENDING / UNAVAILABLE / OUT_OF_SCOPE`. Integration is never fabricated — an unavailable source is
classified, not faked.

## Real adapter configuration + controlled ingestion
Actual schemas receive explicit registered versions (`live_source_schema_version`); mappings are
reviewable; every transformed field retains source lineage; unsupported columns stay visible; missing
fields get no invented default; blank/zero/missing/invalid stay distinct; effective time comes from the
source contract; a corrected adapter is a NEW version and prior imports remain replayable; test fixtures are
kept separate from real migration data. Controlled ingestion drives the real Phase 11 adapters/orchestrator
into a **dedicated migration/pilot database** (never production-primary); each source records
`migration_run_source` statistics that reconcile to row-level `migration_fact_reconciliation`; a repeated
real import is idempotent; a failed import preserves the prior valid state; Partial stays Partial; a Full-
Snapshot absence follows its approved contract only.

## Identity migration
`migration_identity_reconciliation` outcomes: `MATCHED_EXISTING / CREATED_CANONICAL / ALIAS_LINKED /
PREVIN_LINKED_TO_VIN / DUPLICATE_RECONCILED / CONFLICTING_IDENTITY / UNRESOLVED_IDENTITY / EXCLUDED_INVALID
/ CORRECTION_REQUIRED`. One physical unit stays one Vehicle Unit; a pre-VIN order transitioning to a VIN
stays one future identity; cross-domain fleet conflict stays blocked; unresolved identities cannot silently
enter calculations; corrections preserve the original mapping; manual resolution requires authority, a
reason, and an Audit Event (governed).

## Historical migration
No missing event is invented; snapshot history is flagged as a point (`SNAPSHOT_POINT`), never false
continuous availability; the migration date never replaces the business/event date; a duplicate historical
row does not become a new fact; corrections/reversals preserve history; totals reconcile to accepted source
rows; historical source and calculated legacy output remain distinguishable.

## Policy + authority migration
`migration_policy_resolution` is created only from a CONFIRMED dealership value (owner + evidence + scope +
effective date + authority all required — a synthetic/unattested value cannot become official policy);
missing required policy blocks affected-domain readiness; conflicting proposals stay conflicting; official
activation follows Phase 3 governance; migration is reversible prospectively. `migration_authority_
configuration` grants real capabilities at an EXPLICIT scope (governed + audited); an overbroad grant
(`*` scope or capability) is rejected; proposal/approval/execution/completion/correction/activation/rollback
remain distinct; temporary grants expire; missing authority blocks the related workflow; default shared
accounts are prohibited.

## Shadow mode (ADR-0048)
`domain_shadow_mode` is a governed, immutable event log (the latest row is the current mode; history is
preserved). States: `DATA_ONLY / CALCULATE_ONLY / REVIEW_ONLY / DECISION_PILOT / EXECUTION_PILOT /
CUTOVER_ELIGIBLE / BLOCKED`. Mode is visible + domain-specific; no domain advances automatically; execution
stays blocked unless a mode explicitly enables it (`EXECUTION_PILOT` / `CUTOVER_ELIGIBLE`); every change is
governed + audited.

## Sustained parallel validation (ADR-0050)
`parallel_validation_run` + `parallel_validation_result` capture dated Elite-vs-legacy comparisons,
preserve BOTH outputs, classify each difference (`MATCH / DATA / TIMING / IDENTITY / POLICY / CALCULATION /
ELITE_DEFECT / LEGACY_LIMITATION / EXPECTED_DIFFERENCE / UNRESOLVED`), and mutate neither tool. The required
duration + sample coverage are an approved release criterion (not a hardcoded number). A material unresolved
difference blocks affected-domain readiness.

## Discrepancy burn-down (ADR-0050)
`discrepancy_record` + immutable `discrepancy_transition` are governed. Statuses: `OPEN / TRIAGED /
DATA_CORRECTION_REQUIRED / IDENTITY_CORRECTION_REQUIRED / POLICY_REVIEW_REQUIRED / ELITE_DEFECT_CONFIRMED /
LEGACY_LIMITATION_CONFIRMED / EXPECTED_DIFFERENCE / ACCEPTED_WITH_WARNING / RESOLVED / BLOCKING / CLOSED`.
Classification requires evidence; a confirmed Elite defect enters the defect registry; closing a discrepancy
alters neither historical result; burn-down metrics reconcile to discrepancy records.

## Operator acceptance testing
`operator_acceptance_test` + immutable `operator_acceptance_result` are conducted on the real application by
operators (not developer tests); a failure remains historical; a retest is a new result linked to the
original (never erased); a material failure blocks affected-domain readiness; missing operator sign-off
stays missing.

## Rehearsals (ADR-0051)
`migration_rehearsal` starts from a CLEAN database, applies migrations v1-v12, seeds approved data, backs
up, simulates restart, and reconciles counts (immutable evidence, repeatable, hashes + duration recorded).
`rollback_rehearsal` proves operational control returns to the legacy tool (Elite history preserved, legacy
available, in-flight actions identified, no replay into legacy). `recovery_rehearsal` preserves committed
truth and identifies unresolved consequences. A failed rehearsal blocks readiness. Rollback is **proven,
not merely documented.**

## Release package (ADR-0052)
`release_package` (immutable once issued) + immutable `release_package_artifact` pin the application
revision, migration level, config template, source registry, adapter versions, policy/calc/model/comparison
versions, authority matrix, unresolved risks, discrepancy status, UAT + rehearsal + backup + health
evidence, certification, checksum manifest, release notes, and known limitations. A `cutover_runbook_
reference` documents prerequisites, abort criteria, rollback trigger + steps — and does not execute itself.

## Final readiness certification + authorization (ADR-0049)
`final_readiness_certification` + immutable `final_readiness_dimension` assess ten separate dimensions —
`ENGINEERING_READY / DATA_READY / POLICY_READY / AUTHORITY_READY / OPERATOR_READY / MIGRATION_READY /
ROLLBACK_READY / SECURITY_READY / OPERATIONALLY_READY / GO_LIVE_AUTHORIZED` — each `PASS / PASS_WITH_WARNINGS
/ FAIL / UNRESOLVED / NOT_APPLICABLE`. `OPERATIONALLY_READY` is DERIVED from the eight prerequisite
dimensions (it cannot be asserted directly by a test). `GO_LIVE_AUTHORIZED` is **never** set by
certification — it reflects the separate authorization state. A later failed check supersedes prior
readiness; prior certifications remain historical; readiness and authorization stay separately inspectable.
`release_authorization_decision` is the explicit governed release Decision (`AUTHORIZE_GO_LIVE /
AUTHORIZE_LIMITED_DOMAIN_GO_LIVE / CONTINUE_PARALLEL_RUN / DEFER / REJECT / ROLLBACK_REQUIRED`): it requires
an issued package + an operationally-ready certification (for go-live) + an authorized Principal; a
limited-domain authorization names its exact domains; the Decision + Audit Event are atomic; an expired
authorization cannot be used; **authorization does not itself perform cutover**, and no authorization leaves
the system in parallel pilot mode. GO_LIVE_AUTHORIZED can only be set by an authorized Principal's explicit
governed Decision, never by automated tests.

## Migration v12 (append-preserving; no business truth moved; release package immutable once issued)
24 record families: `live_source_connection`, `live_source_schema_version`, `migration_run`,
`migration_run_source`, `migration_identity_reconciliation`, `migration_fact_reconciliation`,
`migration_policy_resolution`, `migration_authority_configuration`, `domain_shadow_mode`,
`parallel_validation_run`, `parallel_validation_result`, `discrepancy_record`, `discrepancy_transition`,
`operator_acceptance_test`, `operator_acceptance_result`, `migration_rehearsal`, `rollback_rehearsal`,
`recovery_rehearsal`, `release_package`, `release_package_artifact`, `final_readiness_certification`,
`final_readiness_dimension`, `release_authorization_decision`, `cutover_runbook_reference`. Point-in-time
evidence rows are immutable (no-update + no-delete); lifecycle/registry rows are append-preserving
(no-delete); a release package is immutable once issued (trigger). v1-v11 are untouched; the migration is
rerun-safe; no cutover state is ever automatically activated.
