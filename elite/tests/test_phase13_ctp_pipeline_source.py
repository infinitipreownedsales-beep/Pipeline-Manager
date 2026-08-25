"""CTP ↔ Pipeline connection (live unblock 2026-08-25).

The live disconnect: CTP read ONLY the computed `future_supply_projection`, so production orders the operator
had loaded but Elite had not yet projected read as 'not in the Pipeline'. The fix makes CTP reconcile against
the SAME authoritative incoming-order sources the rest of the app uses — the certified projection AND the raw
Production Orders snapshot — matched EXACTLY by Order# or VIN, never fabricating a board position for a
snapshot-only match. These tests lock: (1) a loaded-but-unprojected order becomes a reconcilable Pipeline row;
(2) the projection still wins (with its board combination) and is not duplicated by the snapshot; (3) CTP's
reconcile matches such an order by exact Order# and the evaluator gates it honestly (no board position).
"""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.views import operator as OP
from elite.workflow import ctp_intake as CTP


def _mini_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE sellable_combination(id TEXT, canonical_identity TEXT, store_scope TEXT)")
    c.execute("CREATE TABLE future_supply_projection(store_scope TEXT, combination_id TEXT, arrival_month TEXT, "
              "production_order_id TEXT, status TEXT, calculation_timestamp TEXT)")
    c.execute("CREATE TABLE production_order(id TEXT, manufacturer_order_id TEXT, vin TEXT)")
    return c


class _App:
    def __init__(self, conn):
        self.stack = type("S", (), {"db": type("D", (), {"conn": conn})()})()


