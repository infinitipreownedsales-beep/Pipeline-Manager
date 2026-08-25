"""Live multi-file CTP intake / reconciliation / evaluation (CTP live-redesign packet).

Parser (CSV/XLSX/HTML-as-.xls, header-agnostic); strict candidate qualification (legend/footer excluded);
reconciliation by Order#/VIN with unmatched/conflict/ambiguous; a decision STATE MACHINE where any reconcile
or essential-fact gap → CAN'T EVALUATE (never a silent KEEP); KEEP/CHANGE only for matched+evaluable orders.
"""
import io
import os
import unittest
import zipfile

from elite.workflow import ctp_intake as CTP


def _fixture(name):
    with open(os.path.join(os.path.dirname(__file__), "fixtures", name), "rb") as fh:
        return fh.read()


def _mini_xlsx(header, rows):
    """Minimal valid .xlsx (inline strings, real A1 refs) — stdlib only."""
    def colname(i):
        s, i = "", i + 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    def rowxml(rn, values):
        cells = "".join(f'<c r="{colname(ci)}{rn}" t="inlineStr"><is><t>{v}</t></is></c>'
                        for ci, v in enumerate(values))
        return f'<row r="{rn}">{cells}</row>'
    sheet_rows = [rowxml(1, header)] + [rowxml(ri, r) for ri, r in enumerate(rows, start=2)]
    sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             "<sheetData>" + "".join(sheet_rows) + "</sheetData></worksheet>")
    wb = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
    ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="xml" ContentType="application/xml"/></Types>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


# ---- A. Parser -------------------------------------------------------------------------------------------
class TestParse(unittest.TestCase):
    def test_parse_csv(self):
        data = b"Order #,VIN,Model,Ext,Int,Production Month\nP100,VIN1,QX80,QBE,G,2026-11\n"
        c = CTP.to_candidate(CTP.parse_ctp_file("q.csv", data)[0])
        self.assertEqual((c.order_number, c.vin, c.model, c.exterior, c.arrival_month),
                         ("P100", "VIN1", "QX80", "QBE", "2026-11"))

    def test_parse_xlsx_still_works(self):
        rows = CTP.parse_ctp_file("q.xlsx", _mini_xlsx(["Order#", "VIN", "Model"], [["P200", "VINX", "QX65"]]))
        self.assertEqual(CTP.to_candidate(rows[0]).order_number, "P200")

    def test_candidate_requires_order_and_vehicle_identity(self):
        self.assertIsNone(CTP.to_candidate({"model": "QX80"}))              # no order#/VIN
        self.assertIsNone(CTP.to_candidate({"order": "P1"}))                # no vehicle identity
        self.assertIsNotNone(CTP.to_candidate({"order": "P1", "model": "QX80"}))

    def test_unreadable_is_empty_not_crash(self):
        self.assertEqual(CTP.parse_ctp_file("x.xlsx", b"not a zip"), [])


# ---- HTML-as-.xls (the real OEM export) + legend exclusion ------------------------------------------------
class TestOemHtmlXls(unittest.TestCase):
    def _cands(self):
        rows = CTP.parse_ctp_file("CTP (1).xls", _fixture("ctp_qx60_html.xls"))
        return rows, [c for c in (CTP.to_candidate(r, source_file="CTP (1).xls") for r in rows) if c]

    def test_html_detected_by_content_not_extension(self):
        rows, _ = self._cands()
        self.assertTrue(len(rows) >= 6 and "colortrim" in rows[0])

    def test_exactly_six_orders_footer_excluded(self):
        # the fixture includes the legend row "* C=Customer Order"; it must NOT become a candidate
        rows, cands = self._cands()
        self.assertTrue(any("=customerorder" in " ".join(r.values()).replace(" ", "").lower() for r in rows))
        self.assertEqual([c.order_number for c in cands],
                         ["TK76329", "TK76327", "TK76337", "TK76338", "TK76339", "TK76340"])

    def test_full_build_parsed(self):
        _rows, cands = self._cands()
        c0 = cands[0]
        self.assertEqual((c0.model_code, c0.model, c0.trim, c0.drivetrain), ("84317", "QX60", "LUXE", "FWD"))
        self.assertEqual((c0.exterior, c0.interior, c0.exterior_name, c0.interior_name),
                         ("KAD", "K", "Graphite Shadow", "Stone Gray"))
        self.assertEqual(c0.color_trim_raw, "KAD-K Graphite Shadow / Stone Gray")   # raw preserved
        self.assertEqual((c0.packages, c0.accessories, c0.arrival_month), ("PA1", "Cargo Package", "2026-11"))
        c3 = cands[3]
        self.assertEqual((c3.exterior, c3.interior, c3.exterior_name, c3.interior_name),
                         ("XKJ", "P", "2T Radiant White", "Saddle Brown"))


