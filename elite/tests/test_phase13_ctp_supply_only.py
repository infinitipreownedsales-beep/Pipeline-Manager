"""CTP coverage via an honest SUPPLY-ONLY planning position (live fix 2026-09-02).

Kyle's live CTP loaded five QX80 production orders. Three 86317 (LUXE 2WD, demand-backed) resolved to KEEP; two
valid incoming builds — 86117 PURE 2WD and 86217 LUXE 4WD — with real supply but NO accepted demand history (and
no approved lineage) were REFUSED a plan position, so CTP had no official supply/demand position and showed
"Elite doesn't have a current supply/demand position for this build yet."

The authoritative planning rail (run_planning) now issues an HONEST supply-only position for such a cohort:
known supply is recorded, demand basis is UNKNOWN / NOT ASSERTED (Need & Excess never fabricated, never zeroed),
and NO demand lineage is created. CTP consumes that official position (one rail) and evaluates KEEP/CHANGE with
honest no-demand-basis language.
"""
import os
import tempfile
import unittest

from elite.newinv.fixtures import Phase4, SCOPE
from elite.newinv import supply_bridge as SB
from elite.newinv import demand_bridge as DB
from elite.newinv import board_recompute as BR
from elite.newinv import output as NIOUT
from elite.newinv.store import NewInvStore
from elite.newinv.planning_runner import PlanningContext, run_planning
from elite.ops.fixtures import Phase11, SCOPE as OPS_SCOPE
from elite.identity.translation import TranslationStore
from elite.identity import seed_infiniti as SEED
from elite.ui.views import operator as OP
from elite.tests.test_phase12_real_demand_planning_bridge import S, D
from elite.tests.test_phase12_dms_xlsx_adapter import make_xlsx, HEADERS as PIPE_HEADERS
from elite.workflow import ctp_intake as CTP
from elite.workflow.ctp_intake import Candidate, Reconciled, MATCHED


class TestSupplyOnlyUpstream(unittest.TestCase):
    """The authoritative planning rail issues a supply-only position for supply-present / no-demand cohorts."""

    def setUp(self):
        self.p4 = Phase4(os.path.join(tempfile.mkdtemp(), "e.db"))
        self.ctx = PlanningContext(scope=SCOPE, store=self.p4.store, clock=self.p4.clock,
                                   demand=self.p4.demand, forecast=self.p4.forecasts,
                                   planning=self.p4.planning, demand_cv=self.p4.demand_cv,
                                   plan_cv=self.p4.plan_cv, metadata=self.p4.stack.metadata)
        self.conn = self.p4.store.conn

    def _run(self, supply, demand):
        return run_planning(self.ctx, supply, demand, [], target_days_supply=60, current_month="2026-08")

    # 1 + 2 + 3: supply-present / no-demand cohort -> authoritative supply-only position; Need/Excess UNKNOWN;
    # no-demand is not turned into zero-demand; and no demand lineage is created.
    def test_supply_present_no_demand_issues_supply_only_position(self):
        sup = SB.build_supply([S("DLR-INV", "86117", "KH3", "G", dis=10),        # 86117 PURE 2WD arrived
                               S("ONS", "86117", "KH3", "G", pm="2026-11")], current_month="2026-08")  # +1 incoming
        res = self._run(sup, {})                                                 # NO demand at all
        self.assertEqual(res["issued_count"], 1)                                 # issued, not refused
        self.assertEqual(res["refused_count"], 0)
        o = res["outcomes"][0]
        self.assertTrue(o.issued)
        self.assertTrue(o.supply_only)
        self.assertEqual(o.planning_state, "supply_only")
        self.assertIsNone(o.refused_reason)
        self.assertEqual((o.current_supply, o.future_supply), (1, 1))            # supply recorded normally
        # Need and Excess remain UNKNOWN / NOT ASSERTED — never fabricated
        self.assertIsNone(o.need)
        self.assertIsNone(o.excess)
        self.assertEqual(res["total_need"], 0.0)                                 # no fabricated need aggregate
        self.assertEqual(res["total_excess"], 0.0)

        # the PERSISTED authoritative plan is honest: NULL need/excess/demand, distinct state, NO demand_result
        row = self.conn.execute(
            "SELECT planning_state, need, excess, expected_demand, demand_result_id, current_supply, future_supply "
            "FROM inventory_plan_result WHERE id=?", (o.plan_id,)).fetchone()
        self.assertEqual(row["planning_state"], "supply_only")
        self.assertIsNone(row["need"])                                           # Need NOT asserted (not zero)
        self.assertIsNone(row["excess"])                                         # Excess NOT asserted (not zero)
        self.assertIsNone(row["expected_demand"])                               # demand UNKNOWN, not zero-demand
        self.assertIsNone(row["demand_result_id"])                              # no demand issued; NO lineage borrow
        self.assertEqual((row["current_supply"], row["future_supply"]), (1, 1))

    # 7: a cohort WITH real accepted demand is unchanged (exact demand-backed position, NOT supply-only).
    def test_demand_backed_cohort_unchanged(self):
        built = DB.build_demand([D(f"2026{m:02d}", f"V{m}", "20", "8631", "KH3", "B") for m in range(1, 9)],
                                latest_midx=DB.midx_of("202608"), current_midx=DB.midx_of("202608"), part_frac=0.2)
        sup = SB.build_supply([S("DLR-INV", "86317", "KH3", "B", dis=10)], current_month="2026-08")  # 86317 LUXE 2WD
        res = self._run(sup, built["cohorts"])
        o = res["outcomes"][0]
        self.assertTrue(o.issued)
        self.assertFalse(o.supply_only)                                          # demand-backed, not supply-only
        self.assertEqual(o.evidence_tier, "exact")                              # its own accepted demand

    # 8: no demand-sharing lineage is created implicitly by the supply-only path.
    def test_supply_only_creates_no_demand_or_lineage(self):
        sup = SB.build_supply([S("DLR-INV", "86217", "KH3", "P", dis=5)], current_month="2026-08")  # 86217 LUXE 4WD
        res = self._run(sup, {})
        o = res["outcomes"][0]
        self.assertTrue(o.supply_only)
        # no demand_result rows were issued for this scope (no fabricated/borrowed demand)
        n_demand = self.conn.execute("SELECT COUNT(*) FROM demand_result WHERE store_scope=?", (SCOPE,)).fetchone()[0]
        self.assertEqual(n_demand, 0)


