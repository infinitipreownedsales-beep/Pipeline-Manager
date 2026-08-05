"""Phase 4 acceptance — Current / Future / Committed Supply (items 7-15, 46, 47)."""
import os
import tempfile
import unittest

from elite.newinv.fixtures import SCOPE, Phase4


class TestPhase4Supply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase4(os.path.join(self.tmp, "elite.db"))
        self.c = self.p.combination(exterior_color="BLACK")

    def tearDown(self):
        self.p.close()

    def _qual(self):
        return {u["key"] for u in self.p.supply.qualifying_supply(self.c.id, SCOPE)}

    def test_07_current_supply_counts_one_vehicle_unit_once(self):
        self.p.seed_current(self.c, [
            {"vehicle_unit_id": "vu1", "state": "available_unsold", "identity_status": "resolved"},
            {"vehicle_unit_id": "vu1", "state": "available_unsold", "identity_status": "resolved"}])
        self.assertEqual(len(self.p.store.current_supply_for(self.c.id, SCOPE)), 1)
        self.assertEqual(self._qual(), {"vu1"})

    def test_08_sold_or_ineligible_units_excluded(self):
        self.p.seed_current(self.c, [
            {"vehicle_unit_id": "vu_ok", "state": "available_unsold", "identity_status": "resolved"},
            {"vehicle_unit_id": "vu_sold", "state": "sold", "identity_status": "resolved"},
            {"vehicle_unit_id": "vu_xfer", "state": "transferred", "identity_status": "resolved"}])
        elig = self.p.store.current_supply_for(self.c.id, SCOPE, eligible_only=True)
        self.assertEqual([e.vehicle_unit_id for e in elig], ["vu_ok"])
        self.assertEqual(self._qual(), {"vu_ok"})

    def test_09_unresolved_identity_does_not_silently_count(self):
        self.p.seed_current(self.c, [{"vehicle_unit_id": None, "state": "available_unsold",
                                      "identity_status": "unresolved"}])
        self.assertEqual(self.p.store.current_supply_for(self.c.id, SCOPE, eligible_only=True), [])
        self.assertEqual(self._qual(), set())

    def test_10_future_supply_counts_distinct_production_orders(self):
        self.p.seed_future(self.c, [{"production_order_id": "poA", "arrival_month": "2026-10"},
                                    {"production_order_id": "poB", "arrival_month": "2026-10"}])
        self.assertEqual(len(self.p.store.future_supply_for(self.c.id, SCOPE)), 2)
        self.assertEqual(self._qual(), {"poA", "poB"})

    def test_11_pre_vin_to_vin_does_not_double_count(self):
        self.p.seed_future(self.c, [
            {"production_order_id": "poX", "arrival_month": "2026-10"},
            {"production_order_id": "poX", "vehicle_unit_id": "vu_late", "arrival_month": "2026-10"}])
        self.assertEqual(len(self.p.store.future_supply_for(self.c.id, SCOPE)), 1)   # one future unit
        self.assertEqual(len(self.p.supply.qualifying_supply(self.c.id, SCOPE)), 1)

    def test_12_cancelled_future_orders_excluded(self):
        self.p.seed_future(self.c, [{"production_order_id": "poC", "arrival_month": "2026-10",
                                     "cancellation_status": "cancelled"}])
        self.assertEqual(self.p.store.future_supply_for(self.c.id, SCOPE, active_only=True), [])
        self.assertEqual(self._qual(), set())

    def test_13_proposed_action_is_not_committed_supply(self):
        self.p.supply.propose_commitment(self.c.id, SCOPE, commitment_type="cpo_like",
                                         unit_or_order_id="prop1", arrival_month="2026-10")
        self.assertEqual(self.p.store.commitments_for(self.c.id, SCOPE, committed_only=True), [])
        self.assertEqual(self._qual(), set())                # proposal does not count

    def test_14_approved_commitment_contributes_exactly_once(self):
        self.p.approved_commitment(self.c, unit_id="cmt1", arrival_month="2026-10")
        self.assertEqual(len(self.p.store.commitments_for(self.c.id, SCOPE, committed_only=True)), 1)
        self.assertEqual(self._qual(), {"cmt1"})

    def test_15_cancelled_commitment_stops_contributing_prospectively(self):
        cm = self.p.approved_commitment(self.c, unit_id="cmt2", arrival_month="2026-10")
        self.assertEqual(self._qual(), {"cmt2"})
        self.p.supply.cancel_commitment(cm.id, reason="synthetic")
        self.assertEqual(self._qual(), set())                # no longer qualifying
        self.assertIsNotNone(self.p.store.get_commitment(cm.id))    # but still historical

    def test_46_supply_states_separately_inspectable(self):
        self.p.seed_current(self.c, [{"vehicle_unit_id": "vc", "state": "available_unsold",
                                      "identity_status": "resolved"}])
        self.p.seed_future(self.c, [{"production_order_id": "pf", "arrival_month": "2026-10"}])
        self.p.approved_commitment(self.c, unit_id="cc", arrival_month="2026-10")
        counts = self.p.supply.counts(self.c.id, SCOPE)
        self.assertEqual((counts["current"], counts["future"], counts["committed"]), (1, 1, 1))
        self.assertEqual(counts["qualifying"], 3)

    def test_47_one_unit_not_counted_twice_across_states(self):
        # The same production order appears as Future Supply AND is committed -> counted once.
        self.p.seed_future(self.c, [{"production_order_id": "poDual", "arrival_month": "2026-10"}])
        self.p.approved_commitment(self.c, unit_id="poDual", arrival_month="2026-10")
        counts = self.p.supply.counts(self.c.id, SCOPE)
        self.assertEqual((counts["future"], counts["committed"]), (1, 1))    # inspectable separately
        self.assertEqual(counts["qualifying"], 1)                            # but qualifying once
        self.assertEqual(self._qual(), {"poDual"})


if __name__ == "__main__":
    unittest.main()
