"""Service Loaner cockpit read model + UI surface — three fleet counts never conflated, governed desired
fleet + monthly placement requirement persist, and the mix is honestly UNDETERMINED (no fabrication) until
real per-unit economics are loaded."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.loaner_cockpit import MetaPrefs, build_cockpit, set_desired_fleet
from elite.loaner import placement_settings as PS
from elite.loaner.ideal_mix import UnitEcon
from elite.loaner.preowned_evidence import ModelEvidence, PreownedEvidence, summarize_model_sales


class TestLoanerCockpit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _month(self):
        from elite.clock import to_utc_iso
        return to_utc_iso(self.p.clock.now())[:7]

    # counts are distinct; with no economics loaded the mix is UNDETERMINED, not fabricated
    def test_counts_and_undetermined_mix(self):
        ck = build_cockpit(self.conn, SCOPE, self.p.app.prefs, self._month())
        self.assertIsInstance(ck.current_fleet, int)
        self.assertIsNone(ck.desired_fleet)                 # not set yet
        self.assertFalse(ck.economically_determined)        # no per-unit economics -> honest
        self.assertIsNone(ck.ideal_fleet)
        self.assertIn("undetermined", ck.note().lower())

    # desired fleet is a governed, store-scoped setting that persists
    def test_desired_fleet_persists(self):
        meta = MetaPrefs(self.p.app.prefs, SCOPE)
        set_desired_fleet(meta, 22)
        ck = build_cockpit(self.conn, SCOPE, self.p.app.prefs, self._month())
        self.assertEqual(ck.desired_fleet, 22)

    # a monthly placement requirement resolves for its month only, and drives the optimizer when economics exist
    def test_requirement_and_economic_mix(self):
        month = self._month()
        PS.set_requirement(MetaPrefs(self.p.app.prefs, SCOPE), effective_month=month, required=3, reason="OEM push")
        held = [UnitEcon(id=f"h{i}", keep_value=200 - i, exit_value=0.0) for i in range(2)]
        cands = [UnitEcon(id="x1", in_value=500), UnitEcon(id="x2", in_value=450), UnitEcon(id="weak", in_value=-40)]
        ck = build_cockpit(self.conn, SCOPE, self.p.app.prefs, month, held=held, candidates=cands)
        self.assertTrue(ck.economically_determined)
        self.assertIsNotNone(ck.requirement)
        self.assertEqual(ck.requirement["required"], 3)
        self.assertEqual(len(ck.mix.by_action("IN")), 3)    # requirement met
        self.assertTrue(any(d["objective_driven"] for d in ck.mix.by_action("IN")))  # weak one is objective-driven
        # next month has no requirement (temporary, not inherited)
        nxt = "2027-01"
        ck2 = build_cockpit(self.conn, SCOPE, self.p.app.prefs, nxt, held=held, candidates=cands)
        self.assertIsNone(ck2.requirement)

    # the V8 manager execution board renders and surfaces the operating fleet position, without crashing
    def test_service_loaner_page_renders(self):
        # C (V8 contract): the pre-V8 "Program state / Current fleet / Ideal (Pending Economics)" page was
        # replaced by the V8 manager execution board. The surviving invariant is that the board renders and
        # surfaces the operating fleet position (target = the governed desired fleet) without crashing.
        set_desired_fleet(MetaPrefs(self.p.app.prefs, SCOPE), 20)
        r = self.full.get("/service-loaner")
        self.assertEqual(r.status, 200)
        self.assertIn("Service Loaner Command Board", r.body)
        self.assertIn("Fleet position", r.body)
        self.assertIn("Target", r.body)
        self.assertIn("20", r.body)                          # governed desired fleet surfaced as the target

    def test_preowned_evidence_summarizes_dts_without_inventing_economics(self):
        rows = [
            {"model": "QX60", "days_to_sell": 28},
            {"model": "QX60", "days_to_sell": 34},
            {"model": "QX60", "days_to_sell": 70},
            {"model": "QX80", "days_to_sell": 15},
        ]
        ev = summarize_model_sales(rows, {"QX60": 7})
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0].model, "QX60")
        self.assertEqual(ev[0].active_units, 7)
        self.assertEqual(ev[0].sales_count, 3)
        self.assertEqual(ev[0].numeric_dts_count, 3)
        self.assertEqual(ev[0].median_dts, 34.0)

    def test_service_loaner_page_keeps_ideal_undetermined(self):
        # A (engine invariant preserved): the cockpit never fabricates an economic mix. C (surface): the pre-V8
        # "Undetermined / Pending Economics" page copy was retired with that page; the V8 execution board simply
        # never renders a fabricated economic ideal on the manager surface.
        r = self.full.get("/service-loaner")
        self.assertEqual(r.status, 200)
        self.assertNotIn("Ideal Mix", r.body)                # no fabricated economic ideal on the execution board
        ck = build_cockpit(self.conn, SCOPE, self.p.app.prefs, self._month())
        self.assertFalse(ck.economically_determined)
        self.assertIsNone(ck.ideal_fleet)

    # setting desired fleet through the governed POST persists across a reload
    def test_set_desired_fleet_post(self):
        r = self.full.post("/service-loaner/desired-fleet", {"desired": "18"})
        self.assertEqual(r.status, 303)
        ck = build_cockpit(self.conn, SCOPE, self.p.app.prefs, self._month())
        self.assertEqual(ck.desired_fleet, 18)


if __name__ == "__main__":
    unittest.main(verbosity=2)