def _mk(order, cid, code, trim, drivetrain, arrival="2026-11"):
    c = Candidate(order_number=order, vin="", model="QX80", model_code=code, trim=trim, drivetrain=drivetrain)
    return Reconciled(c, MATCHED, {"combination_id": cid, "canonical": "c" + cid, "arrival_month": arrival},
                      "matched by order #", "order#", {"order_match_count": 1, "vin_match_count": 0})


class TestSupplyOnlyCtp(unittest.TestCase):
    """CTP consumes the official supply-only position and evaluates honestly — one rail, no CTP fabrication."""

    def _board(self, *, short_target=False):
        board = {
            "cid_8611": {"canonical": "c8611", "line": "QX80 PURE 2WD", "colors": "", "model": "QX80",
                         "trim": "PURE", "excess": 0, "short": 0, "supply_only": True,
                         "exterior_code": "K", "interior_code": "G", "color_complete": True},
            "cid_8621": {"canonical": "c8621", "line": "QX80 LUXE 4WD", "colors": "", "model": "QX80",
                         "trim": "LUXE", "excess": 0, "short": 0, "supply_only": True,
                         "exterior_code": "K", "interior_code": "P", "color_complete": True},
        }
        if short_target:
            board["cid_8699"] = {"canonical": "c8699", "line": "QX80 LUXE 2WD", "colors": "Black/Graphite",
                                 "model": "QX80", "trim": "PURE", "excess": 0, "short": 2, "supply_only": False,
                                 "exterior_code": "B", "interior_code": "G", "color_complete": True}
        return board

    # 4 + 5: 86117 / 86217 are now evaluable through the official supply-only position and KEEP with honest
    # no-demand-basis language when no eligible alternative has a stronger governed Need position.
    def test_supply_only_orders_keep_without_needed_language(self):
        recs = CTP.evaluate([_mk("TL22501", "cid_8611", "86117", "PURE", "2WD"),
                             _mk("TK79127", "cid_8621", "86217", "LUXE", "4WD")], self._board(), now="2026-09")
        self.assertEqual([r.decision_state for r in recs], [CTP.KEEP, CTP.KEEP])
        for r in recs:
            self.assertNotIn("CANT_EVALUATE", r.decision_state)
            self.assertIn("no established demand basis", r.reason_plain)
            self.assertNotIn("needed supply", r.reason_plain)        # never call a no-demand build "needed"
            self.assertNotIn("at or below", r.reason_plain)

    # 6: with a real eligible governed shortage (demand-backed) the supply-only order CHANGES toward it.
    def test_supply_only_order_changes_to_real_shortage(self):
        recs = CTP.evaluate([_mk("TL22501", "cid_8611", "86117", "PURE", "2WD")],
                            self._board(short_target=True), now="2026-09")
        self.assertEqual(recs[0].decision_state, CTP.CHANGE)
        self.assertEqual(recs[0].proposed_combination_id, "cid_8699")
        self.assertIn("no established demand basis", recs[0].reason_plain)
        self.assertIn("governed shortage supported by accepted demand evidence", recs[0].reason_plain)


