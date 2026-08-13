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


def position_math(inputs: dict) -> dict:
    """Time-phased order-up-to Need/Excess (the corrected dealer-facing model).

    Target Days Supply is a STOCK LEVEL, not a flow: `target_level` already equals the desired ~60-day
    productive coverage in units (decided upstream from credibility-shrunk velocity, DTS risk, and the
    breadth/depth split). The planning horizon is only a CLOCK used to time supply and detect near-term
    troughs — horizon demand is NEVER added to the target (that was the 3mo+60d ≈ 150-day bug).

    Inventory position = arrived-now + incoming that reliably arrives within the horizon (known ETA).
    Incoming with UNKNOWN timing is never credited as available — it is reported as pending_timing and
    only lowers urgency. Incoming with a KNOWN ETA beyond the horizon is future coverage (reported, not
    counted as immediately-available position).

        net_need   = max(0, target_level - inventory_position)      # additional units to acquire NOW
        net_excess = max(0, inventory_position - target_level)      # genuine surplus vs the 60-day level

    A month-by-month trajectory (arrived + timed incoming - cumulative demand) is walked purely to flag a
    near-term shortage even when net_need is 0 (e.g. inbound arrives after the dip)."""
    horizon = inputs["horizon"]
    demand = inputs["demand_monthly"]
    qualifying = inputs["qualifying"]
    target = inputs["target_level"]
    end = horizon[-1] if horizon else None

    arrived = [u for u in qualifying if u.get("stage") == "DLR-INV"]
    incoming = [u for u in qualifying if u.get("stage") != "DLR-INV"]
    known_in = [u for u in incoming if u.get("available_month") and u["available_month"] <= end]
    known_post = [u for u in incoming if u.get("available_month") and u["available_month"] > end]
    pending = [u for u in incoming if not u.get("available_month")]

    inventory_position = len(arrived) + len(known_in)
    net_need = round(max(0.0, target - inventory_position), 6)
    net_excess = round(max(0.0, inventory_position - target), 6)
    state = "need" if net_need > 0 else ("excess" if net_excess > 0 else "balanced")

    months, cum_d, trough = [], 0.0, None
    for i, m in enumerate(horizon):
        cum_d = round(cum_d + demand.get(m, 0.0), 6)
        avail = len(arrived) + sum(1 for u in known_in if u["available_month"] <= m)
        pos = round(avail - cum_d, 6)
        trough = pos if trough is None else min(trough, pos)
        months.append({"month": m, "expected_demand": demand.get(m, 0.0), "cumulative_demand": cum_d,
                       "cumulative_supply": avail, "shortage": round(max(0.0, cum_d - avail), 6),
                       "excess": round(max(0.0, avail - cum_d), 6), "seq": i})
    total_demand = round(sum(demand.get(m, 0.0) for m in horizon), 6)
    return {"state": state, "target_level": round(float(target), 6), "inventory_position": inventory_position,
            "arrived": len(arrived), "incoming_in_horizon": len(known_in),
            "incoming_post_horizon": len(known_post), "pending_timing": len(pending),
            "need": net_need, "excess": net_excess, "total_demand": total_demand,
            "near_term_trough": trough, "months": months}


class PlanningService:
    def __init__(self, store, clock, policy_store):
        self.store, self.clock, self.policy = store, clock, policy_store

    def issue_position(self, demand_result, *, horizon, qualifying, target_level, counts,
                       calculation_version, decision=None, scenario_id=None, confidence=None):
        """Issue a governed DATA_ONLY plan using the corrected time-phased order-up-to model. `target_level`
        is the depth decision (units); `decision` is the explanatory evidence bundle (credibility, breadth,
        depth, DTS burden, timing) recorded on the plan without any schema change (JSON columns)."""
        inputs = {"horizon": list(horizon), "demand_monthly": dict(demand_result.monthly_expected),
                  "qualifying": [{"key": u["key"], "available_month": u.get("available_month"),
                                  "stage": u.get("stage")} for u in qualifying],
                  "target_level": float(target_level)}
        res = position_math(inputs)
        checksum = output_checksum({"need": res["need"], "excess": res["excess"],
                                    "months": [(m["month"], m["shortage"]) for m in res["months"]]})
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "plan_position", "calculation_version": calculation_version,
                                    "inputs": inputs, "demand_result": demand_result.id, "result": res},
            calculation_timestamp=self.store._now(), implementation_revision="phase4-plan-position",
            output_reference=checksum))
        p = InventoryPlanResult(
            id=new_id("plan"), store_scope=demand_result.store_scope, planning_state=res["state"],
            combination_id=demand_result.combination_id, evaluated_start=horizon[0] if horizon else None,
            evaluated_end=horizon[-1] if horizon else None, expected_demand=res["total_demand"],
            current_supply=counts.get("current", 0), future_supply=counts.get("future", 0),
            committed_supply=counts.get("committed", 0), qualifying_supply=res["inventory_position"],
            desired_ending_coverage={"target_units": res["target_level"], "model": "target_days_supply_level",
                                     "inventory_position": res["inventory_position"],
                                     "incoming_in_horizon": res["incoming_in_horizon"],
                                     "incoming_post_horizon": res["incoming_post_horizon"],
                                     "pending_timing": res["pending_timing"],
                                     "near_term_trough": res["near_term_trough"]},
            need=res["need"], excess=res["excess"], confidence=confidence or demand_result.confidence,
            evidence={"demand_result": demand_result.id, "evidence_tier": demand_result.evidence_tier,
                      "model": "time_phased_order_up_to", "decision": (decision or {}),
                      "qualifying_keys": [u["key"] for u in qualifying]},
            policy_versions=list(demand_result.policy_versions), calculation_version=calculation_version,
            reproducibility_package=pkg.id, demand_result_id=demand_result.id, scenario_id=scenario_id,
            months=[InventoryPlanMonth(id=new_id("pm"), plan_id="", month=m["month"],
                                       expected_demand=m["expected_demand"], cumulative_demand=m["cumulative_demand"],
                                       cumulative_supply=m["cumulative_supply"], shortage=m["shortage"],
                                       excess=m["excess"], confidence=confidence or demand_result.confidence,
                                       seq=m["seq"]) for m in res["months"]])
        return self.store.add_plan(p)

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
