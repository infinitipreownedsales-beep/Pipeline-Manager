"""Wholesale physical-unit completion (live acceptance 2026-08-26).

Combination-level arrived excess (e.g. 'QX60 8481 XKJ/K — EXCESS 3 arrived') now resolves to the exact N
on-ground physical VINs/stock to dispose (oldest first, by days-in-stock), separately from the unit(s) retained.
Real DMS inventory only — no VIN is invented; incoming units are never mixed into arrived disposition; the
safe-to-send dealer list stays combination + quantity only.
"""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.intake import content_hash
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id
from elite.ui.views.operator import _wholesale_on_ground, _plan_key_of
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS


def _pipe(rows):
    return make_xlsx([PIPE_HEADERS] + rows, sheet_name="vehicleInventorySummary0")


def _q60(stock, dis, loc, code="84816", ext="XKJ", inte="K", pm=""):
    # [Stock#, Serial, Status, MY, Model Line, Model Code, Description, Trans, Ext, Int, MSRP, Inv, Location, DIS, ETA, ProdMonth]
    return [stock, stock, "", "2026", "QX60", code, "QX60", "AUTO", ext, inte, "58900", "55000", loc, dis, "", pm]


KEY = ("QX60", "8481", "XKJ", "K")


class TestWholesaleOnGround(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        # three arrived (DLR-INV) XKJ/K units at different ages + one incoming (must NOT appear) + one other combo
        xp = _pipe([_q60("S1", 90, "DLR-INV"), _q60("S2", 200, "DLR-INV"), _q60("S3", 15, "DLR-INV"),
                    _q60("S4", 0, "ONS", pm="2026-11"),                       # incoming -> excluded
                    _q60("S9", 300, "DLR-INV", ext="GAT", inte="G")])          # different combo
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:w", effective_time=self.p.now_iso())

    def tearDown(self):
        self.p.close()

    def test_plan_key_parses_identity(self):
        self.assertEqual(_plan_key_of("dms_planning|model=QX60|model_code=8481|exterior=XKJ|interior=K"), KEY)

    def test_on_ground_units_oldest_first_real_only(self):
        units = _wholesale_on_ground(self.p.app, SCOPE, KEY)
        self.assertEqual([u["stock"] for u in units], ["S2", "S1", "S3"])     # oldest (200) -> newest (15)
        self.assertNotIn("S4", [u["stock"] for u in units])                   # incoming excluded
        self.assertNotIn("S9", [u["stock"] for u in units])                   # other combo excluded
        self.assertTrue(all(u["dis"] is not None for u in units))

    def test_dispose_n_oldest_and_retain_rest(self):
        units = _wholesale_on_ground(self.p.app, SCOPE, KEY)
        n = 2                                                                # arrived excess of 2
        move, keep = units[:n], units[n:]
        self.assertEqual([u["stock"] for u in move], ["S2", "S1"])           # the two oldest disposed
        self.assertEqual([u["stock"] for u in keep], ["S3"])                # newest retained


class TestWholesaleRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        xp = _pipe([_q60("S1", 90, "DLR-INV"), _q60("S2", 200, "DLR-INV"), _q60("S3", 15, "DLR-INV")])
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:w2", effective_time=self.p.now_iso())
        store = NewInvStore(self.conn, self.p.clock)
        cb = resolve_or_create_planning_combination(
            store, self.p.clock, {"model_code": "84816", "exterior": "XKJ", "interior": "K"}, SCOPE, source_ref="t")
        store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=3, future_supply=0, committed_supply=0, qualifying_supply=3,
            desired_ending_coverage={"target_units": 1.0}, need=0.0, excess=2.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 0, "arrived_excess": 2, "incoming_excess": 0,
                                                 "target_level": 1.0, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))
        self.full = self.p.p10.login(self.p.p10.op_full)

    def tearDown(self):
        self.p.close()

    def test_wholesale_shows_physical_units(self):
        b = self.full.get("/wholesale").body
        self.assertIn("Physical units to move", b)
        self.assertIn("S2", b)                              # oldest disposed
        self.assertIn("Retain on ground", b)               # retained section present
        self.assertIn("no rank, age, or internal reasoning", b)   # safe dealer list preserved


if __name__ == "__main__":
    unittest.main(verbosity=2)
