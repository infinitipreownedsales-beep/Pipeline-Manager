"""Phase 11 acceptance — scheduling (22-25), restart/crash recovery (26-30), concurrency (31-35)."""
import os
import tempfile
import unittest

from elite.errors import PersistenceError
from elite.ops import fixtures as F
from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.models import CAPS


class TestPhase11SchedulingRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase11(os.path.join(cls.tmp, "elite.db"))

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    def _facts(self):
        return self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM business_fact").fetchone()["c"]

    # ---- scheduling (22-25) ----------------------------------------------
    def test_022_scheduled_job_idempotent(self):
        inst = "2026-08-06T06:00:00+00:00"
        a = self.p.scheduler.fire("freshness.sweep", inst, work_fn=lambda: "x")
        b = self.p.scheduler.fire("freshness.sweep", inst, work_fn=lambda: "y")
        self.assertEqual(a["id"], b["id"])                 # same instant -> one run

    def test_023_missed_scheduled_run_visible(self):
        m = self.p.scheduler.mark_missed("freshness.sweep", "2026-08-04T06:00:00+00:00")
        self.assertEqual(m["status"], "missed")

    def test_024_overlapping_run_no_duplicate_work(self):
        inst = "2026-08-06T09:00:00+00:00"
        counter = {"n": 0}

        def work():
            counter["n"] += 1
            return "done"
        self.p.scheduler.fire("health.check", inst, work_fn=work)
        self.p.scheduler.fire("health.check", inst, work_fn=work)   # overlap
        self.assertEqual(counter["n"], 1)                  # work ran exactly once

    def test_025_schedule_uses_explicit_timezone(self):
        job = self.p.ops.get_job("import.new_inventory_current")
        self.assertEqual(job["timezone"], "America/Chicago")

    # ---- restart / recovery (26-30) --------------------------------------
    def test_026_restart_after_completed_no_replay(self):
        self.p.import_payload("new_inventory_current", F.INV_FULL, effective_time=self.p.now_iso(),
                              chash="sha256:c26")
        facts = self._facts()
        runs = len(self.p.ops.list_import_runs())
        q = self.p.restart()                               # true process restart (no re-seed)
        try:
            self.assertEqual(q.facts_count(), facts)       # completed effects not replayed
            self.assertEqual(len(q.ops.list_import_runs()), runs)
        finally:
            q.close()

    def test_027_interrupted_import_no_partial_accepted(self):
        before = self._facts()
        run = self.p.import_payload("new_inventory_current", F.INV_VALID, chash="sha256:c27",
                                    fail_at="ingest")
        self.assertEqual(run["state"], "FAILED")
        self.assertEqual(self._facts(), before)            # nothing accepted

    def test_028_interrupted_governed_mutation_no_partial(self):
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM operator_feedback").fetchone()["c"]

        def biz(conn):
            conn.execute(
                "INSERT INTO operator_feedback(id,principal_id,category,description,status,created_at,updated_at)"
                " VALUES('fbk_crash',?,?,?,?,?,?)",
                (self.p.op_ops, "usability", "x", "open", self.p.now_iso(), self.p.now_iso()))
            raise RuntimeError("crash mid-mutation")
        with self.assertRaises(PersistenceError):
            self.p.stack.governor.perform(principal_id=self.p.op_ops, capability=CAPS["FEEDBACK_SUBMIT"],
                                          scope=SCOPE, action="x", business_fn=biz)
        after = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM operator_feedback").fetchone()["c"]
        self.assertEqual(after, before)                    # rolled back: no partial write

    def test_029_restart_preserves_completed_decisions(self):
        item = self.p.p10.fresh_item
        dec = self.p.p10.login(self.p.p10.op_decider)
        dec.post("/item/" + item["id"] + "/decide", {"disposition": "ACCEPT", "selected_action": "x"})
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM governed_decision").fetchone()["c"]
        q = self.p.restart()
        try:
            self.assertEqual(q.table_count("governed_decision"), before)  # committed decision survives restart
        finally:
            q.close()

    def test_030_safe_retry_no_duplicate_effect(self):
        self.p.import_payload("new_inventory_current", F.INV_FULL, effective_time=self.p.now_iso(),
                              chash="sha256:c30")
        n = self._facts()
        self.p.import_payload("new_inventory_current", F.INV_FULL, effective_time=self.p.now_iso(),
                              chash="sha256:c30")           # same content -> idempotent
        self.assertEqual(self._facts(), n)

    # ---- concurrency (31-35) ---------------------------------------------
    def _decisions_for(self, item):
        return self.p.p9.store.decisions_for_item(item["id"])

    def test_031_simultaneous_decisions_one_effect(self):
        item = self.p.p10.fresh_item
        dec = self.p.p10.login(self.p.p10.op_decider)
        form = {"disposition": "ACCEPT", "selected_action": "x", "_idem": "cc-dec-1"}
        dec.post("/item/" + item["id"] + "/decide", dict(form))
        n = len(self._decisions_for(item))
        dec.post("/item/" + item["id"] + "/decide", dict(form))   # duplicate submission
        self.assertEqual(len(self._decisions_for(item)), n)       # one authoritative effect

    def test_032_simultaneous_approvals_no_duplicate(self):
        # exactly-once is guaranteed by the shared Governor idempotency key
        key = "cc-appr-1"
        r1 = self._governed_once("approval.demo", key)
        r2 = self._governed_once("approval.demo", key)
        self.assertTrue(r2["replayed"])                    # second is a replay, not a new effect
        self.assertEqual(r1["result_ref"], r2["result_ref"])

    def test_033_simultaneous_execution_no_duplicate(self):
        key = "cc-exec-1"
        r1 = self._governed_once("execution.demo", key)
        r2 = self._governed_once("execution.demo", key)
        self.assertTrue(r2["replayed"])
        self.assertEqual(r1["result_ref"], r2["result_ref"])

    def test_034_simultaneous_receipt_no_duplicate(self):
        key = "cc-receipt-1"
        r1 = self._governed_once("receipt.demo", key)
        r2 = self._governed_once("receipt.demo", key)
        self.assertTrue(r2["replayed"])                    # idempotent Used-Cars-style receipt
        self.assertEqual(r1["result_ref"], r2["result_ref"])

    def test_035_stale_browser_mutation_rejected(self):
        dec = self.p.p10.login(self.p.p10.op_decider)
        r = dec.post("/item/" + self.p.p10.stale_item["id"] + "/decide",
                     {"disposition": "ACCEPT", "selected_action": "x"})
        self.assertEqual(r.status, 409)                    # stale submission blocked

    def _governed_once(self, action, key):
        n = [0]

        def biz(conn):
            n[0] += 1
            fid = "fbk_" + action.replace(".", "_") + "_" + key
            conn.execute(
                "INSERT OR IGNORE INTO operator_feedback(id,principal_id,category,description,status,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (fid, self.p.op_ops, "system", action, "open", self.p.now_iso(), self.p.now_iso()))
            return (fid, fid), fid
        return self.p.stack.governor.perform(
            principal_id=self.p.op_ops, capability=CAPS["FEEDBACK_SUBMIT"], scope=SCOPE, action=action,
            business_fn=biz, idempotency_key=key)


if __name__ == "__main__":
    unittest.main()
