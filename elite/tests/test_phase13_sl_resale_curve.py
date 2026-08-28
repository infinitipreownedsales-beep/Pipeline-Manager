"""Market/value rail: observed transaction price primary, MSRP retention secondary (live acceptance 2026-08-27).

The preferred market rail is OBSERVED TRANSACTION PRICE -> later observed transaction price: the store's own
recorded used SELLING dollars (the Reynolds 'Vehicle Price') for the SAME governed comparable (model code / trim)
at the sale's lifecycle age. Because it is trim-specific it already differentiates units, with NO MSRP involved.
MSRP-normalized retention is used ONLY as a secondary fallback, when same-comparable transaction evidence is
insufficient — then a broader same-model cohort's retention is re-scaled by THIS unit's own authoritative MSRP.

Proven here:
  * two same-model units of DIFFERENT trims (model codes) get DIFFERENT expected prices directly from observed
    transaction dollars — no MSRP normalization needed in the primary path;
  * the observed-dollar curve is time-sensitive on a continuous age-in-months axis (30/60/90/120 later differ);
  * MSRP is not required for the primary path (a unit with no MSRP still prices from observed transaction dollars
    for its trim); MSRP retention engages only as the fallback and cites itself as such;
  * the market rail stays independent of the dealer-basis rail (invoice -> write-down -> adjusted basis);
  * empty history, unresolved model year, age beyond the observed window, and no defensible evidence at all GATE
    honestly — nothing is manufactured.
"""
import os
import datetime as dt
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_decision import (build_unit_decision, _market_price, _unit_inventory_facts,
                                      _age_months_at)
from elite.loaner.intelligence import UnitIntel
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore

VIN = "5N1AL1HU8TC348756"          # last-8 TC348756 joins to the inventory Serial
VIN_B = "5N1AL1HU8TDD990000"       # a SECOND physical QX60, a different trim/model code

# Two QX60 trims: 84616 (loaded, higher MSRP + higher observed transaction prices) and 84617 (base, lower).
_MSRP = {"84616": {2024: 58000, 2025: 60000, 2026: 62000},
         "84617": {2024: 50000, 2025: 52000, 2026: 54000}}
# The observed used SELLING price level each trim actually transacts at when new-ish (before age decline).
_PRICE0 = {"84616": 60000, "84617": 50000}


def _inv(active=(("TC348756", "S1", "84616", "2026", 62000),
                 ("DD990000", "S2", "84617", "2026", 54000))):
    """Inventory/pipeline rows: the authoritative physical-unit MSRP + model-code source. Carries the two active
    units (matched by Serial last-8) plus per-(code, MY) MSRP anchors used ONLY for the retention fallback."""
    rows = [{"vin": None, "serial": s, "stock_number": st, "model": "QX60",
             "model_code": c, "model_year": my, "msrp": str(ms)} for (s, st, c, my, ms) in active]
    for code, by_my in _MSRP.items():
        for my, ms in by_my.items():
            rows.append({"vin": None, "serial": "ANCHOR", "stock_number": "ANCHOR", "model": "QX60",
                         "model_code": code, "model_year": str(my), "msrp": str(ms)})
    return rows


def _rows(slope=400, codes=("84616", "84617"), ages=range(3, 16), per=5):
    """Real-shaped resale ledger: each row is an observed used SALE carrying its governed model_number (trim
    code), model year and 'Vehicle Price' (the used selling price), declining with lifecycle age. Each trim
    transacts at its own dollar level, so the observed-price curves differ by trim without any MSRP."""
    out = []
    for code in codes:
        for my in (2024, 2025, 2026):
            p0 = _PRICE0[code] + (my - 2026) * 2000
            for a in ages:
                t = my * 12 + a
                y, m = t // 12, t % 12 + 1
                for k in range(per):
                    out.append({"model": "QX60", "model_number": code, "year": str(my),
                                "sold_date": f"{y:04d}-{m:02d}-15",
                                "price": str(p0 - slope * a + (k - 2) * 100), "days_to_sell": "40"})
    return out


def _unit(vin=VIN):
    return UnitIntel(id="u1", vin=vin, model="QX60", in_service_date="2026-02-10", age_days=180, mileage=8000,
                     mileage_available=True, membership_state="ACTIVE_AVAILABLE", rental_state=None,
                     quality_flags=(), model_year="2026")


