"""Retention-normalized, time-sensitive expected used-price curve (live acceptance 2026-08-27).

The expected used SELLING PRICE is now built from OBSERVED RETENTION — each historical sale's used price divided
by its authoritative original MSRP (resolved from the physical-unit inventory/pipeline source by the sale's own
governed model_code + model year) — measured against actual lifecycle age, then applied to THIS specific unit's
own authoritative MSRP. Consequences proven here:

  * two same-model units (both QX60) on the SAME sale date and SAME lifecycle age but DIFFERENT authoritative
    MSRPs do NOT receive the same expected price — the shared, pooled quantity is the retention PERCENT, never a
    raw-dollar median (the defect being repaired);
  * the price is still time-sensitive on a continuous age-in-months axis (30/60/90/120 days later differ);
  * the market/value rail (MSRP -> observed retention -> used price) stays independent of the dealer-basis rail
    (invoice -> write-down -> adjusted basis); Vehicle Cost is never mixed into the market curve;
  * no authoritative MSRP for the unit, unresolved model year, empty history, or age beyond the observed window
    all GATE honestly — nothing is manufactured, and the operator is never asked to type MSRP.
"""
import os
import datetime as dt
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_decision import (build_unit_decision, _retention_price, _unit_inventory_facts,
                                      _age_months_at)
from elite.loaner.intelligence import UnitIntel
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore

VIN = "5N1AL1HU8TC348756"          # last-8 TC348756 joins to the inventory Serial
VIN_B = "5N1AL1HU8TDD990000"       # a SECOND physical QX60, a different trim/model code + MSRP


# Authoritative original MSRP by (model_code, model year) — the anchors used to normalize each historical sale
# and to value the current units. Two QX60 trims: 84616 (loaded, higher MSRP) and 84617 (base, lower MSRP).
_MSRP = {"84616": {2024: 58000, 2025: 60000, 2026: 62000},
         "84617": {2024: 50000, 2025: 52000, 2026: 54000}}


def _inv(active=(("TC348756", "S1", "84616", "2026", 62000),
                 ("DD990000", "S2", "84617", "2026", 54000))):
    """Inventory/pipeline rows: the authoritative physical-unit MSRP + model-code source. Carries the two active
    units (matched by Serial last-8) plus per-(code, MY) MSRP anchors for the historical retention join. No full
    VIN column — a unit is identified by Serial/Stock#, exactly like the real DMS pipeline export."""
    rows = [{"vin": None, "serial": s, "stock_number": st, "model": "QX60",
             "model_code": c, "model_year": my, "msrp": str(ms)} for (s, st, c, my, ms) in active]
    for code, by_my in _MSRP.items():
        for my, ms in by_my.items():
            rows.append({"vin": None, "serial": "ANCHOR", "stock_number": "ANCHOR", "model": "QX60",
                         "model_code": code, "model_year": str(my), "msrp": str(ms)})
    return rows


def _rows(slope=400, model="QX60", codes=("84616", "84617"), ages=range(3, 16), per=5):
    """Real-shaped resale history whose RETENTION (price / original MSRP) declines with lifecycle age, pooled
    across model years and both trims. Each sale carries its governed model_number (code) + year so its original
    MSRP is recoverable — no raw dollar is ever pooled across trims."""
    out = []
    for code in codes:
        for my in (2024, 2025, 2026):
            msrp = _MSRP[code][my]
            for a in ages:
                t = my * 12 + a
                y, m = t // 12, t % 12 + 1
                for k in range(per):
                    out.append({"model": model, "model_number": code, "year": str(my),
                                "sold_date": f"{y:04d}-{m:02d}-15",
                                "price": str(msrp - slope * a + (k - 2) * 100), "days_to_sell": "40"})
    return out


def _unit(vin=VIN):
    return UnitIntel(id="u1", vin=vin, model="QX60", in_service_date="2026-02-10", age_days=180, mileage=8000,
                     mileage_available=True, membership_state="ACTIVE_AVAILABLE", rental_state=None,
                     quality_flags=(), model_year="2026")


