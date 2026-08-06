"""Phase 12 focused single-operator Executive Demo regression (12-point).

Proves the sole-operator (Kyle) pilot workflow end-to-end THROUGH the operator UI, with an EXPLICIT,
audited, reversible single-operator pilot approval exception (not a fake second user, not an out-of-UI
workaround), and the two governed Executive Demo disposition routes (return-to-New-Retail, Used Cars
receipt) that call the ACTUAL Phase 7 services:

  1. Kyle signs in;
  2. opens the Executive Demo recommendation;
  3. issues the Decision (governed);
  4. approves it under the explicit single-operator pilot exception (self-proposed → self-approved);
  5. the exception is visible in the UI and audited (recorded on the approval, not pretended as normal SoD);
  6. execution invokes the REAL Executive Demo service (no synthetic callback);
  7. return to New Retail is confirmed THROUGH the UI (real Phase 7 return_to_new_retail);
  8. Used Cars receipt is confirmed THROUGH the UI (real Phase 7 confirm_used_cars_receipt, one action);
  9. completion + reconciliation are visible;
 10. replay does not duplicate;
 11. restart preserves the lifecycle;
 12. disabling the single-operator pilot removes the self-approval exception (SoD re-enforced).
"""
import os
import tempfile
import unittest

from elite.execdemo import lifecycle
from elite.ops.fixtures import RestartedStore
from elite.release.fixtures import Phase12, SCOPE
from elite.release.models import CAPS
from elite.ui.fixtures import Client

KYLE_CAPS = [
    "workspace.view", "workspace.review", "decision.issue", "decision.approve",
    "execution.authorize", "decision.acknowledge", "audit.view",
    CAPS["EXECUTE_LIVE"], "domain.execute",
    "executive_demo.retirement.execute",
    "executive_demo.return_to_retail.confirm", "executive_demo.used_cars_receipt.confirm",
]


