"""Governed Scenario override creation + isolation contract.

A Scenario override is an *isolated* what-if policy value. Creating one is a governed
action requiring the `scenario.override` capability (enforced below the UI). A scenario
override:
  * exists only within its owning scenario (never resolves in official context);
  * NEVER becomes active official policy merely by existing or by being shared;
  * carries its own effective dating and scope but is tagged is_scenario=1.

Sharing a scenario does not activate its overrides — promotion to official policy would
be a separate, distinct governed action (not provided here in Phase 3).
"""
from __future__ import annotations

from ..clock import to_utc_iso
from ..ids import new_id
from .models import PolicyVersion


def create_override(gov, store, *, principal, scope, family_id, scenario_id, value,
                    subject_scope=None, effective_start=None, effective_end=None, clock,
                    correlation_id=None, idempotency_key=None):
    """Create an isolated Scenario override policy version via a governed action.

    Requires capability `scenario.override`. The version is persisted with
    is_scenario=1 and lifecycle ACTIVE *within the scenario only* — resolution never
    surfaces it in official context (see resolution.resolve)."""
    def business(conn):
        pv = PolicyVersion(
            id=new_id("pv"), family_id=family_id, version_number=1, value=value,
            lifecycle_status="ACTIVE", recorded_time=to_utc_iso(clock.now()),
            scope=subject_scope or {}, effective_start=effective_start, effective_end=effective_end,
            approval_state="scenario", is_scenario=True, scenario_id=scenario_id,
            store_scope=scope, provenance={"scenario": scenario_id})
        store.insert_version(conn, pv)
        return pv, pv.id
    res = gov.perform(principal_id=principal, capability="scenario.override", scope=scope,
                      action="scenario.override.create", business_fn=business,
                      correlation_id=correlation_id, idempotency_key=idempotency_key)
    return store.get_version(res["result_ref"])