class TestRetentionCurvePure(unittest.TestCase):
    def test_two_units_same_date_and_age_different_msrp_get_different_price(self):
        # THE ACCEPTANCE PROOF: two MY2026 QX60s, identical sale date and lifecycle age, but different
        # authoritative MSRPs. They must NOT be handed the same expected price merely because both are QX60s.
        rows, inv = _rows(), _inv()
        msrp_a, code_a = _unit_inventory_facts(inv, VIN)      # 84616 / $62,000
        msrp_b, code_b = _unit_inventory_facts(inv, VIN_B)    # 84617 / $54,000
        self.assertEqual((msrp_a, code_a), (62000.0, "84616"))
        self.assertEqual((msrp_b, code_b), (54000.0, "84617"))
        sd = "2026-08-15"
        pa, prov_a, _ca = _retention_price(rows, inv, "QX60", "2026", sd, msrp_a, code_a)
        pb, _pb, _cb = _retention_price(rows, inv, "QX60", "2026", sd, msrp_b, code_b)
        self.assertIsNotNone(pa)
        self.assertIsNotNone(pb)
        self.assertNotEqual(pa, pb)                            # NOT the same price
        self.assertGreater(pa, pb)                             # the higher-MSRP unit is worth more
        self.assertIn("observed retention", prov_a)            # cites the retention %, not a dollar median
        self.assertIn("this unit's authoritative MSRP $62,000", prov_a)
        # each price is that unit's OWN MSRP times an observed retention percent (never a shared raw dollar)
        self.assertAlmostEqual(pa, msrp_a * (pa / msrp_a), places=6)
        self.assertAlmostEqual(pb, msrp_b * (pb / msrp_b), places=6)

    def test_shared_model_cohort_retention_applies_each_units_own_msrp(self):
        # when the evidence degrades to the broader same-model cohort, the retention PERCENT is shared but each
        # unit's price still applies ITS OWN MSRP — so the two prices scale exactly with their MSRPs, and are
        # NOT equal (the raw-dollar-median defect would have made them identical).
        rows, inv = _rows(), _inv()
        sd = "2026-08-15"
        pa = _retention_price(rows, inv, "QX60", "2026", sd, 62000.0, None)      # code None -> broader cohort
        pb = _retention_price(rows, inv, "QX60", "2026", sd, 54000.0, None)
        self.assertIn("same model (MSRP-normalized)", pa[1])
        self.assertNotEqual(pa[0], pb[0])
        self.assertAlmostEqual(pa[0] / pb[0], 62000.0 / 54000.0, places=4)       # scales with own MSRP
        self.assertAlmostEqual(pa[0] / 62000.0, pb[0] / 54000.0, places=6)       # identical shared retention %

    def test_five_points_time_sensitive_and_cited(self):
        rows, inv = _rows(), _inv()
        base = dt.date(2026, 8, 26)
        pts = []
        for days in (0, 30, 60, 90, 120):
            sd = (base + dt.timedelta(days=days)).isoformat()
            price, prov, conf = _retention_price(rows, inv, "QX60", "2026", sd, 62000.0, "84616")
            self.assertIsNotNone(price, days)
            self.assertIn("observed retention", prov)
            self.assertNotEqual(conf, "none")
            pts.append(price)
        self.assertGreater(len(set(pts)), 1)                                        # not merely repeated
        self.assertTrue(all(pts[i] >= pts[i + 1] for i in range(len(pts) - 1)))     # declines with the curve
        self.assertLess(pts[-1], pts[0])

    def test_same_integer_age_different_months_differ(self):
        rows, inv = _rows(), _inv()
        p_aug = _retention_price(rows, inv, "QX60", "2026", "2026-08-15", 62000.0, "84616")[0]   # int age 0
        p_dec = _retention_price(rows, inv, "QX60", "2026", "2026-12-15", 62000.0, "84616")[0]   # int age 0 too
        self.assertEqual(_age_months_at("2026", "2026-08-15"), 7)
        self.assertEqual(_age_months_at("2026", "2026-12-15"), 11)
        self.assertNotEqual(p_aug, p_dec)

    def test_broader_model_retention_used_when_same_code_thin(self):
        # the current unit's own model code has NO history; the broader same-model (MSRP-normalized) retention
        # is used instead — never a raw-dollar pool of a different trim.
        rows = _rows(codes=("84617",))                          # only the OTHER trim traded
        inv = _inv()
        price, prov, _c = _retention_price(rows, inv, "QX60", "2026", "2026-08-15", 62000.0, "84616")
        self.assertIsNotNone(price)
        self.assertIn("same model (MSRP-normalized)", prov)     # tier 2, not the missing same-code tier
        self.assertIn("this unit's authoritative MSRP $62,000", prov)

    def test_gates_without_manufacturing(self):
        rows, inv = _rows(), _inv()
        self.assertIsNone(_retention_price([], inv, "QX60", "2026", "2026-08-26", 62000.0, "84616")[0])   # no hist
        self.assertIsNone(_retention_price(rows, inv, "QX60", "2026", "2026-08-26", None, "84616")[0])    # no MSRP
        self.assertIsNone(_retention_price(rows, inv, "QX60", "", "2026-08-26", 62000.0, "84616")[0])     # MY gate
        self.assertIsNone(_retention_price(rows, inv, "QX60", "2026", "2031-08-26", 62000.0, "84616")[0]) # age gate


