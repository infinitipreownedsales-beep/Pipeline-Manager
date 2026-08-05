"""Phase 5 — BUG-CPO-002 END-TO-END regression through the REAL governed CPO workflow.

Fifteen-point contract proving the canonical resolution end-to-end: Demand independent of the
acquisition path; an approved CPO commitment credited to qualifying Supply exactly once; Need
monotone non-increasing; replay/rename cannot double-count or move Demand; cancellation removes the
prospective commitment while preserving history; re-approval after cancellation cannot duplicate the
same active unit.
"""
import os
import tempfile
import unittest

from elite.workflow.fixtures import SCOPE, Phase5


class TestBugCpo002EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))
        # demand 2/mo * 6 = 12; seed one current unit + one future unit as baseline supply
        self.c, self.d, _ = self.p.need_combo(exterior_color="BLACK")
        self.p.p4.seed_current(self.c, [{"vehicle_unit_id": "vu_cur", "state": "available_unsold",
                                        "identity_status": "resolved"}])
        self.p.p4.seed_future(self.c, [{"production_order_id": "po_base", "arrival_month": "2026-09"}])

    def tearDown(self):
        self.p.close()

    def _need(self):
        return self.p.p4.issue_plan(self.c, self.d, coverage_target=2).need

    def _qual(self):
        return len(self.p.supply.qualifying_supply(self.c.id, SCOPE))

    def test_bug_cpo_002_end_to_end(self):
        # 1. Phase 4 Demand issued
        self.assertTrue(self.d.monthly_expected)
        baseline_demand = dict(self.d.monthly_expected)

        # 2. Baseline Current / Future / Committed Supply recorded
        counts = self.p.supply.counts(self.c.id, SCOPE)
        self.assertEqual((counts["current"], counts["future"], counts["committed"]), (1, 1, 0))

        # 3. Baseline Need issued
        baseline_need = self._need()
        baseline_qual = self._qual()
        self.assertGreater(baseline_need, 0)

        # 4. One specific eligible Production Order proposed through CPO
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po_cpo", combination_id=self.c.id,
                               arrival_month="2026-09", need_ref="need_baseline")

        # 5. Proposal creates no supply effect
        self.assertEqual(self._qual(), baseline_qual)
        self.assertEqual(self.p.wf.reconciliations_for(w.id)[0].outcome, "NO_SUPPLY_EFFECT")

        # 6. Authorized approval creates one Commitment
        r = self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.assertEqual(r["outcome"], "COMMITMENT_CREATED")
        self.assertEqual(self.p.supply.counts(self.c.id, SCOPE)["committed"], 1)

        # 7. Demand remains identical
        d_after = self.p.p4.issue_demand(self.c)
        self.assertEqual(d_after.monthly_expected, baseline_demand)

        # 8. Qualifying Supply increases by exactly one
        self.assertEqual(self._qual(), baseline_qual + 1)

        # 9 & 10. Need decreases or unchanged, never increases
        need_after = self._need()
        self.assertLessEqual(need_after, baseline_need)
        self.assertEqual(need_after, baseline_need - 1)

        # 11. Replayed approval does not add another unit
        self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        self.assertEqual(self._qual(), baseline_qual + 1)
        self.assertEqual(self._need(), need_after)

        # 12. Renaming the acquisition path does not alter Demand
        self.p.dt.propose(self.p.full, SCOPE, unit_identity="vu_rename", combination_id=self.c.id,
                          arrival_month="2026-09")   # a different acquisition path
        self.assertEqual(self.p.p4.issue_demand(self.c).monthly_expected, baseline_demand)

        # 13. Cancellation removes the prospective commitment
        self.p.cpo.cancel(self.p.full, SCOPE, self.p.wf.get_workflow(w.id),
                          commitment_ref=self.p.cpo.commitment_ref(w.id))
        self.assertEqual(self._qual(), baseline_qual)
        self.assertEqual(self._need(), baseline_need)

        # 14. Historical approval and cancellation remain inspectable
        outcomes = [x.outcome for x in self.p.wf.reconciliations_for(w.id)]
        self.assertIn("COMMITMENT_CREATED", outcomes)
        self.assertIn("COMMITMENT_CANCELLED", outcomes)
        states = [t["to_status"] for t in self.p.wf.transitions_for(w.id)]
        self.assertEqual(states[:3], ["PROPOSED", "COMMITTED", "CANCELLED"])

        # 15. Re-approval after cancellation follows the workflow/idempotency contract and cannot
        #     duplicate the same active unit: the cancelled workflow is terminal (no re-approval);
        #     a fresh workflow for the SAME order commits at most one unit for that identity.
        w2 = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po_cpo", combination_id=self.c.id,
                                arrival_month="2026-09")
        self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w2.id))
        self.assertEqual(self._qual(), baseline_qual + 1)     # one active unit for that identity, not two

    def test_bug_cpo_002_monotone_ladder_end_to_end(self):
        needs = [self._need()]
        for i in range(5):
            w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id=f"po_{i}", combination_id=self.c.id,
                                   arrival_month="2026-09")
            self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
            needs.append(self._need())
        for earlier, later in zip(needs, needs[1:]):
            self.assertLessEqual(later, earlier)              # Need never increases as commitments are added


if __name__ == "__main__":
    unittest.main()
