"""Governed recon is decision-material — a higher governed reconditioning assumption changes ADD candidate
economics and membership, consumed by the ONE shared placement rail (rank_add_candidates), while leaving
unrelated (other-model) fleet decisions untouched.

Recon is now a governed Program Input (ProgramInputsStore kind "recon"), effective-dated per model — no silent
constant in placement logic. When no governed recon is recorded the engine uses the explicit governed default
band (so current live behavior is unchanged); when a governed recon is recorded it overrides, per model, and
recomputes economics consistently on every surface.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_add import rank_add_candidates
from elite.loaner.sl_decision import build_unit_decision
from elite.loaner.placement import EXCESS
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore
import elite.tests.test_phase13_sl_add as ADD
import elite.tests.test_phase12_sl_decision as DEC


def _priced_qx80(price=57000):
    out = []
    for a in range(10, 22):
        t = 2026 * 12 + a
        y, m = t // 12, t % 12 + 1
        for k in range(6):
            out.append({"model": ADD.MODEL, "model_number": ADD.CODE, "year": "2026",
                        "sold_date": f"{y:04d}-{m:02d}-15", "price": str(price + (k - 3) * 100), "days_to_sell": "45"})
    return out


class TestGovernedReconSensitivity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_protection_buffer_days(15, actor="k", at="t")
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        # QX80 ADD-candidate program terms
        pis.add("icv", effective_month="2026-01", model="QX80", model_year="2026", value=6000, actor="k", recorded_at="t")
        pis.add("velocity", effective_month="2026-01", model="QX80", model_year="2026", value=2000,
                day_cap=240, mile_cap=10000, actor="k", recorded_at="t")
        # An UNRELATED QX60 service-loaner fleet unit with full economics (different model from the recon change)
        pol.set_invoice(DEC.VIN, 60000, actor="k", at="t")
        pis.add("icv", effective_month="2026-02", model="QX60", model_year="2026", value=6500, actor="k", recorded_at="t")
        pis.add("velocity", effective_month="2026-02", model="QX60", model_year="2026", value=2500,
                day_cap=240, mile_cap=10000, actor="k", recorded_at="t")
        self.pol, self.pis = pol, pis
        self.rows = [ADD._unit("ROBUST", "ROBUST", invoice="52000"),   # clearly positive net
                     ADD._unit("MARGIN", "MARGIN", invoice="68000")]   # marginal positive net
        self.harm = ADD._harm({(ADD.CODE, "QBE", "G"): EXCESS})

    def tearDown(self):
        self.p.close()

    def _add_ranking(self):
        with patch("elite.loaner.sl_add.read_new_retail_units", return_value=self.rows), \
             patch("elite.loaner.sl_add.certified_harm_index", return_value=self.harm), \
             patch("elite.loaner.sl_add._retail_rows", return_value=_priced_qx80()), \
             patch("elite.loaner.sl_add._inventory_rows", return_value=list(self.rows)):
            return rank_add_candidates(self.app, SCOPE, n=7, today=ADD.TODAY)

    def _qx60_fleet_action(self):
        with patch("elite.loaner.sl_decision._retail_rows", return_value=DEC._priced_rows()), \
             patch("elite.loaner.sl_decision._inventory_rows", return_value=DEC._inv()):
            d = build_unit_decision(self.app, SCOPE, DEC._unit(), DEC._mi(), today="2026-08-09", keep_horizon_days=60)
        return d["action"]

    def test_higher_governed_recon_removes_the_marginal_candidate(self):
        # 1) DEFAULT (no recon recorded -> governed default band): both QX80 surplus units are commandable.
        base = self._add_ranking()
        base_cmd = [c.stock for c in base["commandable"]]
        base_net = {c.stock: c.add_net for c in base["ready"]}
        self.assertEqual(set(base_cmd), {"ROBUST", "MARGIN"})
        self.assertGreater(base_net["MARGIN"], 0)              # marginal but positive at the default recon

        # 2) Record a materially higher GOVERNED recon for QX80 -> recompute the SAME rail.
        self.pis.add("recon", effective_month="2026-01", model="QX80", model_year="2026", value=5000,
                     actor="kyle", recorded_at="t")
        bumped = self._add_ranking()
        bumped_cmd = [c.stock for c in bumped["commandable"]]
        bumped_net = {c.stock: c.add_net for c in bumped["ready"]}

        self.assertEqual(bumped_cmd, ["ROBUST"])              # the marginal unit is no longer commandable
        self.assertNotIn("MARGIN", bumped_cmd)
        self.assertLess(bumped_net["MARGIN"], 0)              # its net went negative under the higher recon
        self.assertGreater(bumped_net["ROBUST"], 0)          # the robust unit still stands
        self.assertLess(bumped_net["ROBUST"], base_net["ROBUST"])   # …with economics consistently recomputed lower

    def test_recon_change_does_not_disturb_unrelated_fleet_decision(self):
        # a QX60 fleet unit's KEEP/PULL/SWAP call is decided BEFORE and AFTER the QX80 recon change — recon is
        # governed per model, so the unrelated (QX60) decision is byte-identical.
        before = self._qx60_fleet_action()
        self.pis.add("recon", effective_month="2026-01", model="QX80", model_year="2026", value=5000,
                     actor="kyle", recorded_at="t")
        after = self._qx60_fleet_action()
        self.assertEqual(before, after)
        self.assertIn(before, ("KEEP", "PULL", "SWAP", "UNRESOLVED"))


class TestReconGovernanceMechanism(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.pis = ProgramInputsStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_recon_is_a_governed_effective_dated_program_input(self):
        from elite.loaner.program_inputs import KINDS, resolve_for_unit
        self.assertIn("recon", KINDS)                          # recon is a governed program-input kind
        self.assertEqual(self.pis.entries("recon"), [])       # nothing recorded yet (no legacy migration crash)
        self.pis.add("recon", effective_month="2026-01", model="QX80", model_year="2026", value=1800,
                     actor="kyle", recorded_at="t")
        r = resolve_for_unit(self.pis, "recon", model="QX80", in_service_date="2026-03-10", model_year="2026")
        self.assertEqual(r["status"], "resolved")
        self.assertEqual(r["entry"].value, 1800)

    def test_recon_default_band_used_and_labelled_when_ungoverned(self):
        from elite.loaner.sl_decision import _recon_assumption
        d = _recon_assumption("QX80")                         # no governed value, no override
        self.assertEqual(d["expected"], 1500.0)               # explicit governed default band (QX80)
        self.assertIn("default band", d["source"])            # labelled — never a silent constant
        g = _recon_assumption("QX80", governed_expected=2400) # governed value overrides
        self.assertEqual(g["expected"], 2400)
        self.assertIn("governed Program Input", g["source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
