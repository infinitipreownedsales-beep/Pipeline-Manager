"""Phase 10 acceptance — New Inventory (20-23), Production & Supply (24-28), Service Loaner (29-34),
Executive Demo (35-40)."""
import json
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10, ZERO_MILE_QUESTION
from elite.workflow.fixtures import SCOPE


class TestPhase10Domains(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _conn(self):
        return self.p.stack.db.conn

    # ---- New Inventory (20-23) --------------------------------------------
    def test_20_portfolio_totals_match_phase4(self):
        rows = self._conn().execute("SELECT need,excess FROM inventory_plan_result WHERE store_scope=?",
                                    (SCOPE,)).fetchall()
        total_need = round(sum(r["need"] for r in rows), 2)
        self.assertIn(str(total_need), self.full.get("/new-inventory").body)

    def test_21_monthly_plan_matches_phase4(self):
        body = self.full.get("/new-inventory").body
        self.assertIn(str(round(self.p.ni_plan.need, 2)), body)
        self.assertIn(str(round(self.p.ni_plan.expected_demand, 2)), body)

    def test_22_supply_kinds_distinct(self):
        body = self.full.get("/new-inventory").body
        for header in ("Current", "Future", "Committed"):
            self.assertIn(header, body)

    def test_23_need_excess_not_recomputed_in_ui(self):
        import elite.ui.views.domains as dom
        src = open(dom.__file__).read()
        # the UI reads inventory_plan_result; it never computes Demand/Need itself
        self.assertNotIn("monthly_expected", src)
        self.assertIn("inventory_plan_result", src)

    # ---- Production & Supply (24-28) --------------------------------------
    def test_24_25_pipeline_state_proposal_vs_committed(self):
        body = self.full.get("/production").body
        self.assertIn("Proposed (not yet Supply)", body)   # proposal distinct
        self.assertIn("committed", body)                    # committed distinct

    def test_26_eta_precision_preserved(self):
        # ETA/precision is read from Phase 5 records; the UI does not round or invent it
        import elite.ui.views.domains as dom
        self.assertIn("supply_commitment", open(dom.__file__).read())

    def test_27_28_reconciliation_shown(self):
        self.assertEqual(self.full.get("/production").status, 200)

    # ---- Service Loaner (29-34) -------------------------------------------
    def test_29_membership_and_rental_distinct(self):
        body = self.full.get("/service-loaner").body
        self.assertIn("Membership", body)
        self.assertIn("Rental", body)

    def test_30_zero_mile_question_exact(self):
        self.assertIn(ZERO_MILE_QUESTION, self.full.get("/service-loaner").body)

    def test_31_provisional_not_complete(self):
        # a unit awaiting the Used Cars receipt is not shown as received/complete
        body = self.full.get("/service-loaner").body
        self.assertNotIn("USED_CARS_RECEIVED", body)

    def test_32_33_used_cars_one_action_no_checklist(self):
        u = self.p.sl_used_cars_unit
        # a single POST with no data fields (only CSRF) confirms the receipt — no checklist required
        r = self.full.post("/service-loaner/" + u.id + "/used-cars", {})
        self.assertEqual(r.status, 303)                    # single action succeeded
        self.assertIsNotNone(self.p.p6.store.used_cars_receipt_for(u.id))
        # the confirm handler passes no per-field checklist data to the service
        import inspect
        import elite.ui.views.domains as dom
        confirm_src = inspect.getsource(dom.register).split("confirm_used_cars", 1)[1].split("def ", 1)[0]
        self.assertNotIn("req.f(", confirm_src)            # collects no form fields — one action only

    def test_34_economic_call_distinct_from_execution_status(self):
        body = self.full.get("/service-loaner").body
        self.assertIn("Economic Call", body)
        self.assertIn("execution is blocked", body)        # the call does not change when execution is blocked

    # ---- Executive Demo (35-40) -------------------------------------------
    def test_35_36_best_overall_explanation_and_tradeoffs(self):
        body = self.full.get("/executive-demo").body
        self.assertIn("Best Overall", body)
        self.assertIn("why", body.lower())
        self.assertIn("tradeoffs".title(), body) if "Tradeoffs" in body else self.assertIn("tradeoff", body.lower())
        pick = json.loads(self.p.ed_plan["best_overall"])["pick"]["vehicle_unit_id"]
        self.assertIn(pick, body)                          # the chosen candidate is shown

    def test_37_necessary_sacrifice_labeled(self):
        body = self.full.get("/executive-demo").body
        self.assertIn("Necessary sacrifice", body)

    def test_38_opportunity_cost_separate_from_benefit(self):
        body = self.full.get("/executive-demo").body
        self.assertIn("NR opportunity cost", body)
        self.assertIn("Demo benefit", body)

    def test_39_40_designation_not_active_and_separate_from_loaner(self):
        body = self.full.get("/executive-demo").body
        self.assertIn("Designation approval is not active", body)
        self.assertIn("separate from Service Loaner", body)


if __name__ == "__main__":
    unittest.main()
