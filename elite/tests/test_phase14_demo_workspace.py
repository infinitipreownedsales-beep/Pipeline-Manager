"""Executive-Demo OPERATOR WORKSPACE — choice, context & one-spot execution (2026-09-04).

The decision engine is preserved (suitability ranking, portfolio no-double-assign, retail protection, mileage
learning, count-once, A/B/C hierarchy). What this suite proves is the added OPERATOR layer:

  A. current-demo CONTEXT survives the unit leaving the current-retail feed (persisted assignment snapshot);
  B. a per-executive REPLACEMENT CHOICE workspace (ALL | QX60 | QX65 | QX80) of governed alternatives;
  C. the operator may SELECT an alternative WITHOUT rewriting Elite's machine recommendation;
  D. PLAN SWAP reserves the physical unit (never re-offered to another exec) and COMPLETE SWAP executes the
     swap in one spot (final mileage, outgoing returned, replacement becomes the active demo) — never leaving
     the Demo workflow;
  E. an incoming candidate surfaces the actionable manufacturer production/order identifier + ETA.
"""
import os
import tempfile
import unittest

from elite.ops.fixtures import Phase11, SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.identity.translation import TranslationStore
from elite.identity import seed_infiniti as SEED
from elite.ids import new_id
from elite.ui.views import operator as OP


def _row(stock, serial, model, code, ext, inte, loc, dis="", pm=""):
    # Stock#, Serial, Status, MY, Model Line, Model Code, Description, Trans, Ext, Int, MSRP, Inv, Location, DIS, ETA, PM
    return [stock, serial, "", "2026", model, code, f"{model} PURE", "AUTO", ext, inte, "78900", "74000",
            loc, dis, "", pm]


class TestDemoWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        self.store = NewInvStore(self.conn, self.p.clock)
        # two governed targets: a QX80 (Holly's stated preference) and a QX60 alternative
        self.qx80 = self._combo("86117", "KH3", "G")
        self.qx60 = self._combo("84317", "GAQ", "G")
        self._persist(self.qx80, acquire=2)
        self._persist(self.qx60, acquire=2)
        self.full = self.p.p10.login(self.p.p10.op_full)

    def tearDown(self):
        self.p.close()

    def _combo(self, code, ext, inte):
        return resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE,
            source_ref="t")

    def _persist(self, comb, *, acquire, current=0):
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
            expected_demand=3.0, current_supply=current, future_supply=0, committed_supply=0,
            qualifying_supply=current, desired_ending_coverage={"target_units": 1.6}, need=float(acquire),
            excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acquire, "arrived_excess": 0,
                                                 "incoming_excess": 0, "monitor_months": []}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _import(self, rows):
        from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS
        xp = make_xlsx([HEADERS] + rows, sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:demo",
                              effective_time=self.p.now_iso())

    def _add_user(self, name, pref):
        self.full.post("/demos/user", {"name": name, "role": "Exec", "model_pref": pref})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        return roster[-1]["id"]

    def _roster_user(self, uid):
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        return next(u for u in roster if u["id"] == uid)

    # ---- A. current-demo context + persisted assignment snapshot ------------------------------------------
    def test_a_assignment_persists_context_snapshot(self):
        self._import([_row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        snap = (self._roster_user(uid)["current"] or {}).get("snapshot") or {}
        self.assertIn("QX80", snap.get("build", ""))               # human build captured at assignment
        self.assertEqual(snap.get("op_id"), "HOLLY80")             # operational unit identity
        self.assertEqual(snap.get("dis"), 22)                      # inventory age captured
        self.assertTrue(snap.get("in_stock_date"))                 # authoritative in-stock date derived
        # the detail page renders that context (operational unit + demo days + in-stock/inventory age)
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("Operational unit", b)
        self.assertIn("Demo days", b)
        self.assertIn("Unit OLLY80", b)                            # masked operational unit tag (last 6)
        self.assertNotIn("Current demo VIN", b)                    # no VINs on the manager surface

    def test_a_context_survives_unit_leaving_feed(self):
        # a demo whose unit is NOT in the current-retail feed still shows full context from the persisted snapshot
        u = {"id": "u1", "name": "Kyle", "model_pref": "QX80",
             "current": {"vin": "GONE01", "start": "2025-10-01", "mi_in": 10,
                         "snapshot": {"build": "QX80 PURE — Black Obsidian", "op_id": "GONE01", "stock": "S9",
                                      "dis": 30, "in_stock_date": "2025-09-01", "captured_at": "2025-10-01"}}}
        ctx = OP._demo_current_context(self.p.app, SCOPE, u, "2026-01-02")
        self.assertIn("QX80", ctx["build"])                        # build survives the unit leaving the feed
        self.assertEqual(ctx["stock"], "S9")
        self.assertEqual(ctx["age_provenance"], "assignment snapshot")  # provenance is its own honest field
        self.assertEqual(ctx["in_stock_date"], "2025-09-01")

    # ---- B. replacement choice workspace (ALL | QX60 | QX65 | QX80) ---------------------------------------
    def test_b_workspace_shows_elite_first_and_selectable_alternatives(self):
        self._import([_row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22"),
                      _row("R8", "REP80A", "QX80", "86117", "KH3", "G", "DLR-INV", dis="10"),
                      _row("R6", "REP60A", "QX60", "84317", "GAQ", "G", "DLR-INV", dis="12")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("Replacement plan", b)
        self.assertIn("from the Executive Demo board", b)
        self.assertIn("FIRST CHOICE", b)                   # the portfolio pick is preserved as default
        for tab in ("All", "QX60", "QX65", "QX80"):                # the model selector
            self.assertIn(f'>{tab}</a>', b)
        self.assertIn("Graphite Shadow", b)                        # the QX60 alternative is offered (ALL view)

    def test_b_model_filter_narrows_candidates(self):
        self._import([_row("R8", "REP80A", "QX80", "86117", "KH3", "G", "DLR-INV", dis="10"),
                      _row("R6", "REP60A", "QX60", "84317", "GAQ", "G", "DLR-INV", dis="12"),
                      _row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        only80 = self.full.get(f"/demos/user/{uid}", rep="QX80").body
        self.assertNotIn("Graphite Shadow", only80)               # QX60 filtered out
        only60 = self.full.get(f"/demos/user/{uid}", rep="QX60").body
        self.assertIn("Graphite Shadow", only60)                  # QX60 shown when its tab is chosen

    # ---- C. operator selection never rewrites the machine recommendation ----------------------------------
    def test_c_select_alternative_preserves_elite_first(self):
        self._import([_row("R8", "REP80A", "QX80", "86117", "KH3", "G", "DLR-INV", dis="10"),
                      _row("R6", "REP60A", "QX60", "84317", "GAQ", "G", "DLR-INV", dis="12"),
                      _row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        self.full.post(f"/demos/user/{uid}/select", {"cid": self.qx60.id})
        self.assertEqual((self._roster_user(uid)["current"]["selection"]), {"cid": self.qx60.id})
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("YOUR SELECTION", b)                        # the operator's choice is reflected
        self.assertIn("FIRST CHOICE", b)                  # ...but Elite's #1 is still shown, not rewritten

    # ---- D. PLAN SWAP reservation + COMPLETE SWAP one-spot execution --------------------------------------
    def test_d_plan_reserves_unit_from_other_execs(self):
        self._import([_row("R8", "REP80A", "QX80", "86117", "KH3", "G", "DLR-INV", dis="10"),
                      _row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        self.full.post(f"/demos/user/{uid}/plan", {"cid": self.qx80.id})
        res = self._roster_user(uid)["current"]["reservation"]
        self.assertEqual(res["op_id"], "REP80A")                  # the physical unit is held
        # another executive's candidate pool no longer contains the reserved unit
        cur, _inc, _o = OP._demo_pools(self.p.app, SCOPE, self.qx80.id, reserved_exclude_uid="someone_else")
        self.assertNotIn("REP80A", [x.vin for x in cur])

    def test_d_complete_swap_executes_in_one_spot(self):
        self._import([_row("R8", "REP80A", "QX80", "86117", "KH3", "G", "DLR-INV", dis="10"),
                      _row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        self.full.post(f"/demos/user/{uid}/plan", {"cid": self.qx80.id})
        self.full.post(f"/demos/user/{uid}/complete", {"mi": "2150", "date": "2026-01-02"})
        u = self._roster_user(uid)
        self.assertEqual(len(u["history"]), 1)                    # the outgoing demo is retained in history
        self.assertEqual(u["history"][0]["vin"], "HOLLY80")
        self.assertEqual(u["history"][0]["mi_out"], 2150)         # final actual mileage recorded
        self.assertEqual(u["current"]["vin"], "REP80A")          # the replacement is now the active demo
        self.assertIn("QX80", (u["current"].get("snapshot") or {}).get("build", ""))
        self.assertTrue(any(e.get("kind") == "swap_complete" for e in u.get("events", [])))

    # ---- E. incoming candidate surfaces the manufacturer production/order id + ETA ------------------------
    def test_e_incoming_surfaces_production_order_identifier(self):
        self._import([_row("SH", "HOLLY80", "QX80", "86117", "KH3", "G", "DLR-INV", dis="22"),
                      _row("R8", "REP80A", "QX80", "86117", "KH3", "G", "DLR-INV", dis="10"),
                      _row("IN", "Q38296", "QX80", "86117", "KH3", "G", "ONS", pm="2026-11")])
        uid = self._add_user("Holly", "QX80")
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "HOLLY80", "start": "2025-10-01", "mi": "40"})
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("Pipeline unit Q38296", b)                  # the internal operational identifier, labelled
        self.assertIn("ETA 2026-11", b)                           # ...with its timing


if __name__ == "__main__":
    unittest.main(verbosity=2)
