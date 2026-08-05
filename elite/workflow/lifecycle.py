"""Governed workflow lifecycle.

Each proposal / transition authorizes below the UI, validates the legal transition for the
workflow type, persists the status change + a transition row + a commitment-reconciliation result
+ any supply effect atomically with an Audit Event (Phase 1 Governor), rejects stale concurrency,
and is idempotent under a retry key. The supply effect runs via RAW inserts on the governed
connection so business write + effect + audit commit together.
"""
from __future__ import annotations

from ..errors import ConcurrencyError, ValidationError
from ..ids import new_id
from .models import TRANSITIONS, ReconciliationResult


def _record_recon(wfstore, conn, workflow_id, transition_id, eff):
    rr = ReconciliationResult(
        id=new_id("crr"), outcome=eff["outcome"], workflow_id=workflow_id, transition_ref=transition_id,
        subject_identity=eff.get("subject_identity"), combination_id=eff.get("combination_id"),
        supply_ref=eff.get("supply_ref"), prior_qualifying=eff.get("prior_qualifying"),
        new_qualifying=eff.get("new_qualifying"), detail=eff.get("detail", ""))
    wfstore.insert_reconciliation(conn, rr)
    return rr


def governed_propose(gov, wfstore, *, principal, capability, scope, workflow, action,
                     effect=None, correlation_id=None, idempotency_key=None):
    """Insert a new workflow already in PROPOSED and record a DRAFT→PROPOSED transition +
    reconciliation (normally NO_SUPPLY_EFFECT), atomically with the Audit Event."""
    def business(conn):
        workflow.lifecycle_status = "PROPOSED"
        wfstore.insert_workflow(conn, workflow)
        eff = effect(conn, workflow) if effect else {"outcome": "NO_SUPPLY_EFFECT"}
        tid = wfstore.insert_transition(conn, workflow.id, "DRAFT", "PROPOSED", actor=principal, action=action)
        _record_recon(wfstore, conn, workflow.id, tid, eff)
        return workflow.id, workflow.id
    res = gov.perform(principal_id=principal, capability=capability, scope=scope, action=action,
                      business_fn=business, target_ref=workflow.id, correlation_id=correlation_id,
                      idempotency_key=idempotency_key)
    return {"workflow": wfstore.get_workflow(workflow.id), "replayed": res.get("replayed", False),
            "audit_id": res.get("audit_id")}


def governed_transition(gov, wfstore, *, principal, capability, scope, workflow_id, expected_version,
                        wf_type, to_status, action, effect=None, guard=None, correlation_id=None,
                        idempotency_key=None):
    """Transition an existing workflow. Legal-transition + optimistic-concurrency checked; the
    supply effect (if any) runs raw inside the same transaction. On idempotent replay, nothing
    re-applies and a DUPLICATE_REPLAY reconciliation is recorded."""
    def business(conn):
        cur = wfstore.get_workflow(workflow_id)
        if cur is None:
            raise ValidationError(technical_detail="workflow not found")
        if to_status not in TRANSITIONS[wf_type].get(cur.lifecycle_status, set()):
            raise ValidationError(message="That workflow change is not allowed.",
                                  technical_detail=f"illegal {wf_type} transition {cur.lifecycle_status}->{to_status}")
        if guard:
            guard(cur)
        c = conn.execute("UPDATE supply_workflow SET lifecycle_status=?,version=version+1 WHERE id=? AND version=?",
                         (to_status, workflow_id, expected_version))
        if c.rowcount == 0:
            raise ConcurrencyError(technical_detail=f"workflow {workflow_id} stale")
        eff = effect(conn, cur) if effect else {"outcome": "NO_SUPPLY_EFFECT"}
        tid = wfstore.insert_transition(conn, workflow_id, cur.lifecycle_status, to_status, actor=principal,
                                        action=action)
        _record_recon(wfstore, conn, workflow_id, tid, eff)
        return (workflow_id, eff), workflow_id
    res = gov.perform(principal_id=principal, capability=capability, scope=scope, action=action,
                      business_fn=business, target_ref=workflow_id, correlation_id=correlation_id,
                      idempotency_key=idempotency_key)
    if res.get("replayed"):
        # No effect re-applied; record the explicit duplicate-replay outcome (own transaction).
        wfstore.add_reconciliation(ReconciliationResult(id=new_id("crr"), outcome="DUPLICATE_REPLAY",
                                   workflow_id=workflow_id, detail=f"idempotent replay of {action}"))
        return {"workflow": wfstore.get_workflow(workflow_id), "replayed": True, "outcome": "DUPLICATE_REPLAY",
                "supply_ref": None}
    eff = res.get("value", (None, {}))[1]
    return {"workflow": wfstore.get_workflow(workflow_id), "replayed": False, "outcome": eff.get("outcome"),
            "supply_ref": eff.get("supply_ref"), "reconciliation": eff, "audit_id": res.get("audit_id")}
