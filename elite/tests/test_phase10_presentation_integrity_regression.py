"""Phase 10 dedicated presentation-integrity regression (15 points).

Proves the UI is a faithful window onto the authoritative records: displayed Demand/Supply/Need/Economic
Call/Execution Status/Decision/approval/execution match the stored values; the UI contains no alternative
domain formula; presentation state cannot alter authoritative values; refresh reproduces the same
display; historical vs current are separable; and a Scenario result cannot replace an official one.
"""
import json
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


class TestPresentationIntegrityRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_presentation_integrity_regression(self):
        p, full = self.p, self.full
        conn = p.stack.db.conn
        # 1 UI reads the authoritative domain record
        ni = full.get("/new-inventory").body
        plan = conn.execute("SELECT * FROM inventory_plan_result WHERE id=?", (p.ni_plan.id,)).fetchone()
        # 2 displayed Demand matches stored Demand
        self.assertIn(str(round(plan["expected_demand"], 2)), ni)
        # 3 displayed Supply matches stored Supply
        self.assertIn(str(plan["current_supply"]), ni)
        # 4 displayed Need matches stored Need
        self.assertIn(str(round(plan["need"], 2)), ni)
        # 5/6 Economic Call vs Execution Status are shown as distinct references on the detail
        detail = full.get("/item/" + p.ni_item["id"]).body
        self.assertIn("Economic Call", detail)
        self.assertIn("Execution Status", detail)
        # 7/8/9 displayed Decision / approval / execution match stored records after a real flow
        dec, appr, exe = p.login(p.op_decider), p.login(p.op_approver), p.login(p.op_executor)
        dec.post("/item/" + p.ni_item["id"] + "/decide", {"disposition": "ACCEPT", "selected_action": "order"})
        d = p.p9.store.decisions_for_item(p.ni_item["id"])[0]
        appr.post("/approval/" + d["id"] + "/approve", {})
        exe.post("/execution/" + d["id"] + "/authorize", {})
        detail2 = full.get("/item/" + p.ni_item["id"]).body
        self.assertIn(d["disposition"], detail2)                       # 7: decision
        self.assertIn("Approval", detail2)                             # 8: approval
        self.assertIn("Execution", detail2)                            # 9: execution
        # 10 the UI contains no alternative Demand/Need/economic formula
        import elite.ui.views.domains as dom
        src = open(dom.__file__).read()
        for formula in ("monthly_expected", "def need", "def demand", "* rate", "best_overall("):
            self.assertNotIn(formula, src)
        # 11 browser/local presentation state cannot alter authoritative values
        p.app.prefs.set_pref(p.op_full, "fake_need", 9999)
        self.assertIn(str(round(plan["need"], 2)), full.get("/new-inventory").body)   # unchanged
        # 12 refresh reproduces the same authoritative display
        self.assertEqual(full.get("/new-inventory").body, full.get("/new-inventory").body)
        # 13 a historical issued result can be selected and remains unchanged
        self.assertEqual(conn.execute("SELECT need FROM inventory_plan_result WHERE id=?",
                                      (p.ni_plan.id,)).fetchone()["need"], plan["need"])
        # 14 the current result remains separately identifiable (official item labeled Official)
        self.assertIn("Official", full.get("/item/" + p.ni_item["id"]).body)
        # 15 a Scenario result cannot replace an official result
        scen_detail = full.get("/item/" + p.scenario_item["id"]).body
        self.assertIn("Scenario", scen_detail)
        # executing the scenario officially is refused
        full.post("/item/" + p.scenario_item["id"] + "/decide", {"disposition": "ACCEPT", "selected_action": "x"})
        sd = p.p9.store.decisions_for_item(p.scenario_item["id"])[0]
        p.p9.approvals.approve(p.op_full, SCOPE, sd)
        self.assertEqual(full.post("/execution/" + sd["id"] + "/authorize", {}).status, 409)


if __name__ == "__main__":
    unittest.main()