# ---- B. Reconciliation -----------------------------------------------------------------------------------
def _cand(order="", vin="", model="QX80"):
    return CTP.Candidate(order_number=order, vin=vin, model=model)


class TestReconcile(unittest.TestCase):
    def _pipe(self):
        return [{"order_number": "TK76329", "vin": "VIN1", "combination_id": "c1", "model": "QX60", "arrival_month": "2026-11"},
                {"order_number": "TK76327", "vin": "VIN2", "combination_id": "c2", "model": "QX60", "arrival_month": "2026-11"}]

    def test_exact_order_match(self):
        r = CTP.reconcile([_cand(order="TK76329")], self._pipe())[0]
        self.assertEqual((r.status, r.match_method), (CTP.MATCHED, "order#"))

    def test_exact_vin_match(self):
        r = CTP.reconcile([_cand(vin="VIN2")], self._pipe())[0]
        self.assertEqual((r.status, r.match_method), (CTP.MATCHED, "vin"))

    def test_both_keys_agree(self):
        r = CTP.reconcile([_cand(order="TK76329", vin="VIN1")], self._pipe())[0]
        self.assertEqual(r.status, CTP.MATCHED)

    def test_order_vin_conflict(self):
        r = CTP.reconcile([_cand(order="TK76329", vin="VIN2")], self._pipe())[0]
        self.assertEqual(r.status, CTP.CONFLICT)

    def test_unmatched(self):
        r = CTP.reconcile([_cand(order="TK99999")], self._pipe())[0]
        self.assertEqual(r.status, CTP.UNMATCHED)
        self.assertIn("not in the Pipeline", r.detail)

    def test_ambiguous(self):
        dup = self._pipe() + [{"order_number": "TK76329", "vin": "VINDUP", "combination_id": "c9", "model": "QX60"}]
        r = CTP.reconcile([_cand(order="TK76329")], dup)[0]
        self.assertEqual(r.status, CTP.AMBIGUOUS)

    def test_normalization_whitespace_case_apostrophe(self):
        r = CTP.reconcile([_cand(order=" 'tk76329 ")], self._pipe())[0]
        self.assertEqual(r.status, CTP.MATCHED)                              # lossless normalization only

    def test_no_fuzzy_model_color_match(self):
        r = CTP.reconcile([_cand(order="ZZZ", model="QX60")], self._pipe())[0]
        self.assertEqual(r.status, CTP.UNMATCHED)                           # model alone never matches identity


