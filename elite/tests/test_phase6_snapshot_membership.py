"""Phase 6 acceptance — active-fleet snapshot + membership reconciliation (items 1-10)."""
import os
import tempfile
import unittest

from elite.loaner.fixtures import Phase6
from elite.workflow.fixtures import SCOPE

VIN = "1GNSKBKC5FR000101"
VIN2 = "1GNSKBKC5FR000102"


class TestPhase6Snapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase6(self.dbp)

    def tearDown(self):
        self.p.close()

    def _ingest(self, rows, snapshot_type="full", authoritative=True):
        b = self.p.snapshot.ingest_fleet(rows, snapshot_type=snapshot_type, authoritative=authoritative)
        summary = self.p.snapshot.reconcile(b, rows)
        return b, summary

    def test_01_unit_survives_restart(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])
        uid = self.p.store.unit_for_vin(VIN, SCOPE).id
        self.p.close()
        p2 = Phase6(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_unit(uid))

    def test_02_03_vehicle_unit_identity_authoritative_not_replaced(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])
        u = self.p.store.unit_for_vin(VIN, SCOPE)
        self.assertIsNotNone(u.vehicle_unit_id)               # Vehicle Unit identity present
        self.assertNotEqual(u.id, u.vehicle_unit_id)          # SL Unit id does not replace it

    def test_02b_vehicle_unit_id_resolves_to_canonical_vehicle(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])
        u = self.p.store.unit_for_vin(VIN, SCOPE)
        v = self.p.data.get_vehicle(u.vehicle_unit_id)
        self.assertIsNotNone(v)
        self.assertEqual(v.vin, VIN)
        self.assertEqual(v.store_scope, SCOPE)

    def test_02c_reconcile_repairs_legacy_synthetic_vehicle_unit_id(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])
        u = self.p.store.unit_for_vin(VIN, SCOPE)

        with self.p.store.conn:
            self.p.store.set_unit_field(self.p.store.conn, u.id, vehicle_unit_id=f"vu_{VIN}")

        broken = self.p.store.unit_for_vin(VIN, SCOPE)
        self.assertEqual(broken.vehicle_unit_id, f"vu_{VIN}")
        self.assertIsNone(self.p.data.get_vehicle(broken.vehicle_unit_id))

        self._ingest([{"vin": VIN, "rental_status": "rented"}])

        repaired = self.p.store.unit_for_vin(VIN, SCOPE)
        vehicle = self.p.data.get_vehicle(repaired.vehicle_unit_id)
        self.assertIsNotNone(vehicle)
        self.assertEqual(vehicle.vin, VIN)
        self.assertNotEqual(repaired.vehicle_unit_id, f"vu_{VIN}")
        self.assertEqual(repaired.current_rental_state, "rented")

    def test_04_valid_full_snapshot_reconciles_by_vin(self):
        _b, s = self._ingest([{"vin": VIN, "rental_status": "available"},
                              {"vin": VIN2, "rental_status": "rented"}])
        self.assertEqual(s.get("MEMBER_ADDED"), 2)
        self.assertEqual(self.p.store.unit_for_vin(VIN2, SCOPE).current_rental_state, "rented")

    def test_05_partial_absence_no_removal(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])           # VIN now active
        _b, s = self._ingest([{"vin": VIN2}], snapshot_type="partial")       # partial without VIN
        self.assertIn("ABSENT_NO_CHANGE", s)                                 # signal only
        self.assertTrue(self.p.store.unit_for_vin(VIN, SCOPE).active_fleet_presence)  # still a member

    def test_06_invalid_full_claim_cannot_remove(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])
        b, s = self._ingest([{"vin": VIN2}], snapshot_type="full", authoritative=False)  # non-capable -> partial
        self.assertEqual(b.validated_snapshot_type, "partial")
        self.assertNotIn("ABSENT_REVIEW", s)                                  # cannot support removal/review
        self.assertTrue(self.p.store.unit_for_vin(VIN, SCOPE).active_fleet_presence)

    def test_07_full_absence_review_not_retirement(self):
        self._ingest([{"vin": VIN, "rental_status": "available"}])
        _b, s = self._ingest([{"vin": VIN2, "rental_status": "available"}])   # full snapshot without VIN
        self.assertGreaterEqual(s.get("ABSENT_REVIEW", 0), 1)
        u = self.p.store.unit_for_vin(VIN, SCOPE)
        self.assertNotEqual(u.membership_state, "RETIRED")                    # no invented retirement
        self.assertTrue(u.active_fleet_presence)

    def test_08_invalid_vin_not_silently_entered(self):
        _b, s = self._ingest([{"vin": "XYZ"}, {"vin": "PENDING"}])
        self.assertEqual(s.get("INVALID_VIN_EXCLUDED"), 2)
        self.assertIsNone(self.p.store.unit_for_vin("XYZ", SCOPE))

    def test_09_duplicate_vin_explicit(self):
        _b, s = self._ingest([{"vin": VIN, "rental_status": "available"},
                              {"vin": VIN, "rental_status": "rented"}])
        self.assertEqual(s.get("DUPLICATE_VIN"), 1)

    def test_10_conflicting_rental_status_explicit(self):
        _b, s = self._ingest([{"vin": VIN, "rental_status": "rented", "conflicting_state": True}])
        self.assertEqual(s.get("CONFLICTING_STATE"), 1)


if __name__ == "__main__":
    unittest.main()
