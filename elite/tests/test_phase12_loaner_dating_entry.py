"""Governed manual in-service-date / mileage entry — the fallback path to resolve a blocked active unit when
the fleet upload did not carry an authoritative in-service date. Verified operator entry; never a guess; a
correction preserves prior lineage."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.ids import new_id
from elite.db import current_version


class TestDatingEntry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _blocked_unit(self, vin="5N1AZ2CS0PC900777"):
        uid = new_id("slu")
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "in_service_date_authority,created_at,version) VALUES(?,?,?,?,1,?,?,1)",
            (uid, vin, SCOPE, "ACTIVE_AVAILABLE", "snapshot", "2026-01-01"))
        self.conn.commit()
        return uid

    def _unit(self, uid):
        from elite.loaner.store import LoanerStore
        return LoanerStore(self.conn, self.p.stack.clock).get_unit(uid)

    def test_resolve_blocked_unit(self):
        uid = self._blocked_unit()
        self.assertIsNone(self._unit(uid).accepted_in_service_date)          # starts blocked
        self.full.post(f"/service-loaner/unit/{uid}/dating",
                       {"in_service_date": "2025-12-01", "last_checkout_mileage": "3400"})
        u = self._unit(uid)
        self.assertEqual(u.accepted_in_service_date, "2025-12-01")
        self.assertEqual(u.in_service_date_authority, "verified")            # authoritative operator entry
        self.assertEqual(str(u.last_checkout_mileage), "3400")

    def test_correction_preserves_prior(self):
        uid = self._blocked_unit()
        self.full.post(f"/service-loaner/unit/{uid}/dating", {"in_service_date": "2025-12-01"})
        self.full.post(f"/service-loaner/unit/{uid}/dating", {"in_service_date": "2025-11-15"})   # correction
        self.assertEqual(self._unit(uid).accepted_in_service_date, "2025-11-15")
        from elite.loaner.store import LoanerStore
        res = LoanerStore(self.conn, self.p.stack.clock).in_service_resolutions(uid)
        self.assertGreaterEqual(len(res), 2)                                 # prior resolution preserved (append-only)

    def test_blank_entry_records_nothing(self):
        uid = self._blocked_unit()
        self.full.post(f"/service-loaner/unit/{uid}/dating", {"in_service_date": "", "last_checkout_mileage": ""})
        self.assertIsNone(self._unit(uid).accepted_in_service_date)          # never fabricated

    def test_schema_unchanged(self):
        uid = self._blocked_unit()
        self.full.post(f"/service-loaner/unit/{uid}/dating", {"in_service_date": "2025-12-01"})
        self.assertEqual(current_version(self.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
