"""Phase 5 acceptance — CPO workflow (items 18-25)."""
import inspect
import os
import tempfile
import unittest

from elite.workflow.cpo import CpoService
from elite.workflow.fixtures import SCOPE, Phase5


class TestPhase5Cpo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))
        self.c, self.d, self.plan = self.p.need_combo(exterior_color="BLACK")

    def tearDown(self):
        self.p.close()

    def _qual(self):
        return len(self.p.supply.qualifying_supply(self.c.id, SCOPE))

    def test_18_cpo_consumes_phase4_need(self):
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=self.c.id,
                               arrival_month="2026-10", need_ref=self.plan.id)
        self.assertEqual(w.originating_need_ref, self.plan.id)     # consumes the Phase 4 Need result

    def test_19_cpo_does_not_calculate_separate_demand(self):
        # No Demand computation lives in the CPO service.
        src = inspect.getsource(CpoService)
        self.assertNotIn("monthly_expected", src)
        self.assertNotIn("DemandService", src)

    def test_20_cpo_proposal_has_no_supply_effect(self):
        self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=self.c.id,
                           arrival_month="2026-10")
        self.assertEqual(self._qual(), 0)

    def test_21_approved_cpo_creates_one_commitment(self):
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        r = self.p.cpo.approve(self.p.full, SCOPE, w)
        self.assertEqual(r["outcome"], "COMMITMENT_CREATED")
        self.assertEqual(self._qual(), 1)
        self.assertEqual(self.p.supply.counts(self.c.id, SCOPE)["committed"], 1)

    def test_22_replayed_cpo_approval_does_not_double_count(self):
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        r2 = self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))   # replay
        self.assertTrue(r2["replayed"])
        self.assertEqual(r2["outcome"], "DUPLICATE_REPLAY")
        self.assertEqual(self._qual(), 1)

    def test_23_cpo_already_represented_does_not_count_twice(self):
        self.p.p4.seed_future(self.c, [{"production_order_id": "poX", "arrival_month": "2026-10"}])
        self.assertEqual(self._qual(), 1)                          # already in Future Supply
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="poX", combination_id=self.c.id,
                               arrival_month="2026-10")
        r = self.p.cpo.approve(self.p.full, SCOPE, w)
        self.assertEqual(r["outcome"], "ALREADY_REPRESENTED")
        self.assertEqual(self._qual(), 1)                          # still once

    def test_24_cpo_cancellation_removes_effect_keeps_history(self):
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        self.assertEqual(self._qual(), 1)
        self.p.cpo.cancel(self.p.full, SCOPE, self.p.wf.get_workflow(w.id),
                          commitment_ref=self.p.cpo.commitment_ref(w.id))
        self.assertEqual(self._qual(), 0)                          # prospective effect removed
        # history preserved: the workflow + its transitions + reconciliations remain
        self.assertEqual(self.p.wf.get_workflow(w.id).lifecycle_status, "CANCELLED")
        outcomes = {r.outcome for r in self.p.wf.reconciliations_for(w.id)}
        self.assertIn("COMMITMENT_CREATED", outcomes)
        self.assertIn("COMMITMENT_CANCELLED", outcomes)

    def test_25_cpo_completion_reconciles_to_same_or_later_unit(self):
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=self.c.id,
                               arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        r = self.p.cpo.complete(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), received_unit_id="vu_final",
                                commitment_ref=self.p.cpo.commitment_ref(w.id))
        self.assertEqual(r["outcome"], "COMPLETED_TO_CURRENT")
        counts = self.p.supply.counts(self.c.id, SCOPE)
        self.assertEqual((counts["current"], counts["committed"], counts["qualifying"]), (1, 0, 1))  # once, now current


if __name__ == "__main__":
    unittest.main()