def _q80(stock, serial, dis, code, ext, inte, loc, pm=""):
    return [stock, serial, "", "2026", "QX80", code, "QX80", "AUTO", ext, inte, "78900", "74000", loc, dis, "", pm]


class TestSupplyOnlyConsumerSafety(unittest.TestCase):
    """PROOF: no existing consumer of the issued plan reads a supply-only position as demand-certified
    Need/Excess. Built end-to-end through the real recompute so the persisted authoritative plan is exercised."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase11(os.path.join(self.tmp, "e.db"))
        self.p.app._p11 = self.p
        self.conn = self.p.stack.db.conn
        SEED.seed(TranslationStore(self.p.app.prefs, OPS_SCOPE))
        # 86117 PURE 2WD: real supply (1 arrived + 1 incoming), NO speed-to-sell demand loaded at all
        xp = make_xlsx([PIPE_HEADERS, _q80("S1", "900001", 10, "86117", "KH3", "G", "DLR-INV"),
                        _q80("", "TL22501", 0, "86117", "KH3", "G", "ONS", "2026-11")],
                       sheet_name="vehicleInventorySummary0")
        self.p.import_payload("new_inventory_pipeline_summary", xp, chash="sha256:s",
                              effective_time=self.p.now_iso())
        self.assertTrue(BR.recompute_board(self.p.app, OPS_SCOPE)["ok"])

    def tearDown(self):
        self.p.close()

    def _plan(self):
        pid = self.conn.execute("SELECT id FROM inventory_plan_result WHERE store_scope=? AND status='issued'",
                                (OPS_SCOPE,)).fetchone()["id"]
        return NewInvStore(self.conn, self.p.app.stack.clock).get_plan(pid)

    def test_persisted_position_is_honest_supply_only(self):
        p = self._plan()
        self.assertEqual(p.planning_state, "supply_only")
        self.assertIsNone(p.need)                 # Need NOT asserted
        self.assertIsNone(p.excess)               # Excess NOT asserted
        self.assertIsNone(p.expected_demand)      # demand UNKNOWN, not zero
        self.assertIsNone(p.demand_result_id)     # no demand issued; no lineage borrowed

    def test_dealer_call_is_supply_only_not_acquire_or_excess(self):
        call = NIOUT._call(self._plan())
        self.assertIn("SUPPLY ONLY", call)
        for banned in ("ACQUIRE", "EXCESS", "NO ACTION", "HOLD/REDUCE"):
            self.assertNotIn(banned, call)        # never a demand-certified action

    def test_certified_positions_and_cpo_board_treat_it_inertly(self):
        certs, _ = OP._certified_positions(self.p.app, OPS_SCOPE)
        self.assertTrue(certs)
        for c in certs:
            self.assertEqual((c["acquire_units"], c["arrived_excess"], c["incoming_excess"]), (0, 0, 0))
            self.assertTrue(c["supply_only"])     # marked, so no surface reads it as Need/Excess
        # the CPO acquire board (buy recommendations) never lists a supply-only combination as a buy
        self.assertEqual(OP._acquire_board(self.p.app, OPS_SCOPE), [])

    def test_ctp_board_position_present_but_asserts_no_need_or_excess(self):
        board = OP._ctp_board(self.p.app, OPS_SCOPE)
        self.assertTrue(board)                    # the combination IS on the board (CTP can now evaluate it)
        for b in board.values():
            self.assertEqual((b["excess"], b["short"]), (0, 0))
            self.assertTrue(b["supply_only"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
