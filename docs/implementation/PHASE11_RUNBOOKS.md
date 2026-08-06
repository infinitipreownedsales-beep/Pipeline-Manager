# PHASE 11 PILOT RUNBOOKS + GUIDES

Operational runbooks, configuration reference, performance-baseline report, and the pilot operator +
administrator guides for the controlled dealership pilot. The pilot runs **alongside** the legacy tool;
the legacy tool remains the operational fallback. **No cutover in Phase 11.**

## Deployment + startup
```
# 1. configure the environment (no secrets in source control)
export ELITE_ENV=development                 # development | test | demo (NOT production in the pilot)
export ELITE_DB_PATH=/path/to/pilot/elite.db
export ELITE_AUTH_SECRET=...                 # credential-hash pepper, from a secret store / env only
export ELITE_DEALERSHIP_TZ=America/Chicago
export ELITE_PILOT_SCOPE=store:HG            # the pilot store scope
# operational config (all have safe defaults):
export ELITE_UPLOAD_DIR=/path/to/pilot/uploads
export ELITE_RAW_RETENTION_DIR=/path/to/pilot/raw
export ELITE_QUARANTINE_DIR=/path/to/pilot/quarantine
export ELITE_BACKUP_DIR=/path/to/pilot/backups
export ELITE_LOG_DIR=/path/to/pilot/logs

# 2. safe diagnostics (no secrets shown) + startup validation
PYTHONPATH=. python3 -m elite.ops.cli diagnostics

# 3. launch the operator web app (pilot mode; legacy remains the fallback)
PYTHONPATH=. python3 -m elite.ops.cli serve         # or: python3 -m elite.ui.serve
# open http://127.0.0.1:8010/login
```
Dependency statement: Python 3 standard library + SQLite only. **No third-party dependency.** A non-loopback
bind host requires `ELITE_ALLOW_NONLOOPBACK=1` (explicit opt-in). Shutdown: stop the process (Ctrl-C); the
SQLite store is durable and safe to reopen.

## Configuration reference
| Variable | Default | Meaning |
|---|---|---|
| `ELITE_ENV` | (required) | environment identity; never production during the pilot |
| `ELITE_DB_PATH` | (required) | authoritative SQLite store |
| `ELITE_AUTH_SECRET` | (required, secret) | credential-hash pepper (env/secret store only) |
| `ELITE_BIND_HOST` | `127.0.0.1` | bind host; non-loopback requires `ELITE_ALLOW_NONLOOPBACK=1` |
| `ELITE_UI_PORT` | `8010` | operator app port |
| `ELITE_DEALERSHIP_TZ` | `America/Chicago` | presentation timezone (never stored) |
| `ELITE_UPLOAD_DIR` | `./pilot/uploads` | controlled upload directory |
| `ELITE_RAW_RETENTION_DIR` | `./pilot/raw` | retained raw source evidence |
| `ELITE_QUARANTINE_DIR` | `./pilot/quarantine` | rejected-file quarantine |
| `ELITE_BACKUP_DIR` | `./pilot/backups` | backup artifacts |
| `ELITE_LOG_DIR` | `./pilot/logs` | operational logs |
| `ELITE_SESSION_EXPIRY_SECONDS` | `3600` | session lifetime |
| `ELITE_MAX_UPLOAD_BYTES` | `26214400` | max upload size (25 MiB) |
| `ELITE_STALE_THRESHOLD_SECONDS` | `172800` | default stale threshold (48h) |
| `ELITE_PILOT_MODE` | `true` | controlled pilot mode |
Invalid configuration fails clearly at startup; safe diagnostics never expose a secret; environment-specific
configuration never changes domain logic.

## Import command
```
PYTHONPATH=. python3 -m elite.ops.cli import <contract_key> <file>
# e.g. import new_inventory_current /path/to/dms_export.csv
```
The adapter parses the file into the Phase 2 canonical contract; the orchestrator validates → ingests →
reconciles. Import success is not acceptance; acceptance is not reconciliation. A malformed/unsupported file
is REJECTED safely; an interruption before acceptance preserves the prior valid state; a retry links to the
failed run.

## Scheduler command
```
PYTHONPATH=. python3 -m elite.ops.cli scheduler <job_key>   # manual fire (distinguishable from scheduled)
```
Jobs: `import.<source>`, `freshness.sweep`, `expiration.sweep`, `stale_recommendation_check`,
`calibration_activation_check`, `zero_mile.monitor`, `health.check`, `backup.nightly`, `pilot.comparison`.
A repeat fire for the same instant does not repeat work; a missed run is recorded.

## Backup + restore runbook
```
# create a verified, transactionally-consistent backup
PYTHONPATH=. python3 -m elite.ops.cli backup [dest_dir]
# validate the newest backup restores + reproduces authoritative counts (non-destructive)
PYTHONPATH=. python3 -m elite.ops.cli restore-validate
```
Restore procedure (manual, non-destructive): stop the app; copy the chosen `elite-backup-v<N>-<ts>.db`
artifact to the target `ELITE_DB_PATH`; run `diagnostics` to confirm startup validation and the migration
version; then start the app. Backups do NOT replace raw source-file retention. Retention marks old backups
expired (record preserved). **Phase 11 automates no destructive production restore** — restore is a manual,
reviewed action.

