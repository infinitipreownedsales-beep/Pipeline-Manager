# PHASE 11 OPERATIONAL ARCHITECTURE + CONTRACTS/REGISTRIES

The Phase 11 operational layer (`elite/ops/`) hardens the Phase 10 application for a **controlled
dealership pilot alongside the legacy tool**. It is built on the Python **stdlib only** (`sqlite3`, `csv`,
`json`, `hashlib`, `http.cookies`, `wsgiref` via Phase 10) — **no new dependency**. Nothing here holds
business truth: it only describes how source data was ingested, reconciled, scheduled, backed up, compared,
and reviewed. Raw source stays preserved in the Phase 2 records; these tables only REFERENCE it. **No
cutover occurs in Phase 11.**

## Package map
| Module | Responsibility |
|---|---|
| `contracts.py` | source-contract registry (the real pilot source families) |
| `adapters.py` | source adapters over Phase 2 ingestion (delimited / JSON / manual) |
| `intake.py` | controlled file intake (allowlist, size, sanitization, hash, quarantine) |
| `imports.py` | import-run orchestration (state machine, idempotency, retry, failure) |
| `reconcile.py` | operational reconciliation + drift (references exact records) |
| `freshness.py` | domain-aware freshness (effective-time + cadence) |
| `scheduler.py` | controlled scheduling (idempotent, missed, overlap, explicit tz) |
| `recovery.py` | restart / crash recovery (in-flight runs → failed/reviewable) |
| `durability.py` | SQLite durability settings + integrity + startup validation |
| `backup.py` | transactionally-consistent backup + restore validation |
| `health.py` | liveness / readiness / operational health |
| `observability.py` | safe operational logging (VIN masking, secret/PII scrub) |
| `performance.py` | performance-baseline measurement |
| `security.py` | session expiry/invalidation, cookie flags, hardening checklist |
| `opsconfig.py` | operational configuration (safe defaults, startup validation) |
| `pilot.py` | pilot mode + parallel-run comparison + feedback + certification |
| `store.py` | repositories for the migration-v11 operational records |
| `cli.py` | pilot packaging commands (diagnostics/health/import/backup/restore/scheduler/serve) |
| `fixtures.py` | Phase 11 stack + 60 operational fixtures |

## Source-contract registry (`contracts.SOURCE_CONTRACTS`)
Each pilot source family declares: owner, source system, access method, file/interface kind, cadence,
Full/Partial snapshot capability, identity keys, effective-time semantics (never file import time),
update-time semantics, schema version, required + optional fields, units, blank/zero/missing behavior,
duplicate behavior, correction behavior, deletion/absence semantics, quality thresholds, blocking vs
nonblocking validation, raw-retention requirement, and expected reconciliation. Families: current New
Inventory, Production Orders, retail history, vehicle identity, arrival/availability, Service Loaner fleet,
Service Loaner status, Service Loaner in-service date, Service Loaner Last Checkout Mileage, Executive Demo
state, policy/incentive inputs, user/authority config, and (optional, where authorized) market/value/
residual. Where no automated source exists, `access="manual_governed"` — a governed operator input, never a
fabricated feed. The registry **invents no source access**.

## Source-adapter architecture (ADR-0041)
An adapter turns a real payload into the Phase 2 **canonical ingestion contract** (`rows` + preserved
`raw_text` + ingestion parameters). Adapters ONLY parse: they never write domain results, resolve identity,
or compute domain math. Schema detection is explicit — a missing required column, an unsupported schema,
invalid UTF-8 encoding, or a fully malformed delimiter **fails safely** (`ValidationError`) at the
VALIDATING stage. Encoding, delimiter, date, decimal, currency, and blank handling are deterministic; the
adapter never coerces blank→zero (Phase 2 owns the sentinels). Every produced row keeps its original file
line for traceability. The adapter version is recorded on every import run (`source_adapter_version`).
Supported kinds: `csv`/`tsv`/`txt`/`spreadsheet_export` (delimited), `json`, and `manual`.

## File-intake contract
Extension allowlist (`.csv/.tsv/.txt/.json`) + explicit executable denylist; bounded size; filename
sanitization (basename only, unsafe characters replaced, `..`/null-byte/traversal refused); content hash;
duplicate detection (never a silent overwrite); quarantine for a rejected file (a receipt is still written,
referencing the rejection reason); upload authorization + scope. A `source_file_receipt` references the
retained raw evidence and is never deleted by cleanup.

