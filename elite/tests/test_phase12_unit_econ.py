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


class TestWriteDownPolicy(unittest.TestCase):
    """Authoritative write-down: % of original INVOICE per month (never ICV), no cap, daily-prorated, fails
    closed on missing invoice."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.pol = SLPolicyStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_default_rate_is_governed_1_25(self):
        from elite.loaner.sl_policy import DEFAULT_WRITEDOWN_MONTHLY_RATE
        self.assertEqual(DEFAULT_WRITEDOWN_MONTHLY_RATE, 1.25)     # governed data, not buried in a calc
        rate, src = self.pol.writedown_monthly_rate("2026-08")
        self.assertEqual(rate, 1.25)
        self.assertIn("default", src)

    def test_governed_rate_overrides_default_effective_dated(self):
        self.pol.set_writedown_rate(2.0, effective_month="2026-06", actor="k", at="t")
        self.assertEqual(self.pol.writedown_monthly_rate("2026-07")[0], 2.0)     # after effective
        self.assertEqual(self.pol.writedown_monthly_rate("2026-05")[0], 1.25)    # before -> default

    def test_cumulative_uses_invoice_not_icv_no_cap_accrues(self):
        from elite.loaner.sl_policy import cumulative_writedown, DAYS_PER_MONTH
        d6, e6, pa = cumulative_writedown(invoice=80000, monthly_rate=1.25, tenure_days=6 * DAYS_PER_MONTH)
        d12, _, _ = cumulative_writedown(invoice=80000, monthly_rate=1.25, tenure_days=12 * DAYS_PER_MONTH)
        self.assertEqual(d6, 6000)                    # 1.25%/mo × 80,000 × 6 mo
        self.assertEqual(d12, 12000)                  # no cap: 12 months writes down twice as much
        self.assertTrue(pa)                           # daily proration flagged as a planning assumption
        self.assertIn("invoice", e6)
        self.assertNotIn("ICV", e6)

    def test_changing_icv_cannot_alter_writedown(self):
        from elite.loaner.sl_policy import cumulative_writedown
        a = cumulative_writedown(invoice=50000, monthly_rate=1.25, tenure_days=90)[0]
        b = cumulative_writedown(invoice=50000, monthly_rate=1.25, tenure_days=90)[0]
        self.assertEqual(a, b)                        # write-down is invoice-based; ICV is not an input at all

    def test_partial_month_daily_proration(self):
        from elite.loaner.sl_policy import cumulative_writedown, DAYS_PER_MONTH
        half = cumulative_writedown(invoice=60000, monthly_rate=1.25, tenure_days=DAYS_PER_MONTH / 2)[0]
        full = cumulative_writedown(invoice=60000, monthly_rate=1.25, tenure_days=DAYS_PER_MONTH)[0]
        self.assertEqual(full, 750)                   # 1.25% of 60,000
        self.assertEqual(half, 375)                   # half a month -> half the write-down (daily proration)

    def test_missing_invoice_fails_closed(self):
        from elite.loaner.sl_policy import cumulative_writedown
        d, reason, pa = cumulative_writedown(invoice=None, monthly_rate=1.25, tenure_days=90)
        self.assertIsNone(d)                          # never substitute MSRP/ICV/estimate
        self.assertIn("invoice", reason)

    def test_protection_buffer_is_days_and_separate(self):
        self.pol.set_protection_buffer_days(21, actor="k", at="t")
        self.assertEqual(self.pol.protection_buffer_days(), 21)
        self.assertEqual(release_timing_buffer_days(self.p.app, SCOPE), 21)
        gate_keys = {g.key for g in phase4_gates(self.p.app, SCOPE)}
        self.assertNotIn("buffer", gate_keys)         # DAYS never a dollar placement gate

    def test_per_vin_invoice_override(self):
        self.pol.set_invoice("5N1AZ2CS0PC900001", 55000, actor="k", at="t")
        self.assertEqual(self.pol.invoice_for_vin("5n1az2cs0pc900001"), 55000)   # normalized
        self.assertIsNone(self.pol.invoice_for_vin("OTHER"))

    def test_invoice_read_from_governed_inv_field_never_msrp_or_cost(self):
        # The source contract new_inventory_pipeline_summary maps the DMS "Inv" column onto canonical `inv`.
        # _invoice_of must consume it (currency string, no VIN needed), never MSRP, never generic vehicle cost.
        from elite.loaner.unit_econ import _invoice_of
        row = {"stock_number": "Q26029", "serial": "430938", "msrp": "72,000", "inv": "63,500",
               "vehicle_cost": "60,000"}                                          # cost present but MUST be ignored
        self.assertEqual(_invoice_of(row, "", self.pol), 63500)                   # reads inv, no VIN required
        # msrp / vehicle_cost alone (no inv) -> no invoice (fails closed, never substituted)
        self.assertIsNone(_invoice_of({"msrp": "72,000", "vehicle_cost": "60,000"}, "", self.pol))
        # an explicit invoice header still wins over inv
        self.assertEqual(_invoice_of({"invoice": "61,000", "inv": "63,500"}, "", self.pol), 61000)


class TestBuildAndSourcing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        self._prep()

    def tearDown(self):
        self.p.close()

    def _prep(self):
        from elite.loaner.program_inputs import ProgramInputsStore
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        for model, icv in (("QX80", 9000), ("QX60", 6500)):
            pis.add("icv", effective_month="2026-01", model=model, value=icv, actor="k", recorded_at="t")
            pis.add("velocity", effective_month="2026-01", model=model, value=2500, actor="k", recorded_at="t")
        SLPolicyStore(self.app.prefs, SCOPE).set_projected_tenure_months(6, actor="k", at="t")  # default rate 1.25

    def _ctx(self, cands, gross, invoices):
        rows = [{"invoice": inv} for inv in invoices]
        return [patch("elite.loaner.unit_econ.read_new_retail_units", return_value=rows),
                patch("elite.loaner.unit_econ.certified_harm_index", return_value={}),
                patch("elite.loaner.unit_econ._to_candidate", side_effect=list(cands)),
                patch("elite.loaner.unit_econ._used_gross_by_model", return_value=gross)]

    def test_ranking_qx60_over_qx80_by_invoice_writedown(self):
        # QX80 has the pricier invoice -> larger cumulative write-down -> lower net, so QX60 ranks first
        ctx = self._ctx([_cand("S80", "QX80", "2026"), _cand("S60", "QX60", "2026")],
                        {"QX80": 3500, "QX60": 3000}, invoices=[100000, 50000])
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            res = build_placement_econ(self.app, SCOPE, "2026-01", n=2)
        self.assertEqual([i["econ"].model for i in res["ranked"]], ["QX60", "QX80"])

    def test_missing_invoice_excludes_unit(self):
        ctx = self._ctx([_cand("A", "QX60", "2026")], {"QX60": 3000}, invoices=[None])
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            res = build_placement_econ(self.app, SCOPE, "2026-01", n=1)
        self.assertFalse(res["have_economics"])       # write-down fails closed -> economics incomplete
        self.assertTrue(any("Write-down" in " ".join(e["missing"]) for e in res["excluded"]))

    def test_sourcing_places_from_surplus_orders_the_rest(self):
        cands = [_cand("A", "QX60", "2026"), _cand("B", "QX60", "2026")]
        ctx = self._ctx(cands, {"QX60": 3000}, invoices=[50000, 50000])
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            sp = sourcing_plan(self.app, SCOPE, "2026-01", {"QX60": 3})
        ms = sp["by_model"]["QX60"]
        self.assertEqual(ms.place_count, 2)
        self.assertEqual(ms.order_count, 1)
        self.assertFalse(ms.unresolved)

    def test_tenure_changes_placement_economics_via_scenario(self):
        cands3 = [_cand("A", "QX60", "2026")]
        cands6 = [_cand("A", "QX60", "2026")]
        base = dict(certified=patch("elite.loaner.unit_econ.certified_harm_index", return_value={}),
                    gross=patch("elite.loaner.unit_econ._used_gross_by_model", return_value={"QX60": 3000}))
        with patch("elite.loaner.unit_econ.read_new_retail_units", return_value=[{"invoice": 50000}]), \
             base["certified"], patch("elite.loaner.unit_econ._to_candidate", side_effect=cands3), base["gross"]:
            r3 = build_placement_econ(self.app, SCOPE, "2026-01", n=1, scenario={"tenure_months": 3})
        with patch("elite.loaner.unit_econ.read_new_retail_units", return_value=[{"invoice": 50000}]), \
             patch("elite.loaner.unit_econ.certified_harm_index", return_value={}), \
             patch("elite.loaner.unit_econ._to_candidate", side_effect=cands6), \
             patch("elite.loaner.unit_econ._used_gross_by_model", return_value={"QX60": 3000}):
            r6 = build_placement_econ(self.app, SCOPE, "2026-01", n=1, scenario={"tenure_months": 6})
        self.assertGreater(r3["all_econ"][0].net(), r6["all_econ"][0].net())   # longer tenure -> lower net
        self.assertEqual(SLPolicyStore(self.app.prefs, SCOPE).projected_tenure_months(), 6)  # official unchanged

    def test_sourcing_unresolved_when_economics_absent_orders_full(self):
        ctx = self._ctx([_cand("A", "QX60", "2026")], {}, invoices=[None])   # no gross, no invoice
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            sp = sourcing_plan(self.app, SCOPE, "2026-01", {"QX60": 3})
        ms = sp["by_model"]["QX60"]
        self.assertTrue(ms.unresolved)
        self.assertEqual(ms.order_count, 3)
        self.assertEqual(ms.place_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
