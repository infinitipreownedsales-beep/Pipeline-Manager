"""Phase 11 acceptance — SQLite durability (36-39), backup/restore (40-44), health checks (45-50)."""
import os
import sqlite3
import tempfile
import unittest

from elite.ops import fixtures as F
from elite.ops.durability import (apply_durability, durability_snapshot, foreign_key_check,
                                   integrity_check, startup_validation)
from elite.ops.fixtures import Phase11, SCOPE


class TestPhase11DurabilityBackupHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase11(os.path.join(cls.tmp, "elite.db"))
        cls.conn = cls.p.stack.db.conn

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    # ---- durability (36-39) ----------------------------------------------
    def test_036_foreign_keys_active(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(foreign_key_check(self.conn), [])

    def test_037_durability_settings_verified(self):
        snap = apply_durability(self.conn)
        self.assertEqual(str(snap["journal_mode"]).lower(), "wal")
        self.assertTrue(int(snap["busy_timeout"]) > 0)
        self.assertEqual(snap["foreign_keys"], 1)

    def test_038_busy_or_locked_safe_handling(self):
        # a busy_timeout is configured so a briefly-locked db waits rather than erroring immediately,
        # and a second connection can still read under WAL
        self.assertTrue(int(durability_snapshot(self.conn)["busy_timeout"]) > 0)
        c2 = sqlite3.connect(self.p.stack.db.path)
        try:
            self.assertIsNotNone(c2.execute("SELECT COUNT(*) FROM migration_record").fetchone())
        finally:
            c2.close()

    def test_039_integrity_check_executable(self):
        self.assertEqual(integrity_check(self.conn), "ok")

    # ---- backup / restore (40-44) ----------------------------------------
    def test_040_backup_transactionally_consistent(self):
        rec = self.p.backup.create_backup(tempfile.mkdtemp())
        self.assertEqual(rec["status"], "verified")            # integrity-verified consistent copy
        self.assertEqual(rec["integrity_verified"], 1)

    def test_041_backup_metadata_recorded(self):
        rec = self.p.backup.create_backup(tempfile.mkdtemp())
        self.assertIsNotNone(rec["content_hash"])
        self.assertIsNotNone(rec["metadata"])
        self.assertIsNotNone(rec["source_schema_version"])

    def test_042_restore_reproduces_counts(self):
        rec = self.p.backup.create_backup(tempfile.mkdtemp())
        rv = self.p.backup.validate_restore(rec["id"], tempfile.mkdtemp())
        self.assertEqual(rv["counts_matched"], 1)
        self.assertEqual(rv["started_ok"], 1)

    def test_043_restore_preserves_migration_version(self):
        rec = self.p.backup.create_backup(tempfile.mkdtemp())
        rv = self.p.backup.validate_restore(rec["id"], tempfile.mkdtemp())
        self.assertEqual(rv["migration_version_matched"], 1)
        self.assertEqual(rv["observed_version"], self.p.stack.db.version())

    def test_044_failed_backup_visible_alert(self):
        rec = self.p.backup.create_backup("/nonexistent\x00/bad")
        self.assertEqual(rec["status"], "failed")
        alerts = self.conn.execute(
            "SELECT * FROM health_check_result WHERE component='backup' AND status='FAILED'").fetchall()
        self.assertTrue(alerts)                                # visible operational alert

    # ---- health (45-50) --------------------------------------------------
    def test_045_liveness_distinct_from_readiness(self):
        self.assertEqual(self.p.health.liveness()["kind"], "liveness")
        self.assertEqual(self.p.health.readiness(SCOPE)["kind"], "readiness")

    def test_046_live_but_not_ready(self):
        # create a blocking condition in an isolated scope: application is UP but scope is NOT ready
        self.p.freshness.evaluate(source_id=self.p.source_id("production_orders"), scope="store:LR46",
                                  domain="production", last_received_at=None, source_effective_time=None,
                                  expected_cadence_seconds=3600, stale_threshold_seconds=7200)
        self.assertEqual(self.p.health.liveness()["status"], "UP")
        self.assertEqual(self.p.health.readiness("store:LR46")["status"], "NOT_READY")

    def test_047_health_reports_source_freshness(self):
        oh = self.p.health.operational_health(SCOPE)
        self.assertIn("source_freshness", oh["components"])

    def test_048_health_reports_latest_import(self):
        oh = self.p.health.operational_health(SCOPE)
        self.assertIn("latest_import", oh["components"])

    def test_049_health_reports_backup_age(self):
        self.p.backup.create_backup(tempfile.mkdtemp())
        oh = self.p.health.operational_health(SCOPE)
        self.assertEqual(oh["components"]["backup"], "PRESENT")

    def test_050_health_reports_critical_exceptions(self):
        oh = self.p.health.operational_health(SCOPE)
        self.assertIn("critical_exceptions", oh["components"])


if __name__ == "__main__":
    unittest.main()
