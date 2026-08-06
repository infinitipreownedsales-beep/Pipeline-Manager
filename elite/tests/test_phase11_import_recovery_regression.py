"""Phase 11 dedicated import-recovery regression (15-point).

Walks the full interrupted-import-and-recovery loop end to end and asserts every guarantee: a prior valid
state exists, a new import is received + validated + started, an interruption before acceptance rolls back
with the prior state intact, the interrupted run is failed/reviewable, a retry links to it, a corrected
retry succeeds with facts appearing exactly once, a restart does not replay, freshness updates, the
audit/correlation chain stays traceable, and ordinary logs expose no raw source or secret.
"""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE

V = "1GNSKBKC5FR000901"
W = "1GNSKBKC5FR000902"
X = "1GNSKBKC5FR000911"
Y = "1GNSKBKC5FR000912"
HEADER = "stock_number,vin,model,production_month,mileage"
GOOD = f"{HEADER}\nR1,{V},qx80,2026-03,5\nR2,{W},qx60,2026-04,3\n"
NEW = f"{HEADER}\nR3,{X},qx80,2026-05,4\nR4,{Y},qx60,2026-06,2\n"


class TestImportRecoveryRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _facts(self, vins, conn=None):
        conn = conn or self.p.stack.db.conn
        ph = ",".join("?" for _ in vins)
        return conn.execute(
            "SELECT COUNT(*) c FROM business_fact WHERE fact_type='vehicle_present' AND status='current'"
            f" AND subject_entity_id IN (SELECT id FROM vehicle_unit WHERE vin IN ({ph}))",
            tuple(vins)).fetchone()["c"]

    def test_import_recovery_regression(self):
        p = self.p
        sid = p.source_id("new_inventory_current")

        # 1. a last valid source state exists
        first = p.import_payload("new_inventory_current", GOOD, effective_time=p.now_iso(),
                                 chash="sha256:reg-good1")
        self.assertEqual(first["state"], "COMPLETED")
        last_valid = p.orch._last_completed(sid, SCOPE)
        self.assertEqual(last_valid, first["id"])
        self.assertEqual(self._facts([V, W]), 2)

        # 2-5. a NEW import (distinct units) is received, validated, begins, then is interrupted BEFORE
        # acceptance
        interrupted = p.import_payload("new_inventory_current", NEW, effective_time=p.now_iso(),
                                       chash="sha256:reg-intr", fail_at="ingest")

        # 6-7. the transaction rolled back; the prior valid state remains authoritative
        self.assertEqual(self._facts([X, Y]), 0)                           # the new snapshot accepted nothing
        self.assertEqual(self._facts([V, W]), 2)                           # prior valid state intact
        self.assertTrue(p.orch.accepted_state_intact(sid, SCOPE, last_valid))

        # 8. the interrupted run is failed / reviewable
        self.assertEqual(interrupted["state"], "FAILED")
        self.assertEqual(interrupted["failure_stage"], "INGESTING")

        # 9-10. a retry links to the interrupted run; a corrected retry succeeds
        retry = p.orch.retry(interrupted["id"], payload=NEW, content_hash="sha256:reg-retry",
                             effective_time=p.now_iso())
        self.assertEqual(retry["retry_of"], interrupted["id"])
        self.assertEqual(retry["state"], "COMPLETED")

        # 11. accepted facts appear exactly once (the retried snapshot applied a single time)
        self.assertEqual(self._facts([X, Y]), 2)

        # 12. a restart does not replay the import
        q = p.restart()
        try:
            self.assertEqual(self._facts([X, Y], q.db.conn), 2)
            self.assertEqual(self._facts([V, W], q.db.conn), 2)
            completed = [r for r in q.ops.list_import_runs(sid, SCOPE)
                         if r["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")]
            self.assertEqual(len(completed), 2)                            # first + corrected retry
        finally:
            q.close()

        # 13. source freshness updates correctly
        fr = p.freshness.evaluate(source_id=sid, scope=SCOPE, domain="new_inventory",
                                  last_received_at=p.now_iso(), source_effective_time=p.now_iso(),
                                  expected_cadence_seconds=999999999, stale_threshold_seconds=999999999)
        self.assertEqual(fr["status"], "CURRENT")

        # 14. the audit / correlation chain remains traceable
        self.assertEqual(interrupted["correlation_id"], "cor_p11")
        errs = p.ops.list_import_errors(interrupted["id"])
        self.assertTrue(errs)
        self.assertEqual(errs[0]["correlation_id"], "cor_p11")

        # 15. ordinary logs expose no raw source row or secret
        logs = p.log_text()
        self.assertNotIn(V, logs)                                         # no raw VIN
        self.assertNotIn(W, logs)
        self.assertNotIn("test-pepper", logs)                            # no credential pepper
        self.assertNotIn("pepper", logs.lower())
        self.assertNotIn("qx80", logs)                                   # no raw source-row field values


if __name__ == "__main__":
    unittest.main()
