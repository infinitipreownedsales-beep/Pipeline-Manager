"""Integrated forecast updates.

After a valid workflow commitment or completion, issue a NEW current planning result (preserving
the previous issued one), identify the workflow action that changed the state, keep Demand fixed
unless its own inputs changed, and update Supply / Need / Excess / risk / portfolio. No historical
issued output is overwritten; Scenario isolation is preserved.
"""
from __future__ import annotations


class IntegrateService:
    def __init__(self, nistore, supply, planning, wfstore, plan_cv):
        self.ni, self.supply, self.planning, self.wf, self.plan_cv = nistore, supply, planning, wfstore, plan_cv

    def reissue_plan(self, demand_result, scope, *, coverage_target, workflow_id, causing_action,
                     coverage_resolution=None, scenario_id=None):
        """Re-issue the combination plan against the updated committed state; record the causing
        workflow action against the new issued output. Returns the new InventoryPlanResult."""
        comb_id = demand_result.combination_id
        qualifying = self.supply.qualifying_supply(comb_id, scope)
        counts = self.supply.counts(comb_id, scope)
        horizon = sorted(demand_result.monthly_expected)
        plan = self.planning.issue(demand_result, horizon=horizon, qualifying=qualifying,
                                   coverage_target=coverage_target, counts=counts,
                                   calculation_version=self.plan_cv, coverage_resolution=coverage_resolution,
                                   scenario_id=scenario_id)
        self.wf.add_workflow_issued_output(workflow_id, causing_action, "inventory_plan", plan.id,
                                           combination_id=comb_id, scope=scope, calculation_version=self.plan_cv,
                                           scenario_id=scenario_id)
        return plan
