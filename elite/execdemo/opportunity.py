"""New Retail opportunity cost — a versioned result that CONSUMES Phase 4 planning.

Opportunity cost consumes the Phase 4 inventory plan (Demand/Supply/Need/Excess/months) for the
candidate's exact Sellable Combination; it NEVER calculates a separate Demand. It identifies the
affected combination and months, remains distinguishable from Executive Demo benefit, and is not a
generic acquisition score. A candidate whose combination is in Need has a higher opportunity cost
than one in Excess (proven from the plan, not assumed); unknown return timing reduces confidence; a
changed Executive Demo assignment path alone never alters Demand (Demand is an input).
"""
from __future__ import annotations

from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from ..ids import new_id


class OpportunityCostService:
    def __init__(self, store, policy_store, clock, calc_version):
        self.store, self.policy, self.clock, self.calc_version = store, policy_store, clock, calc_version

    def assess(self, vehicle_unit_id, combination_id, scope, *, plan, expected_time_removed_months=1,
               expected_return_path=None, policy_versions=None, scenario_id=None):
        """`plan` is a Phase 4 InventoryPlanResult for the candidate's combination. Deterministic
        cost derived from the plan position — higher when the combination is in Need, lower in
        Excess — scaled by the expected months removed from New Retail."""
        if plan.need > 0:
            position, weight = "need", 1.0 + float(plan.need)
        elif plan.excess > 0:
            position, weight = "excess", max(0.1, 1.0 - 0.1 * float(plan.excess))
        else:
            position, weight = "balanced", 1.0
        value = round(float(expected_time_removed_months) * weight, 4)
        confidence = "low" if not expected_return_path else "medium"
        affected_months = [m.month for m in plan.months]
        checksum = output_checksum({"combination": combination_id, "position": position, "value": value,
                                    "months": affected_months})
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "executive_demo_opportunity_cost", "calculation_version": self.calc_version,
                                    "plan": plan.id, "position": position, "value": value},
            calculation_timestamp=self.store._now(), implementation_revision="phase7-opp-cost",
            output_reference=checksum))
        return self.store.add_opportunity_cost(
            vehicle_unit_id, combination_id, scope, affected_months=affected_months, plan_position=position,
            cost_value={"value": value, "basis": "phase4_plan_position"}, expected_return_path=expected_return_path,
            confidence=confidence, policy_versions=policy_versions, calculation_version=self.calc_version,
            plan_refs=[plan.id], reproducibility_package=pkg.id, scenario_id=scenario_id)
