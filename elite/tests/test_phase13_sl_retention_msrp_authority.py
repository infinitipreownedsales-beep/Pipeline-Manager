"""Service-Loaner retention MSRP AUTHORITY (live acceptance 2026-08-28).

The retention denominator (original MSRP) for a USED resale must come from authoritative NEW-lifecycle evidence,
NEVER the used row's own MSRP field, and NEVER a blank/special pseudo-code. Order of authority:
  1. exact-VIN historical NEW original MSRP (stamped `_orig_msrp` by the identity bridge);
  2. else historical NEW-sale MSRP median for the SAME REAL model code + SAME model year;
  3. else the governed inventory (model_code, model_year) MSRP median;
  4. else drop.
_is_real_code() gates both building and consuming the historical NEW MSRP map, so a 'BLANK'/'TRUCK' pseudo-code
can never create an anchor or a retention observation. Windows (±2/3/4/6) and RESALE_WINDOW_GATE=5 are unchanged.
"""
import unittest

from elite.loaner.sl_decision import _retention_observations, _retention_at

# the 5 real governed QX60 model codes observed live at N15159's target age
REAL_CODES = ["84310", "84615", "84816", "84413", "84113"]


def _used(code, age, price, *, my=2027, orig_msrp=None):
    t = my * 12 + age
    y, m = t // 12, t % 12 + 1
    r = {"model": "QX60", "model_number": code, "year": str(my), "sold_date": f"{y:04d}-{m:02d}-15",
         "price": float(price), "_sale_kind": "USED"}
    if orig_msrp is not None:
        r["_orig_msrp"] = float(orig_msrp)
    return r


def _newsale(code, msrp, *, my=2027):
    return {"model": "QX60", "model_number": code, "year": str(my), "sold_date": f"{my}-01-05",
            "price": float(msrp) - 1000, "msrp": str(msrp), "_sale_kind": "NEW"}


class TestRetentionMsrpAuthority(unittest.TestCase):
    def test_blank_special_codes_never_create_anchor_or_observation(self):
        rows = [
            _newsale("BLANK", 90000),                              # NEW row with a pseudo-code -> NO anchor
            _used("84615", 3, 58000),                             # real code but NO authoritative MSRP anywhere -> drop
            {"model": "QX60", "model_number": "TRUCK", "year": "2025", "sold_date": "2025-06-15",
             "price": 58000.0, "_orig_msrp": 62000.0, "_sale_kind": "USED"},   # pseudo-code -> never an obs
        ]
        self.assertEqual(_retention_observations(rows, {}, {}, "QX60"), [])

    def test_five_real_obs_clear_pm6_gate_via_authoritative_new_msrp(self):
        ages = [0, 1, 2, 6, 8]                                    # matches the live shape (±2 n=3 … ±6 n=5)
        rows = [_newsale("84310", 70000)]                        # authority (2): NEW-sale MSRP for 84310 / MY2027
        for i, (code, age) in enumerate(zip(REAL_CODES, ages)):
            # first obs (84310) has NO _orig_msrp -> resolves via authority (2); the rest via (1) exact-VIN MSRP
            rows.append(_used(code, age, 60000 - 300 * age, orig_msrp=(None if i == 0 else 70000)))
        obs = _retention_observations(rows, {}, {}, "QX60")
        self.assertEqual(len(obs), 5)                             # all 5 real-code obs built (blank/special excluded)
        self.assertTrue(all(0 < r < 1 for _am, r, _c in obs))    # real used retention, never forced to 1.0
        ret, w, n, _tier, conf = _retention_at(obs, 2, "84617")  # want-code absent -> broader same-model tier
        self.assertEqual(n, 5)                                    # clears the EXISTING gate (5) …
        self.assertEqual(w, 6)                                    # … at the EXISTING ±6 window (unchanged)
        self.assertIsNotNone(ret)
        self.assertNotEqual(conf, "none")

    def test_authority_order_prefers_exact_vin_then_newsale_then_inventory(self):
        # (1) exact-VIN _orig_msrp wins
        o1 = _retention_observations([_used("84615", 2, 60000, orig_msrp=62000)], {}, {}, "QX60")
        self.assertAlmostEqual(o1[0][1], 60000 / 62000, places=4)
        # (2) no _orig_msrp -> historical NEW-sale (real code, MY) median
        o2 = _retention_observations([_newsale("84615", 61000), _used("84615", 2, 60000)], {}, {}, "QX60")
        self.assertAlmostEqual(o2[0][1], 60000 / 61000, places=4)
        # (3) neither -> governed inventory (code, MY) anchor
        o3 = _retention_observations([_used("84615", 2, 60000)], {("84615", 2027): 63000.0}, {}, "QX60")
        self.assertAlmostEqual(o3[0][1], 60000 / 63000, places=4)
        # (4) none -> drop
        self.assertEqual(_retention_observations([_used("84615", 2, 60000)], {}, {}, "QX60"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
