"""Executive-Demo manager cockpit engine — decision vocabulary, observed mileage learning, and portfolio
allocation (operational rebuild 2026-09-03). Pure engine acceptance (1-9, 12, 13); the governed-identity,
count-once, history and no-VIN/no-economics UI acceptance live in test_phase13_demo_operator."""
import unittest

from elite.operatorstd import demo_board as DB

TODAY = "2026-09-03"


class TestMileageLearning(unittest.TestCase):
    def test_4_velocity_uses_only_observed_points(self):
        obs = [{"date": "2026-08-01", "miles": 1080}, {"date": "2026-08-31", "miles": 1614}]
        v, conf = DB.learn_velocity(obs)
        self.assertAlmostEqual(v, 17.8, places=1)               # 534 mi / 30 d
        self.assertEqual(conf, "low")                           # a single interval = one weak point

    def test_4b_single_observation_yields_no_velocity(self):
        v, conf = DB.learn_velocity([{"date": "2026-08-05", "miles": 1080}])
        self.assertIsNone(v)                                    # one reading has no elapsed evidence
        self.assertEqual(conf, "low")

    def test_5_estimate_is_distinct_from_actual(self):
        ms = DB.mileage_state("2026-08-01", [{"date": "2026-08-01", "miles": 1080},
                                             {"date": "2026-08-05", "miles": 1152}], TODAY)
        self.assertEqual(ms.actual, 1152)                       # last OBSERVED reading
        self.assertEqual(ms.source, "observed")
        self.assertGreater(ms.estimated, ms.actual)             # today's estimate is higher — a separate field
        # the actual reading is always rendered labeled as actual (never an estimate shown as an odometer)
        self.assertIn("actual", ms.display())
        actual_only = DB.MileageState(actual=1152, actual_date="2026-08-05", source="observed")
        self.assertIn("actual", actual_only.display())
        # an estimate-only state (no observation) renders explicitly as an estimate
        est_only = DB.MileageState(estimated=1600, velocity=17.8, source="estimated")
        self.assertIn("estimated", est_only.display())

    def test_6_more_observations_raise_confidence(self):
        weak = DB.learn_velocity([{"date": "2026-08-01", "miles": 0}, {"date": "2026-08-31", "miles": 600}])
        strong = DB.learn_velocity([{"date": "2026-08-01", "miles": 0}, {"date": "2026-08-11", "miles": 200},
                                    {"date": "2026-08-21", "miles": 400}, {"date": "2026-08-31", "miles": 600}])
        self.assertEqual(weak[1], "low")
        self.assertEqual(strong[1], "high")                     # multiple real intervals -> stronger confidence

    def test_6b_completed_cycles_feed_velocity(self):
        v, conf = DB.learn_velocity([], completed_cycles=[{"miles": 1800, "days": 90}, {"miles": 1600, "days": 80}])
        self.assertAlmostEqual(v, 20.0, places=1)               # (1800+1600)/(90+80)
        self.assertEqual(conf, "moderate")


