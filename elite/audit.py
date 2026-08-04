"""Append-only Audit Event persistence.

Audit Events are the governance trail — distinct from Business Facts and Actual
Events. The repository exposes only append + read; the database enforces
append-only via triggers (see db.py). A required audit-write failure must prevent
a governed action from being reported successful (see governance.py).
"""
from __future__ import annotations

import abc
import sqlite3

from .clock import to_utc_iso
from .errors import PersistenceError
from .ids import audit_id
from .models import AuditEvent


class AuditRepository(abc.ABC):
    @abc.abstractmethod
    def append(self, conn, event: AuditEvent) -> AuditEvent: ...
    @abc.abstractmethod
    def get(self, event_id: str) -> AuditEvent | None: ...
    @abc.abstractmethod
    def count(self) -> int: ...


class SqliteAuditRepository(AuditRepository):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def append(self, conn, event: AuditEvent) -> AuditEvent:
        """Append within the CALLER's connection/transaction so it commits or rolls
        back atomically with the governed business write."""
        conn.execute(
            "INSERT INTO audit_event(id,actor,delegated_actor,action,target_ref,scope,environment,"
            "occurred_at,result,correlation_id,prior_ref,resulting_ref)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (event.id, event.actor, event.delegated_actor, event.action, event.target_ref,
             event.scope, event.environment, event.occurred_at, event.result,
             event.correlation_id, event.prior_ref, event.resulting_ref))
        return event

    def get(self, event_id):
        r = self.conn.execute("SELECT * FROM audit_event WHERE id=?", (event_id,)).fetchone()
        if not r:
            return None
        return AuditEvent(id=r["id"], actor=r["actor"], delegated_actor=r["delegated_actor"],
                          action=r["action"], target_ref=r["target_ref"], scope=r["scope"],
                          environment=r["environment"], occurred_at=r["occurred_at"], result=r["result"],
                          correlation_id=r["correlation_id"], prior_ref=r["prior_ref"],
                          resulting_ref=r["resulting_ref"])

    def count(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM audit_event").fetchone()["n"]


def make_event(clock, environment, actor, action, *, result="success", target_ref=None,
               scope=None, correlation_id=None, delegated_actor=None,
               prior_ref=None, resulting_ref=None) -> AuditEvent:
    return AuditEvent(id=audit_id(), actor=actor, action=action,
                      environment=environment.value if hasattr(environment, "value") else str(environment),
                      occurred_at=to_utc_iso(clock.now()), result=result, target_ref=target_ref,
                      scope=scope, correlation_id=correlation_id, delegated_actor=delegated_actor,
                      prior_ref=prior_ref, resulting_ref=resulting_ref)
