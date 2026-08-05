"""Need / Excess (deterministic, month-aware) + portfolio reconciliation.

Demand defines the expected requirement; qualifying Supply defines available/arriving coverage;
desired ending coverage defines the approved target buffer. Need is shortage against the target;
Excess is supply beyond the target. Invariants proven by tests + fixtures:
  * Need >= 0 and Excess >= 0, and never both positive for the same evaluated state.
  * Added qualifying Supply cannot increase Need; removed qualifying Supply cannot decrease it.
  * A later-arriving unit cannot satisfy an earlier month (per-month cumulative supply).
  * One physical/future unit counts once (qualifying is pre-deduped by identity).
  * Committed Supply counts exactly once and updates the next calculation.
  * Changing the acquisition path alone never changes Demand (Demand is an input, supply-blind).
Continued unsold inventory IS explicitly modeled: a unit available in month m stays available in
later months' cumulative supply.
"""
from __future__ import annotations

from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import InventoryPlanMonth, InventoryPlanResult, PortfolioPlanResult


def _le(a, b):
    """available_month <= evaluated month; None means 'already available' (<= everything)."""
    if a is None:
        return True
    return a <= b


def _in_horizon(available_month, horizon):
    if available_month is None:
        return True
    return available_month <= horizon[-1]


def plan_math(inputs: dict) -> dict:
    """Pure, deterministic Need/Excess computation used by issue() and replay()."""
    horizon = inputs["horizon"]
    demand = inputs["demand_monthly"]
    qualifying = inputs["qualifying"]
    coverage = inputs["coverage_target"]              # None => unresolved
    total_demand = round(sum(demand.get(m, 0.0) for m in horizon), 6)
    qual_in = [u for u in qualifying if _in_horizon(u.get("available_month"), horizon)]
    total_qual = len(qual_in)

    months = []
    cum_d = 0.0
    for i, m in enumerate(horizon):
        cum_d = round(cum_d + demand.get(m, 0.0), 6)
        cum_s = sum(1 for u in qualifying if _in_horizon(u.get("available_month"), horizon)
                    and _le(u.get("available_month"), m))
        shortage = round(max(0.0, cum_d - cum_s), 6)
        months.append({"month": m, "expected_demand": demand.get(m, 0.0), "cumulative_demand": cum_d,
                       "cumulative_supply": cum_s, "shortage": shortage,
                       "excess": round(max(0.0, cum_s - cum_d), 6), "seq": i})

    if coverage is None:
        return {"state": "unresolved", "total_demand": total_demand, "total_qualifying": total_qual,
                "need": 0.0, "excess": 0.0, "months": months}
    requirement = round(total_demand + float(coverage), 6)
    need = round(max(0.0, requirement - total_qual), 6)
    excess = round(max(0.0, total_qual - requirement), 6)
    state = "need" if need > 0 else ("excess" if excess > 0 else "balanced")
    return {"state": state, "total_demand": total_demand, "total_qualifying": total_qual,
            "requirement": requirement, "need": need, "excess": excess, "months": months}


