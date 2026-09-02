"""Service Loaner Command Board — Best Available Placement Candidates (Slice 1).

The placement shortlist is explicitly NON-economic: it ranks real physical New-Retail units by currently
certified evidence (retail coverage/harm + aging), identifies each unit fully (Stock/VIN/Year/Model/Trim/
colours/state), protects short-coverage units, and never invents economics. Ideal stays Undetermined and
RETIRE/HOLD stays Pending Economics."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.loaner.placement import (best_available_placement, certified_harm_index, _to_candidate,
                                     EXCESS, COVERED, SHORTAGE, UNKNOWN)
import elite.tests.test_phase12_loaner_intelligence as INTEL


def _vin(tag):
    """A deterministic authoritative-shaped 17-char VIN for a short tag."""
    return ("5N1AZ" + "".join(ch for ch in tag if ch.isalnum())).ljust(17, "0")[:17]


def _unit(stock, tag, model_code, ext, inte, *, dis=10, status="Deal Open", loc="DLR-INV", year="2026",
          model="QX80", trim="LUXE 2WD", serial=None, no_vin=False):
    row = {"stock_number": stock, "model_code": model_code, "exterior": ext, "interior": inte,
           "dis": dis, "status": status, "location": loc, "year": year, "model": model, "trim": trim}
    if no_vin:
        row["serial"] = serial or ("T" + "".join(ch for ch in tag if ch.isalnum()))   # serial only, no VIN
    else:
        row["vin"] = _vin(tag)
    return row


class TestPlacementEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _harm(self, mapping):
        # patch the certified harm index to a controlled state keyed by dms_planning identity
        from elite.newinv.dms_identity import dms_planning_identity
        idx = {}
        for (code, ext, inte), state in mapping.items():
            ident = dms_planning_identity({"model_code": code, "exterior": ext, "interior": inte})
            idx[ident] = {"state": state, "excess": 2 if state == EXCESS else 0,
                          "acquire": 2 if state == SHORTAGE else 0}
        return idx

    def _run(self, rows, harm, n, loaner_vins=frozenset()):
        with patch("elite.loaner.placement.read_new_retail_units", return_value=rows), \
             patch("elite.loaner.placement.certified_harm_index", return_value=harm):
            return best_available_placement(self.p.app, self.conn, SCOPE, n=n, loaner_vins=loaner_vins)

    def test_over_stocked_ranked_first_short_protected(self):
        rows = [_unit("A1", "A1", "8331", "QBE", "G", dis=10),   # EXCESS
                _unit("B2", "B2", "8481", "GAT", "D", dis=90),   # SHORTAGE -> protected
                _unit("C3", "C3", "8361", "XKD", "A", dis=40)]   # COVERED
        harm = self._harm({("8331", "QBE", "G"): EXCESS, ("8481", "GAT", "D"): SHORTAGE,
                           ("8361", "XKD", "A"): COVERED})
        res = self._run(rows, harm, n=3)
        codes = [c.stock for c in res["candidates"]]
        self.assertEqual(codes[0], "A1")                 # over-stocked first
        self.assertNotIn("B2", codes)                    # short combination is protected, never offered
        self.assertEqual(res["protected"], 1)
        self.assertTrue(all(c.new_retail_state in (EXCESS, COVERED) for c in res["candidates"]))

    def test_candidate_identity_is_complete(self):
        rows = [_unit("Q26043", "Q26043", "8331", "QBE", "G", year="2026", model="QX80", trim="LUXE 2WD")]
        res = self._run(rows, self._harm({("8331", "QBE", "G"): EXCESS}), n=1)
        c = res["candidates"][0]
        for field in (c.stock, c.vin, c.year, c.model, c.exterior, c.interior):
            self.assertTrue(field)                        # VIN/Stock/Year/Model/colours all present
        self.assertTrue(c.vin_authoritative)
        self.assertEqual((c.stock, len(c.vin), c.year, c.model), ("Q26043", 17, "2026", "QX80"))

    # 1D: a serial-only row (no VIN, serial_lifecycle) never presents the serial as a VIN
    def test_serial_is_not_promoted_to_vin(self):
        rows = [_unit("N15111", "TC348756", "8331", "QBE", "G", no_vin=True, serial="TC348756")]
        c = self._run(rows, self._harm({("8331", "QBE", "G"): EXCESS}), n=1)["candidates"][0]
        self.assertEqual(c.vin, "")                        # no fabricated VIN
        self.assertFalse(c.vin_authoritative)
        self.assertEqual(c.serial, "TC348756")             # serial preserved as serial, not a VIN

    def test_aging_breaks_ties_within_same_state(self):
        rows = [_unit("NEW", "NEW", "8331", "QBE", "G", dis=5),
                _unit("OLD", "OLD", "8331", "QBE", "C", dis=120)]
        res = self._run(rows, self._harm({("8331", "QBE", "G"): EXCESS, ("8331", "QBE", "C"): EXCESS}), n=2)
        self.assertEqual([c.stock for c in res["candidates"]], ["OLD", "NEW"])   # oldest-aging first

    def test_next_best_and_n_limit(self):
        rows = [_unit(f"S{i}", f"S{i}", "8331", "QBE", "G", dis=100 - i) for i in range(6)]
        res = self._run(rows, self._harm({("8331", "QBE", "G"): COVERED}), n=2)
        self.assertEqual(len(res["candidates"]), 2)
        self.assertEqual(len(res["next_best"]), 3)        # 2-3 next-best alternatives

    def test_excludes_existing_loaners_and_off_lot(self):
        rows = [_unit("ON", "ON", "8331", "QBE", "G", loc="DLR-INV"),
                _unit("INC", "INC", "8331", "QBE", "G", loc="ONS"),        # incoming, not on lot
                _unit("SOLD", "SOLD", "8331", "QBE", "G", status="Sold"),   # leaving retail
                _unit("LOAN", "LOAN", "8331", "QBE", "G")]                  # already a loaner
        res = self._run(rows, self._harm({("8331", "QBE", "G"): EXCESS}), n=5,
                        loaner_vins=frozenset({_vin("LOAN")}))               # committed by AUTHORITATIVE VIN
        got = {c.stock for c in res["candidates"]}
        self.assertEqual(got, {"ON"})                     # only the eligible on-lot, non-loaner, unsold unit

    def test_unresolved_coverage_flagged_not_invented(self):
        rows = [_unit("U1", "U1", "8331", "QBE", "G")]
        res = self._run(rows, {}, n=1)                    # no certified plan for the combo
        self.assertEqual(res["unresolved"], 1)
        self.assertEqual(res["candidates"], [])           # unresolved coverage is not offered as "safe"

    def test_no_inventory_snapshot_is_honest(self):
        res = self._run([], {}, n=3)
        self.assertFalse(res["loaded"])
        self.assertEqual(res["candidates"], [])           # nothing fabricated


class TestCommandBoardPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_command_board_sections_and_boundary(self):
        # A (execution invariant preserved) + C (surface): the pre-V8 "Program state / What needs me / Current
        # fleet / Ideal (Pending Economics)" sections were retired with the V8 manager execution board. The
        # surviving invariant is the economics boundary — no fabricated economic call reaches the execution board.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            b = self.full.get("/service-loaner").body
        self.assertIn("Service Loaner Command Board", b)
        for banned in ("RETIRE NOW", "release-by", "ICV $", "Economic Ideal"):
            self.assertNotIn(banned, b)

    def test_placement_candidates_card_retired_on_v8_contract(self):
        # C (obsolete surface): the pre-V8 "Lowest Retail-harm placement candidates" card (fed by
        # best_available_placement) is retired. In the accepted V8 architecture the manager execution board
        # carries the placement action ("Service Loaner - Manager Action" / "NEXT PLACEMENT - IF NEEDED"),
        # identifying each candidate by Stock#/Vehicle — it has no VIN column, so a raw serial can never
        # masquerade as a VIN (the 1D data-integrity rule is preserved by construction). The ranked economic
        # placement is Strategy depth; the placement ENGINE stays covered by TestPlacementEngine above and by
        # test_phase12_sl_optimizer.
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            b = self.full.get("/service-loaner", add="1").body
        self.assertIn("Service Loaner - Manager Action", b)              # V8 execution placement surface
        self.assertNotIn("Lowest Retail-harm placement candidates", b)   # the retired pre-V8 card is gone
        self.assertNotIn("Best available placement candidates", b)       # and its overclaimed predecessor

    def test_certified_unchanged(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=INTEL._fake_intel()):
            self.full.get("/service-loaner")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