class TestObservedTransactionRailPrimary(unittest.TestCase):
    def test_two_trims_priced_from_observed_dollars_no_msrp(self):
        # THE ACCEPTANCE PROOF: two MY2026 QX60s of different trims, same sale date and lifecycle age. They get
        # DIFFERENT expected prices directly from observed transaction dollars — the primary path uses NO MSRP.
        rows, inv = _rows(), _inv()
        msrp_a, code_a = _unit_inventory_facts(inv, VIN)      # 84616
        msrp_b, code_b = _unit_inventory_facts(inv, VIN_B)    # 84617
        self.assertEqual(code_a, "84616")
        self.assertEqual(code_b, "84617")
        sd = "2026-08-15"
        pa, prov_a, _ca = _market_price(rows, inv, "QX60", "2026", sd, msrp_a, code_a)
        pb, _pb, _cb = _market_price(rows, inv, "QX60", "2026", sd, msrp_b, code_b)
        self.assertIsNotNone(pa)
        self.assertIsNotNone(pb)
        self.assertNotEqual(pa, pb)                            # different trims -> different observed prices
        self.assertGreater(pa, pb)                             # the higher-transacting trim is worth more
        self.assertIn("observed used transaction price", prov_a)   # PRIMARY rail cites observed dollars
        self.assertIn("same model code 84616", prov_a)
        self.assertNotIn("MSRP", prov_a)                       # NO MSRP normalization in the primary path

    def test_msrp_not_required_for_primary(self):
        # a unit with NO resolvable MSRP still prices from observed transaction dollars for its trim
        rows, inv = _rows(), _inv()
        price, prov, _c = _market_price(rows, inv, "QX60", "2026", "2026-08-15", None, "84616")
        self.assertIsNotNone(price)
        self.assertIn("observed used transaction price", prov)

    def test_five_points_time_sensitive_and_cited(self):
        rows, inv = _rows(), _inv()
        base = dt.date(2026, 8, 26)
        pts = []
        for days in (0, 30, 60, 90, 120):
            sd = (base + dt.timedelta(days=days)).isoformat()
            price, prov, conf = _market_price(rows, inv, "QX60", "2026", sd, 62000.0, "84616")
            self.assertIsNotNone(price, days)
            self.assertIn("observed used transaction price", prov)
            self.assertNotEqual(conf, "none")
            pts.append(price)
        self.assertGreater(len(set(pts)), 1)                                        # not merely repeated
        self.assertTrue(all(pts[i] >= pts[i + 1] for i in range(len(pts) - 1)))     # declines with the curve
        self.assertLess(pts[-1], pts[0])

    def test_same_integer_age_different_months_differ(self):
        rows, inv = _rows(), _inv()
        p_aug = _market_price(rows, inv, "QX60", "2026", "2026-08-15", 62000.0, "84616")[0]   # int age 0
        p_dec = _market_price(rows, inv, "QX60", "2026", "2026-12-15", 62000.0, "84616")[0]   # int age 0 too
        self.assertEqual(_age_months_at("2026", "2026-08-15"), 7)
        self.assertEqual(_age_months_at("2026", "2026-12-15"), 11)
        self.assertNotEqual(p_aug, p_dec)


class TestMsrpRetentionFallback(unittest.TestCase):
    # The unit is code 84616 (config 8481). A DIFFERENT QX60 family — 84516 (config 8451) — is the only one that
    # traded, so NEITHER primary tier (exact 84616, nor the year-agnostic 8481 config) matches. Only then does
    # the secondary MSRP-retention rail engage: broader same-model retention re-scaled by THIS unit's own MSRP.
    # (84516 -> 8451 and 84616 -> 8481 are distinct governed families, so the year-agnostic tier does not merge
    # them — that is exactly why the fallback is reached.)
    def _diff_family_rows(self):
        rows = []
        for my in (2024, 2025, 2026):
            msrp = {2024: 50000, 2025: 52000, 2026: 54000}[my]
            for a in range(3, 16):
                t = my * 12 + a
                y, m = t // 12, t % 12 + 1
                for k in range(5):
                    rows.append({"model": "QX60", "model_number": "84516", "year": str(my),
                                 "sold_date": f"{y:04d}-{m:02d}-15", "price": str(50000 - 400 * a + (k - 2) * 100),
                                 "msrp": str(msrp), "days_to_sell": "40"})
        return rows

    def test_fallback_used_only_when_same_trim_transaction_evidence_insufficient(self):
        # the current unit's own config has NO transaction history -> secondary rail: broader same-model retention
        # (MSRP-normalized) re-scaled by THIS unit's own authoritative MSRP. Cites itself as the fallback.
        price, prov, _c = _market_price(self._diff_family_rows(), _inv(), "QX60", "2026", "2026-08-15",
                                        62000.0, "84616")
        self.assertIsNotNone(price)
        self.assertIn("observed retention", prov)
        self.assertIn("MSRP-normalized fallback", prov)
        self.assertIn("this unit's authoritative MSRP $62,000", prov)

    def test_fallback_scales_with_each_units_own_msrp(self):
        # in the fallback, the retention PERCENT is shared but each unit's price applies ITS OWN MSRP, so the two
        # prices scale with their MSRPs and are NOT equal.
        rows = self._diff_family_rows()
        pa = _market_price(rows, _inv(), "QX60", "2026", "2026-08-15", 62000.0, "84616")
        pb = _market_price(rows, _inv(), "QX60", "2026", "2026-08-15", 54000.0, "84616")
        self.assertIn("MSRP-normalized fallback", pa[1])
        self.assertNotEqual(pa[0], pb[0])
        self.assertAlmostEqual(pa[0] / pb[0], 62000.0 / 54000.0, places=4)
        self.assertAlmostEqual(pa[0] / 62000.0, pb[0] / 54000.0, places=6)         # shared retention %

    def test_gates_without_manufacturing(self):
        rows, inv = _rows(), _inv()
        # no observed transaction dollars for the trim AND no MSRP -> gate (nothing to normalize)
        self.assertIsNone(_market_price(rows, inv, "QX60", "2026", "2026-08-26", None, "99999")[0])
        self.assertIsNone(_market_price([], inv, "QX60", "2026", "2026-08-26", 62000.0, "84616")[0])   # no history
        self.assertIsNone(_market_price(rows, inv, "QX60", "", "2026-08-26", 62000.0, "84616")[0])     # MY gate
        self.assertIsNone(_market_price(rows, inv, "QX60", "2026", "2031-08-26", 62000.0, "84616")[0]) # age gate


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

    def test_price_is_observed_transaction_dollars(self):
        d = self._decide(400)
        self.assertEqual(d["facts"]["unit_model_code"], "84616")
        self.assertIn("observed used transaction price", d["facts"]["price_now_basis"])

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

    def test_basis_rail_independent_of_market_rail(self):
        d = self._decide(400)
        f, c = d["facts"], d["components"]
        self.assertEqual(f["invoice"], 60000)                                    # basis rail = invoice + write-down
        self.assertNotAlmostEqual(f["price_now"], c["adjusted_basis_now"], places=0)
        self.assertGreater(c["adjusted_basis_now"], 0)


