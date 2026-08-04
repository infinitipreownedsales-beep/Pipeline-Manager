"""Repository contracts + SQLite implementations.

Persistence sits behind explicit contracts (ABCs) so the store is replaceable.
Writes support optimistic concurrency (version checks) and idempotency. Audit has
its own append-only repository in `audit.py`.
"""
from __future__ import annotations

import abc
import sqlite3
from typing import Optional

from .clock import to_utc_iso
from .errors import ConcurrencyError, PersistenceError
from .models import CapabilityGrant, PersistenceProbe, Principal


# ---- contracts -------------------------------------------------------------
class PrincipalRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, p: Principal, secret_hash: str, secret_salt: str) -> Principal: ...
    @abc.abstractmethod
    def get(self, principal_id: str) -> Optional[Principal]: ...
    @abc.abstractmethod
    def credentials(self, principal_id: str): ...


class GrantRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, g: CapabilityGrant) -> CapabilityGrant: ...
    @abc.abstractmethod
    def list_for(self, principal_id: str) -> list[CapabilityGrant]: ...
    @abc.abstractmethod
    def revoke(self, grant_id: str, expected_version: int, when) -> CapabilityGrant: ...


class MetadataRepository(abc.ABC):
    @abc.abstractmethod
    def put_if_absent(self, key: str, value: str) -> str: ...
    @abc.abstractmethod
    def get(self, key: str) -> Optional[str]: ...


class ProbeRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, p: PersistenceProbe) -> PersistenceProbe: ...
    @abc.abstractmethod
    def get(self, probe_id: str) -> Optional[PersistenceProbe]: ...


class IdempotencyStore(abc.ABC):
    @abc.abstractmethod
    def seen(self, key: str) -> Optional[str]: ...
    @abc.abstractmethod
    def record(self, key: str, result_ref: str, when): ...


# ---- SQLite implementations ------------------------------------------------
class SqlitePrincipalRepository(PrincipalRepository):
    def __init__(self, conn: sqlite3.Connection, clock):
        self.conn, self.clock = conn, clock

    def add(self, p, secret_hash, secret_salt):
        created = p.created_at or to_utc_iso(self.clock.now())
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO principal(id,display_name,secret_hash,secret_salt,active,created_at,version)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (p.id, p.display_name, secret_hash, secret_salt, int(p.active), created, p.version))
        except sqlite3.IntegrityError as e:
            raise PersistenceError(technical_detail=f"principal insert: {e}")
        p.created_at = created
        return p

    def get(self, principal_id):
        r = self.conn.execute("SELECT * FROM principal WHERE id=?", (principal_id,)).fetchone()
        if not r:
            return None
        return Principal(id=r["id"], display_name=r["display_name"], active=bool(r["active"]),
                         version=r["version"], created_at=r["created_at"])

    def credentials(self, principal_id):
        r = self.conn.execute("SELECT secret_hash,secret_salt,active FROM principal WHERE id=?",
                              (principal_id,)).fetchone()
        if not r:
            return None
        return {"secret_hash": r["secret_hash"], "secret_salt": r["secret_salt"], "active": bool(r["active"])}


class SqliteGrantRepository(GrantRepository):
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def add(self, g):
        granted = g.granted_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute(
                "INSERT INTO capability_grant(id,principal_id,capability,authority,scope,active,granted_at,revoked_at,version)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (g.id, g.principal_id, g.capability, g.authority, g.scope,
                 int(g.active), granted, g.revoked_at, g.version))
        g.granted_at = granted
        return g

    def list_for(self, principal_id):
        rows = self.conn.execute("SELECT * FROM capability_grant WHERE principal_id=?",
                                 (principal_id,)).fetchall()
        return [CapabilityGrant(id=r["id"], principal_id=r["principal_id"], capability=r["capability"],
                                authority=r["authority"], scope=r["scope"], active=bool(r["active"]),
                                version=r["version"], granted_at=r["granted_at"], revoked_at=r["revoked_at"])
                for r in rows]

    def revoke(self, grant_id, expected_version, when):
        """Optimistic concurrency: a stale version is rejected."""
        with self.conn:
            cur = self.conn.execute(
                "UPDATE capability_grant SET active=0, revoked_at=?, version=version+1"
                " WHERE id=? AND version=?",
                (to_utc_iso(when), grant_id, expected_version))
            if cur.rowcount == 0:
                exists = self.conn.execute("SELECT version FROM capability_grant WHERE id=?",
                                           (grant_id,)).fetchone()
                if exists is None:
                    raise PersistenceError(technical_detail=f"grant {grant_id} not found")
                raise ConcurrencyError(
                    technical_detail=f"grant {grant_id}: expected v{expected_version}, have v{exists['version']}")
        r = self.conn.execute("SELECT * FROM capability_grant WHERE id=?", (grant_id,)).fetchone()
        return CapabilityGrant(id=r["id"], principal_id=r["principal_id"], capability=r["capability"],
                               authority=r["authority"], scope=r["scope"], active=bool(r["active"]),
                               version=r["version"], granted_at=r["granted_at"], revoked_at=r["revoked_at"])


class SqliteMetadataRepository(MetadataRepository):
    def __init__(self, conn):
        self.conn = conn

    def put_if_absent(self, key, value):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO system_metadata(key,value) VALUES(?,?)", (key, value))
        return self.get(key)

    def get(self, key):
        r = self.conn.execute("SELECT value FROM system_metadata WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None


class SqliteProbeRepository(ProbeRepository):
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def add(self, p):
        created = p.created_at or to_utc_iso(self.clock.now())
        with self.conn:
            self.conn.execute("INSERT INTO persistence_probe(id,note,created_at) VALUES(?,?,?)",
                              (p.id, p.note, created))
        p.created_at = created
        return p

    def get(self, probe_id):
        r = self.conn.execute("SELECT * FROM persistence_probe WHERE id=?", (probe_id,)).fetchone()
        return None if not r else PersistenceProbe(id=r["id"], note=r["note"], created_at=r["created_at"])


class SqliteIdempotencyStore(IdempotencyStore):
    def __init__(self, conn):
        self.conn = conn

    def seen(self, key):
        r = self.conn.execute("SELECT result_ref FROM idempotency_record WHERE key=?", (key,)).fetchone()
        return r["result_ref"] if r else None

    def record(self, key, result_ref, when):
        self.conn.execute("INSERT OR IGNORE INTO idempotency_record(key,result_ref,created_at) VALUES(?,?,?)",
                          (key, result_ref, to_utc_iso(when)))
