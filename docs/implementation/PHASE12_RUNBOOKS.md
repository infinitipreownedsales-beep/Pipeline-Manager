# PHASE 12 RUNBOOKS — MIGRATION, REHEARSALS, CUTOVER, RELEASE PACKAGE

Migration, rollback, and recovery rehearsal runbooks; the cutover runbook; the release-package manifest;
and the final startup + pilot commands. Phase 12 is the final engineering + validation phase. **The legacy
tool remains available throughout migration, parallel validation, rollback rehearsal, and release review;
no irreversible production cutover or legacy retirement occurs.**

## Migration rehearsal runbook (repeatable, non-production)
`elite.release.rehearsal.RehearsalService.migration_rehearsal(seed_fn=...)` performs:
1. create a clean target database (a fresh temp file);
2. apply migrations **v1-v12**;
3. (`seed_fn`) configure real source contracts, load confirmed policies, configure Principals + authority,
   import approved sanitized migration data, reconcile identities, reconstruct domain state, run
   calculations, generate readiness;
4. record input hashes + output counts + duration;
5. create + verify a backup;
6. simulate restart and verify the migration version + counts;
7. produce an immutable `migration_rehearsal` record (`outcome` = pass/fail).
The rehearsal is repeatable, does not affect operational legacy state, and a failure is preserved and
blocks readiness.

## Rollback rehearsal runbook (rollback must be PROVEN)
`RehearsalService.rollback_rehearsal(...)` proves operational control can return to the legacy tool:
1. stop / disable Elite execution (shadow mode → REVIEW_ONLY/BLOCKED);
2. preserve Elite data + Audit + Decisions; retain source imports;
3. restore or retain the last verified Elite database;
4. confirm the legacy tool remains available;
5. communicate operational mode;
6. confirm no duplicate action remains pending; identify actions executed only in Elite; reconcile in-flight
   actions;
7. validate operator access;
8. produce an immutable `rollback_rehearsal` record.
Rollback is non-destructive; Elite history remains available; executed real-world actions are not undone
merely by system rollback; in-flight actions receive explicit treatment; rollback does not silently replay
actions into legacy; a failed rollback rehearsal blocks readiness.

## Recovery rehearsal runbook
`RehearsalService.recovery_rehearsal(scenario=...)` tests, per scenario (corrupted working copy with valid
backup, failed import during pilot, database lock, application crash, scheduler outage, missing source,
expired authentication, revoked authority, unavailable legacy comparison file, interrupted execution):
committed business truth is preserved and unresolved operational consequences are identified
(`recovery_rehearsal` record).

## Cutover runbook (does NOT execute itself)
Recorded via `elite.release.release.CutoverRunbookService.record(...)` (`cutover_runbook_reference`), with:
prerequisites; responsible Principals; approved release window; source freeze / timing rules; final legacy
export; final Elite imports; reconciliation; discrepancy threshold; backup; authority verification; health
verification; domain readiness; execution-mode changes; communication; validation checkpoints; **abort
criteria**; **rollback trigger + steps**; stabilization monitoring; post-release review. The runbook is a
document — it performs no cutover. Actual production-primary activation requires an explicit governed
release-authorization Decision (below) followed by a separate, human-executed release per this runbook.

## Release-package manifest
`elite.release.release.ReleasePackageService.build(...)` then `.issue(...)` (immutable once issued) pins:
application revision; migration level (12); configuration template; source registry; adapter versions;
policy versions; calculation/model/comparison versions; authority matrix; unresolved risks; discrepancy
status; UAT evidence; migration + rollback rehearsal evidence; backup verification; health report; readiness
certification; startup + shutdown + rollback procedures; checksum manifest; release notes; known
limitations. Artifacts are recorded as immutable `release_package_artifact` rows.

## Final readiness certification + release-authorization gate
```python
from elite.release.fixtures import Phase12
p = Phase12("/path/to/elite.db")
pkg  = p.packages.issue(principal=RELEASE_MGR, scope=SCOPE, release_package_id=p.packages.build(
           version_label="v1.0.0", application_revision="<rev>", migration_level=12)["id"])
cert = p.readiness.certify(principal=RELEASE_MGR, scope=SCOPE, release_package_ref=pkg["id"], dimensions={
           "ENGINEERING_READY": {"status": "PASS"}, "DATA_READY": {"status": "PASS"}, ...})  # 8 prereqs
# OPERATIONALLY_READY is DERIVED; GO_LIVE_AUTHORIZED stays NOT_APPLICABLE until authorized.
auth = p.authorization.authorize(principal=RELEASE_AUTHORIZER, scope=SCOPE, release_package_ref=pkg["id"],
           certification_ref=cert["id"], disposition="AUTHORIZE_GO_LIVE", rollback_plan_ref=<rollback>,
           warnings_ack=[...], risks_ack=[...])   # explicit governed Decision; performs NO cutover
```
`GO_LIVE_AUTHORIZED` can only be set by an authorized Principal's explicit governed Decision — never by
automated tests. Authorization is atomic with its Audit Event, supports expiration + separation of duties,
and **does not itself execute cutover**. No authorization leaves the system in parallel pilot mode.

## Final startup + pilot commands
The pilot packaging CLI + operator app remain the Phase 11 commands; Phase 12 adds the migration/validation/
release services in-process:
```
export ELITE_ENV=development ELITE_DB_PATH=/path/to/pilot/elite.db ELITE_AUTH_SECRET=... ELITE_PILOT_SCOPE=store:HG
PYTHONPATH=. python3 -m elite.ops.cli diagnostics          # safe config + startup validation (no secrets)
PYTHONPATH=. python3 -m elite.ops.cli health store:HG      # liveness / readiness / operational
PYTHONPATH=. python3 -m elite.ops.cli serve                # operator app in pilot mode (live executors wired)
```
```python
from elite.release.fixtures import Phase12
p = Phase12("/path/to/elite.db")                           # migrates v1..v12; wires live executors
mr = p.migration.start_run(initiated_by=MIGRATOR)          # migrate into a dedicated migration db
p.migration.migrate_source(mr["id"], contract_key="new_inventory_current", payload=open("export.csv").read(),
                           source_family="new_inventory_current", scope="store:HG", content_hash=...)
p.parallel.run(principal=VALIDATOR, scope="store:HG", run_date="...", subjects=[...])   # Elite vs legacy
```

## Rollback-to-legacy procedure (unchanged availability)
The legacy tool was never modified and is always available. To fall back at any point, continue using the
legacy tool (build the legacy artifact per `RUN_INSTRUCTIONS.md` §Legacy) and set the affected domains'
shadow mode to REVIEW_ONLY/BLOCKED. No Elite data migration or cutover is involved; there is no destructive
step to undo.

## Known limitations (final phase)
- The live-execution path is fully wired and proven end-to-end for Executive Demo retirement; the same
  registry binds the real methods for the other domains (CPO/PPO/Dealer Trade/CTP/loaner entry/return/used-
  cars), each of which requires its domain object in the correct governed state to drive end-to-end.
- Real live-source access is only what the dealership actually provides; unavailable sources are classified
  and use governed manual inputs — never fabricated feeds.
- The parallel-run duration + sample coverage are an approved release criterion, to be met over the pilot
  period, not asserted by a fixed number here.
- Single-node SQLite pilot; multi-node/HA and production hosting remain out of scope. **Production-primary
  activation requires a distinct explicit release authorization after Phase 12 review.**
