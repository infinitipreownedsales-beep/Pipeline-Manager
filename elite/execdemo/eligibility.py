"""Executive Demo candidate eligibility — separate from candidate ranking.

Eligibility is a distinct gate with an explicit, reasoned outcome. It never silently admits a sold /
unresolved / already-demo / active-Service-Loaner / committed unit, and it never expresses a ranking.
An active Service Loaner is ineligible (the two fleet domains are separate; a unit cannot be active
in both simultaneously).
"""
from __future__ import annotations


class EligibilityService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def assess(self, vehicle_unit_id, combination_id, scope, *, is_active_service_loaner=False,
               already_demo=False, committed=False, sold=False, identity_ok=True, data_ok=True,
               policy_ok=True, conflicting=False, policy_versions=None):
        """Return the eligibility result record. Reasons are always recorded. Hard ineligibility
        (e.g. active Service Loaner, already demo, sold) is never overridden by preference/ranking."""
        reasons = []
        if conflicting:
            outcome = "CONFLICTING"; reasons.append("conflicting eligibility evidence")
        elif not identity_ok:
            outcome = "INELIGIBLE_IDENTITY"; reasons.append("unresolved vehicle identity")
        elif not data_ok:
            outcome = "INELIGIBLE_DATA"; reasons.append("insufficient accepted data")
        elif sold:
            outcome = "INELIGIBLE_SOLD"; reasons.append("unit is sold")
        elif is_active_service_loaner:
            outcome = "INELIGIBLE_ACTIVE_SERVICE_LOANER"; reasons.append("active in the Service Loaner domain")
        elif already_demo:
            outcome = "INELIGIBLE_ALREADY_DEMO"; reasons.append("already an active Executive Demo")
        elif committed:
            outcome = "INELIGIBLE_COMMITTED"; reasons.append("committed elsewhere")
        elif not policy_ok:
            outcome = "INELIGIBLE_POLICY"; reasons.append("policy does not permit")
        else:
            outcome = "ELIGIBLE"; reasons.append("meets eligibility criteria")
        return self.store.add_eligibility(vehicle_unit_id, combination_id, scope, outcome, reasons=reasons,
                                          policy_versions=policy_versions)
