"""Per-unit UnitEcon adapter + sourcing decomposition. Proves: the economic wire feeds the certified
ideal_mix; oldest/excess does NOT auto-win; QX80 can lose to (or beat) QX60 on real economics; a missing
authoritative input excludes a unit (never zeroed); DAYS (protection buffer) are never summed with DOLLARS;
and a directive is decomposed into place-from-surplus vs order-specifically before it reaches CPO."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.loaner.unit_econ import compute_placement_econ, build_placement_econ, sourcing_plan
from elite.loaner.placement import PlacementCandidate, EXCESS
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.economics_readiness import phase4_gates, release_timing_buffer_days
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


def _cand(stock, model, year, state=EXCESS):
    return PlacementCandidate(stock=stock, vin="", vin_authoritative=False, serial="", year=year, model=model,
                              trim="LUXE", drivetrain="AWD", exterior="QBE", interior="G", dis=100,
                              new_retail_state=state, harm_label="", rank_reason="", safe=True)


class TestComputeEcon(unittest.TestCase):
    def _econ(self, **kw):
        base = dict(unit_id="u", identity="id", model="QX60", stock="S", icv=6500, velocity=2500,
                    used_gross=3000, writedown_dollars=3000, retail_opportunity_cost=0)
        base.update(kw)
        return compute_placement_econ(**base)

    def test_net_is_value_minus_cost_dollars_only(self):
        pe, missing = self._econ()
        self.assertEqual(missing, [])
        self.assertEqual(pe.in_value, 12000)          # 6500+2500+3000
        self.assertEqual(pe.opportunity_cost, 3000)   # write-down only; NO day-based buffer in dollars
        self.assertEqual(pe.net(), 9000)

    def test_no_day_term_ever_enters_dollars(self):
        pe, _ = self._econ()
        labels = " ".join(t.label for t in pe.terms).lower()
        self.assertNotIn("buffer", labels)            # the DAY protection buffer is not a dollar term
        self.assertNotIn("day", labels)

    def test_higher_writedown_lowers_net(self):
        low, _ = self._econ(model="QX60", writedown_dollars=3000)
        high, _ = self._econ(model="QX80", writedown_dollars=9000, icv=9000, used_gross=3500)
        self.assertLess(high.net(), low.net())        # older/excess QX80 loses on total economics

    def test_qx80_can_win_when_economics_support(self):
        qx60, _ = self._econ(model="QX60", writedown_dollars=3000, used_gross=3000)
        qx80, _ = self._econ(model="QX80", writedown_dollars=3200, used_gross=6000, icv=9000)
        self.assertGreater(qx80.net(), qx60.net())    # data, not the model name, decides

    def test_missing_input_excludes_not_zeroes(self):
        pe, missing = self._econ(used_gross=None)
        self.assertIsNone(pe)
        self.assertIn("Expected used gross ($)", missing)

    def test_explicit_zero_writedown_is_used(self):
        pe, missing = self._econ(writedown_dollars=0)
        self.assertEqual(missing, [])
        self.assertEqual(pe.opportunity_cost, 0)


class TestPolicyUnits(unittest.TestCase):
    """The two governed policies live in different dimensions and are never confused."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.pol = SLPolicyStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_writedown_amount_and_percent_of_icv(self):
        self.pol.set_writedown("QX60", 3000, kind="amount", actor="k", at="t")
        d, expl = self.pol.resolve_writedown_dollars("QX60", icv=6500)
        self.assertEqual(d, 3000)
        self.pol.set_writedown("QX80", 20, kind="percent_icv", actor="k", at="t")
        d2, expl2 = self.pol.resolve_writedown_dollars("QX80", icv=9000)
        self.assertEqual(d2, 1800)                    # 20% of $9,000
        self.assertIn("%", expl2)

    def test_percent_writedown_unknown_when_icv_missing(self):
        self.pol.set_writedown("QX80", 20, kind="percent_icv", actor="k", at="t")
        d, reason = self.pol.resolve_writedown_dollars("QX80", icv=None)
        self.assertIsNone(d)                          # cannot resolve a % without the ICV basis — never guessed
        self.assertIn("ICV", reason)

    def test_protection_buffer_is_days_and_separate(self):
        self.pol.set_protection_buffer_days(21, actor="k", at="t")
        self.assertEqual(self.pol.protection_buffer_days(), 21)
        self.assertEqual(release_timing_buffer_days(self.p.app, SCOPE), 21)
        # the buffer is NOT one of the dollar placement gates
        gate_keys = {g.key for g in phase4_gates(self.p.app, SCOPE)}
        self.assertNotIn("buffer", gate_keys)

    def test_readiness_writedown_gate_flips(self):
        g0 = {g.key: g.present for g in phase4_gates(self.p.app, SCOPE)}
        self.assertFalse(g0["writedown"])
        self.pol.set_writedown("QX60", 3000, kind="amount", actor="k", at="t")
        g1 = {g.key: g.present for g in phase4_gates(self.p.app, SCOPE)}
        self.assertTrue(g1["writedown"])


