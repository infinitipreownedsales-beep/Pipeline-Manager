"""Phase-4 economic readiness — honest reporting of which authoritative inputs exist and which are still
missing, and the removal of the stale 'coverage incomplete' warning once coverage is actually complete. No
economics are computed or fabricated here."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.loaner.economics_readiness import assess_gates, ready, missing, Gate
from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


class TestGates(unittest.TestCase):
    def _all_but(self, **over):
        base = dict(icv_complete=True, velocity_complete=True, used_evidence_defensible=True,
                    writedown_present=True)
        base.update(over)
        return assess_gates(**base)

    def test_all_present_is_ready(self):
        self.assertTrue(ready(self._all_but()))
        self.assertEqual(missing(self._all_but()), [])

    def test_missing_writedown_blocks(self):
        # the realistic live state: ICV + Velocity + used evidence present, write-down policy absent
        gates = self._all_but(writedown_present=False)
        self.assertFalse(ready(gates))
        miss = {g.key for g in missing(gates)}
        self.assertEqual(miss, {"writedown"})

    def test_missing_inputs_are_flagged_not_zeroed(self):
        # a missing input is reported as an explicit gap, never silently treated as present/zero
        gates = self._all_but(writedown_present=False)
        wd = next(g for g in gates if g.key == "writedown")
        self.assertFalse(wd.present)
        self.assertIn("no governed write-down", wd.detail)

    def test_incomplete_coverage_blocks_too(self):
        self.assertFalse(ready(self._all_but(icv_complete=False)))


class TestStaleWarningRemoved(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_complete_coverage_shows_real_gates_not_stale_incomplete(self):
        complete_but_policy_missing = [
            Gate("icv", "Effective-dated ICV coverage", True, "ICV coverage complete"),
            Gate("velocity", "Effective-dated Velocity terms", True, "Velocity coverage complete"),
            Gate("used_evidence", "Dealership used-market evidence (resale / post-loaner DTS)", True, "defensible"),
            Gate("writedown", "Governed write-down policy ($ or % of ICV)", False, "no governed write-down policy input exists yet"),
        ]
        with patch("elite.loaner.economics_readiness.phase4_gates", return_value=complete_but_policy_missing):
            b = self.full.get("/program-inputs").body
        # the stale static claim is gone
        self.assertNotIn("Phase-4 economics are not authoritative while required historical program coverage "
                         "is incomplete", b)
        # replaced by an honest conditional line: coverage complete, and the REAL remaining gates named
        self.assertIn("Program coverage complete.", b)
        self.assertIn("Governed write-down policy", b)

    def test_ready_allows_engine_to_proceed_message(self):
        all_present = [Gate(k, k, True, "have") for k in ("icv", "velocity", "used_evidence", "writedown")]
        with patch("elite.loaner.economics_readiness.phase4_gates", return_value=all_present):
            b = self.full.get("/program-inputs").body
        self.assertIn("economic placement ranking can proceed", b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
