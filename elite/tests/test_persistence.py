"""Acceptance 4,5,6,7,8,9,10,20: ids/clock, durability, repositories, idempotency,
concurrency, migration state."""
import datetime as _dt
import os
import tempfile
import unittest

from elite.clock import FixedClock
from elite.errors import ConcurrencyError
from elite.fixtures import Stack
from elite.ids import probe_id
from elite.models import PersistenceProbe


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "elite.db")
        self.s = Stack(self.path)

    def tearDown(self):
        try:
            self.s.close()
        except Exception:
            pass

    def test_5_controlled_clock_is_deterministic(self):
        c1 = FixedClock(_dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc), step=_dt.timedelta(minutes=1))
        seq1 = [c1.now().isoformat() for _ in range(3)]
        c2 = FixedClock(_dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc), step=_dt.timedelta(minutes=1))
        seq2 = [c2.now().isoformat() for _ in range(3)]
        self.assertEqual(seq1, seq2)
        self.assertTrue(seq1[0].endswith("+00:00"))  # UTC internal

    def test_4_stable_ids_survive_persistence_and_reload(self):
        p = self.s.authn.register("Sales Manager", "pw")
        pid = p.id
        s2 = self.s.reopen()
        try:
            self.assertEqual(s2.principals.get(pid).id, pid)
        finally:
            s2.close()

    def test_6_and_7_authoritative_persistence_survives_restart(self):
        pr = self.s.probes.add(PersistenceProbe(id=probe_id(), note="durable"))
        # 7: durable store is a real on-disk file, independent of any browser-local state.
        self.assertTrue(os.path.exists(self.path))
        self.s.close()
        # "clearing browser localStorage" cannot touch this file (no localStorage in the store):
        s2 = Stack(self.path)
        try:
            self.assertIsNotNone(s2.probes.get(pr.id))       # survives restart
            self.assertEqual(s2.probes.get(pr.id).note, "durable")
        finally:
            s2.close()

    def test_8_repository_contracts(self):
        p = self.s.authn.register("Owner", "pw")
        self.assertEqual(self.s.principals.get(p.id).display_name, "Owner")
        self.assertEqual(self.s.metadata.put_if_absent("k", "v"), "v")
        self.assertEqual(self.s.metadata.put_if_absent("k", "v2"), "v")  # if-absent honored
        g = self.s.grant(p.id, "audit.read", "store:HG")
        self.assertEqual(len(self.s.grants.list_for(p.id)), 1)
        self.assertTrue(g.effective())

    def test_9_idempotent_write_no_duplicate_effect(self):
        p = self.s.authn.register("Owner", "pw")
        self.s.grant(p.id, "probe.write", "store:HG")
        made = {"n": 0}

        def business(conn):
            pid = probe_id()
            conn.execute("INSERT INTO persistence_probe(id,note,created_at) VALUES(?,?,?)",
                         (pid, "idem", self.s.clock.now().isoformat()))
            made["n"] += 1
            return pid, pid

        r1 = self.s.governor.perform(principal_id=p.id, capability="probe.write", scope="store:HG",
                                     action="probe.create", business_fn=business, idempotency_key="K1")
        r2 = self.s.governor.perform(principal_id=p.id, capability="probe.write", scope="store:HG",
                                     action="probe.create", business_fn=business, idempotency_key="K1")
        self.assertFalse(r1["replayed"]); self.assertTrue(r2["replayed"])
        self.assertEqual(made["n"], 1)  # business effect applied exactly once
        n = self.s.db.conn.execute("SELECT COUNT(*) c FROM persistence_probe WHERE note='idem'").fetchone()["c"]
        self.assertEqual(n, 1)

    def test_10_stale_versioned_write_rejected(self):
        p = self.s.authn.register("Owner", "pw")
        g = self.s.grant(p.id, "x", "store:HG")   # version 1
        self.s.grants.revoke(g.id, expected_version=1, when=self.s.clock.now())  # ok -> v2
        with self.assertRaises(ConcurrencyError):
            self.s.grants.revoke(g.id, expected_version=1, when=self.s.clock.now())  # stale

    def test_20_migration_state_survives_restart(self):
        v1 = self.s.db.version()
        self.assertGreaterEqual(v1, 1)
        self.s.close()
        s2 = Stack(self.path)
        try:
            self.assertEqual(s2.db.version(), v1)  # not re-applied, state persisted
        finally:
            s2.close()


if __name__ == "__main__":
    unittest.main()