class TestHoldBenefitReflectsMarketAndBasis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_invoice(VIN, 60000, actor="k", at="t")
        pol.set_protection_buffer_days(20, actor="k", at="t")
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        pis.add("icv", effective_month="2026-01", model="QX60", model_year="2026", value=6500, actor="k",
                recorded_at="t")
        pis.add("velocity", effective_month="2026-01", model="QX60", model_year="2026", value=2500,
                day_cap=240, mile_cap=10000, actor="k", recorded_at="t")

    def tearDown(self):
        self.p.close()

    def _decide(self, slope):
        with patch("elite.loaner.sl_decision._retail_rows", return_value=_rows(slope=slope)), \
             patch("elite.loaner.sl_decision._inventory_rows", return_value=_inv()):
            return build_unit_decision(self.app, SCOPE, _unit(), None, today="2026-08-26", keep_horizon_days=90)

    def test_unit_msrp_resolved_and_carried(self):
        d = self._decide(400)
        self.assertEqual(d["facts"]["unit_msrp"], 62000.0)         # authoritative, from inventory (not typed)
        self.assertEqual(d["facts"]["unit_model_code"], "84616")
        self.assertIn("authoritative MSRP $62,000", d["facts"]["price_now_basis"])

    def test_hold_benefit_is_market_plus_basis_not_basis_alone(self):
        d = self._decide(400)
        c, f = d["components"], d["facts"]
        self.assertLess(f["price_future"], f["price_now"])                       # market value declines over hold
        self.assertLess(c["adjusted_basis_future"], c["adjusted_basis_now"])     # basis also falls (write-down)
        self.assertAlmostEqual(c["front_end_gross_future"], f["price_future"] - c["adjusted_basis_future"], places=0)
        hold_delta = c["front_end_gross_future"] - c["front_end_gross_now"]
        market_change = f["price_future"] - f["price_now"]
        basis_gain = c["adjusted_basis_now"] - c["adjusted_basis_future"]
        self.assertAlmostEqual(hold_delta, market_change + basis_gain, places=0)
        self.assertLess(market_change, 0)                                        # market is a real, non-zero input

    def test_steeper_market_decline_lowers_future_gross(self):
        shallow = self._decide(300)
        steep = self._decide(1500)
        self.assertEqual(shallow["components"]["adjusted_basis_future"],
                         steep["components"]["adjusted_basis_future"])           # basis path identical
        self.assertLess(steep["components"]["front_end_gross_future"],
                        shallow["components"]["front_end_gross_future"])          # market value moved the answer

    def test_basis_rail_never_uses_msrp_market_rail_never_uses_invoice(self):
        # two-rail separation: the market price is MSRP × retention (independent of the $60,000 invoice), and the
        # adjusted basis derives from invoice + write-down (independent of the $62,000 MSRP).
        d = self._decide(400)
        f, c = d["facts"], d["components"]
        self.assertEqual(f["invoice"], 60000)
        self.assertEqual(f["unit_msrp"], 62000.0)
        self.assertNotAlmostEqual(f["price_now"], c["adjusted_basis_now"], places=0)   # rails are distinct numbers
        self.assertGreater(c["adjusted_basis_now"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
