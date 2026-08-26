"""Certified-board recomputation wired to the live Inventory/Pipeline source (the existing planning engine).

Proves the real flow end-to-end: import Inventory/Pipeline + demand -> recompute inventory_plan_result from the
exact imported snapshot -> board is current; a newer Pipeline makes the board stale until recomputed; a missing
required input blocks without overwriting the last valid board. No supply/demand or planning math is changed.
"""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.intake import content_hash
from elite.newinv import board_recompute as BR
from elite.tests.test_phase12_real_demand_planning_bridge import sts_workbook, _row
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS

PIPE_SHEET = "vehicleInventorySummary0"


def _pipe(rows):
    return make_xlsx([PIPE_HEADERS] + rows, sheet_name=PIPE_SHEET)


# one QX60 SPORT AWD (8441) in-stock unit
def _sport_row(stock, serial, dis, loc="DLR-INV"):
    return [stock, serial, "", "2026", "QX60", "84416", "QX60 SPORT AWD", "AUTO", "GAT", "D",
            "58,900", "55,010", loc, dis, "", "2026-10"]


class TestBoardRecompute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.app = self.p.app
        self.app._p11 = self.p                          # wire the ops stack so the recompute resolves it
        self.conn = self.p.stack.db.conn

    def tearDown(self):
        self.p.close()

    def _import_demand(self):
        rows = [_row(m, f"N{i}", d, "8441", "GAT", "D")
                for i, (m, d) in enumerate([("202409", "43"), ("202410", "22"), ("202411", "18"),
                                            ("202412", "31"), ("202501", "25"), ("202502", "28")])]
        x = sts_workbook(rows)
        self.p.import_payload("speed_to_sell", x, chash=content_hash(x))

    def _import_pipeline(self, rows, chash):
        x = _pipe(rows)
        return self.p.import_payload("new_inventory_pipeline_summary", x, chash=chash,
                                    effective_time=self.p.now_iso())

    def _issued(self):
        return self.conn.execute("SELECT COUNT(*) FROM inventory_plan_result WHERE store_scope=? "
                                 "AND status='issued'", (SCOPE,)).fetchone()[0]

    def test_recompute_issues_current_board(self):
        self._import_demand()
        self._import_pipeline([_sport_row("S1", "900001", 10)], "sha256:p1")
        r = BR.recompute_board(self.app, SCOPE)
        self.assertTrue(r["ok"], r.get("reason"))
        self.assertGreaterEqual(r["issued_count"], 1)
        self.assertGreaterEqual(self._issued(), 1)
        self.assertEqual(BR.board_status(self.app, SCOPE)["state"], "current")
        # re-running is atomic (no duplicate issued board — the prior is superseded)
        n1 = self._issued()
        BR.recompute_board(self.app, SCOPE)
        self.assertEqual(self._issued(), n1)

    def test_newer_pipeline_makes_board_stale_until_recomputed(self):
        self._import_demand()
        self._import_pipeline([_sport_row("S1", "900001", 10)], "sha256:p1")
        self.assertTrue(BR.recompute_board(self.app, SCOPE)["ok"])
        self.assertEqual(BR.board_status(self.app, SCOPE)["state"], "current")
        # a newer Pipeline snapshot (different content) arrives -> board is now stale
        self._import_pipeline([_sport_row("S1", "900001", 10), _sport_row("S2", "900002", 5)], "sha256:p2")
        self.assertEqual(BR.board_status(self.app, SCOPE)["state"], "stale")
        # recompute clears it
        self.assertTrue(BR.recompute_board(self.app, SCOPE)["ok"])
        self.assertEqual(BR.board_status(self.app, SCOPE)["state"], "current")

    def test_missing_inventory_snapshot_blocks_without_overwrite(self):
        # first: a valid board
        self._import_demand()
        self._import_pipeline([_sport_row("S1", "900001", 10)], "sha256:p1")
        self.assertTrue(BR.recompute_board(self.app, SCOPE)["ok"])
        before = self._issued()
        # a fresh scope with no inventory snapshot must block and never overwrite an existing board
        r = BR.recompute_board(self.app, "store:NO_SUCH")
        self.assertFalse(r["ok"])
        self.assertIn("No Inventory", r["reason"])
        self.assertEqual(self._issued(), before)          # the valid board is untouched


if __name__ == "__main__":
    unittest.main(verbosity=2)