## Import-run orchestration (ADR-0042)
State machine: `RECEIVED → VALIDATING → VALIDATED → INGESTING → INGESTED → RECONCILING → COMPLETED /
COMPLETED_WITH_WARNINGS`, with `REJECTED / FAILED / CANCELLED / SUPERSEDED`. Guarantees: **same content is
idempotent** (a prior COMPLETED run with the same content hash short-circuits; Phase 2 ingestion is itself
idempotent, so replay adds no facts); **a failed import preserves the prior accepted state** (Phase 2
ingestion is atomic — an interruption before or during acceptance commits nothing); **partial ingestion
never masquerades as complete** (only `INGESTED→RECONCILING→COMPLETED` reaches completion; a failure lands
in FAILED); **a retry links to the failed run** (`retry_of`); the operator sees a **safe, actionable
failure** (`import_run_error` holds a safe message — never a secret or a raw customer row). Import success
is not acceptance; acceptance is not reconciliation; reconciliation is not automatic business action.

## Freshness contract
Freshness is computed from the source **effective time** and expected cadence — never file import time. A
freshly uploaded snapshot with a stale effective date is therefore STALE. Statuses: `CURRENT / AGING /
STALE / MISSING / FAILED / CONFLICTING / UNRESOLVED`. STALE/MISSING/FAILED/CONFLICTING reduce visible
confidence and **block readiness** for the affected domain. Each evaluation appends an immutable freshness
result; a restored-current reading never erases prior stale history, and freshness never rewrites a
historical issued result.

## Reconciliation / drift contract
Reconciliation references the **exact** source observation and domain record. Outcomes: `MATCHED / NEW /
CHANGED / MISSING_EXPECTED / EXTRA / DUPLICATE / IDENTITY_UNRESOLVED / CONFLICTING / STALE /
LEGACY_DIFFERENCE / UNRESOLVED`. A difference is evidence — it **never auto-corrects** a domain record.
Full/Partial Snapshot semantics from Phase 2 are preserved (a Full-Snapshot absence yields
`MISSING_EXPECTED`, never a deletion). One physical unit is never duplicated by reconciliation. An
undeterminable cause stays `UNRESOLVED`/unknown. Reconciliation history is append-preserving.

## Scheduling contract
Stable `job_key`; firing is idempotent (a repeat fire for the same instant does not repeat work — a UNIQUE
claim row guards it); an overlapping run does not duplicate work; a missed run is recorded visibly;
schedules carry an explicit timezone; business-effective time is owned by the source, so clock drift / DST
never shift a business period; a manual run is distinguishable (`trigger`); scheduler failure records a
failed run and corrupts nothing.

## Restart / recovery contract
A committed transaction stays committed; a rolled-back transaction left no partial authoritative state
(Phase 2 ingestion + Phase 1 Governor are atomic). On restart an in-flight import run
(`RECEIVED/VALIDATING/VALIDATED/INGESTING/RECONCILING`) becomes FAILED and reviewable, recording the stage
it was interrupted at. Recovery is idempotent (a terminal run is untouched — nothing is replayed) and never
deletes evidence.

## Concurrency contract
Optimistic concurrency + idempotency guarantee exactly-once effects: simultaneous Decision / approval /
execution / receipt submissions produce one authoritative effect (the shared Governor idempotency key);
a stale browser submission is rejected by the workspace version guard (`ConcurrencyError` → UI 409). No
silent lost update; no duplicate commitment, receipt, activation, or Current-Supply record.

## SQLite durability contract
Foreign keys ON; WAL journal mode; `synchronous=NORMAL` (safe under WAL); a busy timeout so a briefly
locked database waits rather than erroring. Integrity check and startup validation (migrations current +
integrity ok + foreign keys enforced) are executable on demand. Durability is not changed without evidence
and tests. (ADR-0043)

