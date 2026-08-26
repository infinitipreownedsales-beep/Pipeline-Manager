"""Current-generation QX80 (86xxx) model recognition (live unblock 2026-08-26).

QX80 spans two code generations: the prior 83xxx and the CURRENT 86xxx. `_PREFIX_TO_MODEL` recognized 83 but
not 86, so every current QX80 planning identity was model=∅ (untruthful) — its human label and CHANGE-target
grouping were broken. The fix recognizes 86 as the QX80 model LINE only; the raw/current codes stay DISTINCT
(8611/8621/8631/8661 vs 8331/8381) and current 86-gen demand is NEVER merged into historical 83-gen demand
(that would remain a governed lineage decision, never this prefix map).

Proves: (1) 86xxx recognized as QX80; (2) current codes stay distinct — no silent 83 collapse; (3) end-to-end,
a current QX80 86xxx order with a certified position now evaluates with a TRUTHFUL QX80 identity (was ∅);
(4) an 86xxx order whose exact combination has no certified position stays an honest CANT_EVALUATE — the fix
recognizes the model, it never fabricates a supply/demand position.
"""
import os
import tempfile
import unittest

from elite.newinv.dms_identity import model_from_code, normalize_code, code4, dms_planning_key
from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.intake import content_hash
from elite.newinv import board_recompute as BR
from elite.ui.views import operator as OP
from elite.workflow import ctp_intake as CTP
from elite.tests.test_phase12_real_demand_planning_bridge import sts_workbook, _row
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS

# the real current QX80 codes from the live CTP file
CURRENT = [("86117", "QBE", "P", "QX80 PURE 2WD"), ("86217", "GAT", "G", "QX80 LUXE 4WD"),
           ("86317", "QBE", "G", "QX80 LUXE 2WD"), ("86617", "XKJ", "K", "QX80 AUTOGRAPH 4WD")]


class TestQx80PrefixPure(unittest.TestCase):
    def test_86_recognized_as_qx80(self):
        for code, _e, _i, _m in CURRENT:
            self.assertEqual(model_from_code(code), "QX80", code)

    def test_current_codes_stay_distinct_no_83_collapse(self):
        # each current 86xxx keeps its truthful 4-digit planning code — never folded into 83-gen 8331/8381
        self.assertEqual([normalize_code("QX80", c) for c, *_ in CURRENT], ["8611", "8621", "8631", "8661"])
        for code, *_ in CURRENT:
            self.assertNotIn(normalize_code("QX80", code), ("8331", "8381"))
        # 83-generation identities are unchanged by the fix
        self.assertEqual(normalize_code("QX80", "83316"), "8331")
        self.assertEqual(normalize_code("QX80", "8381"), "8381")
        # a current 86-gen planning key never equals a historical 83-gen key
        cur = dms_planning_key({"model_code": "86117", "exterior": "QBE", "interior": "P"})
        old = dms_planning_key({"model_code": "83316", "exterior": "QBE", "interior": "P"})
        self.assertNotEqual(cur, old)
        self.assertEqual(cur, ("QX80", "8611", "QBE", "P"))          # truthful current identity


class TestQx80EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _pipe(self, rows):
        return make_xlsx([PIPE_HEADERS] + rows, sheet_name="vehicleInventorySummary0")

    def _q80(self, stock, serial, dis, code, ext, inte, loc, pm=""):
        return [stock, serial, "", "2026", "QX80", code, "QX80", "AUTO", ext, inte, "78900", "74000", loc, dis, "", pm]

    def test_current_qx80_order_evaluable_with_truthful_identity(self):
        # current QX80 demand + supply for the exact combination -> certified position -> evaluable as QX80
        drows = [_row(f"2026{m:02d}", f"N{m}", "25", "86117", "QBE", "P", "QX80 PURE 2WD") for m in range(1, 6)]
        x = sts_workbook(drows)
        self.p.import_payload("speed_to_sell", x, chash=content_hash(x))
        xp = self._pipe([self._q80("S1", "900001", 10, "86117", "QBE", "P", "DLR-INV"),
                         self._q80("", "TK79127", 0, "86117", "QBE", "P", "ONS", "2026-11")])
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:q80",
                              effective_time=self.p.now_iso())
        self.assertTrue(BR.recompute_board(self.p.app, SCOPE)["ok"])
        board = OP._ctp_board(self.p.app, SCOPE)
        self.assertTrue(board, "current QX80 combo must join the certified board")
        self.assertTrue(all(v["model"] == "QX80" for v in board.values()))   # truthful — was '∅'
        pipeline = OP._ctp_pipeline_rows(self.p.app, SCOPE)
        cand = CTP.to_candidate({"order": "TK79127", "model": "QX80", "arrival": "2026-11", "model_code": "86117"})
        out = CTP.evaluate(CTP.reconcile([cand], pipeline), board, now="2026-08")[0]
        self.assertIn(out.decision_state, (CTP.KEEP, CTP.CHANGE))             # a real decision, not NEEDS ATTENTION
        self.assertNotEqual(out.decision_state, CTP.CANT_EVALUATE)

    def test_no_current_demand_stays_honest_cant_evaluate(self):
        # supply for current 86117 but demand only for old-gen 83316 -> the exact current combo has no certified
        # position. The fix recognizes the model but must NOT fabricate a position: honest CANT_EVALUATE.
        drows = [_row(f"2026{m:02d}", f"N{m}", "25", "83316", "QBE", "P", "QX80 LUXE") for m in range(1, 4)]
        x = sts_workbook(drows)
        self.p.import_payload("speed_to_sell", x, chash=content_hash(x))
        xp = self._pipe([self._q80("", "TK79127", 0, "86117", "QBE", "P", "ONS", "2026-11")])
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:q80b",
                              effective_time=self.p.now_iso())
        BR.recompute_board(self.p.app, SCOPE)
        board = OP._ctp_board(self.p.app, SCOPE)
        pipeline = OP._ctp_pipeline_rows(self.p.app, SCOPE)
        cand = CTP.to_candidate({"order": "TK79127", "model": "QX80", "arrival": "2026-11", "model_code": "86117"})
        out = CTP.evaluate(CTP.reconcile([cand], pipeline), board, now="2026-08")[0]
        self.assertEqual(out.decision_state, CTP.CANT_EVALUATE)               # genuine evidence gap, not forced
        # and the current 86-gen combo was NOT merged into the historical 83-gen demand cohort
        self.assertTrue(all("8611" not in v["canonical"] or v["model"] == "QX80" for v in board.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