class TestYearAgnosticCodeTier(unittest.TestCase):
    """Live root cause: DMS 5-digit model codes embed MODEL YEAR in the 5th digit (normalize_code('QX60',
    '84616') -> '8461'-> governed '8481'; '84614' -> same). A CURRENT-model-year unit's exact 5-digit code can
    never be carried by its OLDER used comparables, so the exact-code-only match gated every unit. The governed
    year-agnostic (4-digit) config tier resolves it against its own configuration's older-model-year used sales
    at the same lifecycle age — without widening the window, lowering the gate, or touching MSRP."""

    def _real_history(self, per=6, ages=range(10, 22)):
        # Real-shaped: the SAME QX60 configuration across model years carries DIFFERENT 5-digit codes (5th digit
        # = MY): 2024 -> 84614, 2025 -> 84615. A 2026 unit is code 84616 — absent from all historical rows.
        out = []
        for my, code in ((2024, "84614"), (2025, "84615")):
            for a in ages:
                t = my * 12 + a
                y, m = t // 12, t % 12 + 1
                for k in range(per):
                    out.append({"model": "QX60", "model_number": code, "year": str(my),
                                "sold_date": f"{y:04d}-{m:02d}-15", "price": str(48000 - 250 * a + (k - 3) * 120),
                                "days_to_sell": "45"})
        return out

    def test_current_my_unit_prices_off_year_agnostic_config_evidence(self):
        rows = self._real_history()
        # unit is a 2026 QX60, exact code 84616 — NO historical row carries 84616 (they are 84614 / 84615)
        price, prov, conf = _market_price(rows, [], "QX60", "2026", "2027-03-15", 62000.0, "84616")
        self.assertIsNotNone(price)                                   # no longer gated
        self.assertIn("observed used transaction price", prov)        # still the PRIMARY transaction rail
        self.assertIn("year-agnostic config code", prov)              # resolved via the governed 4-digit tier
        self.assertNotIn("MSRP", prov)                                # NOT the MSRP retention fallback
        self.assertNotEqual(conf, "none")

    def test_exact_code_tier_still_preferred_when_present(self):
        # add same-year exact-code (84616) evidence: the exact tier must win and cite the exact code, unchanged
        rows = self._real_history()
        for a in range(10, 22):
            t = 2026 * 12 + a
            y, m = t // 12, t % 12 + 1
            for k in range(6):
                rows.append({"model": "QX60", "model_number": "84616", "year": "2026",
                             "sold_date": f"{y:04d}-{m:02d}-15", "price": str(70000 - 250 * a + (k - 3) * 120),
                             "days_to_sell": "45"})
        price, prov, _c = _market_price(rows, [], "QX60", "2026", "2027-03-15", 62000.0, "84616")
        self.assertIn("same model code 84616", prov)                  # exact tier preferred -> trim/MY specificity
        self.assertGreater(price, 50000)                              # priced off the higher exact-code cohort

    def test_no_config_evidence_still_gates(self):
        # a genuinely different configuration (different 4-digit family) with no evidence must still GATE
        rows = self._real_history()
        price, prov, conf = _market_price(rows, [], "QX60", "2026", "2027-03-15", 62000.0, "84990")
        self.assertIsNone(price)                                      # no exact and no year-agnostic match -> gate
        self.assertEqual(conf, "none")


if __name__ == "__main__":
    unittest.main(verbosity=2)