## Backup / restore contract (ADR-0044)
Backups use SQLite's online backup API for a **transactionally consistent** copy, are timestamped,
content-hashed, integrity-verified, and recorded with metadata (schema version + authoritative counts).
Restore validation copies a backup aside, confirms it starts, the migration version matches, and counts
reproduce. Retention marks old backups expired (the record is preserved; the raw source-file retention is
never replaced). A failed backup records a visible operational alert. **Phase 11 automates no destructive
production restore.**

## Health-check contract
Three distinct concerns: **liveness** (the process answers), **readiness** (safe to rely on now), and
**operational** (component detail: database, migrations, foreign keys, latest import, source freshness,
backup, critical exceptions). A live application may still be operationally NOT ready (a stale blocking
source, a failed uncorrected import, or an unreviewed material pilot discrepancy). Each check appends an
immutable `health_check_result`.

## Observability / logging contract
Structured operational logs carry timestamp, level, component, action, correlation ID, scope, actor,
outcome, safe error code, and duration. They contain **no** secret, token, session ID, or raw customer
personal information; VINs are masked to their last six characters; raw source rows are never copied into a
log; a logging failure never propagates into a governed action. A `contains_unsafe` guard can reject unsafe
log content rather than emit it. Logs are diagnostics, not an ungoverned data copy.

## Performance-baseline contract
Representative workloads (startup, primary workspaces, representative import, reconciliation, backup, full
harness) are measured and recorded as immutable `operational_metric` rows with environment, dataset size,
and cold/warm flag. These are baselines, not guarantees. Slow-query evidence guides indexing; optimization
must not change an authoritative result and introduces no caching that risks a stale authoritative display.

## Security-hardening + configuration contract
Session expiry + invalidation; environment-aware cookie flags (HttpOnly + SameSite=Strict always; Secure in
production/demo); CSRF, output encoding, scope isolation, authorization, and the safe error boundary carried
from Phase 10; a runnable hardening checklist (no default credential, secrets externalized, debug off
outside dev/test, safe host binding, pilot not labeled production). Configuration has safe defaults and
startup validation: a non-loopback bind host requires `ELITE_ALLOW_NONLOOPBACK=1`; an invalid port or size
fails clearly; secrets never live in source; safe diagnostics expose no secret; environment-specific config
never changes domain logic.

## Controlled pilot-mode contract (ADR-0046)
Pilot mode is visibly identified (banner + environment), keeps the legacy tool as the operational fallback,
and BLOCKS destructive cutover / legacy-replacement / destructive-migration / production-go-live actions.
Domain-by-domain viewing/review is permitted; governed actions still require explicit authority.

## Parallel-run comparison contract (ADR-0045)
A non-authoritative comparison captures a snapshot of the Elite result and the legacy result and classifies
the difference: `MATCH / DATA_DIFFERENCE / TIMING_DIFFERENCE / IDENTITY_DIFFERENCE / POLICY_DIFFERENCE /
CALCULATION_DIFFERENCE / LEGACY_LIMITATION / ELITE_LIMITATION / UNRESOLVED`. It **mutates neither** result
(only the review fields — reviewer/disposition/notes — are ever written, via a governed review); legacy is
not authoritative because it is legacy and Elite is not authoritative because it is new; an unknown cause
stays UNRESOLVED; reviewer rationale is stored only as supplied; a material unresolved difference blocks
readiness until reviewed.

## Operator-feedback contract
Structured feedback attaches to a screen + exact revision (and optionally a subject/recommendation/decision/
workflow/import/discrepancy). It never mutates authoritative data; an incorrect-result claim is recorded
with status `review` — a review, not an automatic correction (triage may not `auto_correct`). Feedback is
governed and carries an audit reference.

## Migration v11 (operational records — append-preserving; no business truth moved)
`import_run` (+`import_run_error`), `source_adapter_version`, `source_file_receipt`,
`source_freshness_result`, `source_reconciliation_result`, `scheduled_job` (+`scheduled_job_run`),
`health_check_result`, `backup_record` (+`restore_validation`), `pilot_comparison_run`
(+`pilot_comparison_result`), `operator_feedback`, `pilot_readiness_certification`, `operational_metric`,
`operational_log_reference`. Point-in-time evidence rows are immutable (no-update + no-delete); lifecycle
and registry rows are append-preserving (no-delete). No earlier migration is modified; raw source
references are retained; the migration is rerun-safe.
