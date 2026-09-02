"""PPO closeout — make today's pre-produced offers operationally real (live acceptance 2026-09-02).

Kyle's ACTUAL FIRM/PARTIAL/DENY now (a) drives the remaining portfolio, (b) becomes governed Committed Supply
on the EXISTING SupplyCommitment rail (counted once with CPO and reconciled against Production Orders), and (c)
preserves the machine recommendation at the moment he acted, so a later recomputation cannot rewrite an
override. Merely offered/unworked rows never create supply; clearing a window cancels committed units through an
explicit governed reversal, never a silent delete.
"""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.newinv.store import NewInvStore
from elite.newinv.supply import SupplyService
from elite.newinv.dms_identity import resolve_or_create_planning_combination
from elite.newinv.models import InventoryPlanResult
from elite.ids import new_id
from elite.ordering import ppo_commitments as PPO
from elite.ui.views import operator as OP


def _kf(o):
    return o.get("combo")


# ---------------- A. portfolio engine (pure): worked decisions govern the remaining state ------------------
class TestWorkedPortfolio(unittest.TestCase):
    def _cert(self, need):
        return [{"key": "X", "label": "QX80 X", "acquire_units": need}]

    def _offers(self, n):
        return [{"id": chr(65 + i), "combo": "X", "quantity": 1} for i in range(n)]

    def test_1_full_offered_set_gets_machine_recs(self):
        r = PPO.evaluate_window(self._offers(3), self._cert(2), key_for_offer=_kf)
        recs = sorted(v.recommendation for v in r["verdicts"].values())
        self.assertEqual(recs, ["DENY", "FIRM", "FIRM"])          # from official certified Need = 2

    def test_2_recommendations_alone_do_not_commit(self):
        # evaluate_window is pure — it records no operator decision, so nothing is worked and nothing is firmed
        r = PPO.evaluate_window(self._offers(3), self._cert(2), key_for_offer=_kf)
        self.assertEqual(r["counts"]["firmed"], 0)
        self.assertEqual(r["worked"], {})

    def test_6_firming_one_changes_remaining_unworked(self):
        offers = self._offers(3)
        r0 = PPO.evaluate_window(offers, self._cert(2), key_for_offer=_kf)
        self.assertEqual(r0["verdicts"]["C"].recommendation, "DENY")
        offers[0].update({"operator_action": "FIRM", "operator_qty": 1})   # Kyle firms A
        r1 = PPO.evaluate_window(offers, self._cert(2), key_for_offer=_kf)
        self.assertNotIn("A", r1["verdicts"])                    # A is locked/worked, not re-recommended
        self.assertEqual(r1["verdicts"]["B"].recommendation, "FIRM")
        self.assertEqual(r1["counts"]["firmed"], 1)

    def test_7_override_firm_to_deny_frees_need_for_another(self):
        offers = self._offers(3)
        offers[0].update({"operator_action": "FIRM", "operator_qty": 1})   # A firmed (remaining need 1)
        offers[1].update({"operator_action": "DENY", "operator_qty": 0,
                          "recommended_action": "FIRM", "recommended_qty": 1, "override": True})  # B override->DENY
        r = PPO.evaluate_window(offers, self._cert(2), key_for_offer=_kf)
        self.assertEqual(r["verdicts"]["C"].recommendation, "FIRM")   # freed need recomputes C to FIRM

    def test_8_override_deny_to_firm_consumes_and_denies_other(self):
        offers = self._offers(2)
        self.assertEqual(PPO.machine_recommendation_at(offers, self._cert(1), "B", key_for_offer=_kf),
                         {"recommendation": "DENY", "recommended_qty": 0})   # B displayed DENY at the moment
        offers[1].update({"operator_action": "FIRM", "operator_qty": 1,
                          "recommended_action": "DENY", "recommended_qty": 0, "override": True})
        r = PPO.evaluate_window(offers, self._cert(1), key_for_offer=_kf)
        self.assertEqual(r["verdicts"]["A"].recommendation, "DENY")   # B's firm consumed the only need

    def test_9_worked_offer_stays_locked_through_recomputation(self):
        offers = self._offers(3)
        offers[0].update({"operator_action": "FIRM", "operator_qty": 1})
        r = PPO.evaluate_window(offers, self._cert(2), key_for_offer=_kf)
        self.assertEqual(r["worked"]["A"]["action"], "FIRM")     # locked to Kyle's recorded decision
        self.assertEqual(r["worked"]["A"]["qty"], 1)

    def test_10_recommendation_at_action_is_preserved_not_recomputed(self):
        offers = self._offers(3)
        offers[0].update({"operator_action": "FIRM", "operator_qty": 1})
        # B was recommended FIRM at the moment (A already firmed, need 1 remains)
        self.assertEqual(PPO.machine_recommendation_at(offers, self._cert(2), "B", key_for_offer=_kf)["recommendation"],
                         "FIRM")
        # Kyle overrides B->DENY and persists the moment's rec; a later recompute must NOT flip override to False
        offers[1].update({"operator_action": "DENY", "operator_qty": 0,
                          "recommended_action": "FIRM", "recommended_qty": 1, "override": True})
        r = PPO.evaluate_window(offers, self._cert(2), key_for_offer=_kf)
        self.assertTrue(r["worked"]["B"]["override"])            # preserved audit, not a live recomputation
        self.assertEqual(r["worked"]["B"]["recommendation"], "FIRM")

    def test_16_ranking_math_unchanged_no_worked_decisions(self):
        # with nothing worked, the result is exactly the shared evaluator's output (no new math)
        from elite.operatorstd import ppo_engine as ENG
        base = ENG.evaluate(self._offers(3), self._cert(2), key_for_offer=_kf)
        r = PPO.evaluate_window(self._offers(3), self._cert(2), key_for_offer=_kf)
        self.assertEqual(sorted(v.recommendation for v in base.verdicts),
                         sorted(v.recommendation for v in r["verdicts"].values()))

    def test_review_when_evidence_insufficient(self):
        offers = [{"id": "A", "combo": "X", "quantity": 1, "external": True}]   # orderability unknown -> REVIEW
        r = PPO.evaluate_window(offers, self._cert(2), key_for_offer=_kf)
        self.assertEqual(r["verdicts"]["A"].recommendation, "REVIEW")


