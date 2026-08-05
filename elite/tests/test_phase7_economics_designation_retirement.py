"""Phase 7 acceptance — Economic Call + Execution Status (43-48), designation workflow (49-54),
retirement / return-to-retail / Used Cars handoff / reconciliation / correction (55-66)."""
import json
import os
import sqlite3
import tempfile
import unittest

from elite.errors import ValidationError
from elite.execdemo.fixtures import Phase7
from elite.workflow.fixtures import SCOPE

V = "1HGCM82633A400001"


class TestPhase7Economics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase7(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_43_economic_call_versioned_entry_vs_retirement(self):
        u = self.p.make_active(V)
        entry = self.p.economics.issue_call(u, decision_point="entry", alternatives=[
            {"alternative": "designate_now", "incremental_value": 800.0, "basis": "b"},
            {"alternative": "maintain_portfolio", "incremental_value": 300.0, "basis": "b"}])
        ret = self.p.economics.issue_call(u, decision_point="retirement", alternatives=[
            {"alternative": "retire_now", "incremental_value": 200.0, "basis": "b"},
            {"alternative": "retire_later", "incremental_value": 120.0, "basis": "b"}])
        self.assertEqual(entry.decision_point, "entry")
        self.assertEqual(ret.decision_point, "retirement")           # entry vs retirement distinguishable
        self.assertIsNotNone(entry.calculation_version)              # versioned
        self.assertEqual(entry.economic_call["choice"], "designate_now")
        self.assertEqual(ret.economic_call["choice"], "retire_now")

    def test_44_retirement_uses_incremental_no_sunk_cost(self):
        # retirement timing uses INCREMENTAL future economics only; sunk designation cost is not reapplied
        import elite.execdemo.economics as ec
        src = open(ec.__file__).read()
        self.assertNotIn("designation_cost", src)                    # no sunk designation cost reapplied
        u = self.p.make_active(V)
        ret = self.p.economics.issue_call(u, decision_point="retirement", alternatives=[
            {"alternative": "retire_now", "incremental_value": 150.0, "basis": "incremental"}])
        self.assertEqual(ret.economic_call["value"], 150.0)          # exactly the incremental value

    def test_45_missing_inputs_unresolved(self):
        u = self.p.make_active(V)
        r = self.p.economics.issue_call(u, decision_point="entry", alternatives=[], policy_status="unresolved")
        self.assertEqual(r.resolution_status, "unresolved")          # never manufactured
        self.assertEqual(r.economic_call, {})

    def test_46_alternatives_carry_own_values(self):
        u = self.p.make_active(V)
        alts = [{"alternative": "designate_now", "incremental_value": 800.0, "basis": "synthetic"},
                {"alternative": "choose_another", "incremental_value": 500.0, "basis": "synthetic"}]
        r = self.p.economics.issue_call(u, decision_point="entry", alternatives=alts)
        stored = self.p.store.get_economic(r.id)
        # each alternative keeps its own explicit value — the call is not an opaque single score
        self.assertEqual([a["incremental_value"] for a in stored.alternatives], [800.0, 500.0])
        self.assertEqual(stored.economic_call["choice"], "designate_now")

    def test_47_conflicting_policy_conflict(self):
        u = self.p.make_active(V)
        r = self.p.economics.issue_call(u, decision_point="entry", alternatives=[], policy_status="conflicting")
        self.assertEqual(r.resolution_status, "conflicting")

    def test_48_execution_status_separate_incl_new_retail_risk(self):
        u = self.p.make_active(V)
        e = self.p.econ(u)
        ready = self.p.execution.assess(u, e.id)
        risk = self.p.execution.assess(u, e.id, new_retail_risk=True)
        self.assertEqual(ready["status"], "READY")
        self.assertEqual(risk["status"], "BLOCKED_NEW_RETAIL_RISK")  # execution status is its own concern
        self.assertTrue(json.loads(risk["blocking_factors"]))
        # the economic call itself is untouched by a blocked execution (not rewritten)
        self.assertEqual(self.p.store.get_economic(e.id).economic_call, e.economic_call)


class TestPhase7DesignationRetirement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase7(os.path.join(self.tmp, "elite.db"))
        self.c, self.plan = self.p.nr_plan(position="need")

    def tearDown(self):
        self.p.close()

    def _u(self, uid):
        return self.p.store.get_unit(uid)

    def _supply(self, comb_id):
        return len(self.p.ni.current_supply_for(comb_id, SCOPE))

    def _candidate_with_supply(self, vin):
        u = self.p.candidate_unit(vin, self.c.id)
        self.p.p4.seed_current(self.c, [{"vehicle_unit_id": u.vehicle_unit_id, "state": "available_unsold",
                                        "identity_status": "resolved"}])
        return u

    def _designate(self, vin):
        u = self._candidate_with_supply(vin)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        return self.p.units.execute_designation(self.p.full, SCOPE, self._u(u.id))

    # ---- designation (49-54) ----------------------------------------------
    def test_49_propose_creates_action_not_membership(self):
        u = self._candidate_with_supply(V)
        r = self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.assertEqual(r["unit"].membership_state, "DESIGNATION_PROPOSED")
        self.assertIsNotNone(self._u(u.id).designation_decision)
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 0)  # not active

    def test_50_approve_commits_no_supply_effect(self):
        u = self._candidate_with_supply(V)
        before = self._supply(self.c.id)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self._supply(self.c.id), before)            # supply untouched at approval
        self.assertEqual(self.p.portfolio.committed(SCOPE), 1)

    def test_51_execute_membership_once_removes_supply(self):
        u = self._candidate_with_supply(V)
        before = self._supply(self.c.id)                            # 1 (seeded)
        self.assertEqual(before, 1)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        r = self.p.units.execute_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(r["unit"].membership_state, "ACTIVE")
        self.assertEqual(self._supply(self.c.id), before - 1)        # removed from New Retail Current Supply
        self.assertEqual([x["outcome"] for x in self.p.store.reconciliations_for(r["unit"].id)], ["ACTIVE_DEMO"])

    def test_52_replayed_execution_no_double_removal(self):
        r = self._designate(V)
        supply_after = self._supply(self.c.id)
        r2 = self.p.units.execute_designation(self.p.full, SCOPE, self._u(r["unit"].id))
        self.assertTrue(r2["replayed"])
        self.assertEqual(self._supply(self.c.id), supply_after)      # idempotent — no second removal

    def test_53_cancel_removes_committed_preserves_history(self):
        u = self._candidate_with_supply(V)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.cancel_designation(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self._u(u.id).membership_state, "CANCELLED")
        self.assertEqual(self.p.portfolio.committed(SCOPE), 0)
        self.assertIn("DESIGNATION_PROPOSED", [h["to_state"] for h in self.p.store.membership_history(u.id)])

    def test_54_active_service_loaner_cannot_be_designated(self):
        self.p.p6.make_active(V, combination_id=self.c.id)
        u = self._candidate_with_supply(V)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        self.p.units.approve_designation(self.p.full, SCOPE, self._u(u.id))
        with self.assertRaises(ValidationError):
            self.p.units.execute_designation(self.p.full, SCOPE, self._u(u.id))

    # ---- retirement + disposition (55-66) ---------------------------------
    def test_55_eligibility_is_not_retirement(self):
        u = self.p.make_active(V)
        self.p.retirement.assess_eligibility(u, eligible=True, tenure_days=400)
        self.assertEqual(self._u(u.id).membership_state, "ACTIVE")   # eligibility does not retire

    def test_56_approval_is_not_actual_retirement(self):
        u = self.p.make_active(V)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self._u(u.id).membership_state, "RETIREMENT_APPROVED")   # not yet retired
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 1)   # still counted as active until executed

    def test_57_actual_retirement_removes_active_membership(self):
        u = self.p.make_active(V)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        before_active = self.p.portfolio.current_active(SCOPE)
        self.p.retirement.execute(self.p.full, SCOPE, self._u(u.id), disposition="new_retail")
        self.assertEqual(self.p.portfolio.current_active(SCOPE), before_active - 1)   # membership removed

    def test_58_return_to_retail_restores_supply_once(self):
        comb = self.p.combination(exterior_color="RTR")
        u = self.p.make_active(V, comb.id)
        self.assertEqual(self._supply(comb.id), 0)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.execute(self.p.full, SCOPE, self._u(u.id), disposition="new_retail")
        self.assertEqual(self._u(u.id).membership_state, "RETURNED_TO_NEW_RETAIL")
        self.assertEqual(self._supply(comb.id), 1)                   # restored exactly once
        self.assertIn("RETURNED_TO_NEW_RETAIL", [x["outcome"] for x in self.p.store.reconciliations_for(u.id)])

    def test_59_existing_supply_prevents_duplicate_restoration(self):
        comb = self.p.combination(exterior_color="DUP")
        u = self.p.make_active(V, comb.id)
        # supply already present for this exact vehicle unit
        self.p.p4.seed_current(comb, [{"vehicle_unit_id": u.vehicle_unit_id, "state": "available_unsold",
                                      "identity_status": "resolved"}])
        self.assertEqual(self._supply(comb.id), 1)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.execute(self.p.full, SCOPE, self._u(u.id), disposition="new_retail")
        self.assertEqual(self._supply(comb.id), 1)                   # NOT doubled
        self.assertIn("ALREADY_RECONCILED", [x["outcome"] for x in self.p.store.reconciliations_for(u.id)])

    def test_60_used_cars_handoff_separate_record_no_supply(self):
        comb = self.p.combination(exterior_color="UCH")
        u = self.p.make_active(V, comb.id)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.execute(self.p.full, SCOPE, self._u(u.id), disposition="used_cars")
        self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, self._u(u.id))
        self.assertEqual(self._u(u.id).membership_state, "USED_CARS_RECEIVED")
        self.assertEqual(self._supply(comb.id), 0)                   # Used Cars handoff creates no New Retail supply
        # it is its OWN record, not merged into any Service Loaner table
        receipt = self.p.store.used_cars_receipt_for(u.id)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["executive_demo_unit_id"], u.id)

    def test_61_used_cars_receipt_idempotent_and_immutable(self):
        comb = self.p.combination(exterior_color="IMM")
        u = self.p.make_active(V, comb.id)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.execute(self.p.full, SCOPE, self._u(u.id), disposition="used_cars")
        r1 = self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, self._u(u.id))
        r2 = self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, self._u(u.id))
        self.assertTrue(r2["replayed"])                              # one idempotent confirmation
        rid = self.p.store.used_cars_receipt_for(u.id)["id"]
        with self.assertRaises(sqlite3.Error):                      # immutable — no update
            with self.p.store.conn:
                self.p.store.conn.execute("UPDATE executive_demo_used_cars_receipt SET store_scope='x' WHERE id=?",
                                          (rid,))
        with self.assertRaises(sqlite3.Error):                      # immutable — no delete
            with self.p.store.conn:
                self.p.store.conn.execute("DELETE FROM executive_demo_used_cars_receipt WHERE id=?", (rid,))

    def test_62_receipt_cannot_precede_retirement(self):
        u = self.p.make_active(V)                                    # ACTIVE, not retired
        with self.assertRaises(ValidationError):
            self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, u)

    def test_63_reconciliation_outcomes_recorded(self):
        comb = self.p.combination(exterior_color="REC")
        u = self.p.make_active(V, comb.id)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.execute(self.p.full, SCOPE, self._u(u.id), disposition="new_retail")
        outs = [x["outcome"] for x in self.p.store.reconciliations_for(u.id)]
        self.assertIn("RETIRED_AWAITING_DISPOSITION", outs)
        self.assertIn("RETURNED_TO_NEW_RETAIL", outs)

    def test_64_one_vehicle_unit_counts_once(self):
        r = self._designate(V)                                       # active demo, +1
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 1)
        # retire the same unit -> it must not remain counted
        self.p.retirement.propose(self.p.full, SCOPE, self._u(r["unit"].id))
        self.p.retirement.approve(self.p.full, SCOPE, self._u(r["unit"].id))
        self.p.retirement.execute(self.p.full, SCOPE, self._u(r["unit"].id), disposition="new_retail")
        self.assertEqual(self.p.portfolio.current_active(SCOPE), 0)  # counted once, now gone

    def test_65_correction_preserves_prior_records(self):
        u = self._candidate_with_supply(V)
        self.p.units.propose_designation(self.p.full, SCOPE, u)
        corrected = self.p.units.correct(self.p.full, SCOPE, self._u(u.id), {"assigned_role": "gm"}, reason="typo")
        self.assertEqual(self._u(u.id).membership_state, "CORRECTED")
        self.assertEqual(self._u(u.id).superseded_by, corrected.id)
        self.assertEqual(corrected.correction_of, u.id)             # prior record preserved, not overwritten
        self.assertIn("DESIGNATION_PROPOSED", [h["to_state"] for h in self.p.store.membership_history(u.id)])

    def test_66_economic_call_not_rewritten_when_blocked(self):
        u = self.p.make_active(V)
        e = self.p.econ(u)
        original = dict(e.economic_call)
        self.p.execution.assess(u, e.id, new_retail_risk=True)      # blocked
        self.assertEqual(self.p.store.get_economic(e.id).economic_call, original)   # call unchanged


if __name__ == "__main__":
    unittest.main()
