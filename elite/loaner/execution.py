"""Execution Status — separate from the Economic Call.

Execution Status explains why the (financially strongest) Economic Call can or cannot be acted on
right now. Operational infeasibility may BLOCK execution but must never rewrite the Economic Call.
"""
from __future__ import annotations


class ExecutionService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def assess(self, unit, economic_result_id, *, identity_ok=True, data_ok=True, policy_ok=True,
               rented=False, return_confirmed=True, operational_ok=True, approved=False, executed=False,
               failed=False):
        """Derive Execution Status from operational flags (checked in priority order). The Economic
        Call is an input and is never modified here."""
        blockers = []
        if failed:
            status = "FAILED"
        elif not identity_ok:
            status, _ = "BLOCKED_IDENTITY", blockers.append("unresolved identity")
        elif not data_ok:
            status, _ = "BLOCKED_DATA", blockers.append("insufficient accepted data")
        elif not policy_ok:
            status, _ = "BLOCKED_POLICY", blockers.append("policy does not permit")
        elif rented:
            status, _ = "BLOCKED_RENTED", blockers.append("unit is currently rented")
        elif not return_confirmed:
            status, _ = "BLOCKED_RETURN_NOT_CONFIRMED", blockers.append("return not confirmed")
        elif not operational_ok:
            status, _ = "BLOCKED_OPERATIONAL", blockers.append("operational constraint")
        elif executed:
            status = "COMPLETED"
        elif approved:
            status = "APPROVED_NOT_EXECUTED"
        else:
            status = "READY"
        return self.store.add_execution_status(unit.id, economic_result_id, status,
                                               reason="; ".join(blockers), blocking_factors=blockers)
