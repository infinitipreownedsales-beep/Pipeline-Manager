"""Phase 4 acceptance — forecast reconciliation, coverage resolution, Need/Excess semantics,
reproducibility, and official/scenario isolation (items 33-53)."""
import os
import sqlite3
import tempfile
import unittest

from elite.newinv.fixtures import AT, HORIZON, SCOPE, Phase4
from elite.newinv.forecast import reconcile_months, reconcile_totals


class TestPhase4ForecastPlanning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase4(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _stable(self, **kw):
        c = self.p.combination(**kw)
        months = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p.seed_retail(c, {m: 2 for m in months})
        self.p.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2,
                                     "snapshot": "full"} for m in months])
        return c

    def _demand(self, c, **kw):
        return self.p.issue_demand(c, **kw)

    # ---- forecast reconciliation ------------------------------------------
    def test_33_monthly_forecast_reconciles_to_total(self):
        c = self._stable(exterior_color="BLACK")
        f = self.p.forecasts.issue(self._demand(c), calculation_version=self.p.demand_cv)
        self.assertTrue(reconcile_months(f))
        self.assertEqual(len(f.months), len(HORIZON))

    def test_34_combination_totals_reconcile_to_model(self):
        a = self._stable(exterior_color="BLACK")
        b = self._stable(exterior_color="WHITE")
        fa = self.p.forecasts.issue(self._demand(a), calculation_version=self.p.demand_cv)
        fb = self.p.forecasts.issue(self._demand(b), calculation_version=self.p.demand_cv)
        model_total = fa.total_expected + fb.total_expected
        self.assertTrue(reconcile_totals([fa.total_expected, fb.total_expected], model_total))

    def test_35_model_totals_reconcile_to_portfolio(self):
        a = self._stable(exterior_color="BLACK")
        b = self._stable(exterior_color="WHITE")
        pa = self.p.issue_plan(a, self._demand(a), coverage_target=0)
        pb = self.p.issue_plan(b, self._demand(b), coverage_target=0)
        pf = self.p.planning.issue_portfolio(SCOPE, [pa, pb], level="model", grouping_key="QX80",
                                             calculation_version=self.p.plan_cv)
        self.assertAlmostEqual(pf.need, pa.need + pb.need, places=6)
        month_total = sum(pf.monthly_demand.values())
        self.assertAlmostEqual(month_total, pa.expected_demand + pb.expected_demand, places=6)

    # ---- coverage resolution ----------------------------------------------
    def _cov(self, family, subject):
        return self.p.coverage.resolve(None, SCOPE, policy_store=self.p.policy,
                                       family=self.p.policy.get_family(family.id), subject_scope=subject, at_time=AT)

    def test_36_missing_coverage_policy_produces_unresolved(self):
        fam = self.p.coverage_family()                      # no version
        cov = self._cov(fam, {"store": "HG", "model": "QX80", "model_year": "2026"})
        self.assertEqual(cov.resolution_status, "unresolved")
        c = self._stable(exterior_color="BLACK")
        plan = self.p.issue_plan(c, self._demand(c), coverage_resolution=cov)
        self.assertEqual(plan.planning_state, "unresolved")   # no invented target
        self.assertEqual(plan.need, 0.0)

    def test_37_broad_fallback_resolves_only_when_permitted(self):
        fam = self.p.coverage_family()
        self.p.coverage_version(fam.id, months=2, scope={"store": "HG"})   # broad store-level
        cov = self._cov(fam, {"store": "HG", "model": "QX80", "model_year": "2026"})
        self.assertEqual(cov.resolution_status, "resolved")
        self.assertEqual(cov.resolved_value, {"mode": "months", "value": 2})

    def test_38_more_specific_coverage_overrides_broader(self):
        fam = self.p.coverage_family()
        self.p.coverage_version(fam.id, months=2, scope={"store": "HG"})
        self.p.coverage_version(fam.id, units=10, scope={"store": "HG", "model": "QX80", "model_year": "2026"})
        cov = self._cov(fam, {"store": "HG", "model": "QX80", "model_year": "2026"})
        self.assertEqual(cov.resolved_value, {"mode": "units", "value": 10})   # specific wins

    def test_39_conflicting_coverage_produces_conflict(self):
        fam = self.p.coverage_family()
        self.p.coverage_version(fam.id, units=5, scope={"store": "HG"})
        self.p.coverage_version(fam.id, units=9, scope={"store": "HG"})
        cov = self._cov(fam, {"store": "HG"})
        self.assertEqual(cov.resolution_status, "conflicting")

    # ---- Need / Excess semantics ------------------------------------------
    def test_40_41_42_need_excess_signs_and_exclusivity(self):
        c = self._stable(exterior_color="BLACK")             # demand 2/mo * 6 = 12
        d = self._demand(c)
        need_plan = self.p.issue_plan(c, d, coverage_target=2)   # req 14, supply 0 -> need 14
        self.assertGreaterEqual(need_plan.need, 0)
        self.assertGreaterEqual(need_plan.excess, 0)
        self.assertFalse(need_plan.need > 0 and need_plan.excess > 0)
        # oversupply -> excess, need 0
        for i in range(20):
            self.p.seed_future(c, [{"production_order_id": f"po{i}", "arrival_month": "2026-09"}])
        excess_plan = self.p.issue_plan(c, d, coverage_target=2)
        self.assertGreaterEqual(excess_plan.excess, 0)
        self.assertEqual(excess_plan.need, 0)
        self.assertFalse(excess_plan.need > 0 and excess_plan.excess > 0)

    def test_43_added_qualifying_supply_does_not_increase_need(self):
        c = self._stable(exterior_color="BLACK")
        d = self._demand(c)
        base = self.p.issue_plan(c, d, coverage_target=2).need
        self.p.seed_future(c, [{"production_order_id": "add", "arrival_month": "2026-09"}])
        after = self.p.issue_plan(c, d, coverage_target=2).need
        self.assertLessEqual(after, base)

    def test_44_removed_qualifying_supply_does_not_decrease_need(self):
        c = self._stable(exterior_color="BLACK")
        d = self._demand(c)
        self.p.seed_future(c, [{"production_order_id": "will_cancel", "arrival_month": "2026-09"}])
        base = self.p.issue_plan(c, d, coverage_target=2).need
        # remove it (cancel) -> recompute
        fs = self.p.store.future_supply_for(c.id, SCOPE)[0]
        with self.p.store.conn:
            self.p.store.conn.execute("UPDATE future_supply_projection SET cancellation_status='cancelled' WHERE id=?",
                                      (fs.id,))
        after = self.p.issue_plan(c, d, coverage_target=2).need
        self.assertGreaterEqual(after, base)

    def test_45_later_arriving_supply_does_not_satisfy_earlier_month(self):
        c = self._stable(exterior_color="BLACK")
        d = self._demand(c)
        base = self.p.issue_plan(c, d, coverage_target=0)
        first_month_shortage = base.months[0].shortage
        self.p.seed_future(c, [{"production_order_id": "late", "arrival_month": HORIZON[-1]}])   # arrives last month
        after = self.p.issue_plan(c, d, coverage_target=0)
        self.assertEqual(after.months[0].shortage, first_month_shortage)     # earlier month unchanged
        self.assertLess(after.months[-1].shortage, base.months[-1].shortage + 0.0001)

    def test_48_commitment_updates_next_calculation(self):
        c = self._stable(exterior_color="BLACK")
        d = self._demand(c)
        before = self.p.issue_plan(c, d, coverage_target=2).need
        self.p.approved_commitment(c, unit_id="cpo1", arrival_month="2026-09")
        after = self.p.issue_plan(c, d, coverage_target=2).need
        self.assertEqual(after, before - 1)                  # exactly one committed unit credited

    def test_49_supply_method_change_does_not_alter_demand(self):
        c = self._stable(exterior_color="BLACK")
        d1 = self._demand(c)
        self.p.approved_commitment(c, unit_id="cpo", arrival_month="2026-09", commitment_type="dealer_trade_like")
        d2 = self._demand(c)
        self.assertEqual(d1.monthly_expected, d2.monthly_expected)

    def test_50_repeat_reproduces_same_result(self):
        c = self._stable(exterior_color="BLACK")
        d = self._demand(c)
        _m, dok = self.p.demand.replay(d.reproducibility_package)
        self.assertTrue(dok)
        plan = self.p.issue_plan(c, d, coverage_target=2)
        _r, pok = self.p.planning.replay(plan.reproducibility_package)
        self.assertTrue(pok)

    def test_51_new_facts_may_produce_new_current_forecast(self):
        c = self._stable(exterior_color="BLACK")
        f1 = self.p.forecasts.issue(self._demand(c), calculation_version=self.p.demand_cv)
        # new accepted facts in a horizon calendar month (a strong prior-year January)
        self.p.seed_retail(c, {"2025-01": 8})
        self.p.seed_availability(c, [{"month": "2025-01", "opening_depth": 6, "arrivals": 2, "retail": 8,
                                     "snapshot": "full"}])
        f2 = self.p.forecasts.issue(self._demand(c), calculation_version=self.p.demand_cv)
        self.assertNotEqual(f1.id, f2.id)
        self.assertNotEqual(f1.total_expected, f2.total_expected)

    def test_52_new_forecast_does_not_rewrite_history(self):
        c = self._stable(exterior_color="BLACK")
        f1 = self.p.forecasts.issue(self._demand(c), calculation_version=self.p.demand_cv)
        total_before = f1.total_expected
        self.p.seed_retail(c, {"2025-01": 8})
        self.p.seed_availability(c, [{"month": "2025-01", "opening_depth": 6, "arrivals": 2, "retail": 8,
                                     "snapshot": "full"}])
        self.p.forecasts.issue(self._demand(c), calculation_version=self.p.demand_cv)
        self.assertEqual(self.p.store.get_forecast(f1.id).total_expected, total_before)   # preserved
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("DELETE FROM forecast_result WHERE id=?", (f1.id,))

    def test_53_official_and_scenario_results_isolated(self):
        c = self._stable(exterior_color="BLACK")
        official = self._demand(c)
        scenario = self._demand(c, scenario_id="scenario_A")
        self.assertIsNone(official.scenario_id)
        self.assertEqual(scenario.scenario_id, "scenario_A")
        self.assertNotEqual(official.id, scenario.id)
        plan = self.p.issue_plan(c, scenario, coverage_target=2, scenario_id="scenario_A")
        self.assertEqual(plan.scenario_id, "scenario_A")


if __name__ == "__main__":
    unittest.main()