class TestDecisionVocabulary(unittest.TestCase):
    def test_1_missing_mileage_does_not_erase_guidance(self):
        d = DB.decide("2026-06-04", TODAY, DB.mileage_state("2026-06-04", [], TODAY))
        self.assertNotEqual(d.state, DB.REVIEW)
        self.assertIn(d.state, (DB.PLAN_SWAP, DB.SWAP_NOW, DB.KEEP, DB.PULL))
        self.assertTrue(d.detail)                               # never blank

    def test_2_ninety_day_age_produces_plan_swap_without_asserting_mileage(self):
        d = DB.decide("2026-06-04", TODAY, DB.mileage_state("2026-06-04", [], TODAY))   # ~91d, no mileage
        self.assertEqual(d.state, DB.PLAN_SWAP)
        self.assertTrue(d.needs_odometer)                       # odometer required before FINAL swap, not to plan
        self.assertNotIn("2,000 mi — at/past", d.detail)        # no invented odometer assertion

    def test_2b_young_demo_is_not_overdue_on_age_alone(self):
        for start in ("2026-07-18", "2026-07-21"):
            d = DB.decide(start, TODAY, DB.mileage_state(start, [], TODAY))
            self.assertEqual(d.state, DB.KEEP)                  # July assignments are materially younger

    def test_3_swap_now_requires_actual_odometer_not_estimate(self):
        # estimate is well over the swap point, but the only observed reading is below it -> never SWAP NOW
        obs = [{"date": "2026-06-04", "miles": 100}, {"date": "2026-07-04", "miles": 1000}]  # v=30/day -> est high
        ms = DB.mileage_state("2026-06-04", obs, TODAY)
        self.assertGreaterEqual(ms.estimated, DB.SWAP_MILES)    # estimate suggests overdue
        d = DB.decide("2026-06-04", TODAY, ms)
        self.assertEqual(d.state, DB.PLAN_SWAP)                 # NOT SWAP NOW on an estimate
        self.assertTrue(d.needs_odometer)                      # fails toward an odometer check

    def test_3b_actual_over_swap_point_is_swap_now(self):
        ms = DB.mileage_state("2026-05-01", [{"date": "2026-09-01", "miles": 2100}], TODAY)
        d = DB.decide("2026-05-01", TODAY, ms)
        self.assertEqual(d.state, DB.SWAP_NOW)
        self.assertFalse(d.needs_odometer)                     # the actual odometer already authorizes it

    def test_pull_when_dealership_reason(self):
        d = DB.decide("2026-08-20", TODAY, DB.mileage_state("2026-08-20", [], TODAY),
                      pull_reason="last QX80 on lot needed for a retail sale")
        self.assertEqual(d.state, DB.PULL)
        self.assertIn("last QX80", d.detail)

    def test_review_on_unresolved_identity(self):
        d = DB.decide("2026-06-04", TODAY, DB.mileage_state("2026-06-04", [], TODAY), identity_ok=False)
        self.assertEqual(d.state, DB.REVIEW)


class TestPortfolioAllocation(unittest.TestCase):
    def _entry(self, i, state, days, pool_key):
        return {"id": f"u{i}", "decision": DB.DemoDecision(state, "", days=days), "pool_key": pool_key}

    def test_7_one_replacement_unit_never_assigned_twice(self):
        # two demos both point at the same combination with a SINGLE on-ground replacement unit
        entries = [self._entry(1, DB.PLAN_SWAP, 95, "QX80"), self._entry(2, DB.SWAP_NOW, 120, "QX80")]
        pools = {"QX80": {"current": [{"vin": "ONLYUNIT1"}], "incoming": [], "order": True}}
        out = DB.allocate_replacements(entries, pools)
        assigned = [v["unit"] for v in out.values() if v["unit"]]
        self.assertEqual(assigned, ["ONLYUNIT1"])              # exactly one demo gets the physical unit
        # the other is sequenced to the ORDER path, never handed the same VIN
        paths = sorted(v["path"] for v in out.values())
        self.assertEqual(paths, ["ORDER", "USE NOW"])
        self.assertEqual(out["u2"]["path"], "USE NOW")         # SWAP NOW is sequenced first (higher urgency)

    def test_7b_sequence_orders_by_urgency(self):
        entries = [self._entry(1, DB.KEEP, 10, "A"), self._entry(2, DB.SWAP_NOW, 130, "A"),
                   self._entry(3, DB.PLAN_SWAP, 95, "A")]
        pools = {"A": {"current": [{"vin": "V1"}, {"vin": "V2"}], "incoming": [], "order": True}}
        out = DB.allocate_replacements(entries, pools)
        self.assertEqual(out["u2"]["unit"], "V1")              # SWAP NOW first
        self.assertEqual(out["u3"]["unit"], "V2")              # PLAN SWAP second
        self.assertEqual(out["u1"]["path"], "NONE")            # KEEP consumes no replacement

    def test_12_incoming_used_when_no_on_ground(self):
        entries = [self._entry(1, DB.PLAN_SWAP, 95, "A")]
        pools = {"A": {"current": [], "incoming": [{"vin": "INBOUND1"}], "order": True}}
        out = DB.allocate_replacements(entries, pools)
        self.assertEqual(out["u1"]["path"], "WAIT")
        self.assertEqual(out["u1"]["unit"], "INBOUND1")

    def test_13_order_only_when_no_physical_path(self):
        entries = [self._entry(1, DB.PLAN_SWAP, 95, "A")]
        pools = {"A": {"current": [], "incoming": [], "order": True}}
        out = DB.allocate_replacements(entries, pools)
        self.assertEqual(out["u1"]["path"], "ORDER")
        self.assertIsNone(out["u1"]["unit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
