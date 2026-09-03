"""Demos: separate 'is replacement due now?' (Decision A) from 'what should replace it?' (Decision B).

Decision A uses the demo policy (miles first — ~2,000 mi swap point; ~90-day cadence as guidance) and is HONEST
about missing evidence: with no current odometer reading it never pretends the demo is due. Decision B (the next
ideal demo) is shown independently. The two live side by side ("KEEP CURRENT DEMO FOR NOW" while "Next ideal
demo: ...").
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.ui.views.operator import _demo_replacement_due, DEMO_SWAP_MILES


class TestDecisionA(unittest.TestCase):
    def test_no_current_mileage_is_not_due(self):
        d = _demo_replacement_due({"vin": "V1", "start": "2026-05-01", "mi_in": 50}, "2026-08-26")
        self.assertEqual(d["state"], "unknown_mileage")            # never pretends due without a reading
        self.assertIn("Current odometer", d["detail"])

    def test_below_odometer_threshold_keeps(self):
        d = _demo_replacement_due({"vin": "V1", "start": "2026-08-01", "mi_in": 50, "mi_now": 900}, "2026-08-26")
        self.assertEqual(d["state"], "keep")
        self.assertEqual(d["odometer"], 900)                      # threshold is on the odometer, not accumulated

    def test_threshold_is_current_odometer_not_miles_since_assignment(self):
        # assigned at 500, current odometer 2,100: accumulated is only 1,600 but the ODOMETER is past ~2,000 ->
        # DUE. Assignment mileage must never raise the swap bar.
        d = _demo_replacement_due({"vin": "V1", "start": "2026-05-01", "mi_in": 500, "mi_now": 2100}, "2026-08-26")
        self.assertEqual(d["state"], "due")
        self.assertEqual(d["odometer"], 2100)

    def test_approaching_window_still_keeps_but_flagged(self):
        # assigned 500, current 1,950 -> below 2,000 (keep) but in the 1,xxx approaching window, not "1,450 in"
        d = _demo_replacement_due({"vin": "V1", "start": "2026-06-01", "mi_in": 500, "mi_now": 1950}, "2026-08-26")
        self.assertEqual(d["state"], "keep")
        self.assertIn("approaching", d["detail"])

    def test_no_demo(self):
        self.assertEqual(_demo_replacement_due({}, "2026-08-26")["state"], "no_demo")


class TestDemosRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)
        self.full.post("/demos/user", {"name": "Nathan", "role": "Sales", "model_pref": "QX60"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        self.uid = roster[0]["id"]
        # fixture clock is 2026-01-02; assign ~93 days earlier so the cadence window is reached
        self.full.post(f"/demos/user/{self.uid}/assign", {"vin": "5N1AL1HU1TC344699", "start": "2025-10-01", "mi": "40"})

    def tearDown(self):
        self.p.close()

    def test_decisions_are_separate_and_honest(self):
        b = self.full.get(f"/demos/user/{self.uid}").body
        self.assertIn("Decision A — Operating call", b)            # new operating vocabulary
        self.assertIn("Decision B — Next ideal demo", b)
        # ~93 days in service with no fresh odometer -> PLAN SWAP (never a dead-end), odometer required for swap
        self.assertIn("PLAN SWAP", b)
        self.assertNotIn("NEED CURRENT MILEAGE", b)
        self.assertIn("odometer is required before final swap", b)
        # a low current odometer keeps it operational; Decision B still shows independently
        self.full.post(f"/demos/user/{self.uid}/mileage", {"mi": "900"})
        b2 = self.full.get(f"/demos/user/{self.uid}").body
        self.assertTrue("PLAN SWAP" in b2 or "KEEP" in b2)
        self.assertIn("Decision B — Next ideal demo", b2)
        # a high ACTUAL odometer authorizes SWAP NOW
        self.full.post(f"/demos/user/{self.uid}/mileage", {"mi": str(DEMO_SWAP_MILES + 100)})
        b3 = self.full.get(f"/demos/user/{self.uid}").body
        self.assertIn("SWAP NOW", b3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
