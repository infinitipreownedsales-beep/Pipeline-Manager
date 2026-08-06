"""SQLite repositories for Phase 11 operational records (migration v11).

All rows are OPERATIONAL metadata + evidence. Immutable evidence tables are enforced by DB triggers
(no-update / no-delete); this store never tries to mutate them. Append-preserving lifecycle tables
(import_run, operator_feedback, ...) update in place but are never deleted.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id


def _j(v):
    return json.dumps(v) if v is not None else None


def _d(s):
    return json.loads(s) if s else None


class OpsStore:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    def _insert(self, table, **cols):
        keys = list(cols.keys())
        ph = ",".join("?" for _ in keys)
        with self.conn:
            self.conn.execute(
                f"INSERT INTO {table}({','.join(keys)}) VALUES({ph})",
                tuple(cols[k] for k in keys))
        return cols

    # ---- import runs ----------------------------------------------------------
    def add_import_run(self, **c):
        c.setdefault("id", new_id("run"))
        c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        c.setdefault("received_at", c["created_at"])
        return self._insert("import_run", **c)

    def update_import_run(self, run_id, **c):
        c["updated_at"] = self._now()
        sets = ",".join(f"{k}=?" for k in c)
        with self.conn:
            self.conn.execute(f"UPDATE import_run SET {sets} WHERE id=?",
                              tuple(c.values()) + (run_id,))
        return self.get_import_run(run_id)

    def get_import_run(self, run_id):
        return self.conn.execute("SELECT * FROM import_run WHERE id=?", (run_id,)).fetchone()

    def find_import_run_by_hash(self, source_id, scope, content_hash):
        return self.conn.execute(
            "SELECT * FROM import_run WHERE source_id=? AND store_scope=? AND content_hash=?"
            " AND state IN ('COMPLETED','COMPLETED_WITH_WARNINGS') ORDER BY created_at LIMIT 1",
            (source_id, scope, content_hash)).fetchone()

    def list_import_runs(self, source_id=None, scope=None):
        q, args = "SELECT * FROM import_run", []
        cond = []
        if source_id:
            cond.append("source_id=?"); args.append(source_id)
        if scope:
            cond.append("store_scope=?"); args.append(scope)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY created_at"
        return self.conn.execute(q, tuple(args)).fetchall()

    def add_import_error(self, import_run_id, stage, error_class, safe_message, correlation_id=None):
        return self._insert("import_run_error", id=new_id("ierr"), import_run_id=import_run_id,
                            stage=stage, error_class=error_class, safe_message=safe_message,
                            correlation_id=correlation_id, recorded_at=self._now())

    def list_import_errors(self, import_run_id):
        return self.conn.execute("SELECT * FROM import_run_error WHERE import_run_id=? ORDER BY recorded_at",
                                 (import_run_id,)).fetchall()

    # ---- adapter versions -----------------------------------------------------
    def add_adapter_version(self, adapter_key, version, **c):
        existing = self.get_adapter_version(adapter_key, version)
        if existing is not None:
            return existing
        c.update(id=new_id("adpv"), adapter_key=adapter_key, version=version)
        c.setdefault("created_at", self._now())
        return self._insert("source_adapter_version", **c)

    def get_adapter_version(self, adapter_key, version):
        return self.conn.execute("SELECT * FROM source_adapter_version WHERE adapter_key=? AND version=?",
                                 (adapter_key, version)).fetchone()

    # ---- file receipts --------------------------------------------------------
    def add_file_receipt(self, **c):
        c.setdefault("id", new_id("frcpt"))
        c.setdefault("received_at", self._now())
        return self._insert("source_file_receipt", **c)

    def get_file_receipt(self, receipt_id):
        return self.conn.execute("SELECT * FROM source_file_receipt WHERE id=?", (receipt_id,)).fetchone()

    def find_receipt_by_hash(self, content_hash):
        return self.conn.execute(
            "SELECT * FROM source_file_receipt WHERE content_hash=? AND status='received' ORDER BY received_at LIMIT 1",
            (content_hash,)).fetchone()

    # ---- freshness ------------------------------------------------------------
    def add_freshness(self, **c):
        c.setdefault("id", new_id("fr"))
        c.setdefault("recorded_at", self._now())
        if "affected" in c:
            c["affected"] = _j(c["affected"])
        if "evidence" in c:
            c["evidence"] = _j(c["evidence"])
        return self._insert("source_freshness_result", **c)

    def latest_freshness(self, source_id, scope=None):
        q = "SELECT * FROM source_freshness_result WHERE source_id=?"
        args = [source_id]
        if scope:
            q += " AND store_scope=?"; args.append(scope)
        q += " ORDER BY recorded_at DESC LIMIT 1"
        return self.conn.execute(q, tuple(args)).fetchone()

    def freshness_history(self, source_id, scope=None):
        q = "SELECT * FROM source_freshness_result WHERE source_id=?"
        args = [source_id]
        if scope:
            q += " AND store_scope=?"; args.append(scope)
        q += " ORDER BY recorded_at"
        return self.conn.execute(q, tuple(args)).fetchall()

    # ---- operational reconciliation ------------------------------------------
    def add_reconciliation(self, **c):
        c.setdefault("id", new_id("orec"))
        c.setdefault("recorded_at", self._now())
        return self._insert("source_reconciliation_result", **c)

    def list_reconciliation(self, import_run_id=None):
        if import_run_id:
            return self.conn.execute(
                "SELECT * FROM source_reconciliation_result WHERE import_run_id=? ORDER BY recorded_at",
                (import_run_id,)).fetchall()
        return self.conn.execute("SELECT * FROM source_reconciliation_result ORDER BY recorded_at").fetchall()

    # ---- scheduling -----------------------------------------------------------
    def upsert_job(self, job_key, kind, cadence=None, timezone="UTC", scope=None, description=None):
        existing = self.get_job(job_key)
        if existing is not None:
            return existing
        return self._insert("scheduled_job", id=new_id("job"), job_key=job_key, kind=kind, cadence=cadence,
                            timezone=timezone, enabled=1, store_scope=scope, description=description,
                            created_at=self._now(), updated_at=self._now())

    def get_job(self, job_key):
        return self.conn.execute("SELECT * FROM scheduled_job WHERE job_key=?", (job_key,)).fetchone()

    def set_job_enabled(self, job_key, enabled):
        with self.conn:
            self.conn.execute("UPDATE scheduled_job SET enabled=?, updated_at=? WHERE job_key=?",
                              (1 if enabled else 0, self._now(), job_key))
        return self.get_job(job_key)

    def add_job_run(self, job_id, job_key, scheduled_for, status, trigger="scheduled",
                    started_at=None, completed_at=None, correlation_id=None, detail=None):
        return self._insert("scheduled_job_run", id=new_id("jrun"), job_id=job_id, job_key=job_key,
                            scheduled_for=scheduled_for, trigger=trigger, status=status, started_at=started_at,
                            completed_at=completed_at, correlation_id=correlation_id, detail=detail,
                            recorded_at=self._now())

    def claim_job_run(self, job_id, job_key, scheduled_for, trigger="scheduled", correlation_id=None):
        """Insert a 'running' claim. Relies on UNIQUE(job_key, scheduled_for, trigger); a concurrent or
        repeat claim raises sqlite3.IntegrityError (caller treats it as overlap/idempotent)."""
        run_id = new_id("jrun")
        with self.conn:
            self.conn.execute(
                "INSERT INTO scheduled_job_run(id,job_id,job_key,scheduled_for,trigger,status,started_at,"
                "correlation_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, job_id, job_key, scheduled_for, trigger, "running", self._now(),
                 correlation_id, self._now()))
        return self.conn.execute("SELECT * FROM scheduled_job_run WHERE id=?", (run_id,)).fetchone()

    def finish_job_run(self, run_id, status, detail=None):
        with self.conn:
            self.conn.execute(
                "UPDATE scheduled_job_run SET status=?, completed_at=?, detail=? WHERE id=?",
                (status, self._now(), detail, run_id))
        return self.conn.execute("SELECT * FROM scheduled_job_run WHERE id=?", (run_id,)).fetchone()

    def find_job_run(self, job_key, scheduled_for, trigger="scheduled"):
        return self.conn.execute(
            "SELECT * FROM scheduled_job_run WHERE job_key=? AND scheduled_for=? AND trigger=?",
            (job_key, scheduled_for, trigger)).fetchone()

    def list_job_runs(self, job_key=None):
        if job_key:
            return self.conn.execute("SELECT * FROM scheduled_job_run WHERE job_key=? ORDER BY recorded_at",
                                     (job_key,)).fetchall()
        return self.conn.execute("SELECT * FROM scheduled_job_run ORDER BY recorded_at").fetchall()

    # ---- health ---------------------------------------------------------------
    def add_health(self, check_kind, component, status, detail=None, correlation_id=None):
        return self._insert("health_check_result", id=new_id("hc"), check_kind=check_kind, component=component,
                            status=status, detail=detail, correlation_id=correlation_id, recorded_at=self._now())

    # ---- backups --------------------------------------------------------------
    def add_backup(self, **c):
        c.setdefault("id", new_id("bkp"))
        c.setdefault("created_at", self._now())
        if "metadata" in c and not isinstance(c["metadata"], str):
            c["metadata"] = _j(c["metadata"])
        return self._insert("backup_record", **c)

    def get_backup(self, backup_id):
        return self.conn.execute("SELECT * FROM backup_record WHERE id=?", (backup_id,)).fetchone()

    def expire_backup(self, backup_id):
        with self.conn:
            self.conn.execute("UPDATE backup_record SET status='expired', expired_at=? WHERE id=?",
                              (self._now(), backup_id))
        return self.get_backup(backup_id)

    def list_backups(self):
        return self.conn.execute("SELECT * FROM backup_record ORDER BY created_at").fetchall()

    def add_restore_validation(self, **c):
        c.setdefault("id", new_id("rstv"))
        c.setdefault("recorded_at", self._now())
        return self._insert("restore_validation", **c)

    # ---- pilot comparison -----------------------------------------------------
    def add_comparison_run(self, **c):
        c.setdefault("id", new_id("cmpr"))
        c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        return self._insert("pilot_comparison_run", **c)

    def update_comparison_run(self, run_id, **c):
        c["updated_at"] = self._now()
        sets = ",".join(f"{k}=?" for k in c)
        with self.conn:
            self.conn.execute(f"UPDATE pilot_comparison_run SET {sets} WHERE id=?",
                              tuple(c.values()) + (run_id,))
        return self.conn.execute("SELECT * FROM pilot_comparison_run WHERE id=?", (run_id,)).fetchone()

    def add_comparison_result(self, **c):
        c.setdefault("id", new_id("cmp"))
        c.setdefault("recorded_at", self._now())
        for k in ("elite_result", "legacy_result", "difference", "evidence"):
            if k in c and not isinstance(c[k], (str, type(None))):
                c[k] = _j(c[k])
        return self._insert("pilot_comparison_result", **c)

    def get_comparison_result(self, result_id):
        return self.conn.execute("SELECT * FROM pilot_comparison_result WHERE id=?", (result_id,)).fetchone()

    def review_comparison_result(self, result_id, reviewer, disposition, notes=None):
        # Only the review fields are touched; elite_result/legacy_result/classification are never rewritten.
        with self.conn:
            self.conn.execute(
                "UPDATE pilot_comparison_result SET reviewer=?, disposition=?, notes=?, reviewed_at=? WHERE id=?",
                (reviewer, disposition, notes, self._now(), result_id))
        return self.get_comparison_result(result_id)

    def unreviewed_material_results(self, material_classes, scope=None):
        """Unreviewed comparison results whose classification is material, scoped by the run's store_scope."""
        rows = self.conn.execute(
            "SELECT r.* FROM pilot_comparison_result r JOIN pilot_comparison_run run"
            " ON r.comparison_run_id = run.id WHERE (r.disposition IS NULL OR r.disposition='')"
            + (" AND run.store_scope=?" if scope else ""),
            (scope,) if scope else ()).fetchall()
        return [r for r in rows if r["classification"] in material_classes]

    def list_comparison_results(self, comparison_run_id=None, domain=None, scope=None):
        q, args, cond = "SELECT * FROM pilot_comparison_result", [], []
        if comparison_run_id:
            cond.append("comparison_run_id=?"); args.append(comparison_run_id)
        if domain:
            cond.append("domain=?"); args.append(domain)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY recorded_at"
        return self.conn.execute(q, tuple(args)).fetchall()

    # ---- operator feedback ----------------------------------------------------
    def add_feedback(self, **c):
        c.setdefault("id", new_id("fbk"))
        c.setdefault("created_at", self._now())
        c.setdefault("updated_at", c["created_at"])
        return self._insert("operator_feedback", **c)

    def get_feedback(self, feedback_id):
        return self.conn.execute("SELECT * FROM operator_feedback WHERE id=?", (feedback_id,)).fetchone()

    def update_feedback(self, feedback_id, **c):
        c["updated_at"] = self._now()
        sets = ",".join(f"{k}=?" for k in c)
        with self.conn:
            self.conn.execute(f"UPDATE operator_feedback SET {sets} WHERE id=?",
                              tuple(c.values()) + (feedback_id,))
        return self.get_feedback(feedback_id)

    def list_feedback(self, scope=None):
        if scope:
            return self.conn.execute("SELECT * FROM operator_feedback WHERE store_scope=? ORDER BY created_at",
                                     (scope,)).fetchall()
        return self.conn.execute("SELECT * FROM operator_feedback ORDER BY created_at").fetchall()

    # ---- readiness certification ---------------------------------------------
    def add_certification(self, **c):
        c.setdefault("id", new_id("cert"))
        c.setdefault("created_at", self._now())
        if "blockers" in c and not isinstance(c["blockers"], (str, type(None))):
            c["blockers"] = _j(c["blockers"])
        if "evidence" in c and not isinstance(c["evidence"], (str, type(None))):
            c["evidence"] = _j(c["evidence"])
        return self._insert("pilot_readiness_certification", **c)

    def get_certification(self, cert_id):
        return self.conn.execute("SELECT * FROM pilot_readiness_certification WHERE id=?",
                                 (cert_id,)).fetchone()

    def latest_certification(self, scope, domain=None):
        q = "SELECT * FROM pilot_readiness_certification WHERE store_scope=?"
        args = [scope]
        if domain:
            q += " AND domain=?"; args.append(domain)
        q += " ORDER BY created_at DESC LIMIT 1"
        return self.conn.execute(q, tuple(args)).fetchone()

    # ---- metrics + log references --------------------------------------------
    def add_metric(self, metric_key, duration_ms, workload=None, dataset_size=None, environment=None,
                   cold=False, detail=None):
        return self._insert("operational_metric", id=new_id("met"), metric_key=metric_key,
                            workload=workload, dataset_size=dataset_size, environment=environment,
                            cold=1 if cold else 0, duration_ms=duration_ms, detail=detail,
                            recorded_at=self._now())

    def list_metrics(self):
        return self.conn.execute("SELECT * FROM operational_metric ORDER BY recorded_at").fetchall()

    def add_log_reference(self, log_kind, location_ref, retention_class=None, rotation_policy=None, note=None):
        return self._insert("operational_log_reference", id=new_id("logref"), log_kind=log_kind,
                            location_ref=location_ref, retention_class=retention_class,
                            rotation_policy=rotation_policy, note=note, recorded_at=self._now())
