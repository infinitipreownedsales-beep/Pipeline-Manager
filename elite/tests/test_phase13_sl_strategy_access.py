"""Service Loaner Strategy / Proof access boundary (Elite closeout 2026-09-01).

The three-layer information architecture is packet-locked:

  * Execution (/service-loaner) — the manager ACTION board. No economics: no profit/gross, ICV$, Velocity$,
    basis, write-down, recon, or economic proof on the manager surface.
  * Strategy & Proof (/service-loaner/strategy, /service-loaner/unit/{id}) — Kyle / GSM decision + economic
    analysis and the technical proof/lineage behind each call.

Strategy is a DECISION-AUTHORITY layer, not an execution one. Access is gated on the narrowest existing
capabilities that mean decision authority — authority.grant (Kyle's live GSM/admin principal) or
decision.approve. It deliberately EXCLUDES execution.authorize: the ability to EXECUTE a decision is not
permission to INSPECT restricted dealership economics. So an ordinary execution manager (execution.authorize
alone), a view-only user, an operator with no capabilities, and an unauthenticated request are all denied at
the route (not merely unlinked). Both layers consume the SAME decision engines — Strategy is depth, never a
second recomputed rail.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10, Client
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
        # decision authority -> Strategy permitted
        self.op_full = self.p.login(self.p.op_full)          # holds decision.approve (+ authority.grant)
        self.op_approver = self.p.login(self.p.op_approver)  # holds decision.approve only
        # not decision authority -> Strategy denied
        self.op_executor = self.p.login(self.p.op_executor)  # holds execution.authorize only
        self.op_readonly = self.p.login(self.p.op_readonly)  # workspace.view / workspace.review only
        self.op_unauth = self.p.login(self.p.op_unauth)      # no capabilities
        self.anon = Client(self.p.app, None)                 # no session at all

    def tearDown(self):
        self.p.close()

    def test_decision_authority_reaches_strategy_and_sees_the_link(self):
        # authority.grant and/or decision.approve -> Strategy permitted (op_full, op_approver)
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            for who in (self.op_full, self.op_approver):
                board = who.get("/service-loaner")
                strat = who.get("/service-loaner/strategy")
                self.assertEqual(board.status, 200)
                self.assertIn("/service-loaner/strategy", board.body)   # a normal navigable path, never a secret URL
                self.assertEqual(strat.status, 200)
                self.assertIn("Strategy &amp; Proof", strat.body)       # the deeper decision + economic layer
                self.assertIn("Recommended action per unit", strat.body)  # per-unit KEEP/PULL/SWAP depth

    def test_execution_or_view_only_authority_is_denied_and_unlinked(self):
        # execution.authorize alone -> denied; workspace.view / review alone -> denied. Executing a decision is
        # NOT permission to inspect restricted economics.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            for who in (self.op_executor, self.op_readonly):
                board = who.get("/service-loaner")
                self.assertEqual(board.status, 200)                        # the execution board stays available
                self.assertNotIn("/service-loaner/strategy", board.body)   # …but the Strategy path is not offered
                self.assertEqual(who.get("/service-loaner/strategy").status, 403)   # denied at the route
                self.assertEqual(who.get("/service-loaner/unit/slu_x").status, 403)  # per-unit Proof denied too

    def test_unauthenticated_or_capabilityless_is_denied(self):
        # an operator with no capabilities, and a request with no session at all, never reach Strategy.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            self.assertEqual(self.op_unauth.get("/service-loaner/strategy").status, 403)
            self.assertNotEqual(self.anon.get("/service-loaner/strategy").status, 200)  # login redirect / denied

    def test_decision_authority_passes_the_unit_auth_gate(self):
        # the authority gate runs BEFORE the unit lookup, so an authorized operator hitting an unknown unit
        # gets an honest 404 (auth passed) — proving the 403 for the others is authorization, not a 404.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            self.assertEqual(self.op_full.get("/service-loaner/unit/nonexistent").status, 404)

    def test_execution_board_carries_no_restricted_economics(self):
        # the manager execution surface (as a view-only operator would see it) exposes NONE of the restricted
        # financial detail — the economics live only behind the Strategy decision-authority gate.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            b = self.op_readonly.get("/service-loaner").body
        for term in RESTRICTED_ON_EXECUTION:
            self.assertNotIn(term, b)

    def test_strategy_shows_both_fleet_decisions_and_placement_ranking(self):
        # presentation contract: the Strategy page visibly carries BOTH the Fleet decisions section and the
        # Placement ranking section (the placement ranking is always present — its heading renders even when no
        # inventory snapshot is loaded, so Kyle is never left without it).
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            b = self.op_full.get("/service-loaner/strategy").body
        self.assertIn("Recommended action per unit", b)      # Fleet decisions
        self.assertIn("Placement ranking", b)                # Placement ranking

    def test_strategy_fleet_decisions_are_compact_not_a_wide_table(self):
        # the per-unit decisions render as compact rows with the economics folded into an expandable
        # "Economics / Proof", NOT the old ten-column table that clipped the Why/Proof column.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            b = self.op_full.get("/service-loaner/strategy").body
        flat = b.replace(" ", "")
        self.assertIn("Economics/Proof", flat)               # economics folded into an expandable disclosure
        for wide_header in ("<th>Adj.basis</th>", "<th>Frontgross</th>", "<th>Releaseby</th>", "<th>Conf.</th>"):
            self.assertNotIn(wide_header, flat)              # the wide clipping table is gone


if __name__ == "__main__":
    unittest.main(verbosity=2)