# ---------------- B. governed committed supply (same rail as CPO) + reconciliation -------------------------
def _combo(store, clock, code, ext, inte):
    return resolve_or_create_planning_combination(
        store, clock, {"model_code": code, "exterior": ext, "interior": inte}, SCOPE, source_ref="ppo-test")


def _persist(store, comb, *, acquire):
    store.add_plan(InventoryPlanResult(
        id=new_id("plan"), store_scope=SCOPE, planning_state="balanced", combination_id=comb.id,
        expected_demand=0.0, current_supply=0, future_supply=0, committed_supply=0, qualifying_supply=0,
        desired_ending_coverage={"target_units": 1.6}, need=float(acquire), excess=0.0, confidence="medium",
        evidence={"model": "m", "decision": {"acquire_units": acquire, "arrived_excess": 0, "incoming_excess": 0,
                                              "target_level": 1.6, "monitor_months": []}},
        policy_versions=[], calculation_version="cv", reproducibility_package="r", demand_result_id=None,
        status="issued", months=[]))


class TestGovernedCommitmentRail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.conn = self.p.stack.db.conn
        store = NewInvStore(self.conn, self.p.clock)
        self.c1 = _combo(store, self.p.clock, "8501", "QBE", "G")     # QX65 LUXE, acquire 2
        _persist(store, self.c1, acquire=2)
        self.full = self.p.login(self.p.op_full)
        certs, self.l2k = OP._certified_positions(self.p.app, SCOPE)
        self.label = next(lbl for lbl, cid in self.l2k.items() if cid == self.c1.id)
        self.supply = SupplyService(NewInvStore(self.conn, self.p.clock), self.p.clock)

    def tearDown(self):
        self.p.close()

    def _qual(self):
        return self.supply.qualifying_supply(self.c1.id, SCOPE)

    def _committed(self):
        return [x for x in self._qual() if x["kind"] == "committed"]

    def _add_offer(self, window, *, qty=1, vin=None):
        self.full.post("/ordering/ppo/offer",
                       {"window": window, "combo": self.label, "quantity": str(qty), **({"vin": vin} if vin else {})})
        offers = OP._ws_get(self.p.app, SCOPE, f"ppo_offers::{window}", []) or []
        return offers[-1]["id"]

    def _record(self, window, oid, action, aqty):
        self.full.post("/ordering/ppo/record",
                       {"window": window, "offer": oid, "action": action, "action_qty": str(aqty)})

    def test_15_offered_but_unworked_creates_no_supply(self):
        self._add_offer("W")                                     # adding an offer creates the window
        self.assertEqual(self._committed(), [])                  # a mere offer never becomes supply

    def test_3_firm_creates_committed_supply_once(self):
        oid = self._add_offer("W", vin="VINFIRM1")
        self._record("W", oid, "FIRM", 1)
        self.assertEqual(len(self._committed()), 1)             # one FIRM -> one committed unit
        self._record("W", oid, "FIRM", 1)                       # re-record the same FIRM
        self.assertEqual(len(self._committed()), 1)             # still ONCE (idempotent by identity)

    def test_4_partial_creates_exactly_recorded_quantity(self):
        oid = self._add_offer("W", qty=3)
        self._record("W", oid, "PARTIAL", 2)
        self.assertEqual(len(self._committed()), 2)             # exactly the 2 recorded, not 3 offered

    def test_5_deny_creates_zero_supply(self):
        oid = self._add_offer("W", vin="VINDENY")
        self._record("W", oid, "DENY", 0)
        self.assertEqual(self._committed(), [])

    def test_5b_override_firm_then_deny_reverses_the_commitment(self):
        oid = self._add_offer("W", vin="VINREV")
        self._record("W", oid, "FIRM", 1)
        self.assertEqual(len(self._committed()), 1)
        self._record("W", oid, "DENY", 0)                       # override to DENY
        self.assertEqual(self._committed(), [])                 # governed reversal frees the supply

    def test_11_and_12_production_order_reconciles_count_once_idempotent(self):
        oid = self._add_offer("W", vin="V1")
        self._record("W", oid, "FIRM", 1)
        self.assertEqual(len(self._qual()), 1)                  # committed shadow present
        # the authoritative Production Order later arrives carrying the SAME physical VIN
        self.supply.project_future(self.c1.id, SCOPE, [{"production_order_id": "PO1", "vehicle_unit_id": "V1",
                                                        "arrival_month": "2026-11"}])
        self.assertEqual(len(self._qual()), 1)                  # count ONCE (deduped by the shared identity key)
        self.supply.project_future(self.c1.id, SCOPE, [{"production_order_id": "PO1", "vehicle_unit_id": "V1",
                                                        "arrival_month": "2026-11"}])
        self.assertEqual(len(self._qual()), 1)                  # idempotent — re-reconciling never duplicates

    def test_13_cpo_and_ppo_share_one_committed_supply_truth(self):
        oid = self._add_offer("W", vin="VSHARED")
        self._record("W", oid, "FIRM", 1)
        rows = self.conn.execute("SELECT commitment_type, lifecycle_status FROM supply_commitment "
                                 "WHERE store_scope=? AND combination_id=?", (SCOPE, self.c1.id)).fetchall()
        self.assertEqual([(r["commitment_type"], r["lifecycle_status"]) for r in rows], [("ppo", "committed")])
        # it is the SAME qualifying-supply rail CPO planning reads (one row, counted once)
        self.assertEqual(self.supply.counts(self.c1.id, SCOPE)["committed"], 1)

    def test_14_clear_window_cancels_committed_supply_not_silent_delete(self):
        oid = self._add_offer("W", vin="VCLEAR")
        self._record("W", oid, "FIRM", 1)
        self.assertEqual(len(self._committed()), 1)
        self.full.post("/ordering/ppo/revert", {"window": "W"})
        self.assertEqual(self._committed(), [])                 # no longer counts
        row = self.conn.execute("SELECT lifecycle_status, cancellation_status FROM supply_commitment "
                                "WHERE store_scope=? AND combination_id=?", (SCOPE, self.c1.id)).fetchone()
        self.assertEqual(row["lifecycle_status"], "cancelled")  # explicit governed reversal, NOT deleted
        self.assertTrue(row["cancellation_status"])

    def test_10_override_audit_persisted_end_to_end(self):
        # A firmed, then B overridden DENY: the record route preserves B's machine rec at the moment (FIRM)
        a = self._add_offer("W")
        b = self._add_offer("W")
        self._record("W", a, "FIRM", 1)
        self._record("W", b, "DENY", 0)
        offers = OP._ws_get(self.p.app, SCOPE, "ppo_offers::W", []) or []
        bo = next(o for o in offers if o["id"] == b)
        self.assertEqual(bo["recommended_action"], "FIRM")      # preserved: Elite recommended FIRM at that moment
        self.assertTrue(bo["override"])                         # Kyle's DENY is a recorded override


if __name__ == "__main__":
    unittest.main(verbosity=2)
