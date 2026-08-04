"""Deterministic fixture-loading support for tests and controlled bootstrap.

Builds a fully wired platform stack against an explicit db path + injected clock,
so tests are reproducible and never depend on wall-clock or ambient config.
"""
from __future__ import annotations

import datetime as _dt

from .audit import SqliteAuditRepository
from .authz import Authorizer
from .auth import Authenticator
from .clock import FixedClock
from .db import Db
from .environment import Environment
from .governance import Governor
from .ids import grant_id
from .logging_ import StructuredLogger
from .models import CapabilityGrant
from .repositories import (SqliteGrantRepository, SqliteIdempotencyStore,
                           SqliteMetadataRepository, SqlitePrincipalRepository,
                           SqliteProbeRepository)

FIXED_START = _dt.datetime(2026, 1, 2, 15, 4, 5, tzinfo=_dt.timezone.utc)


class Stack:
    """A wired platform stack for tests/bootstrap."""

    def __init__(self, db_path, *, environment=Environment.TEST, pepper="test-pepper",
                 clock=None):
        self.environment = environment
        self.clock = clock or FixedClock(FIXED_START, step=_dt.timedelta(seconds=1))
        self.db = Db(db_path, self.clock)
        self.db.migrate()
        conn = self.db.conn
        self.principals = SqlitePrincipalRepository(conn, self.clock)
        self.grants = SqliteGrantRepository(conn, self.clock)
        self.metadata = SqliteMetadataRepository(conn)
        self.probes = SqliteProbeRepository(conn, self.clock)
        self.idempotency = SqliteIdempotencyStore(conn)
        self.audit = SqliteAuditRepository(conn)
        self.authn = Authenticator(self.principals, pepper)
        self.authz = Authorizer(self.grants)
        self.logger = StructuredLogger(environment, "test")
        self.governor = Governor(self.db, self.authz, self.audit, self.idempotency,
                                 self.clock, environment, self.logger)
        # Stamp environment identity so a store is never silently mistaken for another.
        self.metadata.put_if_absent("environment", environment.value)

    def grant(self, principal_id, capability, scope, authority="system"):
        g = CapabilityGrant(id=grant_id(), principal_id=principal_id, capability=capability,
                            authority=authority, scope=scope)
        return self.grants.add(g)

    def close(self):
        self.db.close()

    def reopen(self):
        """Simulate a process restart against the same durable file."""
        return Stack(self.db.path, environment=self.environment, clock=self.clock)
