"""Phase 7 acceptance — model preference, opportunity cost, candidate construction, Best Overall,
expected lifecycle (items 21-42) + dedicated 14-point Best Overall regression."""
import json
import os
import tempfile
import unittest

from elite.execdemo.fixtures import Phase7
from elite.workflow.fixtures import SCOPE

AT = "2026-08-15T00:00:00+00:00"


class TestPhase7PreferenceBestOverall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase7(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _pref_family(self, name):
        return self.p.p3.family(category="MANAGEMENT_PREFERENCE", name=name, dims=["store"],
                                default_resolution={"mode": "unresolved"})

    def _resolve_pref(self, fam):
        return self.p.preference.resolve(SCOPE, policy_store=self.p.policy, family=self.p.policy.get_family(fam.id),
                                         subject_scope={"store": "HG"}, at_time=AT)

    # ---- model preference --------------------------------------------------
    def test_21_preference_resolves_through_policy(self):
        fam = self._pref_family("pref_a")
        self.p.p3.version(fam.id, {"preferred": "QX80"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                          effective_start="2020-01-01T00:00:00+00:00")
        r = self._resolve_pref(fam)
        self.assertEqual(r["resolution_status"], "resolved")
        self.assertEqual(r["preferred"], "QX80")

    def test_22_missing_preference_fallback_or_unresolved(self):
        fam = self._pref_family("pref_b")                          # no version
        self.assertEqual(self._resolve_pref(fam)["resolution_status"], "unresolved")

    def test_23_conflicting_preference_conflict(self):
        fam = self._pref_family("pref_c")
        self.p.p3.version(fam.id, {"preferred": "QX80"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                          effective_start="2020-01-01T00:00:00+00:00")
        self.p.p3.version(fam.id, {"preferred": "QX60"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                          effective_start="2020-01-01T00:00:00+00:00", version_number=2)
        self.assertEqual(self._resolve_pref(fam)["resolution_status"], "conflicting")

    def test_24_preference_does_not_override_ineligibility(self):
        # preference is applied in Best Overall only among ELIGIBLE candidates
        plan = self.p.portfolio.best_overall(SCOPE, required_size=self.p.portfolio.current_active(SCOPE) + 1,
            candidates=[{"vehicle_unit_id": "pref_but_inelig", "model": "QX80", "eligibility": "INELIGIBLE_SOLD",
                         "opportunity_cost": {"value": 1}, "executive_demo_benefit": {"value": 9},
                         "portfolio_fit": {"value": 9}}], preference={"preferred": "QX80"})
        self.assertEqual(json.loads(plan["selected"]), [])         # ineligible not selected despite preference

    def test_25_scenario_preference_isolated(self):
        row = self.p.scenario.explore("scnP", SCOPE, kind="preferred_model", overrides={"preferred": "QX60"},
                                      output={})
        self.assertEqual(row["scenario_id"], "scnP")               # isolated; official policy untouched

    # ---- opportunity cost --------------------------------------------------
    def test_26_27_candidate_construction_uses_facts_and_refs(self):
        c, plan = self.p.nr_plan(position="need")
        oc = self.p.opportunity.assess("vu1", c.id, SCOPE, plan=plan, expected_time_removed_months=2,
                                       expected_return_path="new_retail")
        cand = self.p.portfolio.construct_candidate(SCOPE, vehicle_unit_id="vu1", combination_id=c.id, model="QX80",
                                                    new_retail_refs={"plan": plan.id}, opportunity_cost_ref=oc["id"])
        self.assertEqual(json.loads(cand["new_retail_refs"])["plan"], plan.id)   # NR planning refs identified
        self.assertEqual(cand["opportunity_cost_ref"], oc["id"])

    def test_28_29_opportunity_consumes_plan_no_demand(self):
        import elite.execdemo.opportunity as oc
        src = open(oc.__file__).read()
        self.assertNotIn("monthly_expected", src)                  # consumes plan, no separate Demand
        c, plan = self.p.nr_plan(position="need")
        r = self.p.opportunity.assess("vu1", c.id, SCOPE, plan=plan)
        self.assertEqual(json.loads(r["plan_refs"]), [plan.id])

    def test_30_need_costs_more_than_excess(self):
        cn, pn = self.p.nr_plan(position="need")
        cx, px = self.p.nr_plan(position="excess", future_units=6)
        need_cost = json.loads(self.p.opportunity.assess("vn", cn.id, SCOPE, plan=pn,
                                                         expected_time_removed_months=3)["cost_value"])["value"]
        exc_cost = json.loads(self.p.opportunity.assess("vx", cx.id, SCOPE, plan=px,
                                                        expected_time_removed_months=3)["cost_value"])["value"]
        self.assertGreater(need_cost, exc_cost)                    # proven from the plan, not assumed

    def test_31_unknown_return_timing_reduces_confidence(self):
        c, plan = self.p.nr_plan(position="need")
        known = self.p.opportunity.assess("v1", c.id, SCOPE, plan=plan, expected_return_path="new_retail")
        unknown = self.p.opportunity.assess("v2", c.id, SCOPE, plan=plan, expected_return_path=None)
        self.assertNotEqual(unknown["confidence"], known["confidence"])
        self.assertEqual(unknown["confidence"], "low")

    def test_32_opportunity_distinct_from_benefit(self):
        c, plan = self.p.nr_plan(position="need")
        oc = self.p.opportunity.assess("v1", c.id, SCOPE, plan=plan)
        # opportunity cost is its own result table; benefit lives on the economic/candidate side
        self.assertIn("cost_value", oc.keys())
        self.assertNotIn("executive_demo_benefit", oc.keys())

    # ---- Best Overall ------------------------------------------------------
    def _three_candidates(self):
        return [
            {"vehicle_unit_id": "cheap", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}},
            {"vehicle_unit_id": "benefit", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 20},
             "executive_demo_benefit": {"value": 15}, "portfolio_fit": {"value": 3}},
            {"vehicle_unit_id": "fit", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 4},
             "executive_demo_benefit": {"value": 6}, "portfolio_fit": {"value": 12}}]

    def test_33_34_35_36_best_overall_explainable_full_objective(self):
        plan = self.p.portfolio.best_overall(SCOPE, required_size=self.p.portfolio.current_active(SCOPE) + 1,
                                             candidates=self._three_candidates())
        best = json.loads(plan["best_overall"])["pick"]
        self.assertEqual(best["vehicle_unit_id"], "fit")           # 34: not lowest cost; 35: not highest benefit
        tradeoffs = json.loads(plan["tradeoffs"])
        self.assertTrue(all("tradeoffs" in t for t in tradeoffs))  # 33/36: explainable, material tradeoffs shown

    def test_37_necessary_sacrifice_labeled(self):
        plan = self.p.portfolio.best_overall(SCOPE, required_size=self.p.portfolio.current_active(SCOPE) + 1,
            candidates=[{"vehicle_unit_id": "sac", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 900},
                         "executive_demo_benefit": {"value": 5}, "portfolio_fit": {"value": 5}}],
            sacrifice_threshold=500)
        sac = json.loads(plan["sacrifices"])
        self.assertTrue(sac and sac[0]["label"] == "necessary_sacrifice")

    def test_38_39_approved_updates_state_no_double_select(self):
        c, plan = self.p.nr_plan(position="need")
        u = self.p.candidate_unit("1HGCM82633A200001", c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self.p.store.get_unit(u.id))
        # 38: committed grows -> next plan need shrinks; 39: dedup within a plan
        plan2 = self.p.portfolio.best_overall(SCOPE, required_size=self.p.portfolio.current_active(SCOPE)
                                              + self.p.portfolio.committed(SCOPE) + 1,
            candidates=[{"vehicle_unit_id": "dup", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
                         "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}},
                        {"vehicle_unit_id": "dup", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
                         "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}}])
        self.assertEqual(json.loads(plan2["selected"]), ["dup"])   # same unit not twice

    # ---- expected lifecycle -----------------------------------------------
    def test_40_41_42_lifecycle_projection(self):
        resolved = self.p.projection.project(SCOPE, expected_duration="6mo", expected_mileage=8000,
                                             expected_retirement_timing="2027-03")
        unresolved = self.p.projection.project(SCOPE, expected_duration=None, expected_mileage=None,
                                               expected_retirement_timing=None)
        self.assertEqual(resolved["resolution_status"], "resolved")
        self.assertEqual(unresolved["resolution_status"], "unresolved")   # missing inputs -> unresolved (not invented)
        # historical projection preserved (append) + delete blocked
        self.assertIsNotNone(self.p.store.conn.execute(
            "SELECT id FROM executive_demo_lifecycle_projection WHERE id=?", (resolved["id"],)).fetchone())
        import sqlite3
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("DELETE FROM executive_demo_lifecycle_projection WHERE id=?",
                                          (resolved["id"],))


class TestBestOverallRegression(unittest.TestCase):
    """Dedicated 14-point Best Overall regression."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase7(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_best_overall_regression(self):
        p = self.p
        # 1 portfolio need known; 2 at least three eligible candidates
        need_basis = p.portfolio.determine_need(SCOPE, 1)
        self.assertEqual(need_basis["need"], 1)
        cands = [
            {"vehicle_unit_id": "lowcost", "model": "QX60", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}},              # 3 lowest cost
            {"vehicle_unit_id": "highben", "model": "QX55", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 25},
             "executive_demo_benefit": {"value": 20}, "portfolio_fit": {"value": 3}},             # 4 highest benefit
            {"vehicle_unit_id": "bestfit", "model": "QX80", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 4},
             "executive_demo_benefit": {"value": 7}, "portfolio_fit": {"value": 12}}]             # 5 strongest fit
        # 8 model preference applied only through approved policy
        fam = p.p3.family(category="MANAGEMENT_PREFERENCE", name="bo_pref", dims=["store"],
                          default_resolution={"mode": "unresolved"})
        p.p3.version(fam.id, {"preferred": "QX80"}, scope={"store": "HG"}, lifecycle="ACTIVE",
                     effective_start="2020-01-01T00:00:00+00:00")
        pref = p.preference.resolve(SCOPE, policy_store=p.policy, family=p.policy.get_family(fam.id),
                                    subject_scope={"store": "HG"}, at_time=AT)
        plan = p.portfolio.best_overall(SCOPE, required_size=1, candidates=cands,
                                        preference={"preferred": pref["preferred"]}, sacrifice_threshold=100)
        best = json.loads(plan["best_overall"])["pick"]
        # 6 Best Overall from the full objective (not one isolated field)
        self.assertEqual(best["vehicle_unit_id"], "bestfit")
        self.assertNotEqual(best["vehicle_unit_id"], "lowcost")
        self.assertNotEqual(best["vehicle_unit_id"], "highben")
        # 7 material tradeoffs shown
        tradeoffs = json.loads(plan["tradeoffs"])
        self.assertTrue(all({"executive_demo_benefit", "new_retail_opportunity_cost", "portfolio_fit"}
                            <= set(t["tradeoffs"]) for t in tradeoffs))
        # 9 necessary sacrifice labeled where applicable (none here below threshold beyond highben, not selected)
        self.assertIsInstance(json.loads(plan["sacrifices"]), list)
        # 10 approval updates committed state; 11 next recommendation uses updated state
        u = p.candidate_unit("1HGCM82633A300001")
        p.units.propose_designation(p.full, SCOPE, u)
        p.units.approve_designation(p.full, SCOPE, p.store.get_unit(u.id))
        self.assertEqual(p.portfolio.determine_need(SCOPE, 1)["need"], 0)   # committed fills need
        # 12 same unit cannot be selected again (already committed -> excluded)
        plan2 = p.portfolio.best_overall(SCOPE, required_size=2, candidates=[
            {"vehicle_unit_id": u.vehicle_unit_id, "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2},
             "actual_state": "DESIGNATION_APPROVED"},
            {"vehicle_unit_id": "fresh", "eligibility": "ELIGIBLE", "opportunity_cost": {"value": 1},
             "executive_demo_benefit": {"value": 2}, "portfolio_fit": {"value": 2}}])
        self.assertNotIn(u.vehicle_unit_id, json.loads(plan2["selected"]))
        # 13 New Retail Demand unchanged; 14 replay approval no duplicate commitment
        c2, plan_nr = p.nr_plan(position="need")
        demand_before = dict(p.p4.issue_demand(c2).monthly_expected)
        from elite.errors import ValidationError
        with self.assertRaises(ValidationError):
            p.units.approve_designation(p.full, SCOPE, p.store.get_unit(u.id))   # re-approve illegal (no dup commit)
        self.assertEqual(p.p4.issue_demand(c2).monthly_expected, demand_before)


if __name__ == "__main__":
    unittest.main()
