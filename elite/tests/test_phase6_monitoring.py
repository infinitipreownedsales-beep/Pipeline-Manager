"""Phase 6 acceptance — zero-mile-rented monitoring (items 24-30) + dedicated 14-point regression."""
import os
import tempfile
import unittest

from elite.loaner.fixtures import Phase6
from elite.loaner.monitoring import PROMPT, RULE
from elite.workflow.fixtures import SCOPE

VIN = "1GNSKBKC5FR000301"


class TestPhase6Monitoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _rented_zero(self, in_service="2025-01-01", vin=VIN):
        return self.p.make_active(vin, rental="rented", in_service_date=in_service, checkout_mileage=0)

    def test_24_rented_zero_elapsed_produces_alert(self):
        u = self._rented_zero()
        a = self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        self.assertIsNotNone(a)
        self.assertEqual(a.prompt, PROMPT)

    def test_25_rented_zero_before_threshold_no_alert(self):
        u = self._rented_zero(in_service="2026-05-25")
        self.assertIsNone(self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30))

    def test_26_rented_nonzero_no_alert(self):
        u = self.p.make_active(VIN, rental="rented", in_service_date="2025-01-01", checkout_mileage=800)
        self.assertIsNone(self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30))

    def test_27_no_longer_rented_clears_alert(self):
        u = self._rented_zero()
        self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        self.p.units.set_rental_state(self.p.store.get_unit(u.id), "available")
        self.assertIsNone(self.p.monitoring.evaluate(self.p.store.get_unit(u.id), at_date="2026-06-02", threshold_days=30))
        self.assertIsNone(self.p.store.active_alert(u.id, RULE))

    def test_28_prior_alert_history_preserved(self):
        u = self._rented_zero()
        self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        self.p.units.set_rental_state(self.p.store.get_unit(u.id), "available")
        self.p.monitoring.evaluate(self.p.store.get_unit(u.id), at_date="2026-06-02", threshold_days=30)
        self.assertEqual(len(self.p.store.alerts_for(u.id)), 1)   # cleared, still historical
        self.assertEqual(self.p.store.alerts_for(u.id)[0].status, "cleared")

    def test_29_30_no_invented_location_or_mileage(self):
        u = self._rented_zero()
        a = self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        # the alert asks a question; it never asserts a location or an actual mileage
        self.assertEqual(a.prompt, PROMPT)
        self.assertNotIn("located at", a.prompt.lower())
        self.assertIsNone(a.__dict__.get("actual_mileage"))


class TestZeroMileRegression(unittest.TestCase):
    """Dedicated 14-point zero-mile-rented monitoring regression."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))
        # 1. authoritative in-service date known
        self.u = self.p.make_active(VIN, rental="rented", in_service_date="2025-01-01", checkout_mileage=0)

    def tearDown(self):
        self.p.close()

    def test_zero_mile_regression(self):
        u = self.u
        self.assertEqual(u.in_service_date_authority, "verified")           # 1
        self.assertEqual(u.current_rental_state, "rented")                  # 2 current snapshot shows rented
        self.assertEqual(self.p.store.current_mileage(u.id).value_kind, "zero")   # 3 accepted mileage == 0
        # 4 elapsed exceeds threshold -> 5 alert with the approved question
        a = self.p.monitoring.evaluate(u, at_date="2026-06-01", threshold_days=30)
        self.assertIsNotNone(a)
        self.assertGreater(a.elapsed_days, a.threshold_days)
        self.assertEqual(a.prompt, PROMPT)
        # 6 no rental-history table required
        tables = {r[0] for r in self.p.store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertFalse(any("rental_history" in t for t in tables))
        # 7 repeated evaluation idempotent
        a2 = self.p.monitoring.evaluate(self.p.store.get_unit(u.id), at_date="2026-06-02", threshold_days=30)
        self.assertEqual(a.id, a2.id)
        self.assertEqual(len([x for x in self.p.store.alerts_for(u.id) if x.status == "active"]), 1)
        # 8 later nonzero checkout mileage clears the active alert; 9 prior remains historical
        self.p.dating.record_mileage(self.p.store.get_unit(u.id), 42)
        self.assertIsNone(self.p.monitoring.evaluate(self.p.store.get_unit(u.id), at_date="2026-06-03", threshold_days=30))
        self.assertEqual(self.p.store.alerts_for(u.id)[0].status, "cleared")
        # 10 a later not-rented snapshot clears the active alert (fresh unit)
        u2 = self.p.make_active("1GNSKBKC5FR000350", rental="rented", in_service_date="2025-01-01", checkout_mileage=0)
        self.p.monitoring.evaluate(u2, at_date="2026-06-01", threshold_days=30)
        self.p.units.set_rental_state(self.p.store.get_unit(u2.id), "available")
        self.assertIsNone(self.p.monitoring.evaluate(self.p.store.get_unit(u2.id), at_date="2026-06-02", threshold_days=30))
        # 11-13 blank / missing / invalid mileage do not trigger the rule
        for i, raw in enumerate(("", None, "abc")):
            uu = self.p.make_active(f"1GNSKBKC5FR00036{i}", rental="rented", in_service_date="2025-01-01",
                                    checkout_mileage=999)
            self.p.dating.record_mileage(uu, raw)
            self.assertIsNone(self.p.monitoring.evaluate(uu, at_date="2026-06-01", threshold_days=30))
        # 14 no customer-vehicle location or actual loaner mileage invented
        self.assertEqual(a.prompt, PROMPT)
        self.assertIsNone(a.__dict__.get("customer_location"))
        self.assertIsNone(a.__dict__.get("actual_mileage"))


if __name__ == "__main__":
    unittest.main()
