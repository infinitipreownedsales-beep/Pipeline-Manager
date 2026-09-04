"""Demo LIVE-closeout — three specific defects (2026-09-04).

1. arrival timing parses the REAL feed formats (US M/D/YYYY specific dates -> real day counts; month-only stays
   month-level and never fabricates a day), and it actually reorders equal-demand candidates;
2. one canonical unit identity — a short serial is never truncated, and the candidate card, Swap Plan and
   reservation show identical identifiers;
3. one normal swap-execution rail for an active demo (the legacy assign/return form is behind Admin/Manual
   Recovery).
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


class TestEtaParsing(unittest.TestCase):
    T = "2026-09-04"

    def test_us_specific_dates_give_real_day_counts(self):
        self.assertEqual(OP._demo_eta_parse("09/11/2026", self.T), (7, "day", "2026-09-11"))
        self.assertEqual(OP._demo_eta_parse("09/15/2026", self.T), (11, "day", "2026-09-15"))

    def test_iso_specific_date(self):
        self.assertEqual(OP._demo_eta_parse("2026-09-11", self.T), (7, "day", "2026-09-11"))

    def test_month_only_stays_month_level(self):
        d, gran, disp = OP._demo_eta_parse("2026-10", self.T)
        self.assertEqual((gran, disp), ("month", "Oct 2026"))       # never a fabricated specific day
        self.assertEqual(d, 27)                                     # Sep 4 -> Oct 1 (conservative month anchor)
        self.assertEqual(OP._demo_eta_parse("October 2026", self.T), (27, "month", "Oct 2026"))
        self.assertEqual(OP._demo_eta_parse("10/2026", self.T), (27, "month", "Oct 2026"))

    def test_unparseable_is_none(self):
        self.assertEqual(OP._demo_eta_parse("whenever", self.T), (None, "none", ""))
        self.assertEqual(OP._demo_eta_parse("", self.T), (None, "none", ""))


class TestOpRef(unittest.TestCase):
    def test_short_serial_is_never_truncated(self):
        self.assertEqual(OP._demo_op_ref("UQ38296"), "UQ38296")    # 7-char serial shown in FULL
        self.assertEqual(OP._demo_op_ref("Q38296"), "Q38296")
        self.assertEqual(OP._demo_op_ref("A" * 17), "A" * 6)       # a real 17-char VIN is masked to last 6


def _row(stock, serial, code, ext, inte, loc, pm="", dis=""):
    return [stock, serial, "", "2026", "QX80", code, "QX80 PURE", "AUTO", ext, inte, "78900", "74000",
            loc, dis, "", pm]


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, SCOPE))
        self.store = NewInvStore(self.conn, self.p.clock)
        self.full = self.p.p10.login(self.p.p10.op_full)

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

    def _import(self, rows):
        from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS
        xp = make_xlsx([HEADERS] + rows, sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:x",
                              effective_time=self.p.now_iso())

    def _add_active(self, name, pref, vin):
        self.full.post("/demos/user", {"name": name, "role": "Exec", "model_pref": pref})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        uid = roster[-1]["id"]
        self.full.post(f"/demos/user/{uid}/assign", {"vin": vin, "start": "2026-06-03", "mi": "50"})
        return uid


class TestTimingReranksLiveHolly(_Base):
    def setUp(self):
        super().setUp()
        # three QX65 candidates with the SAME demand/depth, differing only in trim/colour and ARRIVAL, expressed
        # in the real feed formats (US specific dates for 9/11 & 9/15; month-only for October)
        self.oct_ = self._combo("85017", "QBE", "G")     # QX65 LUXE Radiant White / Graphite  — month-only Oct
        self.s911 = self._combo("85017", "QBE", "K")     # QX65 LUXE Radiant White / Stone Gray — 09/11/2026
        self.s915 = self._combo("85117", "KBY", "G")     # QX65 SPORT Harbor Gray / Graphite    — 09/15/2026
        for c in (self.oct_, self.s911, self.s915):
            self._persist(c, 3.0)                         # identical visible demand
        self._import([
            self._q65("O", "SEROCT", "85017", "QBE", "G", "2026-10"),        # month-only
            self._q65("A", "SER911", "85017", "QBE", "K", "09/11/2026"),     # US specific date
            self._q65("B", "SER915", "85117", "KBY", "G", "09/15/2026")])

    def _q65(self, stock, serial, code, ext, inte, eta):
        # put the ETA in the ETA column (index 14), like the real export
        return [stock, serial, "", "2026", "QX65", code, "QX65", "AUTO", ext, inte, "70000", "66000",
                "ONS", "", eta, ""]

    def test_specific_and_month_level_timing(self):
        self.assertEqual(OP._demo_timing(self.p.app, SCOPE, self.s911.id, "2026-09-04")[0], 7)
        self.assertEqual(OP._demo_timing(self.p.app, SCOPE, self.s915.id, "2026-09-04")[0], 11)
        octd, octlabel, octdisp, octgran = OP._demo_timing(self.p.app, SCOPE, self.oct_.id, "2026-09-04")
        self.assertEqual(octgran, "month")
        self.assertIn("Oct 2026", octlabel)
        self.assertIn("month-level", octlabel)
        self.assertNotIn("~21d", octlabel)                          # the old fabricated fallback is gone

    def test_equal_demand_reranks_to_soonest_under_urgency(self):
        from elite.operatorstd import demo_board as DB
        cards = OP._demo_candidate_cards(self.p.app, SCOPE, today="2026-09-04",
                                         urgency=OP._demo_urgency(DB.PLAN_SWAP))
        self.assertIn("Stone Gray", cards[0]["build"])              # 9/11 wins on timing when demand is equal
        self.assertEqual(cards[0]["timing_days"], 7)
        # and it did not simply become "earliest wins": the 9/15 SPORT is behind the sooner 9/11 LUXE, and
        # October (month-level) is last of the three
        octcard = next(c for c in cards if "Radiant White" in c["build"] and "Graphite" in c["build"])
        self.assertGreater(octcard["timing_days"], cards[0]["timing_days"])


class TestIdentifierContract(_Base):
    def setUp(self):
        super().setUp()
        self.gov = self._combo("86117", "KH3", "G")
        self._persist(self.gov, 4.0)
        # an incoming unit whose Pipeline/Elite operational id is a 7-char serial (must never be truncated)
        self._import([_row("SI", "UQ38296", "86117", "KH3", "G", "ONS", pm="2026-11")])
        self.uid = self._add_active("Holly", "QX80", "HOLLYDEMO80")

    def test_serial_identity_is_consistent_across_card_plan_and_reservation(self):
        b = self.full.get(f"/demos/user/{self.uid}").body
        self.assertIn("Pipeline unit UQ38296", b)                  # candidate card
        self.assertNotIn("Unit Q38296", b)                         # the old truncation contradiction is gone
        # PLAN SWAP the (auto-selected #1) replacement, then the reservation shows the SAME id
        self.full.post(f"/demos/user/{self.uid}/plan", {"cid": self.gov.id})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        res = next(x for x in roster if x["id"] == self.uid)["current"]["reservation"]
        self.assertEqual(res["op_id"], "UQ38296")
        self.assertEqual(res["identity"]["pipeline_unit"], "UQ38296")
        b2 = self.full.get(f"/demos/user/{self.uid}").body
        self.assertIn("RESERVED", b2)
        self.assertIn("Pipeline unit UQ38296", b2)                 # reservation shows the identical id
        self.assertNotIn("Unit Q38296", b2)


class TestSingleExecutionRail(_Base):
    def setUp(self):
        super().setUp()
        self.gov = self._combo("86117", "KH3", "G")
        self._persist(self.gov, 4.0)
        self._import([_row("R1", "REP801", "86117", "KH3", "G", "DLR-INV", dis="15")])

    def test_active_demo_hides_legacy_form_behind_recovery(self):
        uid = self._add_active("Holly", "QX80", "HOLLYDEMO80")
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("PLAN SWAP", b)                              # the governed rail is present
        self.assertIn("Admin / Manual Recovery", b)               # legacy form is disclosed, not a normal button
        self.assertNotIn("<h3>Assign / swap</h3>", b)             # the old normal-execution card is gone
        self.assertNotIn("<h3>Assign demo</h3>", b)               # ...and there is no normal assign card either

    def test_no_active_demo_offers_assign(self):
        self.full.post("/demos/user", {"name": "Kyle", "role": "Exec", "model_pref": "QX80"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        uid = roster[-1]["id"]
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("Assign demo", b)                           # first assignment is the ordinary path
        self.assertNotIn("Admin / Manual Recovery", b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
