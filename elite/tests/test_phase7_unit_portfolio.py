"""Phase 7 acceptance — Executive Demo Unit + lifecycle, portfolio need, eligibility (items 1-20)."""
import os
import tempfile
import unittest

from elite.execdemo.fixtures import Phase7
from elite.workflow.fixtures import SCOPE

V = "1HGCM82633A100001"


class TestPhase7UnitPortfolio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase7(self.dbp)
        self.c, self.plan = self.p.nr_plan(position="need")

    def tearDown(self):
        self.p.close()

    def _u(self, uid):
        return self.p.store.get_unit(uid)

    def _designate(self, vin):
        u = self.p.candidate_unit(vin, self.c.id)
        self.p.p4.seed_current(self.c, [{"vehicle_unit_id": u.vehicle_unit_id, "state": "available_unsold",
                                        "identity_status": "resolved"}])
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        return self.p.units.execute_designation(self.p.full, SCOPE, self._u(u.id))

    def test_01_unit_survives_restart(self):
        u = self.p.candidate_unit(V, self.c.id)
        self.p.close()
        p2 = Phase7(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_unit(u.id))

    def test_02_03_vehicle_identity_not_replaced(self):
        u = self.p.candidate_unit(V, self.c.id)
        self.assertIsNotNone(u.vehicle_unit_id)
        self.assertNotEqual(u.id, u.vehicle_unit_id)

    def test_04_05_domains_separate_no_dual_active(self):
        self.p.p6.make_active(V, combination_id=self.c.id)          # active Service Loaner
        u = self.p.candidate_unit(V, self.c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        from elite.errors import ValidationError
        with self.assertRaises(ValidationError):                    # cannot be active demo while active loaner
            self.p.units.execute_designation(self.p.full, SCOPE, self._u(u.id))

    def test_06_candidate_not_membership(self):
        u = self.p.candidate_unit(V, self.c.id)
        self.assertEqual(u.membership_state, "CANDIDATE")
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 0)

    def test_07_approval_not_membership(self):
        u = self.p.candidate_unit(V, self.c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        r = self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(r["unit"].membership_state, "DESIGNATION_APPROVED")
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 0)   # committed, not active

    def test_08_execution_establishes_membership_once(self):
        r = self._designate(V)
        self.assertEqual(r["unit"].membership_state, "ACTIVE")
        self.assertIsNotNone(r["unit"].designation_execution_event)
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 1)

    def test_09_replayed_approval_no_duplicate_committed(self):
        u = self.p.candidate_unit(V, self.c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self.p.portfolio.committed(SCOPE), 1)
        # re-approving an already-approved unit is an illegal transition (no second commit)
        from elite.errors import ValidationError
        with self.assertRaises(ValidationError):
            self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self.p.portfolio.committed(SCOPE), 1)

    def test_10_replayed_execution_no_duplicate(self):
        r = self._designate(V)
        ev = r["unit"].designation_execution_event
        r2 = self.p.units.execute_designation(self.p.full, SCOPE, self._u(r["unit"].id))
        self.assertTrue(r2["replayed"])
        self.assertEqual(self._u(r["unit"].id).designation_execution_event, ev)

    def test_11_cancellation_removes_committed_preserves_history(self):
        u = self.p.candidate_unit(V, self.c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.cancel_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self._u(u.id).membership_state, "CANCELLED")
        self.assertEqual(self.p.portfolio.committed(SCOPE), 0)
        states = [h["to_state"] for h in self.p.store.membership_history(u.id)]
        self.assertIn("DESIGNATION_PROPOSED", states)               # history preserved

    def test_12_need_resolved_independently_of_ranking(self):
        basis = self.p.portfolio.determine_need(SCOPE, 3)
        self.assertEqual(basis["need"], 3)                          # required - active - committed

    def test_13_active_and_committed_affect_need(self):
        self._designate(V)                                          # +1 active
        u2 = self.p.candidate_unit("1HGCM82633A100002", self.c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u2)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u2.id))   # +1 committed
        self.assertEqual(self.p.portfolio.determine_need(SCOPE, 3)["need"], 1)

    def test_14_healthy_portfolio_no_recommendation(self):
        plan = self.p.portfolio.best_overall(SCOPE, required_size=0, candidates=[
            {"vehicle_unit_id": "x", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 1}, "portfolio_fit": {"value": 1}}])
        import json
        self.assertEqual(json.loads(plan["selected"]), [])          # no need -> nothing selected

    def test_15_16_service_loaner_need_and_demand_excluded(self):
        # Executive Demo need has no Service Loaner dependency; Demand is never recalculated here.
        import elite.execdemo.portfolio as pf
        src = open(pf.__file__).read()
        self.assertNotIn("..loaner", src)                          # no import of the Service Loaner package
        self.assertNotIn("LoanerStore", src)
        self.assertNotIn("monthly_expected", src)                  # no Demand computation
        # need is a pure function of required size + this domain's active/committed counts
        basis = self.p.portfolio.determine_need(SCOPE, 2)
        self.assertEqual(set(basis), {"required", "current_active", "committed", "need"})

    def test_17_eligibility_separate_from_ranking(self):
        e = self.p.eligibility.assess("vu1", "c1", SCOPE)
        self.assertEqual(e["outcome"], "ELIGIBLE")
        self.assertTrue(e["reasons"])                               # explains its reason

    def test_18_active_service_loaner_ineligible(self):
        e = self.p.eligibility.assess("vu1", "c1", SCOPE, is_active_service_loaner=True)
        self.assertEqual(e["outcome"], "INELIGIBLE_ACTIVE_SERVICE_LOANER")

    def test_19_already_active_demo_ineligible(self):
        e = self.p.eligibility.assess("vu1", "c1", SCOPE, already_demo=True)
        self.assertEqual(e["outcome"], "INELIGIBLE_ALREADY_DEMO")

    def test_20_sold_or_unresolved_not_silently_eligible(self):
        self.assertEqual(self.p.eligibility.assess("v", "c", SCOPE, sold=True)["outcome"], "INELIGIBLE_SOLD")
        self.assertEqual(self.p.eligibility.assess("v", "c", SCOPE, identity_ok=False)["outcome"],
                         "INELIGIBLE_IDENTITY")


if __name__ == "__main__":
    unittest.main()
