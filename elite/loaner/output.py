"""Operational Service Loaner output slices.

Smallest real outputs for: active fleet, entry recommendation, retirement recommendation, Economic
Call, Execution Status, provisional-retirement queue, awaiting-return queue, Used Cars handoff queue,
zero-mile-rented review queue, and policy scenario comparison. Each uses REAL stored domain records.
Not the full Phase 10 UX.
"""
from __future__ import annotations


def _call(unit):
    st = unit.membership_state
    return {
        "CANDIDATE": "REVIEW — candidate, not active membership.",
        "ACTIVE_AVAILABLE": "ACTIVE — available in the loaner fleet.",
        "ACTIVE_RENTED": "ACTIVE — currently rented.",
        "RETIREMENT_PROPOSED": "REVIEW — retirement proposed.",
        "PROVISIONAL_RETIREMENT": "PROVISIONAL — retire on return (still active/rented).",
        "AWAITING_USED_CARS_RECEIPT": "HANDOFF — awaiting Used Cars receipt.",
        "USED_CARS_RECEIVED": "DONE — received by Used Cars.",
        "RETURNED_TO_NEW_RETAIL": "DONE — returned to New Retail supply.",
    }.get(st, f"{st}")


def build_unit_slice(store, nistore, unit_id, *, economic=None, execution=None):
    """Structured slice for one Service Loaner unit from stored records."""
    u = store.get_unit(unit_id)
    if u is None:
        return None
    mileage = store.current_mileage(unit_id)
    alerts = [a for a in store.alerts_for(unit_id) if a.status == "active"]
    return {
        "call": _call(u),
        "why": {"membership_state": u.membership_state, "rental_state": u.current_rental_state,
                "active_fleet_presence": u.active_fleet_presence},
        "proof": {"membership_history": [(h["from_state"], h["to_state"], h["action"])
                                         for h in store.membership_history(unit_id)],
                  "reconciliations": [r["outcome"] for r in store.reconciliations_for(unit_id)]},
        "vehicle_unit_id": u.vehicle_unit_id,
        "vin": u.vin,
        "combination_id": u.combination_id,
        "membership_and_rental_state": {"membership": u.membership_state, "rental": u.current_rental_state},
        "in_service_date": {"accepted": u.accepted_in_service_date, "authority": u.in_service_date_authority},
        "last_checkout_mileage": ({"kind": mileage.value_kind, "value": mileage.value} if mileage else None),
        "economic_alternatives": (economic.alternatives if economic else []),
        "economic_call": (economic.economic_call if economic else {}),
        "execution_status": (execution["status"] if execution else None),
        "policy_versions": (economic.policy_versions if economic else []),
        "calculation_version": (economic.calculation_version if economic else None),
        "confidence": u.confidence,
        "uncertainty": (economic.uncertainty if economic else {}),
        "workflow_state": u.membership_state,
        "evidence_references": {"economic_result": (economic.id if economic else None),
                                "reproducibility_package": (economic.reproducibility_package if economic else None),
                                "active_alerts": [a.id for a in alerts]},
        "raw_history_path": f"service_loaner_unit/{unit_id}",
        "monitoring_alerts": [{"rule": a.rule, "prompt": a.prompt} for a in alerts],
        "unresolved": u.membership_state == "ACTIVE_UNRESOLVED",
    }


def queue(store, scope, states):
    """Real projection of units in the given membership states (for queue slices)."""
    return [{"service_loaner_unit_id": u.id, "vin": u.vin, "state": u.membership_state,
             "rental": u.current_rental_state} for u in store.units_in_states(scope, states)]


def zero_mile_queue(store, scope):
    """Units with an active zero-mile-rented alert."""
    out = []
    for u in store.units_in_states(scope, ["ACTIVE_RENTED", "ACTIVE_AVAILABLE", "PROVISIONAL_RETIREMENT"]):
        a = store.active_alert(u.id, "zero_mile_rented")
        if a:
            out.append({"service_loaner_unit_id": u.id, "vin": u.vin, "prompt": a.prompt,
                        "elapsed_days": a.elapsed_days, "threshold_days": a.threshold_days})
    return out
