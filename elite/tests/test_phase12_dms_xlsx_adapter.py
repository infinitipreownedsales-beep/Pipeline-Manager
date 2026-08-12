"""Phase 12 first-source DMS XLSX adapter — SAFE OBSERVATION-ONLY phase.

Proves the real DMS `vehicleInventorySummary` workbook is ingestible directly (native stdlib XLSX parse +
contract header aliases + original-artifact retention) as retained Source Observations ONLY — with NO
identity created from Serial, NO ProductionOrder/VehicleUnit, NO fabricated VIN, NO recommendations, and
placeholder Stock# values (e.g. "75") never collapsing distinct rows. Schema stays v12.

The committed fixture is a SANITIZED synthetic workbook that reproduces the real structure — it contains no
real VIN, customer, or private dealership record.
"""
import io
import os
import tempfile
import unittest
import zipfile

from elite.db import current_version
from elite.ops.adapters import run_adapter
from elite.ops.contracts import get_contract
from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.intake import content_hash

CONTRACT = "new_inventory_pipeline_summary"
SHEET = "vehicleInventorySummary0"
HEADERS = ["Stock#", "Serial", "Status", "MY", "Model Line", "Model Code", "Description", "Trans",
           "Ext", "Int", "MSRP", "Inv", "Location", "DIS", "ETA", "Production Month"]

# Sanitized rows — no real VIN/customer data. Three placeholder Stock#=75 rows (distinct configs), an
# unconventional stock ("HP", "DEMOREED"), ambiguous six-char Serials, comma money, YYYY-MM, MM/DD/YYYY,
# and one genuinely numeric cell (DIS) to exercise numeric parsing.
ROWS = [
    ["75", "800001", "Deal Opened", "2026", "QX60", "60111", "QX60 LUXE AWD", "AUTO", "BLK", "GRY",
     "58,900", "55,010", "DLR-INV", 40, "07/15/2026", "2025-07"],
    ["75", "800002", "Deal Opened", "2026", "QX80", "83816", "QX80 SPORT 4WD", "AUTO", "WHT", "BLK",
     "92,150", "88,300", "DLR-INV", 12, "08/01/2026", "2025-08"],
    ["75", "640790", "Deal Closed", "2026", "QX65", "65220", "QX65 SENSORY", "AUTO", "SIL", "GRY",
     "71,400", "68,900", "DLR-INV", 5, "06/20/2026", "2025-06"],
    ["HP", "341525", "Deal Opened", "2025", "QX80", "83816", "QX80 SPORT 4WD", "AUTO", "BLU", "TAN",
     "90,000", "86,000", "DLR-INV", 88, "05/10/2026", "2025-05"],
    ["DEMOREED", "430938", "Deal Opened", "2026", "QX60", "60111", "QX60 LUXE AWD", "AUTO", "BLK", "BLK",
     "59,300", "56,000", "DLR-INV", 3, "09/01/2026", "2025-09"],
]


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col(n):
    s, n = "", n + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def make_xlsx(rows, sheet_name=SHEET):
    """Build a minimal but valid .xlsx (stdlib only) with shared strings + numeric cells."""
    shared, sidx = [], {}

    def si(v):
        if v not in sidx:
            sidx[v] = len(shared)
            shared.append(v)
        return sidx[v]

    sheet_rows = []
    for r_i, row in enumerate(rows, start=1):
        cells = []
        for c_i, val in enumerate(row):
            ref = f"{_col(c_i)}{r_i}"
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif val is None or val == "":
                continue
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{si(str(val))}</v></c>')
        sheet_rows.append(f'<row r="{r_i}">{"".join(cells)}</row>')
    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    sst = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared)}" '
           f'uniqueCount="{len(shared)}">'
           + "".join(f'<si><t xml:space="preserve">{_esc(s)}</t></si>' for s in shared) + '</sst>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets><sheet name="{_esc(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
               'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
               'relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
              'officedocument.spreadsheetml.sheet.main+xml"/>'
              '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-'
              'officedocument.spreadsheetml.worksheet+xml"/>'
              '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-'
              'officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                 'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


class TestDmsXlsxAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        self.xlsx = make_xlsx([HEADERS] + ROWS)

    def _obs(self, batch_id):
        import json
        rows = self.conn.execute(
            "SELECT id, acceptance_status, identity_status, raw_values FROM source_observation "
            "WHERE import_batch_id=?", (batch_id,)).fetchall()
        return [(r["acceptance_status"], r["identity_status"], json.loads(r["raw_values"])) for r in rows]

    # --- pure adapter parse: aliases, numeric, serial_semantic ------------------
    def test_parse_headers_and_values(self):
        res = run_adapter(get_contract(CONTRACT), self.xlsx)
        self.assertEqual(len(res.rows), 5)
        r0 = res.rows[0]
        self.assertEqual(r0["stock_number"], "75")           # Stock# -> stock_number
        self.assertEqual(r0["model"], "QX60")                # Model Line -> model
        self.assertEqual(r0["production_month"], "2025-07")  # Production Month -> production_month
        self.assertEqual(r0["serial"], "800001")             # Serial preserved verbatim
        self.assertEqual(r0["serial_semantic"], "unknown")   # deferred classification
        self.assertEqual(r0["msrp"], "58,900")               # comma money preserved verbatim
        self.assertEqual(r0["dis"], "40")                    # numeric cell parsed deterministically
        self.assertNotIn("vin", r0)                          # no VIN field, none fabricated

    # --- CASE A: placeholder Stock#=75 never collapses --------------------------
    def test_placeholder_stock_never_collapses(self):
        run = self.p.import_payload(CONTRACT, self.xlsx, chash=content_hash(self.xlsx))
        obs = self._obs(run["import_batch_id"])
        stock75 = [o for o in obs if o[2].get("stock_number") == "75"]
        self.assertEqual(len(stock75), 3)                    # three distinct observations retained
        self.assertTrue(all(o[0] != "duplicate" for o in stock75))   # none collapsed as duplicate
        self.assertTrue(all(o[1] == "unresolved" for o in obs))      # all identity UNRESOLVED

    # --- CASE B: same-file replay is idempotent ---------------------------------
    def test_replay_idempotent(self):
        ch = content_hash(self.xlsx)
        r1 = self.p.import_payload(CONTRACT, self.xlsx, chash=ch)
        n1 = self.conn.execute("SELECT COUNT(*) c FROM source_observation").fetchone()["c"]
        r2 = self.p.import_payload(CONTRACT, self.xlsx, chash=ch)
        n2 = self.conn.execute("SELECT COUNT(*) c FROM source_observation").fetchone()["c"]
        self.assertEqual(n1, n2)                             # no duplicate observations on replay
        self.assertEqual(r1["id"], r2["id"])                # idempotent short-circuit to prior run

    # --- CASE F + K: no entity, no fact, no VIN created -------------------------
    def test_no_entity_no_fact_created(self):
        self.p.import_payload(CONTRACT, self.xlsx, chash=content_hash(self.xlsx))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM vehicle_unit").fetchone()["c"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM production_order").fetchone()["c"], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) c FROM business_fact WHERE store_scope=?", (SCOPE,)).fetchone()["c"], 0)

    # --- CASE D: malformed workbook (not a zip) -> safe REJECT ------------------
    def test_malformed_workbook_rejected(self):
        run = self.p.import_payload(CONTRACT, b"this-is-not-a-real-xlsx", chash=content_hash(b"nope"))
        self.assertEqual(run["state"], "REJECTED")
        # nothing was created from a rejected file
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM vehicle_unit").fetchone()["c"], 0)

    # --- scope + schema + observation retention --------------------------------
    def test_scope_schema_and_retention(self):
        run = self.p.import_payload(CONTRACT, self.xlsx, chash=content_hash(self.xlsx))
        obs = self._obs(run["import_batch_id"])
        self.assertEqual(len(obs), 5)                        # every row retained as an observation
        scopes = {r["source_scope"] for r in self.conn.execute(
            "SELECT source_scope FROM source_observation WHERE import_batch_id=?", (run["import_batch_id"],))}
        self.assertEqual(scopes, {SCOPE})                    # scope applied from the configured pilot scope
        self.assertEqual(current_version(self.conn), 12)     # schema unchanged

    # --- CASE G: unconventional stock values preserved verbatim ----------------
    def test_unconventional_stock_preserved(self):
        run = self.p.import_payload(CONTRACT, self.xlsx, chash=content_hash(self.xlsx))
        stocks = {o[2].get("stock_number") for o in self._obs(run["import_batch_id"])}
        self.assertTrue({"75", "HP", "DEMOREED"} <= stocks)  # preserved exactly, not rejected

    # --- FileIntake retains the original .xlsx artifact ------------------------
    def test_fileintake_accepts_and_retains_xlsx(self):
        receipt = self.p.intake.accept(filename="vehicleInventorySummary.xlsx", payload=self.xlsx,
                                       scope=SCOPE, received_by=self.p.op_importer)
        self.assertEqual(receipt["status"], "received")
        self.assertEqual(receipt["content_hash"], content_hash(self.xlsx))


if __name__ == "__main__":
    unittest.main()
