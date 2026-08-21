"""KEEP vs PULL vs SWAP total-economic comparison (§16 resolved). Proves adjusted-basis mechanics
(write-down lowers basis, can raise exit gross) but that KEEP is NOT automatically best when market
depreciation, Velocity risk, or a superior SWAP overwhelms it. Front-end gross only — no backend/F&I."""
import unittest

from elite.loaner.keep_pull_swap import compare_actions, expected_front_end_gross
from elite.loaner.sl_policy import DAYS_PER_MONTH


def _base(**over):
    b = dict(invoice=60000, monthly_rate=1.25, tenure_days_now=90, keep_extra_days=int(3 * DAYS_PER_MONTH),
             used_price_now=52000, used_price_future=52000, recon=1000, icv=6500, velocity=2500,
             velocity_preserved_now=True, velocity_preserved_future=True, retail_opportunity_cost=0,
             swap_candidate_net=None)
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

    def test_market_depreciation_can_overwhelm_and_pull_wins(self):
        # holding longer drops the selling price faster than the basis benefit -> PULL now is better
        r = compare_actions(**_base(used_price_now=52000, used_price_future=45000))
        self.assertEqual(r["best"], "PULL")

    def test_velocity_forfeited_past_deadline_can_flip_to_pull(self):
        # keeping pushes the exit past the 240-day deadline, forfeiting Velocity -> PULL can win
        r = compare_actions(**_base(velocity_preserved_future=False, velocity=6000,
                                    used_price_now=52000, used_price_future=52200))
        self.assertEqual(r["components"]["velocity_future"], 0)
        self.assertEqual(r["best"], "PULL")

    def test_superior_swap_beats_keep(self):
        r = compare_actions(**_base(swap_candidate_net=9000))   # a strong replacement candidate
        self.assertEqual(r["best"], "SWAP")
        self.assertEqual(r["nets"]["SWAP"], round(r["nets"]["PULL"] + 9000, 2))

    def test_icv_and_velocity_counted_once(self):
        r = compare_actions(**_base())
        c = r["components"]
        # KEEP net = future gross + icv + velocity_future — each program benefit appears exactly once
        self.assertEqual(r["nets"]["KEEP"],
                         round(c["front_end_gross_future"] + c["icv"] + c["velocity_future"], 2))

    def test_missing_invoice_gates_actions(self):
        r = compare_actions(**_base(invoice=None))
        self.assertIn("invoice", r["missing"])
        self.assertEqual(r["nets"], {})               # no action is fabricated without the basis
        self.assertIsNone(r["best"])

    def test_keep_not_automatically_best_even_with_writedown_benefit(self):
        # a genuinely superior SWAP AND market depreciation both present -> KEEP is not chosen
        r = compare_actions(**_base(used_price_future=48000, swap_candidate_net=5000))
        self.assertNotEqual(r["best"], "KEEP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