class TestCtpPipelineSource(unittest.TestCase):
    def setUp(self):
        self.conn = _mini_conn()
        self.app = _App(self.conn)

    def test_snapshot_order_becomes_pipeline_row(self):
        prod_rows = [{"manufacturer_order_id": "TK76329", "vin": "", "model": "QX60", "eta_month": "2026-11"}]
        with patch.object(OP, "_read_production_orders", return_value=prod_rows):
            rows = OP._ctp_pipeline_rows(self.app, "store:HG")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["order_number"], "TK76329")
        self.assertIsNone(rows[0]["combination_id"])       # snapshot-only: no fabricated board position
        self.assertEqual(rows[0]["arrival_month"], "2026-11")

    def test_projection_wins_and_no_duplicate(self):
        self.conn.execute("INSERT INTO sellable_combination VALUES('cid1','dms_planning|model=QX60','store:HG')")
        self.conn.execute("INSERT INTO production_order VALUES('po1','TK76329','VINX')")
        self.conn.execute("INSERT INTO future_supply_projection VALUES('store:HG','cid1','2026-11','po1','current','2026-08-25T10:00:00Z')")
        self.conn.commit()
        # the SAME order also present in the raw snapshot must not double-count
        prod_rows = [{"manufacturer_order_id": "tk76329", "vin": "VINX", "model": "QX60", "eta_month": "2026-11"}]
        with patch.object(OP, "_read_production_orders", return_value=prod_rows):
            rows = OP._ctp_pipeline_rows(self.app, "store:HG")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["combination_id"], "cid1")  # certified projection row wins

    def test_reconcile_matches_snapshot_order_then_gates(self):
        prod_rows = [{"manufacturer_order_id": "TK76329", "vin": "", "model": "QX60", "eta_month": "2026-11"}]
        with patch.object(OP, "_read_production_orders", return_value=prod_rows):
            pipeline = OP._ctp_pipeline_rows(self.app, "store:HG")
        cand = CTP.to_candidate({"order": "TK76329", "model": "QX60"})
        recs = CTP.reconcile([cand], pipeline)
        self.assertEqual(recs[0].status, CTP.MATCHED)        # exact Order# match — no longer 'not in Pipeline'
        # snapshot-only match has no board position -> honest CANT_EVALUATE, never a fabricated call
        out = CTP.evaluate(recs, {}, now="2026-08-25")
        self.assertEqual(out[0].decision_state, CTP.CANT_EVALUATE)

    def test_pipeline_age_falls_back_to_snapshot(self):
        class _Snap:
            observed_time = "2026-08-25T09:30:00Z"
            received_at = "2026-08-25T09:31:00Z"

        class _Reader:
            def __init__(self, *a):
                pass

            def latest_snapshot(self, *a):
                return _Snap()

        ops = type("O", (), {"ops": object(), "data": object(),
                             "source_id": staticmethod(lambda k: "src")})()
        with patch.object(OP, "_ops_stack", return_value=ops), \
             patch("elite.newinv.snapshots.SnapshotReader", _Reader):
            age = OP._ctp_pipeline_age(self.app, "store:HG")
        self.assertEqual(age, "2026-08-25 09:30")


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ---- end-to-end: the six live QX60 orders reconcile AND evaluate through the real /ctp page ----
class TestCtpSixOrdersEndToEnd(unittest.TestCase):
    def setUp(self):
        from elite.ui.fixtures import Phase10
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "e.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _fixture(self):
        here = os.path.dirname(__file__)
        with open(os.path.join(here, "fixtures", "ctp_qx60_html.xls"), "rb") as fh:
            return fh.read()

    def test_six_orders_reconcile_and_evaluate(self):
        # the six real QX60 orders, mapped to a seeded certified Pipeline + board
        pipeline = [
            {"order_number": "TK76329", "vin": "", "combination_id": "cidA", "canonical": "dms_planning|model=QX60",
             "model": "QX60", "arrival_month": "2026-11"},
            {"order_number": "TK76327", "vin": "", "combination_id": "cidA", "canonical": "dms_planning|model=QX60",
             "model": "QX60", "arrival_month": "2026-11"},
            {"order_number": "TK76337", "vin": "", "combination_id": "cidB", "canonical": "dms_planning|model=QX60",
             "model": "QX60", "arrival_month": "2026-12"},
            {"order_number": "TK76338", "vin": "", "combination_id": "cidB", "canonical": "dms_planning|model=QX60",
             "model": "QX60", "arrival_month": "2026-12"},
            {"order_number": "TK76339", "vin": "", "combination_id": None, "canonical": None,
             "model": "QX60", "arrival_month": "2026-12"},   # snapshot-only: no board position
            {"order_number": "TK76340", "vin": "", "combination_id": "cidC", "canonical": "dms_planning|model=QX60",
             "model": "QX60", "arrival_month": "2027-01"},
        ]
        board = {
            "cidA": {"canonical": "dms_planning|model=QX60", "line": "QX60 LUXE FWD", "colors": "Graphite Shadow",
                     "model": "QX60", "excess": 2, "short": 0},
            "cidB": {"canonical": "dms_planning|model=QX60", "line": "QX60 AUTOGRAPH AWD", "colors": "Mineral Black",
                     "model": "QX60", "excess": 0, "short": 3},   # the certified-short CHANGE target
            "cidC": {"canonical": "dms_planning|model=QX60", "line": "QX60 LUXE AWD", "colors": "Moonbow Blue",
                     "model": "QX60", "excess": 0, "short": 0},
        }
        self.full.post("/ctp/upload", {}, files={"file": ("CTP (1).xls", self._fixture())})
        from unittest.mock import patch
        with patch.object(OP, "_ctp_pipeline_rows", return_value=pipeline), \
             patch.object(OP, "_ctp_board", return_value=board):
            b = self.full.get("/ctp").body
        # all six reconciled and evaluated — not "not in the Pipeline"
        for o in ("TK76329", "TK76327", "TK76337", "TK76338", "TK76339", "TK76340"):
            self.assertIn(o, b)
        self.assertNotIn("not in the Pipeline file currently loaded", b)
        # real decisions present: CHANGE (excess->short), KEEP, and one honest NEEDS ATTENTION (no board position)
        self.assertIn("CHANGE", b)
        self.assertIn("KEEP", b)
        self.assertIn("NEEDS ATTENTION", b)

    def test_reconcile_evaluate_counts(self):
        from elite.workflow import ctp_intake as CTP
        cands = [CTP.to_candidate(r, source_file="CTP (1).xls")
                 for r in CTP.parse_ctp_file("CTP (1).xls", self._fixture())]
        cands = [c for c in cands if c]
        self.assertEqual(len(cands), 6)
        pipeline = [{"order_number": c.order_number, "vin": "", "combination_id": "cidB",
                     "canonical": "dms_planning|model=QX60", "model": "QX60", "arrival_month": "2026-12"}
                    for c in cands]
        board = {"cidB": {"canonical": "dms_planning|model=QX60", "line": "QX60 AUTOGRAPH AWD",
                          "colors": "Mineral Black", "model": "QX60", "excess": 0, "short": 0}}
        recs = CTP.evaluate(CTP.reconcile(cands, pipeline), board, now="2026-08-25")
        summ = CTP.summarize(recs)
        self.assertEqual(summ["orders"], 6)
        self.assertEqual(summ["keep"], 6)          # all matched, board position, no excess -> all KEEP
        self.assertEqual(summ["attention"], 0)


