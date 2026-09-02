"""CTP governed-target eligibility + configuration-change presentation (live fix 2026-09-02).

Live CTP evaluated all five orders but surfaced non-executable CHANGE targets: a phantom `8311`/`83117` (no
governed order code) and a `KAV` exterior with no governed name. A CHANGE target is EXECUTABLE only when its
full production identity is governed — orderable model/order code, trim, drivetrain, and governed exterior AND
interior names, with no `(unmapped)` component. Such non-executable candidates are excluded from the executable
candidate universe BEFORE final ranking; the existing ranking/Need logic then reruns over the governed
remainder. A governed cross-configuration target (e.g. LUXE 4WD -> LUXE 2WD) stays eligible but is labeled
plainly as a CONFIGURATION CHANGE. No identity mapping or demand lineage is fabricated.
"""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE as OPS_SCOPE
from elite.newinv import board_recompute as BR
from elite.identity.translation import TranslationStore
from elite.identity.lineage import LineageStore
from elite.identity import seed_infiniti as SEED
from elite.ui.views import operator as OP
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS
from elite.workflow import ctp_intake as CTP
from elite.workflow.ctp_intake import Candidate, Reconciled, MATCHED, order_key


def _mk(order, cid, code, trim, dt):
    c = Candidate(order_number=order, vin="", model="QX80", model_code=code, trim=trim, drivetrain=dt)
    return Reconciled(c, MATCHED, {"combination_id": cid, "canonical": "src" + cid, "arrival_month": "2026-11"},
                      "matched by order #", "order#", {"order_match_count": 1, "vin_match_count": 0})


def _src(**kw):
    b = {"canonical": "c8621", "line": "QX80 LUXE 4WD", "colors": "White/Sepia", "model": "QX80",
         "trim": "LUXE", "drivetrain": "4WD", "excess": 1, "short": 0, "executable": True, "color_complete": True}
    b.update(kw)
    return b


def _phantom(**kw):
    # phantom 8311 / 83117 — no governed order code; strongest short so it would rank FIRST if not excluded
    b = {"canonical": "c8311", "line": "QX80 [8311 (unmapped)]", "colors": "QBE (unmapped) / C (unmapped)",
         "model": "QX80", "trim": "", "drivetrain": "", "excess": 0, "short": 9, "executable": False,
         "color_complete": True}
    b.update(kw)
    return b


def _gov_luxe2wd(**kw):
    b = {"canonical": "c8331", "line": "83317 QX80 LUXE 2WD", "colors": "Radiant White (QBE) / Graphite (G)",
         "model": "QX80", "trim": "LUXE", "drivetrain": "2WD", "excess": 0, "short": 2, "executable": True,
         "color_complete": True, "exterior_code": "QBE", "interior_code": "G"}
    b.update(kw)
    return b


