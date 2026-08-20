"""Per-unit UnitEcon adapter — proves the economic wire feeds the certified ideal_mix, that oldest/excess does
NOT automatically win, that QX80 can lose to (or beat) QX60 on real economics, that a missing authoritative
input excludes a unit (never zeroed), and that the governed policy flips economic readiness."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.loaner.unit_econ import compute_placement_econ, build_placement_econ
from elite.loaner.placement import PlacementCandidate, EXCESS
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.economics_readiness import phase4_gates, ready
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


def _cand(stock, model, year, state=EXCESS):
    return PlacementCandidate(stock=stock, vin="", vin_authoritative=False, serial="", year=year, model=model,
                              trim="LUXE", drivetrain="AWD", exterior="QBE", interior="G", dis=100,
                              new_retail_state=state, harm_label="", rank_reason="", safe=True)


class TestComputeEcon(unittest.TestCase):
    def _econ(self, **kw):
        base = dict(unit_id="u", identity="id", model="QX60", stock="S", icv=6500, velocity=2500,
                    used_gross=3000, writedown=3000, buffer=500, retail_opportunity_cost=0)
        base.update(kw)
        return compute_placement_econ(**base)

    def test_net_is_value_minus_cost(self):
        pe, missing = self._econ()
        self.assertEqual(missing, [])
        # in=6500+2500+3000=12000 ; cost=3000+500+0=3500 ; net=8500
        self.assertEqual(pe.in_value, 12000)
        self.assertEqual(pe.opportunity_cost, 3500)
        self.assertEqual(pe.net(), 8500)

    def test_higher_writedown_lowers_net(self):
        low, _ = self._econ(model="QX60", writedown=3000)
        high, _ = self._econ(model="QX80", writedown=9000, icv=9000, used_gross=3500)  # pricier, bigger write-down
        # QX80: in=9000+2500+3500=15000 ; cost=9000+500=9500 ; net=5500  < QX60 net 8500
        self.assertEqual(high.net(), 5500)
        self.assertLess(high.net(), low.net())        # oldest/excess QX80 loses on total economics

    def test_qx80_can_still_win_when_economics_support(self):
        qx60, _ = self._econ(model="QX60", writedown=3000, used_gross=3000)
        qx80, _ = self._econ(model="QX80", writedown=3200, used_gross=6000, icv=9000)  # strong retained value
        self.assertGreater(qx80.net(), qx60.net())    # data, not model name, decides

    def test_missing_input_excludes_not_zeroes(self):
        pe, missing = self._econ(used_gross=None)      # no defensible used-gross sample
        self.assertIsNone(pe)
        self.assertIn("Expected used gross", missing)

    def test_explicit_zero_is_used_not_missing(self):
        pe, missing = self._econ(writedown=0)          # a real $0 write-down policy
        self.assertEqual(missing, [])
        self.assertEqual(pe.opportunity_cost, 500)     # 0 write-down + 500 buffer


class TestBuildLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app

    def tearDown(self):
        self.p.close()

    def _prep_policy(self, buffer=500, qx80_wd=9000, qx60_wd=3000):
        from elite.loaner.program_inputs import ProgramInputsStore
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        for kind, val in (("icv", 6500), ("velocity", 2500)):
            pis.add(kind, effective_month="2026-01", model="QX80", value=(9000 if kind == "icv" else val),
                    actor="k", recorded_at="t")
            pis.add(kind, effective_month="2026-01", model="QX60", value=(6500 if kind == "icv" else val),
                    actor="k", recorded_at="t")
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_writedown("QX80", qx80_wd, actor="k", at="t")
        pol.set_writedown("QX60", qx60_wd, actor="k", at="t")
        pol.set_buffer(buffer, actor="k", at="t")

    def test_ranking_qx60_over_qx80_when_writedown_worse(self):
        self._prep_policy(qx80_wd=9000, qx60_wd=3000)
        cands = [_cand("S80", "QX80", "2026"), _cand("S60", "QX60", "2026")]
        with patch("elite.loaner.unit_econ.read_new_retail_units", return_value=[{"x": 1}, {"x": 2}]), \
             patch("elite.loaner.unit_econ.certified_harm_index", return_value={}), \
             patch("elite.loaner.unit_econ._to_candidate", side_effect=cands), \
             patch("elite.loaner.unit_econ._used_gross_by_model", return_value={"QX80": 3500, "QX60": 3000}):
            res = build_placement_econ(self.app, SCOPE, "2026-01", n=2)
        self.assertTrue(res["have_economics"])
        order = [item["econ"].model for item in res["ranked"]]
        self.assertEqual(order[0], "QX60")            # QX60 ranks first on total-dealership net
        self.assertEqual(order, ["QX60", "QX80"])

    def test_unit_excluded_when_gross_unknown(self):
        self._prep_policy()
        cands = [_cand("S80", "QX80", "2026")]
        with patch("elite.loaner.unit_econ.read_new_retail_units", return_value=[{"x": 1}]), \
             patch("elite.loaner.unit_econ.certified_harm_index", return_value={}), \
             patch("elite.loaner.unit_econ._to_candidate", side_effect=cands), \
             patch("elite.loaner.unit_econ._used_gross_by_model", return_value={}):   # no defensible sample
            res = build_placement_econ(self.app, SCOPE, "2026-01", n=1)
        self.assertFalse(res["have_economics"])
        self.assertEqual(len(res["excluded"]), 1)
        self.assertIn("Expected used gross", res["excluded"][0]["missing"])


class TestReadinessFlip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_policy_flips_writedown_and_buffer_gates(self):
        g0 = {x.key: x.present for x in phase4_gates(self.p.app, SCOPE)}
        self.assertFalse(g0["writedown"])
        self.assertFalse(g0["buffer"])
        pol = SLPolicyStore(self.p.app.prefs, SCOPE)
        pol.set_writedown("QX60", 3000, actor="k", at="t")
        pol.set_buffer(500, actor="k", at="t")
        g1 = {x.key: x.present for x in phase4_gates(self.p.app, SCOPE)}
        self.assertTrue(g1["writedown"])
        self.assertTrue(g1["buffer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
