"""Consolidated Audit review over the Phase 1 append-only Audit Event stream.

The Audit Event remains immutable; review is read-only and never rewrites the underlying event.
Correlated multi-step actions stay traceable by correlation id; failed atomic actions stay
distinguishable from successful ones; a missing expected Audit Event creates an exception. Audit access
is authorized and scoped.
"""
from __future__ import annotations


class AuditAdminService:
    def __init__(self, store, authorizer, clock):
        self.store, self.authorizer, self.clock = store, authorizer, clock
        self.conn = store.conn

    def review(self, principal, scope, *, actor=None, action=None, target_ref=None, correlation_id=None,
               result=None, limit=200):
        self.authorizer.require(principal, "audit.view", scope)
        q, args = "SELECT * FROM audit_event WHERE 1=1", []
        for col, val in (("actor", actor), ("action", action), ("target_ref", target_ref),
                         ("correlation_id", correlation_id), ("result", result)):
            if val is not None:
                q += f" AND {col}=?"
                args.append(val)
        return self.conn.execute(q + " ORDER BY occurred_at,id LIMIT ?", (*args, limit)).fetchall()

    def trace(self, principal, scope, correlation_id):
        """Correlated multi-step action trace (Decision → approval → execution …)."""
        return self.review(principal, scope, correlation_id=correlation_id, limit=1000)

    def detect_missing(self, *, expected_action, correlation_id=None, subject_ref=None):
        """A missing expected Audit Event creates an exception (never a silent gap)."""
        q, args = "SELECT COUNT(*) n FROM audit_event WHERE action=?", [expected_action]
        if correlation_id is not None:
            q, _ = q + " AND correlation_id=?", args.append(correlation_id)
        n = self.conn.execute(q, args).fetchone()["n"]
        if n == 0:
            return self.store.add_audit_exception(kind="missing_expected_event", expected_action=expected_action,
                                                  correlation_id=correlation_id, subject_ref=subject_ref,
                                                  detail="expected audit event not found")
        return None
