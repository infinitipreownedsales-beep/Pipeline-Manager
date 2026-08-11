"""Deterministic fixture-loading support for tests and controlled bootstrap.

Builds a fully wired platform stack against an explicit db path + injected clock,
so tests are reproducible and never depend on wall-clock or ambient config.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

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


@dataclass(frozen=True)
class RuntimeConfig:
    """Real runtime configuration for the production/pilot launcher.

    The launcher resolves this ONCE from the environment (the credential pepper from ELITE_AUTH_SECRET,
    a real system clock, and the explicit ELITE_ENV environment) and threads it down the constructor chain
    so the base Stack is built with real runtime identity instead of the test defaults. Test and fixture
    constructors pass no RuntimeConfig and keep their deterministic defaults.

    ``pilot_scope`` is the authoritative store scope (resolved once from ELITE_PILOT_SCOPE) that the login
    UI and ops CLI operate at — kept here as the single source of truth so no UI/CLI site re-parses the
    environment or hardcodes a dealership string.

    ``revision`` is the technical build/release identity stamped on diagnostic logs (distinct from
    ``environment``, the deployment class, and from the UI's schema/db revision). The real launcher resolves
    it once from ELITE_REVISION, falling back to the environment value — never the fixture "test" default.
    """
    pepper: str
    clock: object
    environment: Environment
    pilot_scope: str = ""
    revision: str = "test"


class Stack:
    """A wired platform stack. Test/fixture callers use the deterministic defaults; the production launcher
    passes a real pepper, a real clock, and the real environment."""

    def __init__(self, db_path, *, environment=Environment.TEST, pepper="test-pepper",
                 clock=None, revision="test"):
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
        self.logger = StructuredLogger(environment, revision)
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
