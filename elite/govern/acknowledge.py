"""Decision acknowledgment — operational receipt/awareness.

Acknowledgment is NOT approval and NOT execution; it cannot alter the Decision; it is idempotent under
a retry key; and a required-but-missing acknowledgment stays visible.
"""
from __future__ import annotations


class AcknowledgmentService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def acknowledge(self, principal, scope, *, decision_id=None, workspace_item_id=None, ack_type="receipt",
                    comment=None, correlation_id=None, idempotency_key=None):
        key = idempotency_key or f"ack:{decision_id or workspace_item_id}:{principal}:{ack_type}"

        def business(conn):
            aid = self.store.insert_ack(conn, decision_id=decision_id, workspace_item_id=workspace_item_id,
                                        acknowledging_principal=principal, acknowledgment_type=ack_type,
                                        comment=comment, scope=scope, correlation_id=correlation_id,
                                        idempotency_key=key)
            return (aid, aid), aid
        res = self.gov.perform(principal_id=principal, capability="decision.acknowledge", scope=scope,
                               action="decision.acknowledge", business_fn=business,
                               target_ref=(decision_id or workspace_item_id), correlation_id=correlation_id,
                               idempotency_key=key)
        if res.get("replayed"):
            return {"acknowledgment": self.store.ack_by_idempotency(key), "replayed": True}
        return {"acknowledgment": self.store.ack_by_idempotency(key), "replayed": False}

    def outstanding(self, decision_id):
        """Required-but-missing acknowledgment stays visible: True when none recorded yet."""
        return not self.store.acks_for_decision(decision_id)
