"""Service Loaner board — Fleet Position band (self-balancing) + honest fleet cascade, and the independence
of the management directive from the engine-calculated requirement."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.ids import new_id
from elite.loaner.self_balancing import build_requirement
from elite.loaner.loaner_cockpit import MetaPrefs, set_desired_fleet
from elite.ordering.cross_domain import PlannedRequirementStore


class TestBoardAndEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _unit(self, tag, isd=None, miles=None):
        self.conn.execute(
            "INSERT INTO service_loaner_unit(id,vin,store_scope,membership_state,active_fleet_presence,"
            "accepted_in_service_date,in_service_date_authority,last_checkout_mileage,created_at,version)"
            " VALUES(?,?,?,?,1,?,?,?,?,1)",
            (new_id("slu"), f"5N1AZ2CS0PC9{tag:05d}", SCOPE, "ACTIVE_AVAILABLE", isd,
             "verified" if isd else "snapshot", miles, "2026-01-01"))
        self.conn.commit()

    def test_directive_is_independent_of_calculated_need(self):
        for i in range(4):
            self._unit(i, isd="2025-11-01", miles="3000")
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), 3)          # 4 >= 3 -> need 0
        before = build_requirement(self.conn, SCOPE, self.p.app.prefs).calculated_need
        PlannedRequirementStore(self.p.app.prefs, SCOPE).add(model="QX60", quantity=5, actor="k", recorded_at="t")
        after = build_requirement(self.conn, SCOPE, self.p.app.prefs).calculated_need
        self.assertEqual(before, 0)
        self.assertEqual(after, 0)                    # a management directive never changes the calculated need

    def test_cascade_renders_all_units_and_unknown_icv_not_zero(self):
        self._unit(1, isd="2025-11-01", miles="3000")
        self._unit(2, isd=None)                       # blocked unit
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), 5)
        b = self.full.get("/service-loaner").body
        self.assertIn("Fleet position — self-balancing", b)
        self.assertIn("Applicable ICV", b)
        self.assertIn("Unknown", b)                   # no ICV recorded -> Unknown, never $0
        self.assertNotIn("$0 pending", b)             # the legacy "$0 pending" bug must not reappear
        self.assertNotIn(">$0<", b)                   # and no ICV cell renders a bare $0 for an unknown value
        self.assertIn("PC900001", b)                  # unit 1 VIN tail present (rendered, no per-unit nav needed)
        self.assertIn("PC900002", b)                  # unit 2 present too


if __name__ == "__main__":
    unittest.main(verbosity=2)
