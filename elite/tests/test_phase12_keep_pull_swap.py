"""KEEP vs PULL vs SWAP total-economic comparison — incremental-from-now (§2, §3). Proves already-earned
ICV is not re-earned by KEEP, Velocity is contingent, write-down counts exactly once, adjusted-basis
mechanics, and that KEEP is NOT automatically best. Front-end gross only — no backend/F&I."""
import unittest

from elite.loaner.keep_pull_swap import compare_actions, expected_front_end_gross
from elite.loaner.sl_policy import DAYS_PER_MONTH


def _base(**over):
    b = dict(invoice=60000, monthly_rate=1.25, tenure_days_now=90, keep_extra_days=int(3 * DAYS_PER_MONTH),
             used_price_now=52000, used_price_future=52000, recon=1000,
             velocity_contingent=2500, velocity_preserved_now=True, velocity_preserved_future=True,
             icv_earned=6500, retail_opportunity_cost=0, swap_candidate_net=None)
    b.update(over)
    return b


class TestKeepPullSwap(unittest.TestCase):
    def test_front_end_gross_uses_adjusted_basis_only(self):
        g = expected_front_end_gross(used_price=52000, adjusted_basis=57000, recon=1000)
        self.assertEqual(g, 52000 - 57000 - 1000)     # price − adjusted basis − recon; no backend term

    def test_more_writedown_lowers_basis_and_raises_gross(self):
        r = compare_actions(**_base())                # price held FIXED now vs future
        c = r["components"]
        self.assertLess(c["adjusted_basis_future"], c["adjusted_basis_now"])   # more write-down -> lower basis
        self.assertGreater(c["front_end_gross_future"], c["front_end_gross_now"])  # -> higher exit gross
        self.assertEqual(r["best"], "KEEP")           # with price flat, extra write-down favors KEEP

    def test_already_earned_icv_not_re_earned_by_keep(self):
        lo = compare_actions(**_base(icv_earned=0))
        hi = compare_actions(**_base(icv_earned=50000))
        # sunk ICV changes NEITHER action net; the KEEP-vs-PULL delta is identical
        self.assertEqual(lo["nets"], hi["nets"])
        self.assertEqual(lo["best"], hi["best"])

    def test_velocity_is_contingent_and_can_flip_action(self):
        # keeping pushes exit past the 240-day deadline, forfeiting the CONTINGENT Velocity -> PULL can win
        r = compare_actions(**_base(velocity_preserved_future=False, velocity_contingent=6000,
                                    used_price_now=52000, used_price_future=52200))
        self.assertEqual(r["components"]["velocity_future"], 0)
        self.assertEqual(r["best"], "PULL")

    def test_writedown_counts_exactly_once(self):
        # a $1 increase in FUTURE write-down (via a slightly longer keep) must move KEEP economics by ~$1, not $2.
        base = compare_actions(**_base())
        # bump future write-down by exactly $1 by extending keep by (1 / daily_writedown) days
        daily_wd = 60000 * (1.25 / 100.0) / DAYS_PER_MONTH
        more = compare_actions(**_base(keep_extra_days=int(3 * DAYS_PER_MONTH) ))
        # instead assert the mechanical identity: KEEP net == future front gross + future velocity (one WD only)
        c = base["components"]
        self.assertEqual(base["nets"]["KEEP"], round(c["front_end_gross_future"] + c["velocity_future"], 2))
        # and front gross already embeds the write-down once (price − (invoice − wd) − recon)
        self.assertEqual(c["front_end_gross_future"],
                         round(_base()["used_price_future"] - c["adjusted_basis_future"] - _base()["recon"], 2))

    def test_dollar_of_future_writedown_moves_economics_by_one_dollar(self):
        b = _base(used_price_future=52000)
        r0 = compare_actions(**b)
        # raise the rate so future cumulative write-down increases by exactly $1, holding tenure fixed
        wd0 = r0["components"]["cumulative_write_down_future"]
        # find a rate delta giving +$1 future WD: wd = invoice*(rate/100/DPM)*days ; d_wd/d_rate linear
        days = b["tenure_days_now"] + b["keep_extra_days"]
        per_rate = b["invoice"] * (1 / 100.0 / DAYS_PER_MONTH) * days
        r1 = compare_actions(**{**b, "monthly_rate": 1.25 + 1.0 / per_rate})
        self.assertAlmostEqual(r1["components"]["cumulative_write_down_future"], wd0 + 1, places=2)
        self.assertAlmostEqual(r1["nets"]["KEEP"], r0["nets"]["KEEP"] + 1, places=2)  # exactly $1, not $2

    def test_market_depreciation_can_overwhelm_and_pull_wins(self):
        r = compare_actions(**_base(used_price_now=52000, used_price_future=45000))
        self.assertEqual(r["best"], "PULL")

    def test_superior_swap_beats_keep(self):
        r = compare_actions(**_base(swap_candidate_net=9000))
        self.assertEqual(r["best"], "SWAP")
        self.assertEqual(r["nets"]["SWAP"], round(r["nets"]["PULL"] + 9000, 2))

    def test_missing_invoice_gates_actions(self):
        r = compare_actions(**_base(invoice=None))
        self.assertIn("invoice", r["missing"])
        self.assertEqual(r["nets"], {})
        self.assertIsNone(r["best"])

    def test_no_backend_term_anywhere(self):
        r = compare_actions(**_base())
        keys = " ".join(r["components"].keys()).lower()
        for backend in ("reserve", "warranty", "gap", "f&i", "backend", "finance", "product"):
            self.assertNotIn(backend, keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
