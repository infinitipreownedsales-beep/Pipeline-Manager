"""Demo LIVE workspace closeout — three real-world gaps (2026-09-04).

Preserves the existing Demo ranking engine except for a BOUNDED availability-timing factor. Covers:

  1. existing active-Demo CONTEXT backfill from the authoritative inventory-snapshot HISTORY, plus a one-time
     governed "record known vehicle context" workflow when no source exists (operator-observed provenance);
  2. swap-urgency × arrival-timing as a bounded Demo-suitability factor (Holly recompute);
  3. unresolved ORDER PATH — REVIEW candidates remain visible but are NOT selectable / reservable / plannable.
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
from elite.operatorstd import demo_board as DB


# ---- 2. pure-engine timing factor -----------------------------------------------------------------------
def _cand(cid, vel, td, **kw):
    d = {"cid": cid, "label": cid, "model": "QX65", "expected_demand": vel, "depth": 1,
         "has_incoming_or_order": True, "governed": True, "timing_days": td}
    d.update(kw)
    return d


class TestTimingFactor(unittest.TestCase):
    def test_urgency_zero_is_timing_inert(self):
        # no urgency -> the timing factor must not move scores at all (pure regression safety)
        r = DB.rank_demo_candidates([_cand("far", 3.0, 55), _cand("near", 3.0, 0)], urgency=0.0)
        self.assertEqual(r[0].proof["score"], r[1].proof["score"])

    def test_near_beats_far_on_a_tie(self):
        r = DB.rank_demo_candidates([_cand("far", 3.0, 55), _cand("near", 3.0, 0)], urgency=1.0)
        self.assertEqual(r[0].cid, "near")                       # on-ground > distant incoming, all else equal

    def test_timing_breaks_a_marginal_demand_lead(self):
        # 'far' has a marginally higher demand but arrives far out; under urgency the near unit wins
        r = DB.rank_demo_candidates([_cand("far", 3.2, 55), _cand("near", 3.0, 0)], urgency=1.0)
        self.assertEqual(r[0].cid, "near")

    def test_timing_does_not_overpower_material_retail_value(self):
        # 'far' is a materially stronger retail asset -> timing must NOT overturn it
        r = DB.rank_demo_candidates([_cand("far", 5.0, 55), _cand("near", 3.0, 0)], urgency=1.0)
        self.assertEqual(r[0].cid, "far")

    def test_no_placeable_unit_is_maximally_distant(self):
        r = DB.rank_demo_candidates([_cand("order", 3.0, None), _cand("near", 3.0, 0)], urgency=1.0)
        self.assertEqual(r[0].cid, "near")


# ---- 2. Holly recompute (operator integration) --------------------------------------------------------
class TestHollyTimingRecompute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        self.store = NewInvStore(self.conn, self.p.clock)
        # the three real Holly QX65 candidates (near-parity retail demand; different trims/colours/arrival)
        self.october = self._combo("85017", "QBE", "G")     # QX65 LUXE Radiant White / Graphite  — arrives 10/15
        self.sept11 = self._combo("85017", "QBE", "K")      # QX65 LUXE Radiant White / Stone Gray — arrives 9/11
        self.sept15 = self._combo("85117", "KBY", "G")      # QX65 SPORT Harbor Gray / Graphite    — arrives 9/15
        self._persist(self.october, 3.1)                    # marginally higher demand (why it led before timing)
        self._persist(self.sept11, 3.0)
        self._persist(self.sept15, 3.0)
        self._import([self._row("O", "SEROCT", "85017", "QBE", "G", "ONS", "2026-10-15"),
                      self._row("A", "SER911", "85017", "QBE", "K", "ONS", "2026-09-11"),
                      self._row("B", "SER915", "85117", "KBY", "G", "ONS", "2026-09-15")])

    def tearDown(self):
        self.p.close()

    def _combo(self, code, ext, inte):
        return resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE,
            source_ref="t")

    def _persist(self, comb, demand):
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
            expected_demand=demand, current_supply=0, future_supply=1, committed_supply=0, qualifying_supply=0,
            desired_ending_coverage={"target_units": 1.6}, need=2.0, excess=0.0, confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 2, "arrived_excess": 0, "incoming_excess": 0,
                                                 "monitor_months": []}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _row(self, stock, serial, code, ext, inte, loc, pm):
        return [stock, serial, "", "2026", "QX65", code, "QX65", "AUTO", ext, inte, "70000", "66000", loc, "", "", pm]

    def _import(self, rows):
        from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS
        xp = make_xlsx([HEADERS] + rows, sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:x",
                              effective_time=self.p.now_iso())

    def test_before_timing_october_leads_on_demand(self):
        cards = OP._demo_candidate_cards(self.p.app, SCOPE, today="2026-09-04", urgency=0.0)
        self.assertIn("Radiant White", cards[0]["build"])
        self.assertIn("Graphite", cards[0]["build"])            # October (highest demand) leads when timing is off
        self.assertNotIn("Stone Gray", cards[0]["build"])

    def test_after_timing_urgent_holly_gets_the_soonest_comparable_unit(self):
        # PLAN SWAP urgency + a bounded timing factor promotes the 9/11 LUXE unit over the marginally-stronger
        # but ~5-weeks-later October unit; the 9/15 unit stays behind the sooner 9/11 unit
        cards = OP._demo_candidate_cards(self.p.app, SCOPE, today="2026-09-04",
                                         urgency=OP._demo_urgency(DB.PLAN_SWAP))
        self.assertIn("Stone Gray", cards[0]["build"])          # 9/11 QX65 LUXE Radiant White / Stone Gray
        self.assertEqual(cards[0]["timing_days"], 7)
        self.assertIn("Radiant White", cards[1]["build"])       # October slips to #2
        self.assertIn("Graphite", cards[1]["build"])
        self.assertEqual(cards[1]["timing_days"], 41)


# ---- 3. execution gate: unresolved order paths are not selectable ---------------------------------------
class TestExecutionGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        self.store = NewInvStore(self.conn, self.p.clock)
        # an EXECUTABLE governed QX65 target (on-ground unit) that ranks #1, plus an UNRESOLVED one (no physical
        # unit, orderability unresolved) that stays a visible-but-non-selectable alternative
        self.executable = self._combo("85017", "QBE", "G")
        self.unresolved = self._combo("85217", "QBE", "K")
        self._persist(self.executable, 4.0, current=1)
        self._persist(self.unresolved, 2.5, current=0)
        self._import([self._row("R1", "REP651", "85017", "QBE", "G", "DLR-INV", "20")])
        self.full = self.p.p10.login(self.p.p10.op_full)

    def tearDown(self):
        self.p.close()

    def _combo(self, code, ext, inte):
        return resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE,
            source_ref="t")

    def _persist(self, comb, demand, *, current=0):
        self.store.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
            expected_demand=demand, current_supply=current, future_supply=0, committed_supply=0,
            qualifying_supply=current, desired_ending_coverage={"target_units": 1.6}, need=2.0, excess=0.0,
            confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": 2, "arrived_excess": 0, "incoming_excess": 0,
                                                 "monitor_months": []}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _row(self, stock, serial, code, ext, inte, loc, dis):
        return [stock, serial, "", "2026", "QX65", code, "QX65", "AUTO", ext, inte, "70000", "66000", loc, dis, "", ""]

    def _import(self, rows):
        from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS
        xp = make_xlsx([HEADERS] + rows, sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:x",
                              effective_time=self.p.now_iso())

    def _add_user(self, name, pref):
        self.full.post("/demos/user", {"name": name, "role": "Exec", "model_pref": pref})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        return roster[-1]["id"]

    def test_unresolved_order_path_is_visible_but_not_selectable(self):
        # the candidate has no on-ground/incoming unit and unresolved orderability
        self.assertFalse(OP._demo_order_orderable(self.p.app, SCOPE, self.unresolved.id))
        cards = OP._demo_candidate_cards(self.p.app, SCOPE, today="2026-09-04")
        card = next((c for c in cards if c["cid"] == self.unresolved.id), None)
        self.assertIsNotNone(card)                              # still VISIBLE as an alternative
        self.assertFalse(card["executable"])                   # ...but NOT selectable/executable

    def test_plan_swap_rejects_a_non_executable_reservation(self):
        uid = self._add_user("Kyle", "QX65")
        # assign an active demo so the workspace is live
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "KYLEDEMO651", "start": "2026-06-03", "mi": "50"})
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("Review order path", b)                  # the copy replaces "Select this replacement"
        # a server-side PLAN SWAP against the unresolved path must be refused (no reservation stored)
        self.full.post(f"/demos/user/{uid}/plan", {"cid": self.unresolved.id})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        u = next(x for x in roster if x["id"] == uid)
        self.assertIsNone((u.get("current") or {}).get("reservation"))


# ---- 1. active-Demo context backfill --------------------------------------------------------------------
class TestActiveDemoContextBackfill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        self.store = NewInvStore(self.conn, self.p.clock)
        self.qx80 = resolve_or_create_planning_combination(
            self.store, self.p.clock, {"model_code": "86117", "exterior": "KH3", "interior": "G"}, SCOPE,
            source_ref="t")
        self.full = self.p.p10.login(self.p.p10.op_full)

    def tearDown(self):
        self.p.close()

    def _row(self, stock, serial, loc, dis="", pm=""):
        return [stock, serial, "", "2026", "QX80", "86117", "QX80 PURE", "AUTO", "KH3", "G", "78900", "74000",
                loc, dis, "", pm]

    def _import(self, rows, eff):
        from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS
        xp = make_xlsx([HEADERS] + rows, sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:" + eff, effective_time=eff)

    def _roster(self, u):
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "demo_roster", [u])

    def test_history_backfills_context_after_unit_leaves_feed(self):
        # snapshot #1 (older) carries the demo unit on the lot (DIS 40); snapshot #2 (latest) no longer lists it
        self._import([self._row("S1", "331601", "DLR-INV", dis="40")], "2026-07-01T00:00:00Z")
        self._import([self._row("S9", "999999", "DLR-INV", dis="5")], "2026-09-01T00:00:00Z")
        self.assertEqual(OP._demo_current_build(self.p.app, SCOPE, "331601"), "")   # gone from the live feed
        hist = OP._demo_historical_context(self.p.app, SCOPE, "331601")
        self.assertIn("QX80", hist.get("build", ""))                                # recovered from history
        self.assertTrue(hist.get("in_stock_date"))                                  # in-stock date from DIS
        # the operator context surface reflects it, honestly labelled as snapshot-derived
        u = {"id": "u1", "name": "Holly", "model_pref": "QX80",
             "current": {"vin": "331601", "start": "2026-06-03", "mi_in": 10}}
        ctx = OP._demo_current_context(self.p.app, SCOPE, u, "2026-09-04")
        self.assertIn("QX80", ctx["build"])
        self.assertEqual(ctx["age_provenance"], "historical snapshot")
        self.assertFalse(ctx["incomplete"])

    def test_record_known_context_when_no_source_exists(self):
        # a demo VIN with NO snapshot and NO history -> context is incomplete and the record form is offered
        uid_user = {"id": "u1", "name": "Holly", "role": "Sales", "model_pref": "QX60",
                    "current": {"vin": "5N1AL1E53VC331601", "start": "2026-06-03", "mi_in": 20}, "history": []}
        self._roster(uid_user)
        b = self.full.get("/demos/user/u1").body
        self.assertIn("Record known vehicle context", b)
        # operator records source-backed known values -> stored as operator-observed provenance
        self.full.post("/demos/user/u1/context",
                       {"build": "QX60 LUXE AWD — Graphite Shadow", "stock": "H12345",
                        "in_stock_date": "2026-05-01"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        oc = roster[0]["current"]["observed_context"]
        self.assertEqual(oc["provenance"], "operator_observed")
        self.assertEqual(oc["in_stock_date"], "2026-05-01")
        ctx = OP._demo_current_context(self.p.app, SCOPE, roster[0], "2026-09-04")
        self.assertIn("QX60", ctx["build"])
        self.assertEqual(ctx["age_provenance"], "operator-observed")   # inv age from recorded in-stock date
        self.assertEqual(ctx["inv_age"], "126d")                       # 2026-05-01 -> 2026-09-04, NOT the demo start
        self.assertFalse(ctx["incomplete"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
