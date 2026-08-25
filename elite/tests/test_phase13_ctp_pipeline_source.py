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
