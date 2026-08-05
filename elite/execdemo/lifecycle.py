"""Governed Executive Demo lifecycle transitions.

Each transition authorizes below the UI, validates the legal membership transition, persists the
state change + a membership-history row + any field/effect atomically with an Audit Event (Phase 1
Governor), rejects stale concurrency, and is idempotent under a retry key.
"""
from __future__ import annotations

from ..errors import ConcurrencyError, ValidationError
from .models import TRANSITIONS


def governed_transition(gov, store, *, principal, capability, scope, unit_id, expected_version, to_state,
                        action, effect=None, guard=None, field_updates=None, correlation_id=None,
                        idempotency_key=None):
    def business(conn):
        cur = store.get_unit(unit_id)
        if cur is None:
            raise ValidationError(technical_detail="executive demo unit not found")
        if to_state not in TRANSITIONS.get(cur.membership_state, set()):
            raise ValidationError(message="That Executive Demo change is not allowed.",
                                  technical_detail=f"illegal transition {cur.membership_state}->{to_state}")
        if guard:
            guard(cur)
        sets = {"membership_state": to_state}
        if field_updates:
            sets.update(field_updates(cur))
        cols = ",".join(f"{k}=?" for k in sets)
        params = list(sets.values()) + [unit_id, expected_version]
        c = conn.execute(f"UPDATE executive_demo_unit SET {cols},version=version+1 WHERE id=? AND version=?", params)
        if c.rowcount == 0:
            raise ConcurrencyError(technical_detail=f"executive demo unit {unit_id} stale")
        eff = effect(conn, cur) if effect else {}
        store.insert_membership_history(conn, unit_id, cur.membership_state, to_state, actor=principal, action=action,
                                        reconciliation_ref=eff.get("reconciliation_ref"), detail=eff.get("detail", ""))
        return (unit_id, eff), unit_id
    res = gov.perform(principal_id=principal, capability=capability, scope=scope, action=action, business_fn=business,
                      target_ref=unit_id, correlation_id=correlation_id, idempotency_key=idempotency_key)
    if res.get("replayed"):
        return {"unit": store.get_unit(unit_id), "replayed": True, "effect": {}}
    return {"unit": store.get_unit(unit_id), "replayed": False, "effect": res.get("value", (None, {}))[1],
            "audit_id": res.get("audit_id")}
