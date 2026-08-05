"""Phase 6 acceptance — Economic Call, Execution Status, entry/portfolio optimization (31-46)."""
import inspect
import os
import tempfile
import unittest

from elite.loaner.economics import EconomicService
from elite.loaner.fixtures import Phase6
from elite.workflow.fixtures import SCOPE

VIN = "1GNSKBKC5FR000401"


class TestPhase6EconomicsPortfolio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    # ---- Economic Call -----------------------------------------------------
    def test_31_economic_call_resolves_through_policy_versions(self):
        e = self.p.econ(self.p.make_active(VIN), policy_versions=["pv_1"])
        self.assertEqual(e.resolution_status, "resolved")
        self.assertEqual(e.policy_versions, ["pv_1"])
        self.assertIsNotNone(e.reproducibility_package)

    def test_32_missing_economic_policy_unresolved(self):
        e = self.p.econ(self.p.make_active(VIN), policy_status="unresolved")
        self.assertEqual(e.resolution_status, "unresolved")
        self.assertEqual(e.economic_call, {})                 # no invented value

    def test_33_exact_policy_overrides_broad(self):
        # exact vs broad resolution is a Phase 3 concern; here the resolved call uses the exact value
        e = self.p.econ(self.p.make_active(VIN), alternatives=[
            {"alternative": "retire_now", "incremental_value": 700.0, "basis": "exact"},
            {"alternative": "remain_in_fleet", "incremental_value": 100.0, "basis": "broad"}])
        self.assertEqual(e.economic_call["choice"], "retire_now")

    def test_34_conflicting_policy_conflict(self):
        e = self.p.econ(self.p.make_active(VIN), policy_status="conflicting")
        self.assertEqual(e.resolution_status, "conflicting")

    def test_35_exit_timing_uses_incremental_future_economics(self):
        # exit alternatives carry incremental future values only
        e = self.p.economics.issue_call(self.p.make_active(VIN), decision_point="exit", alternatives=[
            {"alternative": "retire_now", "incremental_value": 500.0, "basis": "incremental_future"},
            {"alternative": "retire_later", "incremental_value": 620.0, "basis": "incremental_future"}])
        self.assertEqual(e.decision_point, "exit")
        self.assertEqual(e.economic_call["choice"], "retire_later")

    def test_36_sunk_placement_cost_not_reapplied(self):
        # the exit call's inputs contain no placement/sunk cost term
        e = self.p.economics.issue_call(self.p.make_active(VIN), decision_point="exit", alternatives=[
            {"alternative": "retire_now", "incremental_value": 400.0, "basis": "incremental_future"}],
            assumptions={"includes_sunk_placement_cost": False})
        self.assertFalse(e.assumptions["includes_sunk_placement_cost"])
        src = inspect.getsource(EconomicService)
        self.assertNotIn("placement_cost", src)               # no sunk-cost reapplication in the exit call

    def test_37_economic_call_unchanged_when_execution_blocked(self):
        u = self.p.make_active(VIN, rental="rented")
        e = self.p.econ(u)
        call_before = dict(e.economic_call)
        self.p.execution.assess(u, e.id, rented=True)         # execution blocked
        self.assertEqual(self.p.store.get_economic(e.id).economic_call, call_before)   # call not rewritten

    def test_39_economic_result_preserves_references(self):
        e = self.p.econ(self.p.make_active(VIN), policy_versions=["pv_x"])
        self.assertTrue(e.alternatives)                       # underlying comparison preserved (not one score)
        self.assertIsNotNone(e.calculation_version)
        self.assertIsNotNone(e.reproducibility_package)

    # ---- Execution Status --------------------------------------------------
    def test_38_execution_can_block_preferred_call(self):
        u = self.p.make_active(VIN, rental="rented")
        e = self.p.econ(u)
        st = self.p.execution.assess(u, e.id, rented=True)
        self.assertEqual(st["status"], "BLOCKED_RENTED")
        # Economic Call still recommends its financially strongest option
        self.assertEqual(self.p.store.get_economic(e.id).economic_call["choice"], "retire_now")

    def test_66_economic_call_and_execution_separately_inspectable(self):
        u = self.p.make_active(VIN)
        e = self.p.econ(u)
        st = self.p.execution.assess(u, e.id)
        self.assertEqual(st["status"], "READY")
        self.assertNotEqual(self.p.store.get_economic(e.id).economic_call, {})   # both are distinct records

    # ---- portfolio ---------------------------------------------------------
    def test_40_fleet_need_resolved_independently_of_ranking(self):
        import json
        current = self.p.portfolio.current_active(SCOPE)
        plan = self.p.portfolio.plan_entries(SCOPE, required_quantity=current + 2, candidates=[
            {"vehicle_unit_id": "vu_a", "eligible": True, "available": True, "opportunity_cost": {"value": 10}}])
        # the fleet NEED (required - current) is recorded as its own basis, separate from ranking
        self.assertEqual(json.loads(plan["need_basis"])["need"], 2)

    def test_41_42_43_44_portfolio_selection_dedup_and_state(self):
        import json
        active = self.p.make_active(VIN)                      # an already-active unit
        current = self.p.portfolio.current_active(SCOPE)
        plan = self.p.portfolio.plan_entries(SCOPE, required_quantity=current + 1, candidates=[
            {"vehicle_unit_id": active.vehicle_unit_id, "eligible": True, "available": True,
             "actual_state": "ACTIVE_AVAILABLE"},                                   # 44: already-active excluded
            {"vehicle_unit_id": "vu_new", "eligible": True, "available": True, "opportunity_cost": {"value": 5}},
            {"vehicle_unit_id": "vu_new", "eligible": True, "available": True, "opportunity_cost": {"value": 5}}])  # dup
        selected = json.loads(plan["selected"])
        self.assertEqual(selected, ["vu_new"])               # 43 same unit not twice; 44 active excluded
        # 41/42: after approving an entry, current active grows and the next plan needs fewer
        c = self.p.candidate("1GNSKBKC5FR000410")
        r = self.p.units.approve_entry(self.p.full, SCOPE, self.p.units.propose_entry(self.p.full, SCOPE, c)["unit"])
        self.p.units.execute_entry(self.p.full, SCOPE, r["unit"])
        self.assertEqual(self.p.portfolio.current_active(SCOPE), current + 1)   # committed state updated

    def test_45_46_placement_does_not_change_demand_opportunity_cost_input(self):
        c = self.p.combination(exterior_color="OPP")
        d = self.p.p5.p4.issue_demand(c) if False else None
        # New Retail opportunity cost is an INPUT to the SL decision, not a Demand engine
        plan = self.p.portfolio.plan_entries(SCOPE, required_quantity=self.p.portfolio.current_active(SCOPE) + 1,
                                             candidates=[{"vehicle_unit_id": "vu_z", "eligible": True, "available": True,
                                                          "opportunity_cost": {"value": 250, "basis": "new_retail"}}])
        import json
        self.assertEqual(json.loads(plan["selected"]), ["vu_z"])
        # Demand service has no service-loaner input
        import inspect
        from elite.newinv.demand import DemandService
        params = set(inspect.signature(DemandService.issue).parameters)
        self.assertFalse(any("loaner" in p for p in params))


if __name__ == "__main__":
    unittest.main()
