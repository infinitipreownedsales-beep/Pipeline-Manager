"""Service-Loaner USED-market rail excludes NEW sales (live acceptance 2026-08-28).

The combined Reynolds Retail History carries BOTH new and used deliveries. A NEW sale transacts at ~MSRP, and —
because lifecycle age is anchored to Jan 1 of the model year — a prior-model-year unit sold NEW early the next
year lands at ~13-15 months lifecycle age. Those NEW rows contaminated the ~14mo cohort and fabricated ~100%
retention (N15126REED: MSRP $116,715 -> expected used $116,715, 100.0% retention, n=62).

Fix: the USED-market pricing cohorts (_price_observations and _retention_observations — the raw material for
exact-code, raw-code4, market-lineage-predecessor and MSRP-retention pricing) now exclude rows flagged NEW.
NEW rows remain fully usable for VIN/model-code/MSRP IDENTITY (the bridge index). No gate/window/pricing-formula
change. A row with no New/Used indicator (legacy used-only export) is treated as USED.
"""
import unittest

from elite.loaner.sl_decision import _price_observations, _retention_observations, _market_price
from elite.loaner.preowned_evidence import _sale_kind

CODE = "86616"          # QX80, code4 8661
MSRP = 116715.0


def _row(price, kind, *, year, sold, code=CODE, model="QX80", msrp=MSRP):
    return {"model": model, "model_number": code, "year": str(year), "sold_date": sold,
            "price": float(price), "msrp": str(msrp), "_sale_kind": kind}


def _used(n=6):
    # USED QX80s at ~14mo lifecycle age (2023 model sold 2024-03), transacting BELOW MSRP
    return [_row(90000 + k * 200, "USED", year=2023, sold="2024-03-15") for k in range(n)]


def _new(n=6):
    # NEW QX80s that ALSO land at ~14mo age (2024 model sold new 2025-03), transacting AT MSRP -> 100% retention
    return [_row(MSRP, "NEW", year=2024, sold="2025-03-15") for _ in range(n)]


class TestNewUsedSplit(unittest.TestCase):
    def test_sale_kind_detection(self):
        self.assertEqual(_sale_kind({"New/Used": "New"}), "NEW")
        self.assertEqual(_sale_kind({"New/Used": "Used"}), "USED")
        self.assertEqual(_sale_kind({"New/Used": "N"}), "NEW")
        self.assertEqual(_sale_kind({"New/Used": "U"}), "USED")
        self.assertEqual(_sale_kind({"Sale Type": "Pre-Owned"}), "USED")
        self.assertEqual(_sale_kind({"New/Used": "N/A"}), "")       # ambiguous/absent -> not NEW
        self.assertEqual(_sale_kind({"model": "QX80"}), "")         # no indicator -> '' (treated as USED)

    def test_new_rows_excluded_from_price_observations(self):
        rows = _used() + _new()
        obs = _price_observations(rows, "QX80")
        self.assertEqual(len(obs), 6)                                # only the 6 USED rows
        self.assertTrue(all(p < MSRP for _am, p, _c in obs))         # no MSRP-priced NEW rows leaked in

    def test_new_rows_excluded_from_retention(self):
        rows = _used() + _new()
        ret = _retention_observations(rows, {}, {}, "QX80")
        self.assertEqual(len(ret), 6)                                # only USED
        self.assertTrue(all(r < 1.0 for _am, r, _c in ret))         # never the 100% NEW retention

    def test_market_price_prices_below_msrp_after_excluding_new(self):
        # target ~14mo age (2026 model, sale 2027-03); USED median ~ $90k, NOT the $116,715 MSRP contamination
        price, prov, conf = _market_price(_used() + _new(), [], "QX80", "2026", "2027-03-15", MSRP, CODE)
        self.assertIsNotNone(price)
        self.assertLess(price, MSRP)                                 # the fix: below MSRP, not 100% retention
        self.assertLess(price, 95000)
        self.assertNotEqual(conf, "none")

    def test_only_new_rows_gate_not_price_at_msrp(self):
        # if the ONLY evidence at the age is NEW sales, the used rail must GATE (never price a loaner at MSRP)
        price, _prov, conf = _market_price(_new(), [], "QX80", "2026", "2027-03-15", MSRP, CODE)
        self.assertIsNone(price)
        self.assertEqual(conf, "none")

    def test_untagged_rows_still_used(self):
        # legacy used-only export with NO New/Used indicator must still price (backward compatible)
        rows = [{"model": "QX80", "model_number": CODE, "year": "2023", "sold_date": "2024-03-15",
                 "price": 90000.0, "msrp": str(MSRP)} for _ in range(6)]
        self.assertEqual(len(_price_observations(rows, "QX80")), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
