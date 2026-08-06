"""Structured health checks.

Three distinct concerns are kept separate:
  * LIVENESS   — the application process is up and can answer.
  * READINESS  — the application is safe to rely on operationally right now.
  * OPERATIONAL — component-level detail (db, migrations, freshness, imports, scheduler, backup, audit).

A live application may still be operationally NOT ready (e.g. a stale blocking source or an unreviewed
material pilot discrepancy). Each check appends an immutable health_check_result.
"""
from __future__ import annotations

from .durability import startup_validation
from .models import COMPARISON_MATERIAL, NOT_READY, READY, READY_WITH_WARNINGS


class HealthService:
    def __init__(self, db, ops_store, clock, *, freshness=None, logger=None):
        self.db, self.ops, self.clock = db, ops_store, clock
        self.freshness = freshness
        self.logger = logger

    def liveness(self):
        # answering at all == alive; does not imply ready
        self.ops.add_health("liveness", "application", "UP")
        return {"kind": "liveness", "status": "UP"}

    def _backup_age(self):
        backups = [b for b in self.ops.list_backups() if b["status"] == "verified"]
        if not backups:
            return None, "NONE"
        return backups[-1], "PRESENT"

    def _failed_imports(self, scope=None):
        failed = []
        for r in self.ops.list_import_runs(scope=scope):
            if r["state"] == "FAILED":
                # any later completed run for the same source clears it
                later = [x for x in self.ops.list_import_runs(r["source_id"], r["store_scope"])
                         if x["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
                         and x["created_at"] > r["created_at"]]
                if not later:
                    failed.append(r)
        return failed

    def _unreviewed_material_diffs(self, scope=None):
        return self.ops.unreviewed_material_results(COMPARISON_MATERIAL, scope=scope)

    def _critical_exceptions(self):
        """Count unresolved critical exceptions from the Phase 9 queues (safe if the tables are absent)."""
        total = 0
        for sql in ("SELECT COUNT(*) c FROM operational_exception_item WHERE status='open'",
                    "SELECT COUNT(*) c FROM audit_exception"):
            try:
                total += self.db.conn.execute(sql).fetchone()["c"]
            except Exception:
                pass
        return total

    def operational_health(self, scope=None):
        sv = startup_validation(self.db.conn)
        backup, backup_status = self._backup_age()
        failed_imports = self._failed_imports(scope)
        blocking_fresh = self.freshness.blocking_sources(scope) if self.freshness else []
        critical = self._critical_exceptions()
        components = {
            "database": "UP" if sv["integrity_ok"] else "DOWN",
            "migrations": "CURRENT" if sv["migrations_current"] else "BEHIND",
            "foreign_keys": "ON" if sv["foreign_keys_on"] else "OFF",
            "latest_import": "FAILED" if failed_imports else "OK",
            "source_freshness": "BLOCKING" if blocking_fresh else "OK",
            "backup": backup_status,
            "critical_exceptions": critical,
        }
        for comp, status in components.items():
            self.ops.add_health("operational", comp, status)
        return {"kind": "operational", "components": components,
                "failed_imports": [r["id"] for r in failed_imports],
                "blocking_sources": [r["source_id"] for r in blocking_fresh]}

    def readiness(self, scope=None):
        """Operational readiness. Returns a classification + the evidence behind it. Records the result."""
        sv = startup_validation(self.db.conn)
        blocking_fresh = self.freshness.blocking_sources(scope) if self.freshness else []
        failed_imports = self._failed_imports(scope)
        material = self._unreviewed_material_diffs(scope)
        backup, backup_status = self._backup_age()

        blockers = []
        if not sv["migrations_current"]:
            blockers.append("migrations_behind")
        if not sv["integrity_ok"]:
            blockers.append("integrity_failed")
        if blocking_fresh:
            blockers.append("stale_or_missing_source")
        if failed_imports:
            blockers.append("failed_import_uncorrected")
        if material:
            blockers.append("unreviewed_material_discrepancy")

        warnings = []
        if backup_status == "NONE":
            warnings.append("no_backup")

        if blockers:
            status = NOT_READY
        elif warnings:
            status = READY_WITH_WARNINGS
        else:
            status = READY
        self.ops.add_health("readiness", "application", status,
                            detail=("; ".join(blockers) if blockers else ("; ".join(warnings) or None)))
        return {"kind": "readiness", "status": status, "blockers": blockers, "warnings": warnings,
                "evidence": {"blocking_sources": [r["source_id"] for r in blocking_fresh],
                             "failed_imports": [r["id"] for r in failed_imports],
                             "material_discrepancies": [r["id"] for r in material],
                             "backup": backup_status}}