class PlanningService:
    def __init__(self, store, clock, policy_store):
        self.store, self.clock, self.policy = store, clock, policy_store

    def issue(self, demand_result, *, horizon, qualifying, coverage_target, counts,
              calculation_version, coverage_resolution=None, scenario_id=None, confidence=None):
        inputs = {"horizon": list(horizon), "demand_monthly": dict(demand_result.monthly_expected),
                  "qualifying": [{"key": u["key"], "available_month": u.get("available_month")} for u in qualifying],
                  "coverage_target": coverage_target}
        res = plan_math(inputs)
        checksum = output_checksum({"need": res["need"], "excess": res["excess"],
                                    "months": [(m["month"], m["shortage"]) for m in res["months"]]})
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "plan", "calculation_version": calculation_version,
                                    "inputs": inputs, "demand_result": demand_result.id, "result": res},
            calculation_timestamp=self.store._now(), implementation_revision="phase4-plan",
            output_reference=checksum))
        p = InventoryPlanResult(
            id=new_id("plan"), store_scope=demand_result.store_scope, planning_state=res["state"],
            combination_id=demand_result.combination_id, evaluated_start=horizon[0] if horizon else None,
            evaluated_end=horizon[-1] if horizon else None, expected_demand=res["total_demand"],
            current_supply=counts.get("current", 0), future_supply=counts.get("future", 0),
            committed_supply=counts.get("committed", 0), qualifying_supply=res["total_qualifying"],
            desired_ending_coverage=(coverage_resolution.resolved_value if coverage_resolution else
                                     {"target_units": coverage_target}),
            need=res["need"], excess=res["excess"], confidence=confidence or demand_result.confidence,
            evidence={"demand_result": demand_result.id, "evidence_tier": demand_result.evidence_tier,
                      "coverage_status": (coverage_resolution.resolution_status if coverage_resolution else "assumed"),
                      "qualifying_keys": [u["key"] for u in qualifying]},
            policy_versions=list(demand_result.policy_versions), calculation_version=calculation_version,
            reproducibility_package=pkg.id, demand_result_id=demand_result.id, scenario_id=scenario_id,
            months=[InventoryPlanMonth(id=new_id("pm"), plan_id="", month=m["month"],
                                       expected_demand=m["expected_demand"], cumulative_demand=m["cumulative_demand"],
                                       cumulative_supply=m["cumulative_supply"], shortage=m["shortage"],
                                       excess=m["excess"], confidence=confidence or demand_result.confidence,
                                       seq=m["seq"]) for m in res["months"]])
        return self.store.add_plan(p)

    def replay(self, package_id):
        pkg = self.policy.get_reproducibility(package_id)
        res = plan_math(pkg.refs["inputs"])
        checksum = output_checksum({"need": res["need"], "excess": res["excess"],
                                    "months": [(m["month"], m["shortage"]) for m in res["months"]]})
        return res, (checksum == pkg.output_reference)

    # ---- portfolio aggregation (never recalculates Demand) -----------------
    def issue_portfolio(self, scope, plans, *, level, grouping_key, calculation_version,
                        evaluated_start=None, evaluated_end=None):
        """Aggregate canonical combination plans into a model / model-year / portfolio summary.
        Aggregation SUMS issued combination results — it does not independently recompute Demand.
        Combination-level errors remain traceable via plan_refs."""
        monthly_demand = {}
        supply_by_state = {"current": 0, "future": 0, "committed": 0, "qualifying": 0}
        need = excess = unresolved = 0.0
        for p in plans:
            for m in p.months:
                monthly_demand[m.month] = round(monthly_demand.get(m.month, 0.0) + m.expected_demand, 6)
            for k in supply_by_state:
                supply_by_state[k] += getattr(p, {"current": "current_supply", "future": "future_supply",
                                                   "committed": "committed_supply",
                                                   "qualifying": "qualifying_supply"}[k])
            need += p.need
            excess += p.excess
            if p.planning_state == "unresolved":
                unresolved += 1
        confidences = {p.confidence for p in plans}
        conf = "low" if "low" in confidences else ("medium" if "medium" in confidences else "high")
        pf = PortfolioPlanResult(
            id=new_id("pf"), store_scope=scope, level=level, grouping_key=grouping_key,
            evaluated_start=evaluated_start, evaluated_end=evaluated_end,
            summary={"combinations": len(plans), "need": round(need, 6), "excess": round(excess, 6)},
            plan_refs=[p.id for p in plans], monthly_demand=monthly_demand, supply_by_state=supply_by_state,
            need=round(need, 6), excess=round(excess, 6), unresolved_quantity=unresolved, confidence=conf,
            timing_risk="elevated" if any(p.months and p.months[0].shortage > 0 for p in plans) else "normal",
            calculation_version=calculation_version)
        return self.store.add_portfolio(pf)
