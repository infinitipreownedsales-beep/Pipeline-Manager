"""Sequential recomputation planner.

Starts from one accepted portfolio state, applies one approved Commitment effect at a time, and
recomputes qualifying Supply / Need / Excess against the UPDATED committed state before producing
the next recommendation. Every intermediate issued plan is preserved; the same unit/order can never
be selected twice; an action that is no longer necessary (its combination's Need already met) is
suppressed. Demand is never recomputed here — it is an input, owned by Phase 4.
"""
from __future__ import annotations

from ..newinv.models import SupplyCommitment
from ..ids import new_id


class SequentialPlanner:
    def __init__(self, nistore, supply, planning, wfstore, clock, plan_cv):
        self.ni, self.supply, self.planning, self.wf, self.clock, self.plan_cv = \
            nistore, supply, planning, wfstore, clock, plan_cv

    def _plan(self, demand_result, scope, coverage_target, scenario_id=None):
        comb_id = demand_result.combination_id
        qualifying = self.supply.qualifying_supply(comb_id, scope)
        counts = self.supply.counts(comb_id, scope)
        horizon = sorted(demand_result.monthly_expected)
        return self.planning.issue(demand_result, horizon=horizon, qualifying=qualifying,
                                   coverage_target=coverage_target, counts=counts,
                                   calculation_version=self.plan_cv, scenario_id=scenario_id)

    def run(self, scope, actions, *, demand_by_combo, coverage_by_combo, scenario_id=None):
        """`actions`: ordered [{action_ref, combination_id, unit_id, arrival_month}]. Returns the
        run id; steps (with causing action + need before/after + suppression) are persisted."""
        run_id = self.wf.add_sequential_run(scope, calculation_version=self.plan_cv, scenario_id=scenario_id)
        used = set()
        for seq, a in enumerate(actions):
            combo = a["combination_id"]
            unit = a.get("unit_id")
            demand_result = demand_by_combo[combo]
            coverage = coverage_by_combo.get(combo)
            need_before = self._plan(demand_result, scope, coverage, scenario_id).need
            if unit and unit in used:
                self.wf.add_sequential_step(run_id, seq, action_ref=a["action_ref"], combination_id=combo,
                                            causing_action=None, plan_ref=None, need_before=need_before,
                                            need_after=need_before, excess_after=0.0, suppressed=True,
                                            outcome="DUPLICATE_SELECTION")
                continue
            if need_before <= 0:
                self.wf.add_sequential_step(run_id, seq, action_ref=a["action_ref"], combination_id=combo,
                                            causing_action=None, plan_ref=None, need_before=need_before,
                                            need_after=need_before, excess_after=0.0, suppressed=True,
                                            outcome="SUPPRESSED_NO_NEED")
                continue
            # apply the approved commitment effect against updated state
            c = SupplyCommitment(id=new_id("cmt"), store_scope=scope, commitment_type="sequential",
                                 unit_or_order_id=unit, combination_id=combo, arrival_month=a.get("arrival_month"),
                                 lifecycle_status="committed", approval_time=self.ni._now())
            self.ni.add_commitment(c)
            used.add(unit)
            plan = self._plan(demand_result, scope, coverage, scenario_id)
            self.wf.add_sequential_step(run_id, seq, action_ref=a["action_ref"], combination_id=combo,
                                        causing_action=a["action_ref"], plan_ref=plan.id, need_before=need_before,
                                        need_after=plan.need, excess_after=plan.excess, suppressed=False,
                                        outcome="APPLIED")
        self.wf.set_run_status(run_id, "complete")
        return run_id