## Health-check command
```
PYTHONPATH=. python3 -m elite.ops.cli health [scope]
# reports liveness, readiness (blockers/warnings), and operational component health
```
Liveness UP does not imply readiness. Readiness is blocked by: migrations behind, integrity failure, a
stale/missing blocking source, a failed uncorrected import, or an unreviewed material pilot discrepancy.

## Log location + retention
Operational logs are structured JSON lines (see `ELITE_LOG_DIR`). They contain no secret, token, session
ID, or raw customer PII; VINs are masked. Rotation/retention is bounded (see the logging contract); an
`operational_log_reference` records where bounded logs live — the log is never an ungoverned data copy.

## Upload location, raw retention, quarantine review
- Uploads land in `ELITE_UPLOAD_DIR`; each is hashed and recorded as a `source_file_receipt`.
- Accepted raw source is retained (`ELITE_RAW_RETENTION_DIR`, referenced from Phase 2 observations) — never
  deleted by cleanup.
- Rejected files are quarantined (`ELITE_QUARANTINE_DIR`) with a recorded reason; review the quarantine
  receipts (`status='quarantined'`) before re-submitting a corrected file.

## Performance baseline report
Baselines are recorded as `operational_metric` rows (environment + dataset size + cold/warm). Representative
pilot workloads measured: application startup validation, Decision Inbox, recommendation detail, New
Inventory / Service Loaner / Executive Demo workspaces, Audit trace, search, representative source imports,
reconciliation, and backup. These are baselines (evidence for where to look), not guarantees; slow-query
evidence guides indexing. Optimization never changes an authoritative result and adds no caching that risks
a stale authoritative display. Actual numbers are environment-dependent; capture them per pilot host with
`PerformanceHarness` / the metrics table.

## Security-hardening checklist
Run `SecurityChecklist(...).run()` (or review at deploy time):
- [ ] no default credential exists;
- [ ] secrets externalized (env/secret store) and redacted in diagnostics;
- [ ] debug / stack-trace exposure off outside development/test;
- [ ] bind host is loopback (or a non-loopback bind was explicitly confirmed);
- [ ] session expiry configured; session invalidation works;
- [ ] cookies HttpOnly + SameSite=Strict (Secure in production/demo);
- [ ] CSRF enforced on every non-public state-changing action;
- [ ] scope isolation + below-UI authorization enforced;
- [ ] file-upload allowlist + size limit + traversal sanitization + quarantine;
- [ ] pilot mode not labeled production; destructive cutover blocked.

## Pilot operator guide (day-to-day)
1. Sign in with your operator id + password + store scope. The banner shows **PILOT MODE** — the legacy
   tool remains your fallback.
2. Work the Decision Inbox and domain workspaces exactly as in Phase 10; every number is read from the
   authoritative records.
3. When a source file arrives, hand it to an importer (or use the import command). A rejected file is
   quarantined with a reason — fix and re-submit.
4. If a source is stale/missing, readiness for that domain is blocked and confidence is reduced — this is
   expected; escalate to get a fresh source.
5. When Elite and the legacy tool disagree, that is **evidence for review**, not proof either is wrong.
   Record what you see as operator feedback (it references the exact screen + revision and changes nothing).
6. An "incorrect result" claim opens a **review**, not an automatic correction.

## Pilot administrator guide
1. Provision the environment + directories; set secrets via the environment/secret store only.
2. Run `diagnostics` and the security checklist before go-live-for-pilot.
3. Register/verify source schedules; fire a manual import to confirm each adapter.
4. Establish the backup schedule; periodically run `restore-validate`.
5. Review freshness, health readiness, reconciliation drift, and pilot comparison differences.
6. Route material comparison differences to a reviewer; a material unresolved difference blocks readiness.
7. Certify pilot readiness per domain (evidence-based) — READY / READY_WITH_WARNINGS / NOT_READY.
8. **Rollback-to-legacy procedure:** the legacy tool was never modified and is always available — to fall
   back, simply continue using the legacy tool (build the legacy artifact per `RUN_INSTRUCTIONS.md` §Legacy)
   and pause Elite; no Elite data migration or cutover is involved. There is no destructive step to undo.

## Known limitations (pilot)
- Execution wiring behind some UI actions uses caller-supplied refs (synthetic in fixtures); each real
  Phase 5-7 executor call behind the pilot is a later integration concern (Phase 12).
- The parallel-run comparison requires legacy output to be supplied to it; it does not scrape the legacy
  tool automatically.
- Real-source access is only what the dealership actually provides; unavailable sources use governed manual
  inputs, never fabricated feeds.
- Single-node SQLite pilot; multi-node/HA and production hosting are out of Phase 11 scope by contract.
