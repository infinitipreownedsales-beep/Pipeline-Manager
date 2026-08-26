"""CTP 'Not available configuration' operator feedback loop (live unblock 2026-08-26).

When Infiniti accepts a CTP evaluation but rejects the desired specification (restricted item above max /
production restriction / package unavailable / other), the operator marks that exact target NOT AVAILABLE for
THAT order. Elite then: records the OEM rejection as provenance, excludes the target from that order's feasible
set ONLY (never a global blacklist), re-runs the sequential CTP decision on the unchanged supply/demand board,
and returns the next-best certified-short target — repeatable — stopping at a feasible superior configuration or
KEEP (best available outcome) when every superior alternative is exhausted. The board is never mutated (nothing
was executed). State: RECOMMENDED CHANGE -> OEM REJECTED/NOT AVAILABLE -> NEXT BEST, and RECOMMENDED -> CONFIRMED
CHANGED. Mirrors the live TK65797 (QX65 SPORT AWD -> LUXE AWD) case.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.workflow import ctp_intake as CTP
from elite.newinv.store import NewInvStore
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id


# ---- A. engine-level proof (pure evaluate, the exact loop) ------------------------------------------------
class TestNotAvailableEngine(unittest.TestCase):
    def _board(self):
        # one over-supplied QX65 source (the current TK65797 SPORT AWD slot) and two certified-short QX65 LUXE
        # AWD targets. QBE/G ranks first (short 2 > DAT/K short 1), so it is the initial recommendation.
        return {
            "src": {"canonical": "85117 SPORT AWD GAT/G", "line": "QX65 SPORT AWD",
                    "colors": "Grey / Graphite", "model": "QX65", "excess": 2, "short": 0},
            "t_qbe": {"canonical": "85017 LUXE AWD QBE/G", "line": "QX65 LUXE AWD",
                      "colors": "Radiant White / Graphite", "model": "QX65", "excess": 0, "short": 2},
            "t_dat": {"canonical": "85017 LUXE AWD DAT/K", "line": "QX65 LUXE AWD",
                      "colors": "Deep Emerald / Stone Gray", "model": "QX65", "excess": 0, "short": 1},
        }

    def _order(self, num="TK65797"):
        c = CTP.Candidate(order_number=num, model="QX65", arrival_month="2026-11")
        return CTP.Reconciled(c, CTP.MATCHED, {"combination_id": "src", "model": "QX65", "arrival_month": "2026-11"},
                              "matched by order #", "order#")

    def test_initial_recommendation_is_highest_short_target(self):
        r = CTP.evaluate([self._order()], self._board())[0]
        self.assertEqual(r.decision_state, CTP.CHANGE)
        self.assertEqual(r.proposed_combination_id, "t_qbe")     # QBE/G (short 2) first

    def test_not_available_returns_next_best_then_keep(self):
        board = self._board()
        okey = CTP.order_key("TK65797", "")
        # round 1: QBE/G marked NOT AVAILABLE for this order -> next-best DAT/K
        infeasible = {okey: [{"target": "t_qbe", "target_canonical": "85017 LUXE AWD QBE/G",
                              "reason": "above_maximum", "note": "restricted item above max", "at": "2026-08-26T00:00"}]}
        r1 = CTP.evaluate([self._order()], board, infeasible=infeasible)[0]
        self.assertEqual(r1.decision_state, CTP.CHANGE)
        self.assertEqual(r1.proposed_combination_id, "t_dat")    # next-best certified-short target
        self.assertEqual(len(r1.rejected_targets), 1)            # OEM rejection preserved as provenance
        # round 2: DAT/K also NOT AVAILABLE -> every superior alternative exhausted -> KEEP (best available)
        infeasible[okey].append({"target": "t_dat", "target_canonical": "85017 LUXE AWD DAT/K",
                                 "reason": "package_component_unavailable", "note": "", "at": "2026-08-26T00:05"})
        r2 = CTP.evaluate([self._order()], board, infeasible=infeasible)[0]
        self.assertEqual(r2.decision_state, CTP.KEEP)
        self.assertTrue(r2.proof.get("best_available_after_exhaustion"))
        self.assertIn("best available outcome", r2.reason_plain)
        self.assertEqual(len(r2.rejected_targets), 2)

    def test_mark_is_per_order_not_global(self):
        # two orders on the same over-supplied source; only order A rejects QBE/G. Order B must still get QBE/G.
        board = self._board()
        a, b = self._order("TKAAA"), self._order("TKBBB")
        infeasible = {CTP.order_key("TKAAA", ""): [{"target": "t_qbe", "reason": "above_maximum"}]}
        recs = CTP.evaluate([a, b], board, infeasible=infeasible)
        by_order = {r.order_number: r for r in recs}
        self.assertEqual(by_order["TKAAA"].proposed_combination_id, "t_dat")   # A skipped QBE/G
        self.assertEqual(by_order["TKBBB"].proposed_combination_id, "t_qbe")   # B not blacklisted

    def test_board_not_mutated_by_marks(self):
        # a mark alone (order that does NOT reconcile to an excess source) must not consume board excess/short
        board = self._board()
        before = {k: (v["excess"], v["short"]) for k, v in board.items()}
        infeasible = {CTP.order_key("TK65797", ""): [{"target": "t_qbe", "reason": "above_maximum"}]}
        CTP.evaluate([self._order()], board, infeasible=infeasible)
        after = {k: (v["excess"], v["short"]) for k, v in board.items()}
        self.assertEqual(before, after)                          # evaluate copies the board; source unchanged


# ---- B. operator route loop (persistence + re-evaluation through the page) --------------------------------
class TestNotAvailableRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        st = NewInvStore(self.conn, self.p.clock)
        self.src = self._combo(st, "8511", "GAT", "G")          # QX65 SPORT AWD — over-supplied
        self.qbe = self._combo(st, "8501", "QBE", "G")          # QX65 LUXE AWD — short 2
        self.dat = self._combo(st, "8501", "DAT", "K")          # QX65 LUXE AWD — short 1
        self._persist(st, self.src, acq=0, exc=2)
        self._persist(st, self.qbe, acq=2, exc=0)
        self._persist(st, self.dat, acq=1, exc=0)
        # pipeline: TK65797 -> src (certified projection carries the board position)
        self.conn.execute("INSERT INTO production_order(id, manufacturer_order_id, vin, store_scope, "
                          "identity_status, created_at, version) "
                          "VALUES('po1','TK65797','', ?, 'resolved','2026-08-26T10:00:00Z', 1)", (SCOPE,))
        self.conn.execute("INSERT INTO future_supply_projection(id, store_scope, combination_id, arrival_month, "
                          "production_order_id, status, calculation_timestamp) "
                          "VALUES('fs1', ?, ?, '2026-11','po1','current','2026-08-26T10:00:00Z')",
                          (SCOPE, self.src.id))
        self.conn.commit()
        cand = vars(CTP.Candidate(order_number="TK65797", model="QX65", arrival_month="2026-11"))
        self.p.app.prefs.set_pref(f"scope::{SCOPE}", "ctp_session",
                                  {"files": [{"id": "f1", "name": "qx65.csv", "model": "QX65",
                                              "candidates": [cand]}]})
        self.full = self.p.login(self.p.op_full)
        self.okey = CTP.order_key("TK65797", "")

    def tearDown(self):
        self.p.close()

    def _combo(self, st, c, e, i):
        return resolve_or_create_planning_combination(
            st, self.p.clock, {"model_code": c, "exterior": e, "interior": i}, SCOPE, source_ref="t")

    def _persist(self, st, cb, *, acq, exc):
        st.add_plan(InventoryPlanResult(
            id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=cb.id,
            expected_demand=0.0, current_supply=1, future_supply=0, committed_supply=0, qualifying_supply=1,
            desired_ending_coverage={"target_units": 1.6}, need=float(acq), excess=float(exc), confidence="medium",
            evidence={"model": "m", "decision": {"acquire_units": acq, "arrived_excess": exc, "incoming_excess": 0,
                                                 "target_level": 1.6, "incoming_in_horizon": 0, "dts_burden": 1.0}},
            policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
            status="issued", months=[]))

    def _infeasible(self):
        return self.p.app.prefs.get_pref(f"scope::{SCOPE}", "ctp_infeasible", default={})

    def test_full_loop_qbe_then_dat_then_keep_and_confirm(self):
        # translations aren't seeded here, so colors render as codes; assert on combination identity instead.
        def _change_target(body):
            """The proposed target combination id from the CHANGE card's not-available form."""
            import re
            m = re.search(r'action="/ctp/not-available".*?name=target value="([^"]+)"', body, re.S)
            return m.group(1) if m else None

        with patch("elite.newinv.board_recompute.board_status", return_value={"state": "current"}):
            # round 0 — CHANGE to the QBE/G LUXE AWD target (short 2, ranks first)
            b0 = self.full.get("/ctp").body
            self.assertIn("RECOMMENDED CHANGE", b0)
            self.assertIn("Not available configuration", b0)     # the operator feedback control exists
            self.assertEqual(_change_target(b0), self.qbe.id)    # QBE/G first

            # mark QBE/G NOT AVAILABLE for this order (above max)
            self.full.post("/ctp/not-available", {"order": self.okey, "target": self.qbe.id,
                                                   "target_canonical": "QX65 LUXE AWD QBE/G",
                                                   "reason": "above_maximum", "note": "restricted item above max"})
            marks = self._infeasible().get(self.okey, [])
            self.assertEqual([m["target"] for m in marks], [self.qbe.id])   # recorded, per-order

            # round 1 — re-evaluated NEXT BEST: DAT/K
            b1 = self.full.get("/ctp").body
            self.assertEqual(_change_target(b1), self.dat.id)    # DAT/K now recommended
            self.assertIn("NOT AVAILABLE", b1)                   # provenance trail rendered
            self.assertIn("QX65 LUXE AWD QBE/G", b1)             # the rejected target is shown in the trail

            # mark DAT/K NOT AVAILABLE too -> exhausted -> KEEP best available
            self.full.post("/ctp/not-available", {"order": self.okey, "target": self.dat.id,
                                                   "target_canonical": "QX65 LUXE AWD DAT/K",
                                                   "reason": "package_component_unavailable", "note": ""})
            b2 = self.full.get("/ctp").body
            self.assertIn("best available outcome", b2)
            self.assertIn("KEEP", b2)
            self.assertIsNone(_change_target(b2))                # no CHANGE card remains

            # board untouched: certified excess on the source is still 2 (nothing executed)
            row = self.conn.execute("SELECT excess FROM inventory_plan_result WHERE combination_id=?",
                                    (self.src.id,)).fetchone()
            self.assertEqual(int(row["excess"]), 2)

            # reset marks -> QBE/G recommendation returns; confirm-change records CONFIRMED CHANGED
            self.full.post("/ctp/available-reset", {"order": self.okey})
            self.assertEqual(self._infeasible().get(self.okey, []), [])
            b3 = self.full.get("/ctp").body
            self.assertEqual(_change_target(b3), self.qbe.id)
            self.full.post("/ctp/confirm-change", {"order": self.okey, "target": self.qbe.id})
            b4 = self.full.get("/ctp").body
            self.assertIn("CONFIRMED CHANGED", b4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
