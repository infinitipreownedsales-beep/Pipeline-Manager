"""Durable authoritative persistence: SQLite connection + tracked migrations.

SQLite (stdlib) is the authoritative store. It is a real file that survives
process restart and is independent of any browser-local state. Migrations are
ordered, tracked in `migration_record`, and idempotent to re-run.
"""
from __future__ import annotations

import sqlite3

from .errors import MigrationError, PersistenceError


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


# Ordered migrations. Each is (version, name, SQL). Append-only history; never edit
# a released migration in place.
MIGRATIONS = [
    (1, "platform_core", """
        CREATE TABLE system_metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE principal (
            id          TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            secret_hash TEXT NOT NULL,
            secret_salt TEXT NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            version     INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE capability_grant (
            id           TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL REFERENCES principal(id),
            capability   TEXT NOT NULL,
            authority    TEXT NOT NULL,
            scope        TEXT NOT NULL,
            active       INTEGER NOT NULL DEFAULT 1,
            granted_at   TEXT NOT NULL,
            revoked_at   TEXT,
            version      INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE audit_event (
            id             TEXT PRIMARY KEY,
            actor          TEXT NOT NULL,
            delegated_actor TEXT,
            action         TEXT NOT NULL,
            target_ref     TEXT,
            scope          TEXT,
            environment    TEXT NOT NULL,
            occurred_at    TEXT NOT NULL,
            result         TEXT NOT NULL,
            correlation_id TEXT,
            prior_ref      TEXT,
            resulting_ref  TEXT
        );
        -- Audit is append-only, enforced below the application:
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_event
            BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
        CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_event
            BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
        CREATE TABLE idempotency_record (
            key        TEXT PRIMARY KEY,
            result_ref TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE persistence_probe (
            id         TEXT PRIMARY KEY,
            note       TEXT,
            created_at TEXT NOT NULL
        );
    """),
]


def _ensure_migration_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migration_record (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );""")


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_migration_table(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM migration_record").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def migrate(conn: sqlite3.Connection, clock) -> int:
    """Apply pending migrations in order. Returns the resulting version. Each
    migration + its record commit atomically; a failure aborts without partial state."""
    _ensure_migration_table(conn)
    applied_to = current_version(conn)
    for version, name, sql in MIGRATIONS:
        if version <= applied_to:
            continue
        if version != applied_to + 1:
            raise MigrationError(
                message="Migration sequence is broken.",
                technical_detail=f"expected {applied_to + 1}, found {version}")
        try:
            with conn:  # atomic
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO migration_record(version, name, applied_at) VALUES(?,?,?)",
                    (version, name, clock.now().isoformat()))
            applied_to = version
        except sqlite3.Error as e:
            raise MigrationError(message="A schema migration failed.",
                                 technical_detail=f"{name}: {e}")
    return applied_to


class Db:
    """Thin owner of a connection + migration state. Repositories take this."""

    def __init__(self, path: str, clock):
        self.path = path
        self.clock = clock
        self.conn = connect(path)

    def migrate(self) -> int:
        return migrate(self.conn, self.clock)

    def version(self) -> int:
        return current_version(self.conn)

    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error as e:
            raise PersistenceError(technical_detail=str(e))
