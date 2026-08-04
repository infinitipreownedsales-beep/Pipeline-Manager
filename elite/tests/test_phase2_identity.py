"""Phase 2 acceptance — identity invariants (items 17-24)."""
import os
import tempfile
import unittest

from elite.data import identity as idres
from elite.data.fixtures import Phase2

VA = "1GNSKBKC5FR00000A"
VB = "1GNSKBKC5FR00000B"
SCOPE = "store:HG"


class TestPhase2Identity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase2(os.path.join(self.tmp, "elite.db"))
        self.s = self.p.store

    def tearDown(self):
        self.p.close()

    def test_17_exact_vin_resolves_one_unit(self):
        s1, u1, _ = idres.resolve_vehicle(self.s, VA, SCOPE)
        s2, u2, _ = idres.resolve_vehicle(self.s, VA, SCOPE)
        self.assertEqual(s1, idres.CREATED)
        self.assertEqual(s2, idres.MATCHED)
        self.assertEqual(u1.id, u2.id)

    def test_18_class_similarity_does_not_merge(self):
        _, u1, _ = idres.resolve_vehicle(self.s, VA, SCOPE)   # same model, different VIN
        _, u2, _ = idres.resolve_vehicle(self.s, VB, SCOPE)
        self.assertNotEqual(u1.id, u2.id)

    def test_19_reused_stock_number_does_not_merge(self):
        # Same stock number in two rows, different VINs -> two distinct units.
        b = self.p.ingest_dms([dict(stock_number="N9", vin=VA, model="qx80"),
                               dict(stock_number="N9", vin=VB, model="qx80")])
        self.assertEqual(b.accepted_count, 2)
        self.assertNotEqual(self.s.find_vehicle_by_vin(VA, SCOPE).id,
                            self.s.find_vehicle_by_vin(VB, SCOPE).id)

    def test_20_same_config_orders_remain_distinct(self):
        _, o1, _ = idres.resolve_production_order(self.s, "MO-1", None, SCOPE)
        _, o2, _ = idres.resolve_production_order(self.s, "MO-2", None, SCOPE)
        self.assertNotEqual(o1.id, o2.id)
        # No order id either -> still distinct candidates, never merged by config.
        _, o3, _ = idres.resolve_production_order(self.s, None, None, SCOPE)
        _, o4, _ = idres.resolve_production_order(self.s, None, None, SCOPE)
        self.assertNotEqual(o3.id, o4.id)

    def test_21_pre_vin_links_to_later_vin_no_duplicate_unit(self):
        _, order, _ = idres.resolve_production_order(self.s, "MO-9", None, SCOPE)
        self.assertEqual(order.identity_status, "pre_vin")
        status, result, _ = idres.link_order_to_vin(self.s, order.id, VA, SCOPE)
        self.assertEqual(status, idres.MATCHED)
        linked_order, unit = result
        self.assertEqual(linked_order.linked_vehicle_unit_id, unit.id)
        n = self.s.conn.execute("SELECT COUNT(*) c FROM vehicle_unit WHERE vin=? AND store_scope=?",
                                (VA, SCOPE)).fetchone()["c"]
        self.assertEqual(n, 1)                                    # no duplicate canonical unit

    def test_22_ambiguous_or_invalid_stays_unresolved(self):
        st, unit, _ = idres.resolve_vehicle(self.s, "XYZ", SCOPE)       # malformed VIN
        self.assertEqual(st, idres.UNRESOLVED)
        self.assertIsNone(unit)
        st2, _, _ = idres.resolve_vehicle(self.s, "00000000000000000", SCOPE)  # placeholder
        self.assertEqual(st2, idres.UNRESOLVED)

    def test_23_identity_correction_preserves_prior(self):
        _, _, ev1 = idres.resolve_vehicle(self.s, VA, SCOPE)
        ev2 = idres.correct_identity(self.s, "vehicle_unit", "vin", VA, SCOPE, idres.CORRECTED,
                                     reason="misread VIN", resolver="prn_owner", prior_evidence_id=ev1.id)
        chain = self.s.list_evidence_for("vin", VA, SCOPE)
        self.assertGreaterEqual(len(chain), 2)                   # prior preserved alongside correction
        self.assertEqual(ev2.correction_ref, ev1.id)

    def test_24_cross_store_collision_does_not_merge(self):
        _, ua, _ = idres.resolve_vehicle(self.s, VA, "store:HG")
        _, ub, _ = idres.resolve_vehicle(self.s, VA, "store:OTHER")  # same VIN, different store
        self.assertNotEqual(ua.id, ub.id)


if __name__ == "__main__":
    unittest.main()
