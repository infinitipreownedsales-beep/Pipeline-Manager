"""Acceptance 15,16,17,18,19: audit foundation, atomic audit, append-only,
log/audit separation, safe errors."""
import io
import os
import sqlite3
import tempfile
import unittest

from elite.audit import make_event
from elite.errors import EliteError, PersistenceError
from elite.fixtures import Stack
from elite.governance import Governor
from elite.ids import probe_id
from elite.logging_ import StructuredLogger


class _FailingAudit:
    """Audit repo whose required append fails — to prove atomic rollback."""
    def append(self, conn, event):
        raise sqlite3.OperationalError("simulated audit store failure")
    def get(self, i): return None
    def count(self): return 0


class TestAuditLogging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.s = Stack(os.path.join(self.tmp, "elite.db"))
        self.p = self.s.authn.register("Owner", "pw")
        self.s.grant(self.p.id, "probe.write", "store:HG")

    def tearDown(self):
        self.s.close()

    def _business(self, note):
        def fn(conn):
            pid = probe_id()
            conn.execute("INSERT INTO persistence_probe(id,note,created_at) VALUES(?,?,?)",
                         (pid, note, self.s.clock.now().isoformat()))
            return pid, pid
        return fn

    def test_15_governed_action_creates_audit_event(self):
        before = self.s.audit.count()
        r = self.s.governor.perform(principal_id=self.p.id, capability="probe.write",
                                    scope="store:HG", action="probe.create",
                                    business_fn=self._business("ok"), target_ref="probe")
        self.assertEqual(self.s.audit.count(), before + 1)
        self.assertIsNotNone(self.s.audit.get(r["audit_id"]))
        self.assertEqual(self.s.audit.get(r["audit_id"]).action, "probe.create")

    def test_16_required_audit_failure_prevents_unsafe_success(self):
        gov = Governor(self.s.db, self.s.authz, _FailingAudit(), self.s.idempotency,
                       self.s.clock, self.s.environment)
        before = self.s.db.conn.execute("SELECT COUNT(*) c FROM persistence_probe").fetchone()["c"]
        with self.assertRaises(PersistenceError):
            gov.perform(principal_id=self.p.id, capability="probe.write", scope="store:HG",
                        action="probe.create", business_fn=self._business("should-rollback"))
        after = self.s.db.conn.execute("SELECT COUNT(*) c FROM persistence_probe").fetchone()["c"]
        self.assertEqual(before, after)  # business write rolled back with the failed audit
        self.assertEqual(self.s.db.conn.execute(
            "SELECT COUNT(*) c FROM persistence_probe WHERE note='should-rollback'").fetchone()["c"], 0)

    def test_17_audit_cannot_be_modified_by_ordinary_repository_op(self):
        r = self.s.governor.perform(principal_id=self.p.id, capability="probe.write",
                                    scope="store:HG", action="probe.create",
                                    business_fn=self._business("x"))
        aid = r["audit_id"]
        with self.assertRaises(sqlite3.Error):
            self.s.db.conn.execute("UPDATE audit_event SET action='tamper' WHERE id=?", (aid,))
        with self.assertRaises(sqlite3.Error):
            self.s.db.conn.execute("DELETE FROM audit_event WHERE id=?", (aid,))
        self.assertEqual(self.s.audit.get(aid).action, "probe.create")  # unchanged

    def test_18_logs_are_distinct_from_audit(self):
        buf = io.StringIO()
        logger = StructuredLogger(self.s.environment, "test"); logger.stream = buf
        before = self.s.audit.count()
        logger.info("probe.create", correlation_id="cor_x")  # a technical log line
        self.assertEqual(self.s.audit.count(), before)       # logging writes NO audit row
        self.assertIn("probe.create", buf.getvalue())
        self.assertIn('"level": "INFO"', buf.getvalue())

    def test_18b_logger_scrubs_secrets(self):
        buf = io.StringIO()
        logger = StructuredLogger(self.s.environment, "test"); logger.stream = buf
        logger.info("login", password="hunter2", api_key="abc123")
        self.assertNotIn("hunter2", buf.getvalue())
        self.assertNotIn("abc123", buf.getvalue())
        self.assertIn("***", buf.getvalue())

    def test_19_error_exposes_correlation_id_not_protected_detail(self):
        err = EliteError(category="persistence", message="Could not save.",
                         technical_detail="db path /var/secret leaked internals")
        payload = err.safe_payload()
        self.assertIn("correlation_id", payload)
        self.assertEqual(payload["message"], "Could not save.")
        self.assertNotIn("technical_detail", payload)
        self.assertNotIn("secret", str(payload))


if __name__ == "__main__":
    unittest.main()
