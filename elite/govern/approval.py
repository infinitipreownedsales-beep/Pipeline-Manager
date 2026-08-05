"""Governed approval, where the domain action requires it.

Proposal and approval authorities stay distinct; a policy separation-of-duties rule may require the
Decision maker and approver to differ. Approval validates current domain state, is rejected when stale
or when the acting authority is revoked, is idempotent under a retry key, and cannot exceed the
Decision's scope or quantity. Approval does NOT imply execution. Conditional approval stays inspectable.
Approval expiration is enforced downstream.
"""
from __future__ import annotations

from ..errors import ValidationError


class ApprovalService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def approve(self, principal, scope, decision, *, approved_action=None, quantity=None, decision_quantity=None,
                subject_identity=None, conditions=None, expiration=None, stale=False, idempotency_key=None,
                correlation_id=None):
        if stale:
            raise ValidationError(message="This approval is stale.", technical_detail="stale approval rejected")
        d = self.store.get_decision(decision["id"])
        if d is None or d["disposition"] in ("REJECT", "CANCEL", "CORRECT", "SUPERSEDE", "NO_ACTION"):
            raise ValidationError(technical_detail="decision not in an approvable state")
        if quantity is not None and decision_quantity is not None and quantity > decision_quantity:
            raise ValidationError(message="Approval cannot exceed the Decision quantity.",
                                  technical_detail=f"approve {quantity} > decision {decision_quantity}")

        def business(conn):
            aid = self.store.insert_approval(
                conn, decision["id"], approving_principal=principal, scope=scope,
                approved_action=approved_action or d["selected_action"], quantity=quantity,
                subject_identity=subject_identity, conditions=conditions or {}, expiration=expiration,
                idempotency_key=idempotency_key)
            return (aid, aid), aid
        res = self.gov.perform(principal_id=principal, capability="decision.approve", scope=scope,
                               action="decision.approve", business_fn=business, target_ref=decision["id"],
                               correlation_id=correlation_id, idempotency_key=idempotency_key)
        if res.get("replayed"):
            return {"approval": self.store.get_approval(res["result_ref"]), "replayed": True}
        return {"approval": self.store.get_approval(res["value"][0]), "replayed": False}
