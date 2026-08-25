"""Live multi-file CTP intake / reconciliation / evaluation (04_CTP_LIVE_WORKFLOW_SPEC).

Parse (CSV + XLSX, header-agnostic aliases); reconcile to pipeline by Order# then VIN (unmatched + identity
conflict surfaced, never duplicated); evaluate all candidates together against the certified board with a
full-horizon re-run after each CHANGE; KEEP unless a proven superior certified-short target of the same model
exists — never a fabricated target or colour preference.
"""
import io
import unittest
import zipfile

from elite.workflow import ctp_intake as CTP


def _mini_xlsx(header, rows):
    """Build a minimal valid .xlsx (inline strings, with real A1 cell refs) for the parser test — stdlib only."""
    def colname(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    def rowxml(rownum, values):
        cells = "".join(f'<c r="{colname(ci)}{rownum}" t="inlineStr"><is><t>{v}</t></is></c>'
                        for ci, v in enumerate(values))
        return f'<row r="{rownum}">{cells}</row>'
    sheet_rows = [rowxml(1, header)]
    for ri, r in enumerate(rows, start=2):
        sheet_rows.append(rowxml(ri, r))
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


class TestOemHtmlXls(unittest.TestCase):
    """The real OEM export: an HTML table saved with an .xls extension (not an XLSX workbook). It must be
    detected by CONTENT and parsed directly, preserving every column."""
    def _fixture(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "fixtures", "ctp_qx60_html.xls")
        with open(path, "rb") as fh:
            return fh.read()

    def test_html_detected_by_content_not_extension(self):
        rows = CTP.parse_ctp_file("CTP (1).xls", self._fixture())     # .xls extension, HTML content
        self.assertEqual(len(rows), 6)
        self.assertIn("order", rows[0])
        self.assertIn("colortrim", rows[0])                            # every column preserved

    def test_six_qx60_orders_fully_parsed(self):
        cands = [c for c in (CTP.to_candidate(r, source_file="CTP (1).xls")
                             for r in CTP.parse_ctp_file("CTP (1).xls", self._fixture())) if c]
        self.assertEqual([c.order_number for c in cands],
                         ["TK76329", "TK76327", "TK76337", "TK76338", "TK76339", "TK76340"])
        c0 = cands[0]      # TK76329 — 84317 QX60 LUXE FWD — KAD-K Graphite Shadow / Stone Gray
        self.assertEqual((c0.model_code, c0.model, c0.trim, c0.drivetrain), ("84317", "QX60", "LUXE", "FWD"))
        self.assertEqual((c0.exterior, c0.interior), ("KAD", "K"))
        self.assertEqual((c0.exterior_name, c0.interior_name), ("Graphite Shadow", "Stone Gray"))
        self.assertEqual(c0.color_trim_raw, "KAD-K Graphite Shadow / Stone Gray")   # raw preserved
        self.assertEqual((c0.packages, c0.accessories, c0.arrival_month), ("PA1", "Cargo Package", "2026-11"))
        c3 = cands[3]      # TK76338 — 84617 QX60 AUTOGRAPH AWD — XKJ-P 2T Radiant White / Saddle Brown
        self.assertEqual((c3.model_code, c3.trim, c3.drivetrain), ("84617", "AUTOGRAPH", "AWD"))
        self.assertEqual((c3.exterior, c3.interior, c3.exterior_name, c3.interior_name),
                         ("XKJ", "P", "2T Radiant White", "Saddle Brown"))   # model-scoped P handled by source

    def test_all_reconcilable_by_order_number(self):
        cands = [c for c in (CTP.to_candidate(r) for r in CTP.parse_ctp_file("CTP (1).xls", self._fixture())) if c]
        self.assertTrue(all(c.key for c in cands))                     # every row has an Order # to reconcile on


class TestParse(unittest.TestCase):
    def test_parse_csv(self):
        data = b"Order #,VIN,Model,Ext,Int,Production Month\nP100,VIN1,QX80,QBE,G,2026-11\nP101,VIN2,QX60,DAT,K,2026-12\n"
        rows = CTP.parse_ctp_file("qx80.csv", data)
        self.assertEqual(len(rows), 2)
        c = CTP.to_candidate(rows[0], source_file="qx80.csv")
        self.assertEqual((c.order_number, c.vin, c.model, c.exterior, c.arrival_month),
                         ("P100", "VIN1", "QX80", "QBE", "2026-11"))

    def test_parse_xlsx(self):
        data = _mini_xlsx(["Order#", "VIN", "Model"], [["P200", "VINX", "QX65"]])
        rows = CTP.parse_ctp_file("qx65.xlsx", data)
        self.assertEqual(len(rows), 1)
        c = CTP.to_candidate(rows[0])
        self.assertEqual((c.order_number, c.vin, c.model), ("P200", "VINX", "QX65"))

    def test_candidate_requires_order_or_vin(self):
        self.assertIsNone(CTP.to_candidate({"model": "QX80"}))   # no order#/VIN → not reconcilable
        self.assertIsNotNone(CTP.to_candidate({"vin": "V1"}))

    def test_unreadable_file_is_empty_not_crash(self):
        self.assertEqual(CTP.parse_ctp_file("x.xlsx", b"not a zip"), [])


def _cand(order="", vin="", model="QX80"):
    return CTP.Candidate(order_number=order, vin=vin, model=model)


class TestReconcile(unittest.TestCase):
    def _pipeline(self):
        return [{"order_number": "P100", "vin": "VIN1", "combination_id": "c1", "canonical": "x", "model": "QX80",
                 "arrival_month": "2026-11"},
                {"order_number": "P101", "vin": "VIN2", "combination_id": "c2", "canonical": "y", "model": "QX60",
                 "arrival_month": "2026-12"}]

    def test_match_by_order(self):
        r = CTP.reconcile([_cand(order="P100")], self._pipeline())[0]
        self.assertEqual(r.status, CTP.MATCHED)
        self.assertEqual(r.pipeline["combination_id"], "c1")

    def test_match_by_vin_when_no_order(self):
        r = CTP.reconcile([_cand(vin="VIN2")], self._pipeline())[0]
        self.assertEqual(r.status, CTP.MATCHED)
        self.assertEqual(r.pipeline["combination_id"], "c2")

    def test_unmatched_surfaced(self):
        r = CTP.reconcile([_cand(order="P999")], self._pipeline())[0]
        self.assertEqual(r.status, CTP.UNMATCHED)
        self.assertIn("not found in current Pipeline", r.conflict_detail)

    def test_identity_conflict_preserves_both(self):
        r = CTP.reconcile([_cand(order="P100", vin="WRONGVIN")], self._pipeline())[0]
        self.assertEqual(r.status, CTP.CONFLICT)
        self.assertIn("VIN1", r.conflict_detail)
        self.assertIn("WRONGVIN", r.conflict_detail)


class TestEvaluate(unittest.TestCase):
    def _board(self, excess_c1=0, short_c2=0):
        return {"c1": {"canonical": "cx1", "label": "QX80 SPORT 4WD", "model": "QX80", "excess": excess_c1, "short": 0},
                "c2": {"canonical": "cx2", "label": "QX80 LUXE 2WD", "model": "QX80", "excess": 0, "short": short_c2}}

    def _recon(self, cid, order="P1", vin="V1", model="QX80"):
        cand = CTP.Candidate(order_number=order, vin=vin, model=model)
        return CTP.Reconciled(cand, CTP.MATCHED, {"combination_id": cid, "model": model, "canonical": "cx1"})

    def test_keep_when_current_not_oversupplied(self):
        v = CTP.evaluate([self._recon("c1")], self._board(excess_c1=0, short_c2=2))[0]
        self.assertEqual(v.recommendation, CTP.KEEP)

    def test_change_when_excess_and_short_target(self):
        v = CTP.evaluate([self._recon("c1")], self._board(excess_c1=1, short_c2=1))[0]
        self.assertEqual(v.recommendation, CTP.CHANGE)
        self.assertEqual(v.proposed_combination, "cx2")
        self.assertEqual(v.proof["after"], {"source_excess": 0, "target_short": 0})

    def test_no_fabricated_target_when_no_short(self):
        v = CTP.evaluate([self._recon("c1")], self._board(excess_c1=1, short_c2=0))[0]
        self.assertEqual(v.recommendation, CTP.KEEP)
        self.assertIn("will not fabricate a target", v.why)

    def test_sequential_full_horizon_rerun(self):
        # two orders on the over-supplied c1, only ONE short unit at c2 → first CHANGEs, second KEEPs
        board = self._board(excess_c1=2, short_c2=1)
        recon = [self._recon("c1", order="P1"), self._recon("c1", order="P2")]
        vs = CTP.evaluate(recon, board)
        self.assertEqual([v.recommendation for v in vs], [CTP.CHANGE, CTP.KEEP])

    def test_unmatched_cannot_change(self):
        rc = CTP.Reconciled(CTP.Candidate(order_number="P9"), CTP.UNMATCHED, None, "not found")
        v = CTP.evaluate([rc], self._board())[0]
        self.assertEqual(v.recommendation, CTP.KEEP)

    def test_summarize_counts(self):
        board = self._board(excess_c1=1, short_c2=1)
        recon = [self._recon("c1"), CTP.Reconciled(CTP.Candidate(order_number="P9"), CTP.UNMATCHED, None, "x")]
        vs = CTP.evaluate(recon, board)
        summ = CTP.summarize(recon, vs)
        self.assertEqual((summ["candidates"], summ["matched"], summ["unmatched"], summ["change"], summ["keep"]),
                         (2, 1, 1, 1, 1))


class TestCtpUI(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        from elite.ui.fixtures import Phase10
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_empty_then_upload_renders_reconciliation(self):
        b = self.full.get("/ctp").body
        self.assertIn("No current CTP candidate files loaded.", b)
        csv = b"Order #,VIN,Model,Ext,Int\nP100,VIN1,QX80,QBE,G\n"
        self.full.post("/ctp/upload", {}, files={"file": ("qx80_ctp.csv", csv)})
        b = self.full.get("/ctp").body
        self.assertIn("qx80_ctp.csv", b)                    # file/model loaded shown
        self.assertIn("P100", b)                            # candidate order appears
        # no pipeline seeded here → reconciliation surfaces the unmatched candidate (never fabricated)
        self.assertIn("not found in current Pipeline", b)
        self.assertIn("KEEP", b)
        # clear resets the session
        self.full.post("/ctp/clear", {})
        self.assertIn("No current CTP candidate files loaded.", self.full.get("/ctp").body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