class TestGovernedTargetEligibility(unittest.TestCase):
    def _evaluate(self, board, order=("TK79127", "cid_src", "86217", "LUXE", "4WD"), **kw):
        return CTP.evaluate([_mk(*order)], board, now="2026-09", **kw)[0]

    # 1 + 3: a phantom (ungoverned) target — even the top-short — is never an executable CHANGE target; exclusion
    # happens before final selection so the next-best GOVERNED candidate is reranked in.
    def test_phantom_target_excluded_and_governed_reranked(self):
        r = self._evaluate({"cid_src": _src(), "cid_phantom": _phantom(), "cid_gov": _gov_luxe2wd()})
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "cid_gov")       # the governed target, not the phantom top-short
        self.assertNotIn("8311", r.reason_plain)
        self.assertNotIn("(unmapped)", r.reason_plain)

    # 2: an ungoverned-colour (KAV) combination is likewise never executable.
    def test_ungoverned_colour_target_excluded(self):
        kav = _gov_luxe2wd(canonical="c_kav", line="83317 QX80 LUXE 2WD", colors="KAV (unmapped) / P (unmapped)",
                           executable=False, short=9)
        r = self._evaluate({"cid_src": _src(), "cid_kav": kav, "cid_gov": _gov_luxe2wd()})
        self.assertEqual(r.proposed_combination_id, "cid_gov")       # KAV excluded; governed target chosen
        self.assertNotIn("KAV", r.reason_plain)

    # 4: with only GOVERNED targets, the existing ranking/Need math is unchanged (highest governed short wins).
    def test_ranking_math_unchanged_for_governed_targets(self):
        strong = _gov_luxe2wd(canonical="c_strong", line="86417 QX80 SPORT 4WD", trim="SPORT", drivetrain="4WD",
                              short=6, exterior_code="KH3", interior_code="G")
        weak = _gov_luxe2wd(canonical="c_weak", line="86617 QX80 AUTOGRAPH 4WD", trim="AUTOGRAPH", drivetrain="4WD",
                            short=3, exterior_code="KH3", interior_code="G")
        r = self._evaluate({"cid_src": _src(), "cid_strong": strong, "cid_weak": weak})
        self.assertEqual(r.proposed_combination_id, "cid_strong")    # unchanged: the larger governed shortage wins

    # 5 + 6: a FULLY GOVERNED cross-drivetrain target stays eligible AND is labeled a configuration change.
    def test_governed_cross_drivetrain_labeled_configuration_change(self):
        r = self._evaluate({"cid_src": _src(), "cid_gov": _gov_luxe2wd()})
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "cid_gov")
        self.assertIn("CONFIGURATION CHANGE — LUXE 4WD → LUXE 2WD", r.reason_plain)
        self.assertIn("not a model-year/code translation", r.reason_plain.lower())

    # fallback: if the only superior target is ungoverned, KEEP with honest wording (never invent a target).
    def test_all_ungoverned_falls_back_to_honest_keep(self):
        r = self._evaluate({"cid_src": _src(), "cid_phantom": _phantom()})
        self.assertEqual(r.decision_state, CTP.KEEP)
        self.assertIn("no governed, orderable alternative", r.reason_plain.lower())

    # 7: Kyle's manual "not available" mark still excludes that exact combination and reranks (session behavior).
    def test_manual_not_available_still_reranks(self):
        g1 = _gov_luxe2wd(canonical="c8641", line="86417 QX80 SPORT 4WD", trim="SPORT", drivetrain="4WD", short=5,
                          exterior_code="QBE", interior_code="C")
        g2 = _gov_luxe2wd(canonical="c8661", line="86617 QX80 AUTOGRAPH 4WD", trim="AUTOGRAPH", drivetrain="4WD",
                          short=3, exterior_code="KH3", interior_code="G")
        rc = _mk("TK79127", "cid_src", "86217", "LUXE", "4WD")
        okey = order_key(rc.candidate.order_number, rc.candidate.vin)
        infeasible = {okey: [{"target": "cid_g1", "target_canonical": "c8641"}]}   # QBE/C marked unavailable
        r = CTP.evaluate([rc], {"cid_src": _src(), "cid_g1": g1, "cid_g2": g2}, now="2026-09", infeasible=infeasible)[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "cid_g2")        # reranked past the marked-unavailable target


class TestCtpBoardGovernanceFlag(unittest.TestCase):
    """PROOF (end-to-end): _ctp_board computes `executable` from real translation governance — True only when the
    full production identity is governed. No identity mapping or demand lineage is fabricated."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, OPS_SCOPE))

    def tearDown(self):
        self.p.close()

    def _q80(self, stock, serial, code, ext, inte, loc, pm=""):
        return [stock, serial, "", "2026", "QX80", code, "QX80", "AUTO", ext, inte, "78900", "74000", loc, "10", "", pm]

    def test_executable_true_for_governed_false_for_ungoverned_colour(self):
        # one fully governed build (86117 PURE 2WD, KH3 Black Obsidian / G Graphite) and one with an UNGOVERNED
        # exterior (KAV). Both are real supply -> both reach the board as supply-only positions.
        xp = make_xlsx([PIPE_HEADERS,
                        self._q80("S1", "900001", "86117", "KH3", "G", "DLR-INV"),
                        self._q80("S2", "900002", "86117", "KAV", "G", "DLR-INV")],
                       sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:g", effective_time=self.p.now_iso())
        self.assertTrue(BR.recompute_board(self.p.app, OPS_SCOPE)["ok"])
        board = OP._ctp_board(self.p.app, OPS_SCOPE)
        flags = {}
        for b in board.values():
            ext = (b.get("exterior_code") or "").upper()
            flags[ext] = b.get("executable")
        self.assertIn("KH3", flags)
        self.assertIn("KAV", flags)
        self.assertTrue(flags["KH3"])          # fully governed -> executable
        self.assertFalse(flags["KAV"])         # ungoverned exterior name -> NOT executable

    def test_no_lineage_or_new_mappings_fabricated(self):
        xp = make_xlsx([PIPE_HEADERS, self._q80("S1", "900001", "86117", "KAV", "G", "DLR-INV")],
                       sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:h", effective_time=self.p.now_iso())
        ln = LineageStore(self.p.app.prefs, OPS_SCOPE)
        before = len(ln.all())
        BR.recompute_board(self.p.app, OPS_SCOPE)
        OP._ctp_board(self.p.app, OPS_SCOPE)
        self.assertEqual(len(ln.all()), before)               # no demand lineage created by the eligibility gate
        # KAV never acquired a governed name (no fabricated mapping)
        self.assertIsNone(TranslationStore(self.p.app.prefs, OPS_SCOPE).resolve_display("exterior", "KAV", model="QX80"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
