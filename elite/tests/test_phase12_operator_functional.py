"""Functional daily workflows: Wholesale copy list, Demos roster + mileage, Dealer Trade unavailable-promote,
Data bench/unavailable/program-settings persistence, CTP render — and the ZERO-PLACEHOLDER law: no daily
operator page says a workflow is not built / not wired / deferred. Certified board read-only."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id

FORBIDDEN = ["not yet built", "not built", "not wired", "intentionally deferred", "coming soon",
             "no roster", "specialized workflow", "available to an administrator", "is deferred"]


class TestOperatorFunctional(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        st = NewInvStore(self.conn, self.p.clock)
        self._persist(st, self._combo(st, "8501", "QBE", "G"), acq=2, exc=0)
        self._persist(st, self._combo(st, "8481", "XKJ", "K"), acq=0, exc=3)
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _combo(self, st, c, e, i):
        return resolve_or_create_planning_combination(
            st, self.p.clock, {"model_code": c, "exterior": e, "interior": i}, SCOPE, source_ref="t")

    def _persist(self, st, cb, *, acq, exc):
        st.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=1, future_supply=0, committed_supply=0, qualifying_supply=1,
            desired_ending_coverage={"target_units": 1.6}, need=1.0, excess=float(exc), confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": exc, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 0, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    # ZERO-PLACEHOLDER law across every daily route
    def test_no_placeholder_wording_on_daily_pages(self):
        for path in ("/", "/ordering", "/ordering/cpo", "/ordering/ppo", "/dealer-trade", "/wholesale",
                     "/demos", "/ctp", "/data", "/service-loaner"):
            body = self.full.get(path).body.lower()
            for word in FORBIDDEN:
                self.assertNotIn(word, body, f"{word!r} on {path}")

    # Wholesale ranked list + dealer-safe copy text (no internal reasoning)
    def test_wholesale_copy_list(self):
        b = self.full.get("/wholesale").body
        self.assertIn("What to move first", b)
        self.assertIn("QX60 8481 XKJ/K — 3 available", b)   # dealer-safe combination + qty only
        self.assertIn("Copy dealer list", b)

    # Demos: add user -> assign -> return; mileage history persists and velocity computes
    def test_demos_roster_and_mileage(self):
        self.full.post("/demos/user", {"name": "Nathan", "role": "Sales", "model_pref": "QX60"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        uid = roster[0]["id"]
        self.full.post(f"/demos/user/{uid}/assign", {"vin": "VINX", "start": "2026-01-01", "mi": "100"})
        self.full.post(f"/demos/user/{uid}/return", {"mi": "1300", "date": "2026-01-13"})
        roster = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "demo_roster", default=[])
        self.assertEqual(len(roster[0]["history"]), 1)
        self.assertEqual(roster[0]["history"][0]["miles"], 1200)     # 1300-100
        b = self.full.get(f"/demos/user/{uid}").body
        self.assertIn("Nathan", b)
        self.assertIn("Next demo", b)
        # call-up board answers by model
        self.assertIn("Best available QX60 demo", self.full.get("/demos").body)

    # Dealer Trade Their: paste inventory, best-ask ranks, Unavailable promotes next
    def test_their_trade_unavailable_promotes(self):
        self.full.post("/dealer-trade/their", {"requested": "QX60 something",
                                              "inv": "QX60 LUXE unit A\nQX80 unit B"})
        b = self.full.get("/dealer-trade", tab="their").body
        self.assertIn("Best ask", b)
        self.full.post("/dealer-trade/their/unavailable", {"idx": "0"})
        b2 = self.full.get("/dealer-trade", tab="their").body
        self.assertIn("unavailable", b2.lower())

    # Data: bench persists + excludes from CPO; unavailable interval persists; ICV/Velocity program persists
    def test_data_controls_persist(self):
        # bench QX65 acquire combo -> disappears from CPO
        ident = self.conn.execute("SELECT canonical_identity FROM sellable_combination WHERE canonical_identity LIKE ?",
                                  ("%model_code=8501|%",)).fetchone()["canonical_identity"]
        from elite.ui.views.domains import _readable
        readable = _readable(ident)
        self.assertIn(readable, self.full.get("/ordering/cpo").body)
        self.full.post("/data/bench", {"combo": readable})
        self.assertNotIn(readable, self.full.get("/ordering/cpo").body)   # benched excluded from ordering
        self.full.post("/data/bench/restore", {"combo": readable})
        self.assertIn(readable, self.full.get("/ordering/cpo").body)      # restored

        self.full.post("/data/unavailable", {"vin": "VINU", "reason": "body shop", "start": "2026-01-05"})
        un = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "unavailable", default=[])
        self.assertEqual(un[0]["vin"], "VINU")
        self.full.post("/data/unavailable/return", {"idx": "0"})
        un = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "unavailable", default=[])
        self.assertTrue(un[0]["end"])                                    # interval preserved with an end date

        self.full.post("/data/program/icv", {"eff": "2026-01", "model": "QX60", "trim": "LUXE", "amount": "3500"})
        self.full.post("/data/program/velocity", {"eff": "2026-01", "model": "QX60", "trim": "LUXE",
                                                  "amount": "1500", "day_cap": "120", "mile_cap": "9000"})
        icv = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "icv_program", default=[])
        vel = self.p.app.prefs.get_pref(f"scope::{SCOPE}", "velocity_program", default=[])
        self.assertEqual(icv[0]["amount"], 3500)
        self.assertEqual(vel[0]["mile_cap"], 9000)

    def test_backend_unchanged(self):
        self.full.get("/"); self.full.get("/data"); self.full.get("/wholesale")
        self.assertEqual(current_version(self.conn), 12)
        for t in ("vehicle_unit", "production_order"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
