"""First operational New Inventory output slice.

The smallest useful renderable output that proves the domain works: it exposes Call, Why, Proof,
Raw-History / evidence references, the month-by-month plan, Current/Future/Committed Supply,
Demand, Need, Excess, confidence, unresolved state, and applicable versions. It consumes REAL
Phase 4 domain output (a stored InventoryPlanResult + DemandResult) — never mocked text — and is
deliberately NOT the full Phase 10 UX.
"""
from __future__ import annotations


def _call(plan):
    if plan.planning_state == "unresolved":
        return "REVIEW — required coverage policy unresolved; no target set."
    if plan.planning_state == "need":
        return f"ORDER — short {plan.need:g} unit(s) against target."
    if plan.planning_state == "excess":
        return f"HOLD/REDUCE — {plan.excess:g} unit(s) beyond target."
    return "LEAVE ALONE — supply meets the approved target."


def build_slice(store, plan_id):
    """Return a structured slice dict for a stored plan. Pure projection of issued domain output."""
    plan = store.get_plan(plan_id)
    if plan is None:
        return None
    demand = store.get_demand(plan.demand_result_id) if plan.demand_result_id else None
    comb = store.get_combination(plan.combination_id) if plan.combination_id else None
    return {
        "call": _call(plan),
        "why": {
            "planning_state": plan.planning_state,
            "expected_demand": plan.expected_demand,
            "qualifying_supply": plan.qualifying_supply,
            "desired_ending_coverage": plan.desired_ending_coverage,
            "need": plan.need, "excess": plan.excess,
        },
        "proof": {
            "demand_evidence_tier": demand.evidence_tier if demand else None,
            "demand_direct": demand.direct_evidence if demand else None,
            "seasonality": demand.seasonality_ref if demand else None,
            "trend": demand.trend_ref if demand else None,
            "coverage": plan.desired_ending_coverage,
        },
        "raw_history_refs": {
            "demand_fact_refs": demand.fact_refs if demand else [],
            "demand_source_refs": demand.source_refs if demand else [],
            "qualifying_keys": plan.evidence.get("qualifying_keys", []),
        },
        "month_by_month": [
            {"month": m.month, "expected_demand": m.expected_demand, "cumulative_demand": m.cumulative_demand,
             "cumulative_supply": m.cumulative_supply, "shortage": m.shortage} for m in plan.months
        ],
        "supply": {"current": plan.current_supply, "future": plan.future_supply,
                   "committed": plan.committed_supply, "qualifying": plan.qualifying_supply},
        "demand": demand.monthly_expected if demand else {},
        "need": plan.need,
        "excess": plan.excess,
        "confidence": plan.confidence,
        "uncertainty": demand.uncertainty if demand else {},
        "unresolved": plan.planning_state in ("unresolved", "conflicting"),
        "combination": {"id": comb.id, "identity": comb.canonical_identity} if comb else None,
        "versions": {
            "calculation_version": plan.calculation_version,
            "policy_versions": plan.policy_versions,
            "reproducibility_package": plan.reproducibility_package,
            "demand_reproducibility_package": demand.reproducibility_package if demand else None,
            "scenario_id": plan.scenario_id,
        },
    }