class TestBuildAndSourcing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        self._prep()

    def tearDown(self):
        self.p.close()

    def _prep(self, qx80_wd=9000, qx60_wd=3000):
        from elite.loaner.program_inputs import ProgramInputsStore
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        for model, icv in (("QX80", 9000), ("QX60", 6500)):
            pis.add("icv", effective_month="2026-01", model=model, value=icv, actor="k", recorded_at="t")
            pis.add("velocity", effective_month="2026-01", model=model, value=2500, actor="k", recorded_at="t")
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_writedown("QX80", qx80_wd, kind="amount", actor="k", at="t")
        pol.set_writedown("QX60", qx60_wd, kind="amount", actor="k", at="t")

    def _ctx(self, cands, gross):
        return [patch("elite.loaner.unit_econ.read_new_retail_units", return_value=[{"i": i} for i in range(len(cands))]),
                patch("elite.loaner.unit_econ.certified_harm_index", return_value={}),
                patch("elite.loaner.unit_econ._to_candidate", side_effect=list(cands)),
                patch("elite.loaner.unit_econ._used_gross_by_model", return_value=gross)]

    def test_ranking_qx60_over_qx80(self):
        ctx = self._ctx([_cand("S80", "QX80", "2026"), _cand("S60", "QX60", "2026")],
                        {"QX80": 3500, "QX60": 3000})
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            res = build_placement_econ(self.app, SCOPE, "2026-01", n=2)
        self.assertEqual([i["econ"].model for i in res["ranked"]], ["QX60", "QX80"])

    def test_sourcing_places_from_surplus_orders_the_rest(self):
        # need 3 QX60; only 2 QX60 surplus units are economically placeable -> place 2, ORDER 1
        cands = [_cand("A", "QX60", "2026"), _cand("B", "QX60", "2026")]
        ctx = self._ctx(cands, {"QX60": 3000})
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            sp = sourcing_plan(self.app, SCOPE, "2026-01", {"QX60": 3})
        ms = sp["by_model"]["QX60"]
        self.assertEqual(ms.place_count, 2)           # 2 sourced from existing surplus (not ordered)
        self.assertEqual(ms.order_count, 1)           # only 1 ordered specifically for Service Loaner
        self.assertFalse(ms.unresolved)

    def test_sourcing_unresolved_when_economics_absent_orders_full(self):
        SLPolicyStore(self.app.prefs, SCOPE).clear_writedown("QX60")   # break economics readiness
        ctx = self._ctx([_cand("A", "QX60", "2026")], {})              # no gross either
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            sp = sourcing_plan(self.app, SCOPE, "2026-01", {"QX60": 3})
        ms = sp["by_model"]["QX60"]
        self.assertTrue(ms.unresolved)                # cannot assess split -> conservative
        self.assertEqual(ms.order_count, 3)           # order the full requirement, never under-order Retail
        self.assertEqual(ms.place_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