class TestSingleOperatorExecDemo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase12(os.path.join(self.tmp, "elite.db"))
        # a single real operator (Kyle) with exactly the required first-use capabilities
        self.kyle = self.p.stack.authn.register("Kyle Montgomery — General Sales Manager", "pw").id
        for cap in KYLE_CAPS:
            self.p.stack.grant(self.kyle, cap, SCOPE)
        self.p.enable_execution("executive_demo")

    def tearDown(self):
        self.p.close()

    # -- helpers --------------------------------------------------------------
    def _approved_unit(self, vin):
        """A real ACTIVE Executive Demo unit advanced to RETIREMENT_APPROVED via the real Phase 7 lifecycle."""
        p = self.p
        unit = p.p7.make_active(vin, scope=SCOPE)
        p.p7.retirement.propose(p.p7.full, SCOPE, unit)
        unit = p.p7.store.get_unit(unit.id)
        p.p7.retirement.approve(p.p7.full, SCOPE, unit)
        return p.p7.store.get_unit(unit.id)

    def _to_retired(self, unit):
        """Advance an APPROVED unit to RETIRED (awaiting disposition) via the real governed transition."""
        p = self.p

        def eff(conn, cur):
            eid = p.p7.store.add_retirement_event(conn, cur.id, cur.retirement_decision, SCOPE)
            p.p7.store.set_unit_field(conn, cur.id, retirement_event=eid)
            return {"detail": "retired"}
        lifecycle.governed_transition(
            p.gov, p.p7.store, principal=p.p7.full, capability="executive_demo.retirement.execute",
            scope=SCOPE, unit_id=unit.id, expected_version=unit.version, to_state="RETIRED",
            action="executive_demo.retirement.execute", effect=eff)
        return p.p7.store.get_unit(unit.id)

    # -- the regression -------------------------------------------------------
    def test_single_operator_execdemo(self):
        p = self.p
        p.app.single_operator_pilot = True                    # explicit, reversible pilot exception ON

        # 1. Kyle signs in
        tok = p.app.login(self.kyle, "pw", SCOPE)
        self.assertIsNotNone(tok)
        c = Client(p.app, tok)

        # a real ACTIVE unit approved for retirement + a governed workspace item to decide on
        unit = self._approved_unit("1HGCM82633A900001")
        item = p.p9.item(domain="executive_demo", rec="rec_so_main", scope=SCOPE)

        # 2. Kyle opens the Executive Demo recommendation
        r = c.get("/item/" + item["id"])
        self.assertEqual(r.status, 200)

        # 3. Kyle issues the Decision (governed, through the UI)
        r = c.post("/item/" + item["id"] + "/decide",
                   {"disposition": "ACCEPT", "selected_action": "retire", "alternatives": "retire,hold",
                    "_idem": "so-decide-1"})
        self.assertEqual(r.status, 303)
        dec = p.p9.store.decisions_for_item(item["id"])[0]
        self.assertEqual(dec["decision_maker"], self.kyle)    # Kyle is the Decision maker

        # 4. Kyle approves it under the EXPLICIT single-operator pilot exception (self-proposed → self-approved)
        audit_before = p.stack.audit.count()
        r = c.post("/approval/" + dec["id"] + "/approve", {"_idem": "so-approve-1"})
        self.assertEqual(r.status, 303)
        approvals = p.p9.store.approvals_for(dec["id"])
        self.assertTrue(approvals)                             # a real approval exists
        ap = p.p9.store.get_approval(approvals[-1]["id"])

        # 5. the exception is recorded on the approval (NOT pretended as normal SoD) and audited + visible
        self.assertIn("single_operator_pilot_exception", ap["conditions"])
        self.assertIn("NOT_SATISFIED_SINGLE_OPERATOR_PILOT", ap["conditions"])
        self.assertGreater(p.stack.audit.count(), audit_before)   # the governed approval is audited
        body = c.get("/execution").body
        self.assertIn("single-operator pilot exception", body.lower())   # visible in the UI

        # 6. execution invokes the REAL Executive Demo service (no synthetic callback)
        def real_call(principal, sc):
            cur = p.p7.store.get_unit(unit.id)
            if cur.membership_state != "RETIREMENT_APPROVED":
                return cur.retirement_event or ("edrev_" + unit.id)
            p.p7.retirement.execute(principal, sc, cur, disposition="new_retail")
            return p.p7.store.get_unit(unit.id).retirement_event or ("edrev_" + unit.id)
        p.live.bind(dec["id"], domain="executive_demo", action="executive_demo.retirement.execute",
                    real_call=real_call, expected_action="retire")
        self.assertFalse(p.registry.is_synthetic("executive_demo.retirement.execute"))
        r = c.post("/execution/" + dec["id"] + "/authorize", {"_idem": "so-exec-1"})
        self.assertEqual(r.status, 303)
        self.assertEqual(p.p7.store.get_unit(unit.id).membership_state, "RETURNED_TO_NEW_RETAIL")

        # 9. completion + reconciliation are visible (execution queue renders; reconcile is terminal)
        self.assertEqual(c.get("/execution").status, 200)
        self.assertIn(p.p9.execution.reconcile(dec), ("COMPLETED", "ALREADY_RECONCILED"))

        # 10. replay does not duplicate
        state1 = p.p7.store.get_unit(unit.id).membership_state
        c.post("/execution/" + dec["id"] + "/authorize", {"_idem": "so-exec-1"})
        self.assertEqual(p.p7.store.get_unit(unit.id).membership_state, state1)

        # 7. return to New Retail confirmed THROUGH the UI (real Phase 7 service, fresh RETIRED unit)
        ur = self._to_retired(self._approved_unit("1HGCM82633A900002"))
        r = c.post("/executive-demo/" + ur.id + "/return-to-retail", {"_idem": "so-ret-1"})
        self.assertEqual(r.status, 303)
        self.assertEqual(p.p7.store.get_unit(ur.id).membership_state, "RETURNED_TO_NEW_RETAIL")

        # 8. Used Cars receipt confirmed THROUGH the UI (real Phase 7 service, one action, no checklist)
        uu = self._approved_unit("1HGCM82633A900003")
        p.p7.retirement.execute(p.p7.full, SCOPE, uu, disposition="used_cars")   # -> AWAITING_USED_CARS_RECEIPT
        self.assertEqual(p.p7.store.get_unit(uu.id).membership_state, "AWAITING_USED_CARS_RECEIPT")
        r = c.post("/executive-demo/" + uu.id + "/used-cars", {"_idem": "so-uc-1"})
        self.assertEqual(r.status, 303)
        self.assertEqual(p.p7.store.get_unit(uu.id).membership_state, "USED_CARS_RECEIVED")
        # idempotent replay of the one-action confirmation
        c.post("/executive-demo/" + uu.id + "/used-cars", {"_idem": "so-uc-2"})
        self.assertEqual(p.p7.store.get_unit(uu.id).membership_state, "USED_CARS_RECEIVED")

        # 11. restart preserves the lifecycle (the durable records survive a re-open)
        execs = p.stack.db.conn.execute(
            "SELECT COUNT(*) c FROM execution_authorization").fetchone()["c"]
        receipts = p.stack.db.conn.execute(
            "SELECT COUNT(*) c FROM executive_demo_used_cars_receipt").fetchone()["c"]
        q = RestartedStore(p.stack.db.path, p.clock)
        try:
            self.assertEqual(q.table_count("execution_authorization"), execs)
            self.assertEqual(q.table_count("executive_demo_used_cars_receipt"), receipts)
        finally:
            q.close()

        # 12. disabling the single-operator pilot removes the exception (SoD re-enforced)
        p.app.single_operator_pilot = False
        item2 = p.p9.item(domain="executive_demo", rec="rec_so_off", scope=SCOPE)
        c.post("/item/" + item2["id"] + "/decide",
               {"disposition": "ACCEPT", "selected_action": "retire", "_idem": "so-decide-2"})
        dec2 = p.p9.store.decisions_for_item(item2["id"])[0]
        blocked = c.post("/approval/" + dec2["id"] + "/approve", {"_idem": "so-approve-2"})
        self.assertEqual(blocked.status, 403)                    # self-approval refused when exception is off
        self.assertFalse(p.p9.store.approvals_for(dec2["id"]))   # no approval recorded


if __name__ == "__main__":
    unittest.main()
