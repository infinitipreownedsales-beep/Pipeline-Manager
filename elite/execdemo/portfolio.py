"""Executive Demo portfolio need + candidate construction + Best Overall selection.

Portfolio need is resolved BEFORE candidate ranking and accounts for active + committed Executive Demo
state (Service Loaner fleet need never enters it; New Retail Demand is never recalculated here). Best
Overall selection is a PORTFOLIO optimization over the full business objective — not a single-field
sort: the lowest New Retail opportunity cost does not automatically win, nor does the highest Executive
Demo benefit if the New Retail sacrifice is excessive. Model preference influences selection only
through approved policy. Every plan records the per-candidate tradeoff breakdown (so the proof is never
just an opaque composite score), labels necessary sacrifices, updates committed state, and never
selects the same unit twice or an already-active/committed/retired unit.
"""
from __future__ import annotations

from .models import ACTIVE_MEMBERSHIP, UNAVAILABLE

# Objective weights (recorded in each plan for explainability). Portfolio fit is weighted so a
# strong complete fit can outrank both the cheapest and the highest-benefit unit.
W_BENEFIT, W_OPP_COST, W_FIT, W_PREFERENCE = 1.0, 1.0, 2.0, 1.5
_COMMITTED_STATES = {"DESIGNATION_PROPOSED", "DESIGNATION_APPROVED", "DESIGNATION_PENDING"}


def _val(d, key="value", default=0.0):
    if isinstance(d, dict):
        return float(d.get(key, default))
    return float(d if d is not None else default)


class PortfolioService:
    def __init__(self, store, clock, calc_version):
        self.store, self.clock, self.calc_version = store, clock, calc_version

    def current_active(self, scope):
        return len(self.store.units_in_states(scope, sorted(ACTIVE_MEMBERSHIP)))

    def committed(self, scope):
        return len(self.store.units_in_states(scope, sorted(_COMMITTED_STATES)))

    def determine_need(self, scope, required_size):
        """Resolve portfolio need from committed state BEFORE any ranking. Service Loaner need never
        enters this calculation."""
        active, committed = self.current_active(scope), self.committed(scope)
        need = max(0, required_size - active - committed)
        return {"required": required_size, "current_active": active, "committed": committed, "need": need}

    def construct_candidate(self, scope, *, vehicle_unit_id, combination_id, model=None, model_year=None,
                            age_days=None, mileage=None, eligibility="ELIGIBLE", new_retail_refs=None,
                            opportunity_cost_ref=None, expected_value=None, expected_lifecycle_ref=None,
                            policy_versions=None, source_refs=None, scenario_id=None):
        """Build a candidate record from accepted facts + New Retail planning references. Missing
        facts stay absent (never invented)."""
        return self.store.add_candidate(
            vehicle_unit_id=vehicle_unit_id, combination_id=combination_id, store_scope=scope, model=model,
            model_year=model_year, age_days=age_days, mileage=mileage, eligibility=eligibility,
            new_retail_refs=new_retail_refs or {}, opportunity_cost_ref=opportunity_cost_ref,
            expected_value=expected_value or {}, expected_lifecycle_ref=expected_lifecycle_ref,
            policy_versions=policy_versions, calculation_version=self.calc_version, source_refs=source_refs,
            scenario_id=scenario_id)

    def best_overall(self, scope, *, required_size, candidates, preference=None, sacrifice_threshold=None,
                     policy_versions=None, scenario_id=None):
        """`candidates`: [{vehicle_unit_id, combination_id, model, eligibility, opportunity_cost,
        executive_demo_benefit, portfolio_fit, actual_state}]. Selects the Best Overall set for the
        resolved need using the full objective; records tradeoffs + sacrifices."""
        basis = self.determine_need(scope, required_size)
        need = basis["need"]
        preferred_model = (preference or {}).get("preferred") if isinstance(preference, dict) else None
        seen, scored = set(), []
        for c in candidates:
            vid = c.get("vehicle_unit_id")
            if vid in seen:
                continue                                             # never twice
            seen.add(vid)
            if c.get("eligibility") != "ELIGIBLE":
                continue                                             # eligibility is a hard gate
            if c.get("actual_state") in UNAVAILABLE:
                continue                                             # active/committed/retired excluded
            benefit = _val(c.get("executive_demo_benefit"))
            opp = _val(c.get("opportunity_cost"))
            fit = _val(c.get("portfolio_fit"))
            pref_bonus = W_PREFERENCE if (preferred_model and c.get("model") == preferred_model) else 0.0
            objective = round(W_BENEFIT * benefit - W_OPP_COST * opp + W_FIT * fit + pref_bonus, 6)
            scored.append({"vehicle_unit_id": vid, "combination_id": c.get("combination_id"), "model": c.get("model"),
                           "objective": objective,
                           "tradeoffs": {"executive_demo_benefit": benefit, "new_retail_opportunity_cost": opp,
                                         "portfolio_fit": fit, "model_preference_bonus": pref_bonus},
                           "opportunity_cost": opp})
        scored.sort(key=lambda s: s["objective"], reverse=True)
        selected = scored[:need]
        sacrifices = [{"vehicle_unit_id": s["vehicle_unit_id"], "opportunity_cost": s["opportunity_cost"],
                       "label": "necessary_sacrifice"}
                      for s in selected if sacrifice_threshold is not None and s["opportunity_cost"] >= sacrifice_threshold]
        best = selected[0] if selected else {}
        plan = self.store.add_portfolio_plan(
            scope, required_size=required_size, current_active=basis["current_active"], committed=basis["committed"],
            need=need, selected=[s["vehicle_unit_id"] for s in selected],
            best_overall={"pick": best, "objective_weights": {"benefit": W_BENEFIT, "opportunity_cost": W_OPP_COST,
                          "portfolio_fit": W_FIT, "model_preference": W_PREFERENCE}},
            tradeoffs=scored, sacrifices=sacrifices, need_basis=basis, policy_versions=policy_versions,
            calculation_version=self.calc_version, scenario_id=scenario_id)
        return plan
