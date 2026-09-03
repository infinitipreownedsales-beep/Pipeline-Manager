"""Executive-Demo cockpit engine — mileage SEMANTICS + observed learning, decision vocabulary, Demo-suitability
ranking, and portfolio allocation (closeout 2026-09-03). Pure engine acceptance; operator/physical-state items
live in test_phase13_demo_operator.
"""
import unittest

from elite.operatorstd import demo_board as DB

TODAY = "2026-09-03"


class TestMileageSemantics(unittest.TestCase):
    # 1: assignment mileage is its OWN fact and is never labeled current actual mileage
    def test_1_assignment_mileage_is_not_current_actual(self):
        ms = DB.mileage_state("2026-06-04", 17, [], TODAY)     # only the assignment reading exists
        self.assertEqual(ms.assignment_mileage, 17)
        self.assertIsNone(ms.actual)                            # no CURRENT odometer observed
        self.assertNotIn("actual", ms.display())
        self.assertIn("Assigned 17 mi", ms.display())
        self.assertIn("current unknown", ms.display())

    # 2: one assignment observation alone does not create a fake velocity
    def test_2_single_assignment_yields_no_velocity(self):
        ms = DB.mileage_state("2026-06-04", 17, [], TODAY)
        self.assertIsNone(ms.velocity)

    # 3: assignment + a later actual observation learns miles/day
    def test_3_assignment_plus_later_reading_learns_velocity(self):
        ms = DB.mileage_state("2026-08-01", 0, [{"date": "2026-08-31", "miles": 534}], TODAY)
        self.assertAlmostEqual(ms.velocity, 17.8, places=1)     # 534 mi / 30 d
        self.assertEqual(ms.actual, 534)                        # the current odometer is the later reading
        self.assertEqual(ms.source, "observed")

    # 4: completed driver cycles carry learning to the next Demo (different vehicle)
    def test_4_completed_cycles_carry_learning(self):
        ms = DB.mileage_state("2026-08-20", 5, [], TODAY,
                              completed_cycles=[{"miles": 1800, "days": 90}, {"miles": 1600, "days": 80}])
        self.assertAlmostEqual(ms.velocity, 20.0, places=1)     # prior cycles feed the new assignment
        self.assertIsNone(ms.actual)                            # still no current reading on THIS vehicle
        self.assertIsNotNone(ms.estimated)                      # but a forecast exists from learned velocity

    # 5: estimates are never rendered as actuals
    def test_5_estimate_distinct_from_actual(self):
        ms = DB.mileage_state("2026-08-01", 0, [{"date": "2026-08-11", "miles": 300}], TODAY)
        self.assertEqual(ms.actual, 300)
        self.assertGreater(ms.estimated, ms.actual)             # today's estimate is higher, a separate field
        self.assertIn("actual", ms.display())                   # the display shows the actual reading, labeled
        est_only = DB.MileageState(assignment_mileage=17, estimated=1600, velocity=17.8, source="assignment_only")
        self.assertNotIn("1,600 mi (actual", est_only.display())

    # 6: no learned velocity still yields a cadence forecast (time-based)
    def test_6_cadence_forecast_without_velocity(self):
        self.assertIsNone(DB.mileage_state("2026-06-04", 17, [], TODAY).velocity)
        self.assertIsNotNone(DB.cadence_window_date("2026-06-04"))   # ~90 days after assignment


class TestDecisionVocabulary(unittest.TestCase):
    def _ms(self, start, am=None, obs=None):
        return DB.mileage_state(start, am, obs or [], TODAY)

    # 7: age can produce PLAN SWAP without any mileage
    def test_7_age_produces_plan_swap_without_mileage(self):
        d = DB.decide("2026-06-04", TODAY, self._ms("2026-06-04", am=17))   # ~91d, only assignment mileage
        self.assertEqual(d.state, DB.PLAN_SWAP)
        self.assertTrue(d.needs_odometer)                       # odometer only before FINAL swap, not to plan

    def test_7b_young_demo_keeps(self):
        for start in ("2026-07-18", "2026-07-21"):
            self.assertEqual(DB.decide(start, TODAY, self._ms(start, am=18)).state, DB.KEEP)

    # 8: SWAP NOW from mileage requires a real CURRENT observation (never assignment/estimate)
    def test_8_swap_now_requires_actual_observation(self):
        # estimate is over the swap point, but the only CURRENT reading is below it -> never SWAP NOW
        ms = DB.mileage_state("2026-06-04", 100, [{"date": "2026-07-04", "miles": 1000}], TODAY)  # v high
        self.assertGreaterEqual(ms.estimated, DB.SWAP_MILES)
        self.assertEqual(DB.decide("2026-06-04", TODAY, ms).state, DB.PLAN_SWAP)
        # a real current reading over the swap point authorizes SWAP NOW
        ms2 = DB.mileage_state("2026-05-01", 0, [{"date": "2026-09-01", "miles": 2100}], TODAY)
        d2 = DB.decide("2026-05-01", TODAY, ms2)
        self.assertEqual(d2.state, DB.SWAP_NOW)
        self.assertFalse(d2.needs_odometer)

    def test_pull_and_review(self):
        self.assertEqual(DB.decide("2026-08-20", TODAY, self._ms("2026-08-20"), pull_reason="last on lot").state,
                         DB.PULL)
        self.assertEqual(DB.decide("2026-06-04", TODAY, self._ms("2026-06-04"), identity_ok=False).state, DB.REVIEW)


