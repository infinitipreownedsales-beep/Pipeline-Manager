"""Executive-Demo cockpit — operator/route + governed-identity + physical count-once acceptance (rebuild
2026-09-03). Covers acceptance 10, 11, 14, 15, 16, 17 end-to-end on the current governed architecture."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.identity.translation import TranslationStore
from elite.identity import seed_infiniti as SEED
from elite.ids import new_id
from elite.ui.views import operator as OP
from elite.ordering.cross_domain import committed_vins


def _combo(store, clock, code, ext, inte):
    return resolve_or_create_planning_combination(
        store, clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="demo-test")


def _persist(store, comb, *, acquire, current=0):
    store.add_plan(InventoryPlanResult(
        id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
        expected_demand=0.0, current_supply=current, future_supply=0, committed_supply=0, qualifying_supply=current,
        desired_ending_coverage={"target_units": 1.6}, need=float(acquire), excess=0.0, confidence="medium",
        evidence={"model": "m", "decision": {"acquire_units": acquire, "arrived_excess": 0, "incoming_excess": 0,
                                              "monitor_months": []}},
        policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
        status="issued", months=[]))


class TestDemoCockpitGoverned(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        store = NewInvStore(self.conn, self.p.clock)
        # governed QX80 target with a SINGLE on-ground physical unit
        self.gov = _combo(store, self.p.clock, "86117", "KH3", "G")
        _persist(store, self.gov, acquire=2, current=1)
        # a PHANTOM/ungoverned combination (the exact class from the live defect) — also "short"
        self.phantom = _combo(store, self.p.clock, "8311", "QBE", "C")
        _persist(store, self.phantom, acquire=9)
        self._add_unit("DEMOVIN0000GOV11", self.gov.id)
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _add_unit(self, vin, cid):
        self.conn.execute("INSERT INTO vehicle_unit(id,vin,identity_status,store_scope,created_at,version) "
                          "VALUES(?,?, 'resolved', ?, '2026-01-01T00:00:00Z', 1)", (f"vu_{vin}", vin, SCOPE))
        self.conn.execute("INSERT INTO current_supply_projection(id,vehicle_unit_id,combination_id,store_scope,"
                          "availability_state,age_days,retail_eligible,quality_status,confidence,status,"
                          "calculation_timestamp) "
                          "VALUES(?,?,?,?,'available_unsold',20,1,'ok','high','current','2026-01-01T00:00:00Z')",
                          (f"cs_{vin}", f"vu_{vin}", cid, SCOPE))
        self.conn.commit()

    def _add_user(self, name, pref, vin=None, start=None):
        self.full.post("/demos/user", {"name": name, "role": "Exec", "model_pref": pref})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        uid = roster[-1]["id"]
        if vin:
            self.full.post(f"/demos/user/{uid}/assign", {"vin": vin, "start": start or "2025-10-01", "mi": "40"})
        return uid

    # 10: an ungoverned / phantom combination is never a governed target -> never an executable replacement.
    def test_10_ungoverned_target_never_executable(self):
        gov_set = OP._demo_governed_combos(self.p.app, SCOPE)
        self.assertIn(self.gov.id, gov_set)                        # 86117 KH3/G is fully governed
        self.assertNotIn(self.phantom.id, gov_set)                 # 8311 QBE/C is not
        self._add_user("Holly", "QX80", vin="ASSIGNED00000HOL1", start="2025-10-01")
        b = self.full.get("/demos").body
        self.assertNotIn("8311", b)                                # the phantom code never surfaces
        self.assertNotIn("(unmapped)", b)

    # 11: last-on-lot protection is surfaced before pulling the replacement from retail.
    def test_11_last_on_lot_protection_surfaced(self):
        uid = self._add_user("Holly", "QX80", vin="ASSIGNED00000HOL1", start="2025-10-01")
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        meta, alloc, pools = OP._demo_cockpit(self.p.app, SCOPE, roster, "2026-01-02")
        self.assertEqual(alloc[uid]["path"], "USE NOW")            # the one on-ground governed unit
        self.assertEqual(len(pools[meta[uid]["target"]]["current"]), 1)   # it is the LAST one
        b = self.full.get("/demos").body
        self.assertIn("LAST ONE", b)                               # protect / reorder before pulling

    # 15: a VIN active as a demo is one current-use state — excluded from Retail supply (count-once).
    def test_15_active_demo_vin_is_count_once(self):
        self._add_user("Holly", "QX80", vin="ACTIVEDEMO000001", start="2025-10-01")
        committed = committed_vins(self.conn, SCOPE, self.p.app.prefs)
        self.assertEqual(committed.get("ACTIVEDEMO000001"), "demo")   # counted as demo, not free retail
        # and it is excluded from the demo replacement pools (never re-offered to another exec)
        c, i, _o = OP._demo_pools(self.p.app, SCOPE, self.gov.id)
        self.assertNotIn("ACTIVEDEMO000001", [u.vin for u in c])

    # 14: a returning demo contributes supply exactly once — it leaves the committed set, never double-counted.
    def test_14_returning_demo_contributes_supply_once(self):
        uid = self._add_user("Holly", "QX80", vin="RETURNING0000001", start="2025-10-01")
        self.assertIn("RETURNING0000001", committed_vins(self.conn, SCOPE, self.p.app.prefs))
        self.full.post(f"/demos/user/{uid}/return", {"mi": "1800", "date": "2026-01-02"})
        after = committed_vins(self.conn, SCOPE, self.p.app.prefs)
        self.assertNotIn("RETURNING0000001", after)                # returned -> no longer an active-demo commitment
        # never simultaneously counted: it was demo XOR retail, never both
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        u = next(x for x in roster if x["id"] == uid)
        self.assertIsNone(u["current"])                            # exactly one current-use state at a time

    # 16: assignment / mileage / return events populate the demo history (no longer "Nothing here").
    def test_16_events_populate_history(self):
        uid = self._add_user("Holly", "QX80", vin="HISTORYVIN000001", start="2025-10-01")
        self.full.post(f"/demos/user/{uid}/mileage", {"mi": "600"})
        self.full.post(f"/demos/user/{uid}/return", {"mi": "1800", "date": "2026-01-02"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        u = next(x for x in roster if x["id"] == uid)
        self.assertTrue(u.get("history"))                          # a completed cycle is recorded
        kinds = [e["kind"] for e in u.get("events", [])]
        self.assertIn("assignment", kinds)
        self.assertIn("return", kinds)
        self.assertTrue(any(o["source"] == "manual_reading" for o in u.get("mileage_obs", [])))
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertNotIn("Nothing here right now", b)

    # 17: the manager board shows NO full VINs and NO restricted economics ($).
    def test_17_board_has_no_full_vins_or_economics(self):
        self._add_user("Holly", "QX80", vin="FULLVIN000000HOL1", start="2025-10-01")
        b = self.full.get("/demos").body
        self.assertNotIn("FULLVIN000000HOL1", b)                   # full VIN never on the manager board
        self.assertIn("Unit", b)                                   # masked unit tag instead
        self.assertNotIn("$", b)                                   # no economics dollars on execution board


if __name__ == "__main__":
    unittest.main(verbosity=2)
