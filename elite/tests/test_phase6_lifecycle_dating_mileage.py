"""Phase 6 acceptance — entry lifecycle, in-service-date authority, Last Checkout Mileage (11-23)."""
import os
import tempfile
import unittest

from elite.loaner.fixtures import Phase6
from elite.workflow.fixtures import SCOPE

VIN = "1GNSKBKC5FR000201"


class TestPhase6LifecycleDating(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    # ---- entry lifecycle ---------------------------------------------------
    def test_11_entry_approval_does_not_establish_membership(self):
        c = self.p.candidate(VIN)
        r = self.p.units.propose_entry(self.p.full, SCOPE, c)
        r = self.p.units.approve_entry(self.p.full, SCOPE, r["unit"])
        self.assertEqual(r["unit"].membership_state, "ENTRY_APPROVED")
        self.assertFalse(r["unit"].active_fleet_presence)         # approval != membership

    def test_12_entry_execution_establishes_membership_once(self):
        c = self.p.candidate(VIN)
        r = self.p.units.approve_entry(self.p.full, SCOPE, self.p.units.propose_entry(self.p.full, SCOPE, c)["unit"])
        r = self.p.units.execute_entry(self.p.full, SCOPE, r["unit"])
        self.assertEqual(r["unit"].membership_state, "ACTIVE_AVAILABLE")
        self.assertTrue(r["unit"].active_fleet_presence)
        self.assertIsNotNone(r["unit"].entry_execution_event)

    def test_13_replayed_entry_execution_no_duplicate(self):
        c = self.p.candidate(VIN)
        r = self.p.units.approve_entry(self.p.full, SCOPE, self.p.units.propose_entry(self.p.full, SCOPE, c)["unit"])
        e1 = self.p.units.execute_entry(self.p.full, SCOPE, r["unit"])
        e2 = self.p.units.execute_entry(self.p.full, SCOPE, self.p.store.get_unit(e1["unit"].id))
        self.assertTrue(e2["replayed"])
        self.assertEqual(e1["unit"].entry_execution_event, self.p.store.get_unit(e1["unit"].id).entry_execution_event)

    def test_14_rental_state_separate_from_membership(self):
        u = self.p.make_active(VIN, rental="available")
        state_before = u.membership_state
        u = self.p.units.set_rental_state(u, "rented")
        self.assertEqual(u.current_rental_state, "rented")
        self.assertEqual(u.membership_state, state_before)        # membership unchanged by rental

    # ---- in-service date ---------------------------------------------------
    def test_15_verified_in_service_controls_tenure(self):
        u = self.p.make_active(VIN)
        r = self.p.dating.resolve_in_service_date(u, [{"value": "2025-02-01", "source": "dms", "authority": "verified"}])
        self.assertEqual(r.authority_level, "verified")
        self.assertEqual(self.p.store.get_unit(u.id).accepted_in_service_date, "2025-02-01")

    def test_16_import_date_does_not_substitute(self):
        u = self.p.make_active(VIN)
        with self.p.store.conn:                                   # clear accepted date to observe fallback behavior
            self.p.store.set_unit_field(self.p.store.conn, u.id, accepted_in_service_date=None)
        r = self.p.dating.resolve_in_service_date(self.p.store.get_unit(u.id),
                                                  [{"value": "2026-07-01", "source": "file", "authority": "import"}],
                                                  import_date="2026-07-01")
        self.assertIsNone(r.accepted_value)                       # import date never accepted

    def test_17_conflicting_in_service_unresolved(self):
        u = self.p.make_active(VIN)
        r = self.p.dating.resolve_in_service_date(u, [
            {"value": "2025-01-01", "source": "a", "authority": "verified"},
            {"value": "2025-03-01", "source": "b", "authority": "verified"}])
        self.assertEqual(r.authority_level, "unresolved")
        self.assertIsNone(r.accepted_value)

    def test_18_in_service_correction_preserves_history(self):
        u = self.p.make_active(VIN)
        self.p.dating.resolve_in_service_date(u, [{"value": "2025-01-15", "source": "a", "authority": "verified"}])
        self.p.dating.correct_in_service_date(self.p.store.get_unit(u.id), "2024-12-01")
        res = self.p.store.in_service_resolutions(u.id)
        self.assertGreaterEqual(len(res), 2)                      # prior resolution preserved
        self.assertEqual(self.p.store.get_unit(u.id).accepted_in_service_date, "2024-12-01")

    # ---- Last Checkout Mileage --------------------------------------------
    def test_19_20_21_zero_blank_missing_distinct(self):
        z = self.p.dating.record_mileage(self.p.make_active(VIN), "0")
        b = self.p.dating.record_mileage(self.p.make_active("1GNSKBKC5FR000210"), "")
        m = self.p.dating.record_mileage(self.p.make_active("1GNSKBKC5FR000211"), None)
        self.assertEqual((z.value_kind, z.value), ("zero", 0))
        self.assertEqual(b.value_kind, "blank")
        self.assertEqual(m.value_kind, "missing")
        self.assertNotEqual(z.value_kind, b.value_kind)
        self.assertNotEqual(b.value_kind, m.value_kind)

    def test_22_invalid_mileage_not_authoritative(self):
        inv = self.p.dating.record_mileage(self.p.make_active(VIN), "abc")
        self.assertEqual(inv.value_kind, "invalid")
        self.assertFalse(self.p.dating.is_authoritative_zero(inv))

    def test_23_checkout_distinct_from_odometer_and_supersede(self):
        u = self.p.make_active(VIN, checkout_mileage=1000)
        self.p.dating.record_mileage(u, 1500)                     # later value supersedes current use
        cur = self.p.store.current_mileage(u.id)
        self.assertEqual(cur.value, 1500)
        self.assertEqual(len(self.p.store.mileage_history(u.id)), 2)   # earlier observation preserved
        # Last Checkout Mileage is its own fact, not an inferred current odometer.
        self.assertEqual(cur.source, "snapshot")


if __name__ == "__main__":
    unittest.main()
