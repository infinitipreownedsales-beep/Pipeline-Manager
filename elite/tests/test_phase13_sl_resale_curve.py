"""Time-sensitive expected used-price curve (live acceptance 2026-08-26).

The future used price is now a function of the actual SALE DATE, on a continuous age-in-months-from-model-year
axis pooled across model years (a real depreciation-by-age curve from the store's own resales). Two sales in the
same integer model-year-age bucket but different months get different, empirically-observed prices — so KEEP can
no longer look superior merely because write-down lowers basis while a flat resale price stays constant. No
invented rate, no static all-MY median, no oldest cohort; gates when the observed history can't support the age.
"""
import os
import datetime as dt
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_decision import build_unit_decision, _time_resale_price, _age_months_at
from elite.loaner.intelligence import UnitIntel
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore

VIN = "5N1AL1HU8TC348756"


def _rows(slope=400, model="QX60", ages=range(3, 16), per=5):
    """Real-shaped resale history: price declines by `slope`/month of lifecycle age, pooled across model years."""
    out = []
    for my in (2024, 2025, 2026):
        for a in ages:
            t = my * 12 + a
            y, m = t // 12, t % 12 + 1
            for k in range(per):
                out.append({"model": model, "year": str(my), "sold_date": f"{y:04d}-{m:02d}-15",
                            "price": str(52000 - slope * a + (k - 2) * 100), "days_to_sell": "40"})
    return out


def _unit():
    return UnitIntel(id="u1", vin=VIN, model="QX60", in_service_date="2026-02-10", age_days=180, mileage=8000,
                     mileage_available=True, membership_state="ACTIVE_AVAILABLE", rental_state=None,
                     quality_flags=(), model_year="2026")


class TestCurvePure(unittest.TestCase):
    def test_five_points_time_sensitive_and_cited(self):
        rows = _rows()
        base = dt.date(2026, 8, 26)                              # a real-shaped MY2026 QX60
        pts = []
        for days in (0, 30, 60, 90, 120):
            sd = (base + dt.timedelta(days=days)).isoformat()
            price, prov, conf = _time_resale_price(rows, "QX60", "2026", sd)
            self.assertIsNotNone(price, days)
            self.assertIn("observed resale median", prov)        # cites the actual observed evidence
            self.assertIn("real sales", prov)
            self.assertNotEqual(conf, "none")
            pts.append(price)
        # all five dates are integer model-year age 0 (calendar 2026) yet the prices are NOT merely repeated
        self.assertGreater(len(set(pts)), 1)
        self.assertTrue(all(pts[i] >= pts[i + 1] for i in range(len(pts) - 1)))   # declines with the (declining) data
        self.assertLess(pts[-1], pts[0])

    def test_pooled_across_model_years_supports_future_age(self):
        # only PRIOR model-year resales exist; the current MY has not aged that far yet -> still priced from history
        rows = [{"model": "QX60", "year": "2024", "sold_date": f"2024-{m:02d}-15", "price": "45000"}
                for m in (9, 10, 11, 12) for _ in range(3)]
        price, prov, _c = _time_resale_price(rows, "QX60", "2026", "2026-11-15")   # age ~10mo
        self.assertIsNotNone(price)
        self.assertIn("real sales", prov)

    def test_gates_when_history_cannot_support_age(self):
        self.assertIsNone(_time_resale_price([], "QX60", "2026", "2026-08-26")[0])          # no history
        self.assertIsNone(_time_resale_price(_rows(), "QX60", "2026", "2031-08-26")[0])     # age far beyond data
        self.assertIsNone(_time_resale_price(_rows(), "QX60", "", "2026-08-26")[0])         # MY unresolved -> gate

    def test_same_integer_age_different_months_differ(self):
        rows = _rows()
        p_aug = _time_resale_price(rows, "QX60", "2026", "2026-08-15")[0]   # integer age 0
        p_dec = _time_resale_price(rows, "QX60", "2026", "2026-12-15")[0]   # integer age 0 too
        self.assertEqual(_age_months_at("2026", "2026-08-15"), 7)
        self.assertEqual(_age_months_at("2026", "2026-12-15"), 11)
        self.assertNotEqual(p_aug, p_dec)


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
        with patch("elite.loaner.sl_decision._retail_rows", return_value=_rows(slope=slope)):
            return build_unit_decision(self.app, SCOPE, _unit(), None, today="2026-08-26", keep_horizon_days=90)

    def test_hold_benefit_is_market_plus_basis_not_basis_alone(self):
        d = self._decide(400)
        c, f = d["components"], d["facts"]
        self.assertLess(f["price_future"], f["price_now"])                       # market value declines over the hold
        self.assertLess(c["adjusted_basis_future"], c["adjusted_basis_now"])     # basis also falls (write-down)
        # front-end gross = price − adjusted basis (recon 0); the hold delta decomposes into BOTH terms
        self.assertAlmostEqual(c["front_end_gross_future"], f["price_future"] - c["adjusted_basis_future"], places=0)
        hold_delta = c["front_end_gross_future"] - c["front_end_gross_now"]
        market_change = f["price_future"] - f["price_now"]
        basis_gain = c["adjusted_basis_now"] - c["adjusted_basis_future"]
        self.assertAlmostEqual(hold_delta, market_change + basis_gain, places=0)
        self.assertLess(market_change, 0)                                        # market is a real, non-zero input

    def test_steeper_market_decline_lowers_future_gross(self):
        # basis-reduction alone would be identical across curves; a steeper market decline must reduce future gross
        shallow = self._decide(300)
        steep = self._decide(1500)
        self.assertEqual(shallow["components"]["adjusted_basis_future"],
                         steep["components"]["adjusted_basis_future"])           # basis path identical
        self.assertLess(steep["components"]["front_end_gross_future"],
                        shallow["components"]["front_end_gross_future"])          # market value moved the answer


if __name__ == "__main__":
    unittest.main(verbosity=2)