class TestSuitabilityRanking(unittest.TestCase):
    # 9: Demo suitability is NOT simply the largest certified shortage
    def test_9_suitability_not_highest_shortage(self):
        slow_big = {"cid": "slow", "label": "QX80 slow", "model": "QX80", "need": 9, "dts_burden": 120,
                    "expected_demand": 0.2, "depth": 2, "has_incoming_or_order": True, "governed": True}
        fast_small = {"cid": "fast", "label": "QX65 fast", "model": "QX65", "need": 2, "dts_burden": 15,
                      "expected_demand": 6.0, "depth": 3, "has_incoming_or_order": True, "governed": True}
        ranked = DB.rank_demo_candidates([slow_big, fast_small])
        self.assertEqual(ranked[0].cid, "fast")                 # the proven fast mover wins, not the big shortage
        self.assertIn("no former-Demo", ranked[0].note)         # honest about missing resilience history

    # 10: executive preference constrains/reranks candidates appropriately
    def test_10_preference_reranks(self):
        a = {"cid": "a", "label": "QX80", "model": "QX80", "expected_demand": 3.0, "depth": 2,
             "has_incoming_or_order": True, "governed": True}
        b = {"cid": "b", "label": "QX65", "model": "QX65", "expected_demand": 3.5, "depth": 2,
             "has_incoming_or_order": True, "governed": True}
        ranked = DB.rank_demo_candidates([a, b], preferred_model="QX80")
        self.assertEqual(ranked[0].model, "QX80")               # preference lifts the QX80 above a slightly faster QX65

    # 14: an ungoverned/unmapped candidate can never be ranked as a Demo asset
    def test_14_ungoverned_never_ranked(self):
        ranked = DB.rank_demo_candidates([{"cid": "ph", "label": "8311", "model": "QX80", "governed": False,
                                           "expected_demand": 99}])
        self.assertEqual(ranked, [])


class TestPortfolioAllocation(unittest.TestCase):
    def _e(self, i, state, days, key):
        return {"id": f"u{i}", "decision": DB.DemoDecision(state, "", days=days), "pool_key": key}

    # 12: one physical replacement cannot be allocated twice
    def test_12_no_double_allocation(self):
        entries = [self._e(1, DB.PLAN_SWAP, 95, "K"), self._e(2, DB.SWAP_NOW, 120, "K")]
        pools = {"K": {"current": [{"vin": "ONLY1"}], "incoming": [], "order": True}}
        out = DB.allocate_replacements(entries, pools)
        assigned = [v["unit"] for v in out.values() if v["unit"]]
        self.assertEqual(assigned, ["ONLY1"])
        self.assertEqual(out["u2"]["path"], "USE NOW")          # urgency first
        self.assertEqual(out["u1"]["path"], "ORDER")

    # 13: on-ground -> incoming -> order hierarchy preserved
    def test_13_hierarchy_preserved(self):
        self.assertEqual(DB.allocate_replacements(
            [self._e(1, DB.PLAN_SWAP, 95, "K")],
            {"K": {"current": [], "incoming": [{"vin": "INB1"}], "order": True}})["u1"]["path"], "WAIT")
        self.assertEqual(DB.allocate_replacements(
            [self._e(1, DB.PLAN_SWAP, 95, "K")],
            {"K": {"current": [], "incoming": [], "order": True}})["u1"]["path"], "ORDER")


if __name__ == "__main__":
    unittest.main(verbosity=2)
