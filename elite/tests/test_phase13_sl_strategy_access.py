"""Service Loaner Strategy / Proof access boundary (Elite closeout 2026-09-01).

The three-layer information architecture is packet-locked:

  * Execution (/service-loaner) — the manager ACTION board. No economics: no profit/gross, ICV$, Velocity$,
    basis, write-down, recon, or economic proof on the manager surface.
  * Strategy & Proof (/service-loaner/strategy, /service-loaner/unit/{id}) — Kyle / GSM decision + economic
    analysis and the technical proof/lineage behind each call.

Strategy is reachable ONLY by a principal holding store-operating authority — the governed definition reused
verbatim (PILOT_OPERATOR_ANCHORS: authority.grant / decision.approve / execution.authorize). A view-only
operator is DENIED at the route (a real 403, not merely unlinked) and sees no Strategy link on the execution
board. Both layers consume the SAME decision engines — Strategy is depth, never a second recomputed rail.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
import elite.tests.test_phase12_loaner_intelligence as INTEL

# Restricted economics that must NEVER reach the manager execution surface. Each phrase is economics-specific
# (it does not collide with the global shell's "ICV / Service Loaner" source-health label or CSS "flex-basis").
RESTRICTED_ON_EXECUTION = (
    "Economic placement ranking", "Recommended action per unit", "write-down", "adjusted basis",
    "Adjusted basis", "total-dealership net", "ICV earned", "Front-end gross", "Velocity (contingent)",
)


class TestStrategyAccessBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.authorized = self.p.login(self.p.op_full)       # holds decision.approve -> operating authority
        self.viewonly = self.p.login(self.p.op_readonly)     # workspace.view / workspace.review only

    def tearDown(self):
        self.p.close()

    def test_authorized_operator_reaches_strategy_and_sees_the_link(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            board = self.authorized.get("/service-loaner")
            strat = self.authorized.get("/service-loaner/strategy")
        self.assertEqual(board.status, 200)
        self.assertIn("/service-loaner/strategy", board.body)       # a normal navigable path, never a secret URL
        self.assertEqual(strat.status, 200)
        self.assertIn("Strategy &amp; Proof", strat.body)           # the deeper decision + economic layer
        self.assertIn("Recommended action per unit", strat.body)    # per-unit KEEP/PULL/SWAP depth

    def test_view_only_operator_is_denied_strategy_and_sees_no_link(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            board = self.viewonly.get("/service-loaner")
            strat = self.viewonly.get("/service-loaner/strategy")
            unit = self.viewonly.get("/service-loaner/unit/slu_x")
        self.assertEqual(board.status, 200)                          # the execution board itself stays available
        self.assertNotIn("/service-loaner/strategy", board.body)     # …but the Strategy path is not offered
        self.assertEqual(strat.status, 403)                          # denied at the route, not merely unlinked
        self.assertEqual(unit.status, 403)                           # per-unit Proof (economics) is denied too

    def test_authorized_operator_passes_the_unit_auth_gate(self):
        # the authority gate runs BEFORE the unit lookup, so an authorized operator hitting an unknown unit
        # gets an honest 404 (auth passed) — proving 403 for the view-only user is authorization, not a 404.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            unit = self.authorized.get("/service-loaner/unit/nonexistent")
        self.assertEqual(unit.status, 404)

    def test_execution_board_carries_no_restricted_economics(self):
        # the manager execution surface (as a view-only operator would see it) exposes NONE of the restricted
        # financial detail — the economics live only behind the Strategy authority gate.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            b = self.viewonly.get("/service-loaner").body
        for term in RESTRICTED_ON_EXECUTION:
            self.assertNotIn(term, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