# ---- LIVE ingestion: CTP reads the DMS inventory/pipeline export the operator actually loads ----
class TestCtpReadsLiveInventoryPipeline(unittest.TestCase):
    def setUp(self):
        import tempfile
        from elite.ui.fixtures import Phase10
        self.p = Phase10(os.path.join(tempfile.mkdtemp(), "e.db"))
        self.scope = "store:HG"

    def tearDown(self):
        self.p.close()

    def _rows(self, inv):
        from unittest.mock import patch
        with patch("elite.loaner.placement.read_new_retail_units", return_value=inv):
            return OP._ctp_inventory_pipeline_rows(self.p.app, self.scope)

    def test_on_order_serial_is_treated_as_order_number(self):
        from elite.newinv.dms_cohort import INVENTORY_STATE_FIELD as LOC
        rows = self._rows([{"serial": "TK76329", LOC: "ONS", "model": "QX60", "model_code": "84317",
                            "ext": "KAD", "int": "K", "eta": "2026-11"}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["order_number"], "TK76329")
        self.assertEqual(rows[0]["arrival_month"], "2026-11")

    def test_in_stock_serial_is_not_an_order(self):
        from elite.newinv.dms_cohort import INVENTORY_STATE_FIELD as LOC
        rows = self._rows([{"serial": "SER1", LOC: "DLR-INV", "model": "QX60", "model_code": "84317",
                            "ext": "KAD", "int": "K"}])
        self.assertEqual(rows, [])                       # no order number, no authoritative VIN -> not emitted

    def test_explicit_order_column_wins(self):
        from elite.newinv.dms_cohort import INVENTORY_STATE_FIELD as LOC
        rows = self._rows([{"serial": "SER9", "Order #": "TK76340", LOC: "SIT", "model": "QX60",
                            "model_code": "84617", "ext": "XKJ", "int": "P"}])
        self.assertEqual(rows[0]["order_number"], "TK76340")

    def test_ctp_finds_order_from_live_inventory_end_to_end(self):
        from unittest.mock import patch
        from elite.newinv.dms_cohort import INVENTORY_STATE_FIELD as LOC
        from elite.workflow import ctp_intake as CTP
        inv = [{"serial": "TK76329", LOC: "ONS", "model": "QX60", "model_code": "84317",
                "ext": "KAD", "int": "K", "eta": "2026-11"}]
        with patch("elite.loaner.placement.read_new_retail_units", return_value=inv):
            pipeline = OP._ctp_pipeline_rows(self.p.app, self.scope)   # full merge, inventory source included
        cand = CTP.to_candidate({"order": "TK76329", "model": "QX60"})
        self.assertEqual(CTP.reconcile([cand], pipeline)[0].status, CTP.MATCHED)