# ---- C. State machine ------------------------------------------------------------------------------------
class TestStateMachine(unittest.TestCase):
    def _board(self, excess_c1=0, short_c2=0):
        return {"c1": {"canonical": "cx1", "line": "QX80 SPORT 4WD", "colors": "Mineral Black / Graphite",
                       "model": "QX80", "excess": excess_c1, "short": 0},
                "c2": {"canonical": "cx2", "line": "QX80 LUXE 2WD", "colors": "Radiant White / Graphite",
                       "model": "QX80", "excess": 0, "short": short_c2}}

    def _matched(self, cid, order="P1", model="QX80", arrival="2026-11"):
        c = CTP.Candidate(order_number=order, model=model, arrival_month=arrival)
        return CTP.Reconciled(c, CTP.MATCHED, {"combination_id": cid, "model": model, "arrival_month": arrival},
                              "matched by order #", "order#")

    def test_unmatched_is_cant_evaluate_not_keep(self):
        rc = CTP.Reconciled(_cand(order="P9"), CTP.UNMATCHED, None, "P9 is not in the Pipeline file currently loaded")
        r = CTP.evaluate([rc], self._board())[0]
        self.assertEqual(r.decision_state, CTP.CANT_EVALUATE)
        self.assertNotEqual(r.decision_state, CTP.KEEP)
        self.assertIn("Can't evaluate", r.reason_plain)

    def test_conflict_is_cant_evaluate(self):
        rc = CTP.Reconciled(_cand(order="P9", vin="V"), CTP.CONFLICT, None, "disagree on the VIN")
        self.assertEqual(CTP.evaluate([rc], self._board())[0].decision_state, CTP.CANT_EVALUATE)

    def test_ambiguous_is_cant_evaluate(self):
        rc = CTP.Reconciled(_cand(order="P9"), CTP.AMBIGUOUS, None, "more than one Pipeline unit")
        self.assertEqual(CTP.evaluate([rc], self._board())[0].decision_state, CTP.CANT_EVALUATE)

    def test_missing_arrival_is_cant_evaluate(self):
        c = CTP.Candidate(order_number="P1", model="QX80", arrival_month="")     # no ETA anywhere
        rc = CTP.Reconciled(c, CTP.MATCHED, {"combination_id": "c1", "model": "QX80", "arrival_month": ""},
                            "matched", "order#")
        r = CTP.evaluate([rc], self._board(excess_c1=0))[0]
        self.assertEqual(r.decision_state, CTP.CANT_EVALUATE)
        self.assertIn("arrival timing", r.reason_plain)

    def test_no_board_position_is_cant_evaluate(self):
        rc = self._matched("cUNKNOWN")
        self.assertEqual(CTP.evaluate([rc], self._board())[0].decision_state, CTP.CANT_EVALUATE)

    def test_matched_no_superior_target_is_keep(self):
        r = CTP.evaluate([self._matched("c1")], self._board(excess_c1=0, short_c2=2))[0]
        self.assertEqual(r.decision_state, CTP.KEEP)
        self.assertTrue(r.reason_plain.startswith("Keep it"))

    def test_matched_with_proven_target_is_change(self):
        r = CTP.evaluate([self._matched("c1")], self._board(excess_c1=1, short_c2=1))[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertTrue(r.proposed_line and r.proposed_colors)              # CHANGE always has an exact target
        self.assertIn("Radiant White / Graphite", r.reason_plain)

    def test_change_never_fabricates_target(self):
        # over-supplied but nothing short → KEEP, never invent a target
        r = CTP.evaluate([self._matched("c1")], self._board(excess_c1=1, short_c2=0))[0]
        self.assertEqual(r.decision_state, CTP.KEEP)

    def test_sequential_rerun_after_change(self):
        board = self._board(excess_c1=2, short_c2=1)
        recs = CTP.evaluate([self._matched("c1", order="A"), self._matched("c1", order="B")], board)
        self.assertEqual([r.decision_state for r in recs], [CTP.CHANGE, CTP.KEEP])   # hole filled once

    def test_footer_row_never_receives_state(self):
        # a legend row rejected at candidacy never reaches evaluate
        self.assertIsNone(CTP.to_candidate({"order": "* C=Customer Order"}))

    def test_summarize_unmatched_not_keep(self):
        rc = CTP.Reconciled(_cand(order="P9"), CTP.UNMATCHED, None, "not in pipeline")
        summ = CTP.summarize(CTP.evaluate([rc], self._board()))
        self.assertEqual((summ["orders"], summ["keep"], summ["change"], summ["attention"]), (1, 0, 0, 1))


# ---- E. UX -----------------------------------------------------------------------------------------------
class TestCtpUI(unittest.TestCase):
    def setUp(self):
        import tempfile
        from elite.ui.fixtures import Phase10
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_business_language_and_states(self):
        self.assertIn("No CTP files loaded yet.", self.full.get("/ctp").body)
        self.full.post("/ctp/upload", {}, files={"file": ("CTP (1).xls", _fixture("ctp_qx60_html.xls"))})
        b = self.full.get("/ctp").body
        # business-first language present
        self.assertIn("CTP — What Should I Change?", b)
        self.assertIn("orders available", b.lower())
        self.assertIn("Need Attention", b)
        # exactly six orders, footer excluded
        self.assertIn("TK76329", b)
        self.assertNotIn("C=Customer Order", b)
        # no pipeline seeded → all six are CAN'T EVALUATE, never KEEP
        self.assertIn("NEEDS ATTENTION", b)
        self.assertNotIn("Leave this order exactly as it is", b)      # no KEEP card
        # full human build shown (exterior/interior names, not just codes)
        self.assertIn("Graphite Shadow / Stone Gray", b)
        self.assertIn("QX60 LUXE FWD", b)
        # primary page does not LEAD with engine jargon (allowed only inside proof/details)
        self.assertNotIn("certified board", b.lower())
        self.assertNotIn("full horizon", b.lower())
        # remove + clear
        self.full.post("/ctp/clear", {})
        self.assertIn("No CTP files loaded yet.", self.full.get("/ctp").body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
