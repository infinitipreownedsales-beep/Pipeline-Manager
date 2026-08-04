"""Governed actions — bind an authoritative write to its Audit Event, atomically.

A governed action:
  1. requires authorization (below the UI);
  2. optionally short-circuits on an idempotency key (no duplicate effect);
  3. runs the business write AND the audit append inside ONE transaction.

If the required audit write fails, the whole transaction rolls back — so a governed
action can never be reported successful without its Audit Event. Audit is distinct
from the business write but committed with it.
"""
from __future__ import annotations

from .audit import make_event
from .errors import EliteError, PersistenceError, UnknownInternalError


class Governor:
    def __init__(self, db, authorizer, audit_repo, idempotency, clock, environment, logger=None):
        self.db = db
        self.authorizer = authorizer
        self.audit = audit_repo
        self.idem = idempotency
        self.clock = clock
        self.environment = environment
        self.logger = logger

    def perform(self, *, principal_id, capability, scope, action, business_fn,
                target_ref=None, correlation_id=None, delegated_actor=None,
                idempotency_key=None):
        """business_fn(conn) -> (result_value, resulting_ref). Executed inside the
        governed transaction alongside the audit append."""
        self.authorizer.require(principal_id, capability, scope, correlation_id=correlation_id)

        if idempotency_key is not None:
            prior = self.idem.seen(idempotency_key)
            if prior is not None:
                if self.logger:
                    self.logger.info(action, result="idempotent_replay",
                                     correlation_id=correlation_id)
                return {"result_ref": prior, "replayed": True}

        conn = self.db.conn
        try:
            with conn:  # single atomic transaction: business + audit (+ idempotency)
                result_value, resulting_ref = business_fn(conn)
                event = make_event(self.clock, self.environment, actor=principal_id,
                                   action=action, result="success", target_ref=target_ref,
                                   scope=scope, correlation_id=correlation_id,
                                   delegated_actor=delegated_actor, resulting_ref=resulting_ref)
                # Required audit write — failure here aborts the whole action.
                self.audit.append(conn, event)
                if idempotency_key is not None:
                    self.idem.record(idempotency_key, resulting_ref, self.clock.now())
        except EliteError:
            raise
        except Exception as e:  # audit or business failure -> nothing committed
            raise PersistenceError(
                message="The action could not be completed safely.",
                technical_detail=f"governed action rolled back: {type(e).__name__}: {e}",
                **({"correlation_id": correlation_id} if correlation_id else {}))
        if self.logger:
            self.logger.info(action, result="success", correlation_id=correlation_id)
        return {"result_ref": resulting_ref, "audit_id": event.id, "replayed": False,
                "value": result_value}
