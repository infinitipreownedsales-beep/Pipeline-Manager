"""Phase 4 acceptance — historical retail + availability reconstruction (items 16-23)."""
import os
import tempfile
import unittest

from elite.newinv.fixtures import SCOPE, Phase4


class TestPhase4RetailAvailability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase4(os.path.join(self.tmp, "elite.db"))
        self.c = self.p.combination(exterior_color="BLACK")

    def tearDown(self):
        self.p.close()

    def test_16_historical_retail_uses_accepted_facts_only(self):
        self.p.retail.project(self.c.id, SCOPE, [
            {"vehicle_unit_id": "vu1", "retail_date": "2026-01-10", "fact_refs": ["f1"]},
            {"vehicle_unit_id": "vu2", "retail_date": "2026-01-20", "fact_refs": ["f2"]}])
        self.assertEqual(self.p.retail.retail_by_month(self.c.id, SCOPE), {"2026-01": 2})
        # every projected retail carries its accepted fact reference
        rows = self.p.store.retail_for(self.c.id, SCOPE)
        self.assertTrue(all(r.fact_refs for r in rows))

    def test_17_duplicate_observations_do_not_duplicate_retail(self):
        self.p.retail.project(self.c.id, SCOPE, [
            {"vehicle_unit_id": "dup", "retail_date": "2026-02-10"},
            {"vehicle_unit_id": "dup", "retail_date": "2026-02-10"}])
        self.assertEqual(self.p.retail.retail_by_month(self.c.id, SCOPE), {"2026-02": 1})

    def test_18_correction_changes_current_use_without_erasing_history(self):
        rs = self.p.retail.project(self.c.id, SCOPE, [{"vehicle_unit_id": "cr", "retail_date": "2026-02-10"}])
        self.p.retail.correct(rs[0].id, {"combination_id": self.c.id, "vehicle_unit_id": "cr",
                                         "retail_date": "2026-03-10"}, SCOPE)
        self.assertEqual(self.p.retail.retail_by_month(self.c.id, SCOPE), {"2026-03": 1})   # current use moved
        all_rows = self.p.store.retail_for(self.c.id, SCOPE, current_only=False)
        self.assertTrue(any(r.status == "superseded" for r in all_rows))                    # history preserved

    def test_19_reversal_preserves_history(self):
        rs = self.p.retail.project(self.c.id, SCOPE, [{"vehicle_unit_id": "rv", "retail_date": "2026-02-10"}])
        self.p.retail.reverse(rs[0].id, self.c.id, SCOPE, reason="unwound")
        self.assertEqual(self.p.retail.retail_by_month(self.c.id, SCOPE), {})               # excluded from current
        self.assertEqual(self.p.store.retail_for(self.c.id, SCOPE, current_only=False)[0].status, "reversed")

    def test_20_available_no_sales_differs_from_unavailable_no_sales(self):
        avail = self.p.availability.reconstruct(self.c.id, SCOPE, [
            {"month": "2026-01", "opening_depth": 3, "arrivals": 0, "retail": 0, "snapshot": "full"}])
        d = self.p.combination(exterior_color="WHITE")
        unavail = self.p.availability.reconstruct(d.id, SCOPE, [
            {"month": "2026-01", "opening_depth": 0, "arrivals": 0, "retail": 0, "snapshot": "full"}])
        self.assertEqual(avail[0].available_state, "available_unsold")
        self.assertEqual(unavail[0].available_state, "unavailable")
        self.assertNotEqual(avail[0].available_state, unavail[0].available_state)

    def test_21_partial_snapshot_does_not_invent_continuous_availability(self):
        a = self.p.availability.reconstruct(self.c.id, SCOPE, [
            {"month": "2026-01", "opening_depth": 2, "arrivals": 0, "retail": 1, "snapshot": "partial",
             "depth_known": False}])
        self.assertEqual(a[0].available_state, "partial")
        self.assertTrue(a[0].unresolved_gaps)                       # gap recorded, continuity not invented
        self.assertEqual(self.p.availability.exposure_months(self.c.id, SCOPE), 0.0)

    def test_22_stockout_does_not_fabricate_lost_sales(self):
        a = self.p.availability.reconstruct(self.c.id, SCOPE, [
            {"month": "2026-01", "opening_depth": 4, "arrivals": 0, "retail": 4, "snapshot": "full"},
            {"month": "2026-02", "opening_depth": 0, "arrivals": 0, "retail": 0, "stockout": True, "snapshot": "full"}])
        stock = [x for x in a if x.available_state == "stockout"]
        self.assertEqual(len(stock), 1)
        self.assertEqual(stock[0].retail_events, 0)                 # no invented sales during stockout
        self.assertEqual(stock[0].confidence, "medium")            # constrained evidence, not zero demand

    def test_23_availability_gaps_reduce_confidence(self):
        a = self.p.availability.reconstruct(self.c.id, SCOPE, [
            {"month": "2026-01", "opening_depth": 3, "arrivals": 0, "retail": 1, "snapshot": "full"},
            {"month": "2026-02", "gap": True}])
        gap = [x for x in a if x.available_state == "unknown"][0]
        self.assertEqual(gap.confidence, "low")
        self.assertTrue(self.p.availability.has_gaps(self.c.id, SCOPE))


if __name__ == "__main__":
    unittest.main()
