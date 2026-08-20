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


class TestEconomicRankingSurface(unittest.TestCase):
    """The economic ranking must reach the operator surface (not stay in a module) when economics are ready."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_board_renders_economic_ranking_when_ready(self):
        from unittest.mock import patch
        from elite.loaner.unit_econ import compute_placement_econ
        qx60, _ = compute_placement_econ(unit_id="V60", identity="2026 QX60 LUXE AWD", model="QX60", stock="S60",
                                         icv=6500, velocity=2500, used_gross=3000, writedown_dollars=3000)
        qx80, _ = compute_placement_econ(unit_id="V80", identity="2026 QX80 LUXE AWD", model="QX80", stock="S80",
                                         icv=9000, velocity=2500, used_gross=3500, writedown_dollars=9000)
        res = {"loaded": True, "ready": True, "have_economics": True,
               "ranked": [{"econ": qx60, "net": qx60.net(), "identity": qx60.identity},
                          {"econ": qx80, "net": qx80.net(), "identity": qx80.identity}],
               "all_econ": [qx60, qx80], "excluded": [], "mix": None}
        import elite.tests.test_phase12_loaner_intelligence as INTEL
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()), \
             patch("elite.loaner.unit_econ.build_placement_econ", return_value=res):
            b = self.full.get("/service-loaner", add="2").body
        self.assertIn("Economic placement ranking", b)     # the real answer is on the surface
        self.assertIn("2026 QX60 LUXE AWD", b)
        self.assertIn("Proof — terms", b)                  # per-term Proof drilldown
        self.assertLess(b.index("2026 QX60 LUXE AWD"), b.index("2026 QX80 LUXE AWD"))  # QX60 ranked above QX80


class TestPolicyStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        from elite.loaner.sl_policy import SLPolicyStore
        self.pol = SLPolicyStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_set_get_and_explicit_zero(self):
        self.pol.set_writedown("qx60", 0, kind="amount", actor="k", at="t")   # a real $0 policy
        d, _ = self.pol.resolve_writedown_dollars("QX60", icv=6500)
        self.assertEqual(d, 0)                                     # 0, not None
        self.assertIsNone(self.pol.writedown_spec("QX80"))        # unset stays UNKNOWN, never 0
        self.pol.set_protection_buffer_days(21, actor="k", at="t")  # DAYS, a separate dimension
        self.assertEqual(self.pol.protection_buffer_days(), 21)

    def test_blank_rejected(self):
        with self.assertRaises(ValueError):
            self.pol.set_writedown("QX60", "", kind="amount", actor="k", at="t")


if __name__ == "__main__":
    unittest.main(verbosity=2)
