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
        # three-pool Demo decision (USE NOW / WAIT FOR INCOMING / ORDER FOR DEMO), physical-first
        self.assertIn("Demo decision", b)
        self.assertTrue(any(c in b for c in ("USE NOW", "WAIT FOR INCOMING", "ORDER FOR DEMO",
                                             "PENDING DEMO ECONOMICS")))
        self.assertIn("Current on-ground VINs", b)
        # call-up board answers by model
        self.assertIn("Best available QX60 demo", self.full.get("/demos").body)

    # Dealer Trade Their: paste inventory, best-ask ranks, Unavailable promotes next
    def test_their_trade_unavailable_promotes(self):
        # A specific physical DLR-INV unit is an actionable, identity-bearing candidate: it surfaces as an
        # AVAILABLE-NOW ask, and marking it unavailable excludes that exact unit (by its parsed source index).
        st = NewInvStore(self.conn, self.p.clock)
        self._persist(st, self._combo(st, "8521", "GAT", "N"), acq=2, exc=0)
        raw = ("12\tNalley INFINITI / Atlanta\tNIDVC60615\t606152\tQX65 AUTO AWD\tAUTO\t"
               "GAT\tN\t$64,815\t$62,267\t23\t\tDLR-INV")
        self.full.post("/dealer-trade/their", {"requested": "QX65 something", "inv": raw})
        b = self.full.get("/dealer-trade", tab="their").body
        self.assertIn("Best ask by availability", b)
        self.assertIn("AVAILABLE NOW", b)
        self.assertIn("NIDVC60615", b)                      # stock preserved
        self.assertIn("606152", b)                          # serial preserved
        self.full.post("/dealer-trade/their/unavailable", {"idx": "0"})
        b2 = self.full.get("/dealer-trade", tab="their").body
        self.assertIn("unavailable", b2.lower())
        self.assertIn("NIDVC60615", b2)                     # identity preserved on the unavailable row

    def test_their_trade_tiers_physical_dlr_inv_above_future_ons(self):
        # LIVE NALLEY CASE: a physical DLR-INV GAT/N unit plus two future ONS orders (exact GAT/N and XEX/G).
        # Availability must NOT be flattened: the immediate physical unit surfaces as the AVAILABLE-NOW ask with
        # its full identity, and the future orders keep their order/serial + ETA and are labeled FUTURE — a
        # future/order row never silently occupies the immediate slot.
        st = NewInvStore(self.conn, self.p.clock)
        self._persist(st, self._combo(st, "8521", "GAT", "N"), acq=2, exc=0)
        raw = "\n".join([
            "12\tNalley INFINITI / Atlanta\tNIDVC60615\t606152\tQX65 AUTO AWD\tAUTO\tGAT\tN\t$64,000\t$62,000\t23\t\tDLR-INV",
            "0\tGrubbs INFINITI\t\t900111\tQX65 AUTO AWD\tAUTO\tGAT\tN\t$65,000\t$63,000\t0\t2026-12\tONS",
            "0\tGrubbs INFINITI\t\t900222\tQX65 AUTO AWD\tAUTO\tXEX\tG\t$65,000\t$63,000\t0\t2027-01\tONS",
        ])
        self.full.post("/dealer-trade/their", {"requested": "QX65 something", "inv": raw})
        b = self.full.get("/dealer-trade", tab="their").body
        # best-per-tier: immediate physical unit and future order are shown side by side, not merged
        self.assertIn("BEST AVAILABLE-NOW ASK", b)
        self.assertIn("BEST FUTURE / ORDER OPPORTUNITY", b)
        self.assertLess(b.index("BEST AVAILABLE-NOW ASK"), b.index("BEST FUTURE / ORDER OPPORTUNITY"))
        # the physical DLR-INV unit keeps its complete identity and is tier 1
        self.assertIn("NIDVC60615", b)
        self.assertIn("606152", b)
        self.assertIn("DLR-INV", b)
        # the future ONS orders keep their real order/serial + ETA, labeled FUTURE (not anonymous)
        self.assertIn("Serial/Order 900111", b)
        self.assertIn("2026-12", b)
        self.assertIn("FUTURE", b)
        # in the ranked table the immediate physical unit (tier 1) precedes the future ONS orders (tier 3)
        tbl = b[b.index("What we should ask for back"):]
        self.assertLess(tbl.index("NIDVC60615"), tbl.index("900111"))

    def test_their_trade_real_nna_tsv_ranks_exact_combination(self):
        # Real browser clipboard shape from NNA: tab-separated rows with hidden model-code metadata stripped.
        st = NewInvStore(self.conn, self.p.clock)
        self._persist(st, self._combo(st, "8521", "GAT", "N"), acq=2, exc=0)

        raw = (
            "532\tGRUBBS INFINITI S ANTONIO\tVC601030\t601030\tQX65 AUTO AWD\tAUTO\t"
            "GAT\tG\t$64,815\t$ 62,267\t80\t05/28/2026\tSUV\n"
            "532\tGRUBBS INFINITI S ANTONIO\tVC605214\t605214\tQX65 AUTO AWD\tAUTO\t"
            "GAT\tN\t$65,905\t$ 63,296\t16\t07/30/2026\tSUV"
        )

        self.full.post("/dealer-trade/their", {
            "requested": "QX65 something",
            "inv": raw,
        })

        b = self.full.get("/dealer-trade", tab="their").body

        self.assertIn("2 external candidates parsed", b)
        self.assertIn("Exact shortage: QX65 8521 GAT/N (need 2)", b)
        self.assertIn("VC605214", b)
        self.assertIn("VC601030", b)

        # Exact GAT/N shortage must rank above same-code/same-exterior GAT/G within the same availability tier,
        # regardless of the latter unit being substantially older. Both are physical DLR-INV units.
        ranked = b[b.index("What we should ask for back (by availability, ranked)"):]
        self.assertLess(ranked.index("VC605214"), ranked.index("VC601030"))

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

        # effective-dated program inputs (historical month; value + caps) via the durable Program Inputs page
        self.full.post("/program-inputs/icv", {"effective_month": "2026-01", "model": "QX60", "trim": "LUXE",
                                               "value": "3500"})
        self.full.post("/program-inputs/velocity", {"effective_month": "2026-01", "model": "QX60", "trim": "LUXE",
                                                    "value": "1500", "day_cap": "120", "mile_cap": "9000"})
        from elite.loaner.program_inputs import ProgramInputsStore
        st = ProgramInputsStore(self.p.app.prefs, SCOPE)
        self.assertEqual(st.applicable("icv", "QX60", "2026-02", trim="LUXE").value, 3500)
        self.assertEqual(st.entries("velocity")[0].mile_cap, 9000)

    def test_backend_unchanged(self):
        self.full.get("/"); self.full.get("/data"); self.full.get("/wholesale")
        self.assertEqual(current_version(self.conn), 12)
        for t in ("vehicle_unit", "production_order"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
