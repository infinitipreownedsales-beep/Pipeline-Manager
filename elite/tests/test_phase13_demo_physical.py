"""Executive-Demo physical availability — the Demo candidate pools must join the LIVE DMS inventory snapshot
(on-ground DLR-INV / incoming ONS), NOT the empty current_supply_projection table the live board recompute
never populates. Also proves the current-demo vehicle resolves (build + inventory age) by VIN/serial/stock, and
the A/B/C hierarchy over real inventory. (Final live closeout 2026-09-03.)
"""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.identity.translation import TranslationStore
from elite.identity import seed_infiniti as SEED
from elite.ui.views import operator as OP
from elite.operatorstd import demo_board as DB
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS


def _row(stock, serial, code, ext, inte, loc, dis="", pm=""):
    # Stock#, Serial, Status, MY, Model Line, Model Code, Description, Trans, Ext, Int, MSRP, Inv, Location, DIS, ETA, PM
    return [stock, serial, "", "2026", "QX80", code, "QX80 PURE", "AUTO", ext, inte, "78900", "74000",
            loc, dis, "", pm]


class TestDemoPhysicalAvailability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        st = NewInvStore(self.conn, self.p.clock)
        self.gov = resolve_or_create_planning_combination(
            st, self.p.clock, {"model_code": "86117", "exterior": "KH3", "interior": "G"}, SCOPE, source_ref="t")

    def tearDown(self):
        self.p.close()

    def _import(self, rows):
        xp = make_xlsx([HEADERS] + rows, sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:demo",
                              effective_time=self.p.now_iso())

    # ROOT-CAUSE PROOF: pools join the live DMS snapshot (serial-identified units), not the empty projection table
    def test_pools_join_live_dms_on_ground_and_incoming(self):
        self._import([_row("S1", "601129", "86117", "KH3", "G", "DLR-INV", dis="15"),
                      _row("S2", "601130", "86117", "KH3", "G", "DLR-INV", dis="40"),
                      _row("S3", "700001", "86117", "KH3", "G", "ONS", pm="2026-11")])
        cur, inc, order_ok = OP._demo_pools(self.p.app, SCOPE, self.gov.id)
        self.assertEqual(len(cur), 2)                              # two on-ground units are actually found now
        self.assertEqual(len(inc), 1)                              # one incoming unit
        self.assertEqual([u.vin for u in cur][0], "601129")       # youngest (lowest DIS) first for Demo
        self.assertFalse(order_ok)                                 # a physical path exists -> not order-forced

    # A/B/C + backup depth: 2 on-ground -> USE NOW; 1 on-ground -> REORDER BEFORE PULLING; 0+incoming -> WAIT
    def test_action_reflects_real_physical_depth(self):
        self._import([_row("S1", "601129", "86117", "KH3", "G", "DLR-INV", dis="15"),
                      _row("S2", "601130", "86117", "KH3", "G", "DLR-INV", dis="40")])
        cur, inc, _o = OP._demo_pools(self.p.app, SCOPE, self.gov.id)
        self.assertEqual(DB.candidate_action(len(cur), bool(inc), orderable=True), DB.USE_NOW)

    def test_last_on_lot_is_reorder_before_pulling(self):
        self._import([_row("S1", "601129", "86117", "KH3", "G", "DLR-INV", dis="15")])
        cur, inc, _o = OP._demo_pools(self.p.app, SCOPE, self.gov.id)
        self.assertEqual(len(cur), 1)
        self.assertEqual(DB.candidate_action(len(cur), bool(inc), orderable=True), DB.REORDER_BEFORE_PULLING)

    def test_incoming_only_is_wait_for_incoming(self):
        self._import([_row("S3", "700001", "86117", "KH3", "G", "ONS", pm="2026-11")])
        cur, inc, _o = OP._demo_pools(self.p.app, SCOPE, self.gov.id)
        self.assertEqual((len(cur), len(inc)), (0, 1))
        self.assertEqual(DB.candidate_action(len(cur), bool(inc), orderable=True), DB.WAIT_FOR_INCOMING)

    # current demo vehicle resolves by SERIAL (a roster 'unit' is often a serial, not a 17-char VIN)
    def test_current_demo_resolves_build_and_inventory_age_by_serial(self):
        self._import([_row("S1", "601129", "86117", "KH3", "G", "DLR-INV", dis="33")])
        build = OP._demo_current_build(self.p.app, SCOPE, "601129")
        self.assertIn("QX80", build)                               # human build, not the bare id
        self.assertTrue(any(c in build for c in ("Black Obsidian", "KH3")))
        self.assertEqual(OP._demo_inv_age(self.p.app, SCOPE, "601129"), "33d")   # true inventory-age clock

    def test_inventory_age_unknown_when_not_sourced(self):
        self.assertEqual(OP._demo_inv_age(self.p.app, SCOPE, "999999"), "unknown")   # never fabricated

    # committed (active-demo) units are excluded from the pool — count-once holds over the live source too
    def test_committed_demo_unit_excluded_from_pool(self):
        self._import([_row("S1", "601129", "86117", "KH3", "G", "DLR-INV", dis="15"),
                      _row("S2", "601130", "86117", "KH3", "G", "DLR-INV", dis="40")])
        # the active demo's own unit (601129) is a current-use commitment via the roster
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "demo_roster",
                                  [{"id": "u1", "name": "Kyle", "current": {"vin": "601129", "start": "2026-06-04"}}])
        cur, _inc, _o = OP._demo_pools(self.p.app, SCOPE, self.gov.id)
        self.assertNotIn("601129", [u.vin for u in cur])          # the active demo's own unit is not re-offered
        self.assertIn("601130", [u.vin for u in cur])


if __name__ == "__main__":
    unittest.main(verbosity=2)
