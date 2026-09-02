"""One placement-ranking rail — Execution and Strategy must render the SAME governed ADD candidate set and order.

Live production at 61b3714 exposed two rails: the accepted execution board ranked the governed ADD contingency
338432 → 335189 → 334278 → 337625 → 342413, while /service-loaner/strategy independently optimized a DIFFERENT
list (Q26029, N15106BODY, N15126REED, …) via optimize_sl_placement. This contract locks the invariant — both
surfaces consume _governed_add_ranking (rank_add_candidates), so the candidate IDs and their order are identical
from the same state. Strategy explains the shared candidates; it never re-ranks or re-selects them.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.loaner_cockpit import MetaPrefs, set_desired_fleet
from elite.loaner.sl_add import AddCandidate

# The accepted live ranking (ordered by descending total-dealership net).
EXPECTED = ["338432", "335189", "334278", "337625", "342413"]
# The old second-rail (optimize_sl_placement) answer that must NOT appear as the Strategy contingency ranking.
FORBIDDEN = ["Q26029", "N15106BODY", "N15126REED"]


def _ac(stock, trim, net):
    """A fully-populated governed ADD candidate (settled economics); identity preserved verbatim."""
    return AddCandidate(
        stock=stock, vin=("JN1AZ2CS0" + stock).ljust(17, "0")[:17], vin_authoritative=True, serial="",
        year="2027", model="QX60", model_code="84616", trim=trim, drivetrain="AWD",
        exterior="XKJ", interior="G", msrp=58900.0, inventory_age_days=40, new_retail_state="EXCESS",
        invoice=52000, write_down=1200, adjusted_basis=50800.0, expected_used_price=48000.0,
        price_basis="observed used transaction price (same model code 84616)", front_end_gross=2500.0,
        icv=6500.0, velocity=2500.0, velocity_preserved=True, retail_opportunity_cost=0.0, add_net=net,
        hold_days=180, release_by="2027-02-10", expected_sell_days=40.0,
        why=f"Placing this 2027 QX60 {trim} AWD nets ${net:,.0f} to the dealership.",
        retail_impact="leaves Retail coverage excess", caveat="Recon planning assumption applies.")


def _ranked_result():
    # live-shape ranked ADD result: SPORT, SPORT, AUTO, AUTO, AUTO — descending total-dealership net.
    cands = [_ac("338432", "SPORT", 5000), _ac("335189", "SPORT", 4000), _ac("334278", "AUTO", 3000),
             _ac("337625", "AUTO", 2000), _ac("342413", "AUTO", 1000)]
    return {"loaded": True, "requested": 7, "commandable": cands, "ready": list(cands),
            "all_ready": list(cands), "backups": [], "blocked": [], "protected": 0,
            "covered_deferred": 0, "unresolved_state": 0, "eligible": len(cands)}


def _order(body, ids):
    """The given ids in the order they first appear in the rendered body (row order)."""
    present = [s for s in ids if s in body]
    return sorted(present, key=lambda s: body.index(s))


class TestPlacementOneRail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), 20)   # target set so the board issues a placement
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_execution_and_strategy_render_one_ranking(self):
        # Patch the GOVERNED rail once; both surfaces read through _governed_add_ranking -> rank_add_candidates.
        with patch("elite.loaner.sl_add.rank_add_candidates", return_value=_ranked_result()):
            exec_body = self.full.get("/service-loaner").body
            strat_body = self.full.get("/service-loaner/strategy").body
        exec_order = _order(exec_body, EXPECTED)
        strat_order = _order(strat_body, EXPECTED)
        self.assertEqual(exec_order, EXPECTED)                 # live-shape governed order on the execution board
        self.assertEqual(strat_order, EXPECTED)                # …and the SAME order on Strategy
        self.assertEqual(exec_order, strat_order)              # ONE rail — identical candidate IDs and order
        for bad in FORBIDDEN:                                  # the retired second-rail answer is gone
            self.assertNotIn(bad, strat_body)

    def test_strategy_labels_contingency_not_a_directive(self):
        # ADD 0 -> the ranking is a contingency, never an instruction to place these units now.
        with patch("elite.loaner.sl_add.rank_add_candidates", return_value=_ranked_result()):
            b = self.full.get("/service-loaner/strategy").body
        self.assertIn("Contingency placement ranking", b)
        self.assertIn("if a slot is needed", b)
        self.assertIn("338432", b)                             # the shared candidates are explained here


if __name__ == "__main__":
    unittest.main(verbosity=2)
