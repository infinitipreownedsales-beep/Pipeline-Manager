"""Phase 5 acceptance — sequential recomputation + commitment reconciliation (items 45-55)."""
import os
import tempfile
import unittest

from elite.workflow.fixtures import SCOPE, Phase5


class TestPhase5SequentialReconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase5(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _qual(self, comb):
        return len(self.p.supply.qualifying_supply(comb.id, SCOPE))

    def test_45_planner_updates_committed_state_after_each_action(self):
        c, d, _ = self.p.need_combo(exterior_color="SEQ")     # demand 12, coverage 0 -> need 12
        run = self.p.sequential.run(
            SCOPE, [{"action_ref": "a1", "combination_id": c.id, "unit_id": "u1", "arrival_month": "2026-09"},
                    {"action_ref": "a2", "combination_id": c.id, "unit_id": "u2", "arrival_month": "2026-09"}],
            demand_by_combo={c.id: d}, coverage_by_combo={c.id: 0})
        steps = self.p.wf.steps_for(run)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["need_after"], steps[0]["need_before"] - 1)   # committed state updated
        self.assertEqual(steps[1]["need_before"], steps[0]["need_after"])       # second sees updated Need

    def test_46_second_recommendation_uses_updated_need(self):
        c, d, _ = self.p.need_combo(exterior_color="SEQ")
        run = self.p.sequential.run(
            SCOPE, [{"action_ref": "a1", "combination_id": c.id, "unit_id": "u1", "arrival_month": "2026-09"},
                    {"action_ref": "a2", "combination_id": c.id, "unit_id": "u2", "arrival_month": "2026-09"}],
            demand_by_combo={c.id: d}, coverage_by_combo={c.id: 0})
        steps = self.p.wf.steps_for(run)
        self.assertLess(steps[1]["need_before"], 12)          # not the stale baseline

    def test_47_now_unnecessary_action_is_suppressed(self):
        c, d, _ = self.p.need_combo(exterior_color="SEQ1", per_month=0)   # near-zero demand -> need ~0 fast
        # need is 0 already (coverage 0) so the first action is suppressed
        run = self.p.sequential.run(
            SCOPE, [{"action_ref": "a1", "combination_id": c.id, "unit_id": "u1", "arrival_month": "2026-09"}],
            demand_by_combo={c.id: d}, coverage_by_combo={c.id: 0})
        steps = self.p.wf.steps_for(run)
        self.assertTrue(steps[0]["suppressed"])
        self.assertEqual(steps[0]["outcome"], "SUPPRESSED_NO_NEED")

    def test_48_same_unit_cannot_be_selected_twice(self):
        c, d, _ = self.p.need_combo(exterior_color="SEQ")
        run = self.p.sequential.run(
            SCOPE, [{"action_ref": "a1", "combination_id": c.id, "unit_id": "dup", "arrival_month": "2026-09"},
                    {"action_ref": "a2", "combination_id": c.id, "unit_id": "dup", "arrival_month": "2026-09"}],
            demand_by_combo={c.id: d}, coverage_by_combo={c.id: 0})
        steps = self.p.wf.steps_for(run)
        self.assertEqual(steps[1]["outcome"], "DUPLICATE_SELECTION")
        self.assertTrue(steps[1]["suppressed"])

    def test_49_demand_unchanged_when_only_commitments_change(self):
        c, d, _ = self.p.need_combo(exterior_color="D")
        baseline = dict(d.monthly_expected)
        self.p.sequential.run(
            SCOPE, [{"action_ref": "a1", "combination_id": c.id, "unit_id": "u1", "arrival_month": "2026-09"}],
            demand_by_combo={c.id: d}, coverage_by_combo={c.id: 2})
        d2 = self.p.p4.issue_demand(c)
        self.assertEqual(d2.monthly_expected, baseline)

    def test_50_added_commitment_does_not_increase_need(self):
        c, d, plan = self.p.need_combo(exterior_color="M")
        base = self.p.p4.issue_plan(c, d, coverage_target=2).need
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-09")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        after = self.p.p4.issue_plan(c, d, coverage_target=2).need
        self.assertLessEqual(after, base)

    def test_51_later_workflow_supply_does_not_satisfy_earlier_month(self):
        c, d, _ = self.p.need_combo(exterior_color="L")
        base = self.p.p4.issue_plan(c, d, coverage_target=0)
        first_shortage = base.months[0].shortage
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id,
                               arrival_month="2027-02")            # arrives in the last horizon month
        self.p.cpo.approve(self.p.full, SCOPE, w)
        after = self.p.p4.issue_plan(c, d, coverage_target=0)
        self.assertEqual(after.months[0].shortage, first_shortage)   # earliest month unchanged

    def test_52_every_transition_gets_reconciliation_outcome(self):
        c, d, _ = self.p.need_combo(exterior_color="R")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        recons = self.p.wf.reconciliations_for(w.id)
        self.assertGreaterEqual(len(recons), 2)                   # propose + approve each reconciled
        self.assertEqual(recons[0].outcome, "NO_SUPPLY_EFFECT")
        self.assertEqual(recons[-1].outcome, "COMMITMENT_CREATED")

    def test_53_duplicate_replay_produces_no_effect_outcome(self):
        c, d, _ = self.p.need_combo(exterior_color="DR")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        self.p.cpo.approve(self.p.full, SCOPE, self.p.wf.get_workflow(w.id))
        outcomes = [r.outcome for r in self.p.wf.reconciliations_for(w.id)]
        self.assertIn("DUPLICATE_REPLAY", outcomes)

    def test_54_unresolved_identity_prevents_confident_commitment(self):
        from elite.workflow import reconcile
        c, d, _ = self.p.need_combo(exterior_color="U")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id=None, combination_id=c.id, arrival_month="2026-10")
        # approve with no discrete identity -> UNRESOLVED_IDENTITY, no supply
        eff = reconcile.create_commitment(self.p.ni, self.p.supply, unit_or_order_id=None, combination_id=c.id,
                                          scope=SCOPE, arrival_month="2026-10", commitment_type="cpo")
        from elite.workflow import lifecycle
        r = lifecycle.governed_transition(self.p.gov, self.p.wf, principal=self.p.full, capability="cpo.approve",
                                          scope=SCOPE, workflow_id=w.id, expected_version=w.version, wf_type="cpo",
                                          to_status="COMMITTED", action="cpo.approve", effect=eff)
        self.assertEqual(r["outcome"], "UNRESOLVED_IDENTITY")
        self.assertEqual(self._qual(c), 0)

    def test_55_completion_reconciles_future_committed_to_current_once(self):
        c, d, _ = self.p.need_combo(exterior_color="C2C")
        w = self.p.cpo.propose(self.p.full, SCOPE, production_order_id="po", combination_id=c.id, arrival_month="2026-10")
        self.p.cpo.approve(self.p.full, SCOPE, w)
        self.p.cpo.complete(self.p.full, SCOPE, self.p.wf.get_workflow(w.id), received_unit_id="vu",
                            commitment_ref=self.p.cpo.commitment_ref(w.id))
        counts = self.p.supply.counts(c.id, SCOPE)
        self.assertEqual((counts["current"], counts["committed"], counts["qualifying"]), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
