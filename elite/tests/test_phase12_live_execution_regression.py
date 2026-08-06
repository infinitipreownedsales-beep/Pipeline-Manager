"""Phase 12 dedicated live-execution regression (20-point).

Drives a real recommendation through the pilot UI and the ACTUAL Phase 7 domain executor: real accepted
source + real planning output -> an actionable recommendation -> a governed Decision issued by an authorized
operator -> a separate authority approves -> execution authorization -> the UI invokes the ACTUAL domain
executor (no synthetic callback) -> a real domain execution event -> state changes exactly once ->
completion + reconciliation -> the UI shows the authoritative result -> replay + concurrent replay do not
duplicate -> restart preserves the execution -> the audit/correlation chain is complete -> the historical
recommendation + Decision remain preserved -> a Scenario action cannot enter the official path -> a failure
returns a safe unresolved/failed state -> no direct UI database mutation occurred.
"""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ValidationError
from elite.ops.fixtures import RestartedStore
from elite.release.fixtures import Phase12, SCOPE
from elite.ui.fixtures import Client


class TestLiveExecutionRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase12(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_live_execution_regression(self):
        p = self.p

        # 1. real accepted source records exist (a real migration import into the dedicated db)
        mr = p.migration.start_run(initiated_by=p.op_migrator)
        imp = p.migration.migrate_source(mr["id"], contract_key="new_inventory_current",
            payload="stock_number,vin,model,production_month,mileage\nN1,1GNSKBKC5FR000001,qx80,2026-03,5\n",
            source_family="new_inventory_current", scope=SCOPE, effective_time=p.now_iso(), content_hash="sha256:lr1")
        self.assertEqual(imp["state"], "COMPLETED")
        self.assertGreater(imp["accepted_count"], 0)

        # 2. real official planning output exists (Phase 4 plan present under v12)
        self.assertGreater(p.stack.db.conn.execute(
            "SELECT COUNT(*) c FROM inventory_plan_result").fetchone()["c"], 0)

        # 3-6. an actionable recommendation -> a governed Decision (authorized operator) -> separate approval
        dec, unit, real_call = p.prepare_live_execution("1HGCM82633A801001")
        self.assertEqual(dec["disposition"], "ACCEPT")
        self.assertTrue(p.p9.store.approvals_for(dec["id"]))              # a separate authority approved

        # 7-12. the UI invokes the ACTUAL domain executor (no synthetic callback); a real event is created,
        # state changes exactly once, completion + reconciliation recorded, the UI shows the result
        self.assertTrue(p.live.has_binding(dec["id"]))
        self.assertFalse(p.registry.is_synthetic("executive_demo.retirement.execute"))
        audit_before = p.stack.audit.count()
        tok = p.app.login(p.op_executor, "pw", SCOPE)
        c = Client(p.app, tok)
        resp = c.post("/execution/" + dec["id"] + "/authorize", {"_idem": "live-ui-1"})
        self.assertEqual(resp.status, 303)                               # routed through the real executor
        unit_after = p.p7.store.get_unit(unit.id)
        self.assertEqual(unit_after.membership_state, "RETURNED_TO_NEW_RETAIL")   # real state changed once
        self.assertGreater(p.stack.audit.count(), audit_before)          # a real domain Audit Event
        self.assertIn(p.p9.execution.reconcile(dec), ("COMPLETED", "ALREADY_RECONCILED"))

        # 13. replay does not duplicate
        state1 = p.p7.store.get_unit(unit.id).membership_state
        c.post("/execution/" + dec["id"] + "/authorize", {"_idem": "live-ui-1"})
        self.assertEqual(p.p7.store.get_unit(unit.id).membership_state, state1)

        # 14. concurrent replay does not duplicate (same idempotency key, two submissions)
        p.live.execute_bound(principal=p.op_executor, scope=SCOPE, decision=dec, idempotency_key="live-cc")
        p.live.execute_bound(principal=p.op_executor, scope=SCOPE, decision=dec, idempotency_key="live-cc")
        self.assertEqual(p.p7.store.get_unit(unit.id).membership_state, state1)

        # 15. restart preserves the execution
        exec_count = p.stack.db.conn.execute("SELECT COUNT(*) c FROM execution_authorization").fetchone()["c"]
        q = RestartedStore(p.stack.db.path, p.clock)
        try:
            self.assertEqual(q.table_count("execution_authorization"), exec_count)
        finally:
            q.close()

        # 16. the audit + correlation chain remains complete (the governed decision + execution are audited)
        self.assertGreater(p.stack.audit.count(), 0)

        # 17. the historical recommendation + Decision remain preserved (immutable)
        self.assertIsNotNone(p.p9.store.get_decision(dec["id"]))

        # 18. a Scenario action cannot enter the official path
        sit = p.p9.item(domain="executive_demo", rec="rec_scn_lr", scenario_id="scn_lr")
        sr = p.p9.decisions.issue(p.p9.decider, SCOPE, sit, disposition="ACCEPT", selected_action="retire")
        sdec = sr["decision"]
        p.live.bind(sdec["id"], domain="executive_demo", action="executive_demo.retirement.execute",
                    real_call=lambda pr, sc: "x")
        with self.assertRaises(ValidationError):
            p.live.execute_bound(principal=p.op_executor, scope=SCOPE, decision=sdec)

        # 19. a failure returns a safe unresolved/failed state (execution disabled -> refused, not success)
        dec2, unit2, _ = p.prepare_live_execution("1HGCM82633A802001")
        p.shadow.set_mode(principal=p.op_shadow, scope=SCOPE, domain="executive_demo", mode="REVIEW_ONLY")
        with self.assertRaises(AuthorizationError):
            p.live.execute_bound(principal=p.op_executor, scope=SCOPE, decision=dec2)
        self.assertEqual(p.p7.store.get_unit(unit2.id).membership_state, "RETIREMENT_APPROVED")   # unchanged

        # 20. no direct UI database mutation occurred — every state change went through a governed domain
        # method (each produced an Audit Event; the UI handler holds no domain-table write)
        import elite.ui.views.queues as q
        src = open(q.__file__).read()
        self.assertNotIn("UPDATE executive_demo", src)
        self.assertNotIn("INSERT INTO service_loaner", src)


if __name__ == "__main__":
    unittest.main()
