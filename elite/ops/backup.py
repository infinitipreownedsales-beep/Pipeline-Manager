"""Backup and restore for the controlled pilot.

Backups use SQLite's online backup API for a transactionally consistent copy (no torn write, no need to
stop the app). Each backup is timestamped, content-hashed, integrity-verified, and recorded with metadata.
Restore validation copies a backup aside, confirms the application starts, the migration version matches,
and authoritative record counts reproduce. Retention marks old backups expired (never deletes the record,
and never the raw source-file evidence). Phase 11 does NOT automate a destructive production restore.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3

from ..clock import to_utc_iso
from ..db import connect, current_version

# authoritative tables sampled for the count-reproduction check (present since early migrations)
_COUNT_TABLES = ["migration_record", "principal", "business_fact", "audit_event"]


def _file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _counts(conn):
    out = {}
    for t in _COUNT_TABLES:
        try:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            out[t] = None
    return out


class BackupService:
    def __init__(self, db, ops_store, clock, logger=None):
        self.db, self.ops, self.clock, self.logger = db, ops_store, clock, logger

    def create_backup(self, dest_dir, *, retention_class="pilot", correlation_id=None):
        version = current_version(self.db.conn)
        ts = to_utc_iso(self.clock.now()).replace(":", "").replace("-", "")
        name = f"elite-backup-v{version}-{ts}.db"
        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, name)
            src_counts = _counts(self.db.conn)
            # transactionally-consistent online copy
            dest = sqlite3.connect(dest_path)
            with dest:
                self.db.conn.backup(dest)
            dest.close()
            # verify the copy
            vconn = connect(dest_path)
            integ = vconn.execute("PRAGMA integrity_check;").fetchone()[0]
            copy_counts = _counts(vconn)
            copy_version = current_version(vconn)
            vconn.close()
            chash = _file_hash(dest_path)
            ok = (integ == "ok" and copy_counts == src_counts and copy_version == version)
            rec = self.ops.add_backup(
                artifact_ref=dest_path, content_hash=chash, size_bytes=os.path.getsize(dest_path),
                source_schema_version=version, integrity_verified=1 if integ == "ok" else 0,
                status="verified" if ok else "failed", retention_class=retention_class,
                metadata={"counts": src_counts, "version": version}, correlation_id=correlation_id)
            if self.logger:
                self.logger.op("backup", "backup.create", result=rec["status"],
                               correlation_id=correlation_id, version=version)
            if not ok:
                self.ops.add_health("operational", "backup", "FAILED", detail="backup verification failed")
            return rec
        except Exception as e:
            rec = self.ops.add_backup(
                artifact_ref=os.path.join(dest_dir, name), content_hash=None, size_bytes=0,
                source_schema_version=version, integrity_verified=0, status="failed",
                retention_class=retention_class, metadata={"error": type(e).__name__},
                correlation_id=correlation_id)
            self.ops.add_health("operational", "backup", "FAILED", detail=f"backup error: {type(e).__name__}")
            if self.logger:
                self.logger.op_error("backup", "backup.create", type(e).__name__,
                                     correlation_id=correlation_id)
            return rec

    def validate_restore(self, backup_id, restore_dir):
        """Copy the backup aside, confirm it starts, migration version matches, and counts reproduce.
        Records + returns an immutable restore_validation. Non-destructive."""
        rec = self.ops.get_backup(backup_id)
        import json
        meta = json.loads(rec["metadata"]) if rec["metadata"] else {}
        started_ok = version_ok = counts_ok = 0
        observed_version = None
        detail = None
        try:
            os.makedirs(restore_dir, exist_ok=True)
            restore_path = os.path.join(restore_dir, "restored-" + os.path.basename(rec["artifact_ref"]))
            # copy the artifact and open it as the application would
            with open(rec["artifact_ref"], "rb") as src, open(restore_path, "wb") as dst:
                dst.write(src.read())
            rconn = connect(restore_path)
            started_ok = 1
            observed_version = current_version(rconn)
            version_ok = 1 if observed_version == rec["source_schema_version"] else 0
            counts_ok = 1 if _counts(rconn) == meta.get("counts") else 0
            rconn.close()
        except Exception as e:
            detail = f"restore error: {type(e).__name__}"
        return self.ops.add_restore_validation(
            backup_record_id=backup_id, started_ok=started_ok, migration_version_matched=version_ok,
            counts_matched=counts_ok, observed_version=observed_version, detail=detail)

    def apply_retention(self, keep):
        """Retention: keep the newest `keep` verified backups, mark older ones expired (record preserved)."""
        backups = [b for b in self.ops.list_backups() if b["status"] in ("verified", "created")]
        for b in backups[:-keep] if keep < len(backups) else []:
            self.ops.expire_backup(b["id"])
        return self.ops.list_backups()
