"""Exception + unresolved queues.

Each queue item REFERENCES the authoritative source record (it does not duplicate the source truth).
A resolution action routes to the owning domain; closing a queue item never silently resolves the
source; queue history stays inspectable; priority is explainable; dismissal requires authority + reason.
"""
from __future__ import annotations

from ..errors import ValidationError
from .models import EXCEPTION_QUEUES


class ExceptionQueueService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def enqueue(self, *, queue, source_type, source_ref, owning_domain=None, store_scope=None,
                subject_entity_id=None, priority="normal", reason=""):
        if queue not in EXCEPTION_QUEUES:
            raise ValidationError(technical_detail=f"unknown queue {queue}")
        return self.store.add_op_exception(queue=queue, source_type=source_type, source_ref=source_ref,
                                           owning_domain=owning_domain, store_scope=store_scope,
                                           subject_entity_id=subject_entity_id, priority=priority, reason=reason)

    def list(self, queue=None, *, status="open"):
        return self.store.op_exceptions(queue=queue, status=status)

    def route_resolution(self, item):
        """Return the owning-domain route for a resolution action (the resolution happens in the domain,
        NOT here — closing the queue item does not resolve the source)."""
        return {"owning_domain": item["owning_domain"], "source_type": item["source_type"],
                "source_ref": item["source_ref"], "queue": item["queue"]}

    def close(self, item, *, note=""):
        """Mark the queue item closed. This does NOT touch the source record."""
        with self.store.conn:
            self.store.set_op_exception(self.store.conn, item["id"], item["version"], status="closed")
        return self.store.get_op_exception(item["id"])

    def dismiss(self, principal, scope, item, *, reason):
        """Dismissal requires authority + reason (governed + audited)."""
        if not reason:
            raise ValidationError(technical_detail="dismissal requires a reason")

        def business(conn):
            self.store.set_op_exception(conn, item["id"], item["version"], status="dismissed",
                                        dismissed_by=principal, dismissal_reason=reason)
            return (item["id"], item["id"]), item["id"]
        self.gov.perform(principal_id=principal, capability="audit.exception.review", scope=scope,
                         action="exception.dismiss", business_fn=business, target_ref=item["source_ref"])
        return self.store.get_op_exception(item["id"])
