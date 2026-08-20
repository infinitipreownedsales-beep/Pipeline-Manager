"""Cross-domain ordering integrity — committed-VIN protection (one vehicle / one purpose / count once) and the
governed additive planned Service-Loaner requirement (non-economic; never mutates certified Retail demand)."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.ordering.cross_domain import committed_vins, PlannedRequirementStore


class TestCommittedVins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _sl(self, vin, state="ACTIVE_AVAILABLE"):
        from elite.ids import new_id
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "created_at,version) VALUES(?,?,?,?,1,?,1)", (new_id("slu"), vin, SCOPE, state, "2026-01-01"))
        self.conn.commit()

    def test_active_loaner_vins_are_committed(self):
        self._sl("5N1AZ2CS0PC900001")
        self._sl("5N1AZ2CS0PC900002", state="AWAITING_USED_CARS_RECEIPT")
        c = committed_vins(self.conn, SCOPE)
        self.assertEqual(c.get("5N1AZ2CS0PC900001"), "service_loaner")
        self.assertEqual(c.get("5N1AZ2CS0PC900002"), "service_loaner")

    def test_demo_roster_vins_are_committed(self):
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "demo_roster",
                                  [{"id": "d1", "name": "GM", "current": {"vin": "5N1AZ2CS0PC900050"}}])
        c = committed_vins(self.conn, SCOPE, self.p.app.prefs)
        self.assertEqual(c.get("5N1AZ2CS0PC900050"), "demo")

    def test_count_once_sl_wins(self):
        vin = "5N1AZ2CS0PC900099"
        self._sl(vin)
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "demo_roster",
                                  [{"id": "d", "name": "x", "current": {"vin": vin}}])
        c = committed_vins(self.conn, SCOPE, self.p.app.prefs)
        self.assertEqual(c[vin], "service_loaner")            # a VIN is counted once, not in both purposes
        self.assertEqual(len([v for v in c.keys() if v == vin]), 1)   # exactly one committed entry


class TestPlannedRequirement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.store = PlannedRequirementStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_add_and_by_model(self):
        self.store.add(model="QX60", quantity=3, actor="kyle", recorded_at="t", required_by="2026-10",
                       reason="management directive")
        self.store.add(model="QX60", quantity=1, actor="kyle", recorded_at="t")
        self.store.add(model="QX80", quantity=2, actor="kyle", recorded_at="t")
        self.assertEqual(self.store.by_model(), {"QX60": 4, "QX80": 2})

    def test_positive_quantity_required(self):
        with self.assertRaises(ValueError):
            self.store.add(model="QX60", quantity=0, actor="k", recorded_at="t")

    def test_retire_removes_from_active(self):
        e = self.store.add(model="QX60", quantity=3, actor="k", recorded_at="t")
        self.store.retire(e.id, actor="k", at="2026-08-19")
        self.assertEqual(self.store.by_model(), {})           # retired need no longer participates
        self.assertEqual(len(self.store.entries()), 1)        # preserved for audit

    def test_schema_unchanged(self):
        self.store.add(model="QX60", quantity=1, actor="k", recorded_at="t")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
