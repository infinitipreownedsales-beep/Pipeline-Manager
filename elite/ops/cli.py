"""Pilot packaging commands — a small operational CLI for the controlled pilot.

Subcommands (documented in the pilot administrator guide):
  diagnostics        safe configuration + durability + startup validation (no secrets)
  health             liveness / readiness / operational health
  import  <ck> <f>   run a source import through the adapter + orchestrator
  backup             create a verified backup
  restore-validate   validate the newest backup restores + reproduces counts
  scheduler <job>    fire a scheduled job once (manual trigger)
  serve              launch the operator web app (delegates to elite.ui.serve)

Every command builds an operational stack over the configured ELITE_DB_PATH and never prints a secret.
"""
from __future__ import annotations

import json
import os
import sys

from ..clock import SystemClock
from ..data.facts import FactService
from ..data.ingestion import IngestionService
from ..data.models import FieldSpec, SchemaProfile, SourceRegistry
from ..data.store import DataStore
from ..db import Db
from ..environment import resolve_environment, resolve_pilot_scope, resolve_revision
from .backup import BackupService
from .contracts import SOURCE_CONTRACTS, get_contract
from .durability import apply_durability, startup_validation
from .freshness import FreshnessService
from .health import HealthService
from .imports import ImportOrchestrator
from .intake import content_hash
from .observability import OperationalLogger
from .opsconfig import load_ops_config
from .scheduler import Scheduler
from .store import OpsStore
from .fixtures import _kind, Phase11  # reuse the field-kind mapping


class OpsStack:
    """A lightweight operational stack over a real store (no synthetic domain seed)."""

    def __init__(self, db_path=None, env=None):
        self.environment = resolve_environment({"ELITE_ENV": env} if env else os.environ)
        # Authoritative store scope for real pilot operation — fail closed, never a silent store:HG fallback.
        self.pilot_scope = resolve_pilot_scope(os.environ)
        db_path = db_path or os.environ.get("ELITE_DB_PATH", "elite.db")
        self.clock = SystemClock()
        self.db = Db(db_path, self.clock)
        self.db.migrate()
        apply_durability(self.db.conn)
        self.opsconfig = load_ops_config(os.environ)
        # Single source of truth for the log revision: ELITE_REVISION or the environment value (never "test").
        self.oplog = OperationalLogger(self.environment, resolve_revision(os.environ, environment=self.environment))
        self.data = DataStore(self.db.conn, self.clock)
        self.facts = FactService(self.data, self.clock)
        self.ingestion = IngestionService(self.data, self.facts, self.clock)
        self.ops = OpsStore(self.db.conn, self.clock)
        self.orch = ImportOrchestrator(self.ops, self.ingestion, self.data, self.clock, logger=self.oplog)
        self.freshness = FreshnessService(self.ops, self.clock)
        self.scheduler = Scheduler(self.ops, self.clock, logger=self.oplog)
        self.backup = BackupService(self.db, self.ops, self.clock, logger=self.oplog)
        self.health = HealthService(self.db, self.ops, self.clock, freshness=self.freshness)
        self._register_sources()
        self._register_jobs()

    def _register_jobs(self):
        tz = os.environ.get("ELITE_DEALERSHIP_TZ", "America/Chicago")
        self.scheduler.register("import.new_inventory_current", "source_import", cadence="0 6 * * *", timezone=tz)
        self.scheduler.register("freshness.sweep", "freshness_check", cadence="0 * * * *", timezone=tz)
        self.scheduler.register("health.check", "health_check", cadence="*/5 * * * *", timezone="UTC")
        self.scheduler.register("backup.nightly", "backup", cadence="0 2 * * *", timezone=tz)

    def _register_sources(self):
        for c in SOURCE_CONTRACTS.values():
            sid = "src_p11_" + c.key
            if self.data.get_source(sid) is not None:
                continue
            names, seen = [], set()
            for f in (list(c.required_fields) + list(c.optional_fields) + list(c.identity_keys)):
                if f not in seen:
                    seen.add(f); names.append(f)
            fields = [FieldSpec(n, required=(n in c.required_fields), kind=_kind(n), meaning=n) for n in names]
            auth = [c.fact_type] if c.fact_type else []
            snap = c.snapshot_capability in ("full", "full_or_partial")
            self.data.add_source(SourceRegistry(id=sid, name=c.key, owner=c.owner, source_type=c.source_system,
                                                supported_profiles=[sid + "_p1"], authoritative_fact_types=auth,
                                                scope=self.pilot_scope))
            self.data.add_profile(SchemaProfile(id=sid + "_p1", source_id=sid, version=1, fields=fields,
                                                snapshot_capable=snap, full_snapshot_requirements={}))


