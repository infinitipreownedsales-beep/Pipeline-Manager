"""Phase 6 acceptance — retirement, provisional, return, final, Used Cars handoff,
return-to-retail reconciliation (items 47-65)."""
import inspect
import os
import tempfile
import unittest

from elite.errors import ValidationError
from elite.loaner.fixtures import Phase6
from elite.loaner.retirement import RetirementService
from elite.workflow.fixtures import SCOPE

V = "1GNSKBKC5FR000501"


class TestPhase6Retirement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase6(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _u(self, uid):
        return self.p.store.get_unit(uid)

    def _to_awaiting(self, vin=V, handoff="used_cars"):
        u = self.p.make_active(vin)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.confirm_return(self.p.full, SCOPE, self._u(u.id), actual_event_ref="evt")
        self.p.retirement.complete(self.p.full, SCOPE, self._u(u.id), handoff=handoff)
        return self._u(u.id)

    def test_47_eligibility_distinct_from_retirement(self):
        u = self.p.make_active(V)
        self.p.retirement.assess_eligibility(u, eligible=True, tenure_days=400)
        self.assertEqual(self._u(u.id).membership_state, "ACTIVE_AVAILABLE")   # eligible != retired

    def test_48_approval_distinct_from_return(self):
        u = self.p.make_active(V)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        r = self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(r["unit"].membership_state, "RETIREMENT_APPROVED")     # approved, not returned/retired
        self.assertIsNone(r["unit"].return_confirmation)

    def test_49_rented_provisional_remains_active_rented(self):
        u = self.p.make_active(V, rental="rented")
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        r = self.p.retirement.provisional(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(r["unit"].membership_state, "PROVISIONAL_RETIREMENT")
        self.assertEqual(r["unit"].current_rental_state, "rented")             # still rented until returned

    def test_50_provisional_prevents_duplicate_recommendation(self):
        u = self.p.make_active(V, rental="rented")
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        self.p.retirement.provisional(self.p.full, SCOPE, self._u(u.id))
        with self.assertRaises(ValidationError):                                # cannot re-propose in provisional
            self.p.retirement.propose(self.p.full, SCOPE, self._u(u.id))

    def test_51_return_confirmation_separate_event(self):
        u = self.p.make_active(V)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.approve(self.p.full, SCOPE, self._u(u.id))
        r = self.p.retirement.confirm_return(self.p.full, SCOPE, self._u(u.id), actual_event_ref="actual-1")
        self.assertEqual(r["unit"].membership_state, "RETURN_CONFIRMED")
        self.assertIsNotNone(r["unit"].return_confirmation)

    def test_52_final_retirement_changes_membership(self):
        u = self._to_awaiting()
        self.assertIsNotNone(u.retirement_event)
        recon = [r["outcome"] for r in self.p.store.reconciliations_for(u.id)]
        self.assertIn("RETIRED_AWAITING_HANDOFF", recon)

    def test_53_cancellation_preserves_history_restores_state(self):
        u = self.p.make_active(V)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        self.p.retirement.cancel(self.p.full, SCOPE, self._u(u.id), restore_state="ACTIVE_AVAILABLE")
        self.assertEqual(self._u(u.id).membership_state, "ACTIVE_AVAILABLE")    # restored
        states = [h["to_state"] for h in self.p.store.membership_history(u.id)]
        self.assertIn("RETIREMENT_PROPOSED", states)                           # history preserved

    def test_54_corrected_retirement_preserves_prior(self):
        u = self.p.make_active(V)
        self.p.retirement.propose(self.p.full, SCOPE, u)
        action_id = self._u(u.id).retirement_decision
        self.p.retirement.cancel(self.p.full, SCOPE, self._u(u.id))
        self.assertEqual(self.p.store.get_retirement_action(action_id).lifecycle_status, "cancelled")  # preserved

    def test_55_retired_enters_awaiting_used_cars(self):
        u = self._to_awaiting()
        self.assertEqual(u.membership_state, "AWAITING_USED_CARS_RECEIPT")

    def test_56_58_receipt_one_action_no_checklist(self):
        params = set(inspect.signature(RetirementService.confirm_used_cars_receipt).parameters)
        # only self, principal, scope, unit + optional correlation_id — no checklist / mandatory fields
        self.assertEqual(params, {"self", "principal", "scope", "unit", "correlation_id"})

    def test_57_receipt_auto_records_principal_and_time(self):
        u = self._to_awaiting()
        self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, u)
        r = self.p.store.used_cars_receipt_for(u.id)
        self.assertEqual(r["confirming_principal"], self.p.receiver)
        self.assertTrue(r["confirmed_at"])                                     # auto-recorded timestamp

    def test_59_duplicate_receipt_idempotent(self):
        u = self._to_awaiting()
        self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, u)
        r2 = self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, self._u(u.id))
        self.assertTrue(r2["replayed"])
        cnt = self.p.store.conn.execute("SELECT COUNT(*) n FROM used_cars_receipt WHERE service_loaner_unit_id=?",
                                        (u.id,)).fetchone()["n"]
        self.assertEqual(cnt, 1)

    def test_60_receipt_cannot_occur_before_retirement(self):
        u = self.p.make_active(V)                                              # active, not retired
        with self.assertRaises(ValidationError):
            self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, u)

    def test_61_retirement_does_not_imply_receipt(self):
        u = self._to_awaiting()
        self.assertIsNone(self.p.store.used_cars_receipt_for(u.id))            # awaiting, no receipt yet

    def test_62_used_cars_receipt_creates_no_new_retail_supply(self):
        u = self._to_awaiting()
        before = len(self.p.ni.current_supply_for(u.combination_id, SCOPE))
        self.p.retirement.confirm_used_cars_receipt(self.p.receiver, SCOPE, u)
        self.assertEqual(len(self.p.ni.current_supply_for(u.combination_id, SCOPE)), before)   # no supply

    def test_63_64_return_to_new_retail_restores_supply_once(self):
        u = self._to_awaiting(handoff="new_retail")
        self.assertEqual(u.membership_state, "RETURNED_TO_NEW_RETAIL")
        supply = self.p.ni.current_supply_for(u.combination_id, SCOPE)
        self.assertEqual(len(supply), 1)                                       # restored once
        self.assertEqual(supply[0].vehicle_unit_id, u.vehicle_unit_id)
        recon = [r["outcome"] for r in self.p.store.reconciliations_for(u.id)]
        self.assertIn("RETURNED_TO_NEW_RETAIL", recon)

    def test_65_return_to_retail_preserves_historical_membership(self):
        u = self._to_awaiting(handoff="new_retail")
        # historical membership + retirement event remain inspectable after return-to-retail
        self.assertIsNotNone(self.p.store.get_unit(u.id).retirement_event)
        self.assertTrue(self.p.store.membership_history(u.id))


if __name__ == "__main__":
    unittest.main()
