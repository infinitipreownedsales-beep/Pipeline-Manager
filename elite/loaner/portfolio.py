"""Service Loaner entry selection + fleet portfolio optimization.

Fleet NEED is an input or policy-resolved requirement, resolved independently from individual
candidate ranking; the system then answers which specific eligible units should fill it. Selection
is explainable (eligibility + availability + New-Retail opportunity cost as an INPUT), never a single
generic acquisition-ranking score, and never redefines New Retail Demand. Approved entries update
committed fleet state; the next recommendation uses the updated state; the same unit cannot be
recommended twice; a unit already active/approved/retired/committed is treated by its actual state.
Necessary-sacrifice recommendations remain explainable.
"""
from __future__ import annotations

from .models import ACTIVE_MEMBERSHIP

_UNAVAILABLE_STATES = ACTIVE_MEMBERSHIP | {"ENTRY_PROPOSED", "ENTRY_APPROVED", "ENTRY_PENDING", "RETIRED",
                                          "USED_CARS_RECEIVED", "AWAITING_USED_CARS_RECEIPT"}


class PortfolioService:
    def __init__(self, store, clock, calc_version):
        self.store, self.clock, self.calc_version = store, clock, calc_version

    def current_active(self, scope):
        return len(self.store.units_in_states(scope, sorted(ACTIVE_MEMBERSHIP)))

    def plan_entries(self, scope, *, required_quantity, candidates, need_basis=None, policy_versions=None,
                     scenario_id=None, sacrifice_threshold=None):
        """`candidates`: [{vehicle_unit_id, combination_id, eligible, available, opportunity_cost,
        actual_state}]. Selects the fewest eligible+available units to fill (required - current
        active), lowest opportunity cost first; flags necessary sacrifices explicitly."""
        current = self.current_active(scope)
        need = max(0, required_quantity - current)
        seen, eligible = set(), []
        for c in candidates:
            vid = c.get("vehicle_unit_id")
            if vid in seen:
                continue                                         # never consider the same unit twice
            seen.add(vid)
            actual = c.get("actual_state")
            if actual in _UNAVAILABLE_STATES:
                continue                                         # already active/approved/retired/committed
            if not c.get("eligible") or not c.get("available", True):
                continue
            eligible.append(c)
        eligible.sort(key=lambda c: (c.get("opportunity_cost", {}) or {}).get("value", 0))
        selected = eligible[:need]
        sacrifices = [c for c in selected
                      if sacrifice_threshold is not None
                      and (c.get("opportunity_cost", {}) or {}).get("value", 0) >= sacrifice_threshold]
        plan = self.store.add_portfolio_plan(
            scope, required_quantity=required_quantity, current_active=current,
            selected=[c["vehicle_unit_id"] for c in selected],
            sacrifices=[{"vehicle_unit_id": c["vehicle_unit_id"],
                         "opportunity_cost": c.get("opportunity_cost", {})} for c in sacrifices],
            need_basis=need_basis or {"required": required_quantity, "current_active": current, "need": need},
            policy_versions=policy_versions, calculation_version=self.calc_version, scenario_id=scenario_id)
        return plan
