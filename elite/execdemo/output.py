"""Operational Executive Demo output slices.

Smallest real outputs for the portfolio, need, candidates, Best Overall recommendation, tradeoff
comparison, opportunity cost, expected lifecycle, Economic Call, Execution Status, and the pending /
retirement / return-to-retail / used-cars / scenario queues. Each uses REAL stored records. Not the
full Phase 10 UX.
"""
from __future__ import annotations

import json


def _call(unit):
    return {
        "CANDIDATE": "REVIEW — candidate, not active membership.",
        "DESIGNATION_APPROVED": "COMMITTED — designation approved (not yet active).",
        "ACTIVE": "ACTIVE — Executive Demo (removed from New Retail supply).",
        "RETIREMENT_PROPOSED": "REVIEW — retirement proposed.",
        "RETIRED": "RETIRED — awaiting disposition.",
        "RETURNED_TO_NEW_RETAIL": "DONE — returned to New Retail supply.",
        "AWAITING_USED_CARS_RECEIPT": "HANDOFF — awaiting Used Cars receipt.",
        "USED_CARS_RECEIVED": "DONE — received by Used Cars.",
    }.get(unit.membership_state, unit.membership_state)


def build_unit_slice(store, nistore, unit_id, *, economic=None, execution=None, opportunity_cost=None):
    u = store.get_unit(unit_id)
    if u is None:
        return None
    return {
        "call": _call(u),
        "why": {"membership_state": u.membership_state, "portfolio_role": u.portfolio_role,
                "active_fleet_supply_ref": u.active_fleet_supply_ref},
        "proof": {"membership_history": [(h["from_state"], h["to_state"], h["action"])
                                         for h in store.membership_history(unit_id)],
                  "reconciliations": [r["outcome"] for r in store.reconciliations_for(unit_id)]},
        "vehicle_unit_id": u.vehicle_unit_id,
        "vin": u.vin,
        "combination_id": u.combination_id,
        "new_retail_refs": (json.loads(opportunity_cost["plan_refs"]) if opportunity_cost else []),
        "opportunity_cost": (json.loads(opportunity_cost["cost_value"]) if opportunity_cost else {}),
        "executive_demo_benefit": (economic.expected_benefit if economic else {}),
        "model_preference": u.model_preference_evidence,
        "expected_lifecycle": None,
        "portfolio_state": u.membership_state,
        "committed_state": u.designation_decision,
        "economic_call": (economic.economic_call if economic else {}),
        "execution_status": (execution["status"] if execution else None),
        "confidence": u.confidence,
        "uncertainty": (economic.uncertainty if economic else {}),
        "policy_versions": (economic.policy_versions if economic else []),
        "calculation_version": (economic.calculation_version if economic else None),
        "evidence": {"economic_result": (economic.id if economic else None),
                     "opportunity_cost": (opportunity_cost["id"] if opportunity_cost else None)},
        "raw_history_path": f"executive_demo_unit/{unit_id}",
        "unresolved": u.membership_state == "ACTIVE_UNRESOLVED",
    }


def portfolio_slice(plan_row):
    """Real projection of a stored portfolio plan (Best Overall + tradeoffs + need)."""
    return {
        "call": "PORTFOLIO PLAN",
        "need": plan_row["need"], "required_size": plan_row["required_size"],
        "current_active": plan_row["current_active"], "committed": plan_row["committed"],
        "selected": json.loads(plan_row["selected"]),
        "best_overall": json.loads(plan_row["best_overall"]),
        "tradeoffs": json.loads(plan_row["tradeoffs"]),
        "sacrifices": json.loads(plan_row["sacrifices"]),
        "need_basis": json.loads(plan_row["need_basis"]),
    }


def queue(store, scope, states):
    return [{"executive_demo_unit_id": u.id, "vin": u.vin, "state": u.membership_state} for u in
            store.units_in_states(scope, states)]