def _out(obj):
    print(json.dumps(obj, indent=2, default=str))


def cmd_diagnostics(stack, args):
    _out({"environment": stack.environment.value, "config": stack.opsconfig.redacted(),
          "durability": startup_validation(stack.db.conn)})
    return 0


def cmd_health(stack, args):
    scope = args[0] if args else stack.pilot_scope
    _out({"liveness": stack.health.liveness(), "readiness": stack.health.readiness(scope),
          "operational": stack.health.operational_health(scope)})
    return 0


def cmd_import(stack, args):
    if len(args) < 2:
        print("usage: import <contract_key> <file>", file=sys.stderr); return 2
    ck, path = args[0], args[1]
    if get_contract(ck) is None:
        print(f"unknown contract {ck}", file=sys.stderr); return 2
    with open(path, "rb") as f:
        payload = f.read()
    scope = stack.pilot_scope
    run = stack.orch.run(contract_key=ck, payload=payload, source_id="src_p11_" + ck, scope=scope,
                         content_hash=content_hash(payload), initiated_by="cli")
    _out({"import_run": run["id"], "state": run["state"], "accepted": run["accepted_count"]})
    return 0 if run["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS") else 1


def cmd_backup(stack, args):
    dest = args[0] if args else stack.opsconfig.get("ELITE_BACKUP_DIR")
    rec = stack.backup.create_backup(dest)
    _out({"backup": rec["id"], "status": rec["status"], "artifact": rec["artifact_ref"]})
    return 0 if rec["status"] == "verified" else 1


def cmd_restore_validate(stack, args):
    backups = [b for b in stack.ops.list_backups() if b["status"] == "verified"]
    if not backups:
        print("no verified backup", file=sys.stderr); return 1
    import tempfile
    rv = stack.backup.validate_restore(backups[-1]["id"], tempfile.mkdtemp())
    _out({"started_ok": rv["started_ok"], "version_matched": rv["migration_version_matched"],
          "counts_matched": rv["counts_matched"]})
    return 0 if (rv["started_ok"] and rv["migration_version_matched"] and rv["counts_matched"]) else 1


def cmd_scheduler(stack, args):
    if not args:
        print("usage: scheduler <job_key>", file=sys.stderr); return 2
    from ..clock import to_utc_iso
    run = stack.scheduler.run_manual(args[0], to_utc_iso(stack.clock.now()))
    _out({"job_run": run["id"], "status": run["status"], "trigger": run["trigger"]})
    return 0


def cmd_serve(stack, args):
    from ..ui.serve import build_app, main as ui_main
    print("Launching operator app in pilot mode; legacy tool remains the operational fallback.")
    ui_main()
    return 0


COMMANDS = {
    "diagnostics": cmd_diagnostics, "health": cmd_health, "import": cmd_import, "backup": cmd_backup,
    "restore-validate": cmd_restore_validate, "scheduler": cmd_scheduler, "serve": cmd_serve,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("elite.ops.cli <command> [args]\n  commands: " + ", ".join(sorted(COMMANDS)))
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = COMMANDS.get(cmd)
    if fn is None:
        print(f"unknown command {cmd}", file=sys.stderr); return 2
    stack = OpsStack()
    return fn(stack, rest)


if __name__ == "__main__":
    raise SystemExit(main())
