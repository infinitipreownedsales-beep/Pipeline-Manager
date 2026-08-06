"""SQLite durability settings + integrity/startup validation for the controlled pilot.

Documented operational settings suitable for a single-node pilot: foreign keys ON, WAL journal mode,
a NORMAL synchronous level (safe under WAL), and a busy timeout so a briefly locked database waits
rather than failing immediately. Integrity checks and startup validation are executable on demand.
Durability behavior is not changed without evidence + tests.
"""
from __future__ import annotations

from ..db import MIGRATIONS, current_version

DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_SYNCHRONOUS = "NORMAL"       # safe with WAL; FULL is available for stricter durability


def apply_durability(conn, *, busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS, synchronous=DEFAULT_SYNCHRONOUS):
    """Apply + return the durability PRAGMA snapshot. Idempotent."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute(f"PRAGMA synchronous = {synchronous};")
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)};")
    return durability_snapshot(conn)


def durability_snapshot(conn):
    def _one(pragma):
        row = conn.execute(f"PRAGMA {pragma};").fetchone()
        return row[0] if row else None
    return {
        "foreign_keys": _one("foreign_keys"),
        "journal_mode": _one("journal_mode"),
        "synchronous": _one("synchronous"),
        "busy_timeout": _one("busy_timeout"),
    }


def integrity_check(conn):
    """Run PRAGMA integrity_check; return 'ok' or a list of reported problems."""
    rows = conn.execute("PRAGMA integrity_check;").fetchall()
    results = [r[0] for r in rows]
    if results == ["ok"]:
        return "ok"
    return results


def quick_check(conn):
    rows = conn.execute("PRAGMA quick_check;").fetchall()
    results = [r[0] for r in rows]
    return "ok" if results == ["ok"] else results


def foreign_key_check(conn):
    """Return any foreign-key violations (empty list = clean)."""
    return [tuple(r) for r in conn.execute("PRAGMA foreign_key_check;").fetchall()]


def startup_validation(conn):
    """Validate a store is safe to serve: migrations current, integrity ok, foreign keys enforced.
    Returns a dict; `ok` is True only when every check passes."""
    version = current_version(conn)
    expected = MIGRATIONS[-1][0]
    integ = integrity_check(conn)
    fk_on = bool(durability_snapshot(conn)["foreign_keys"])
    fk_violations = foreign_key_check(conn)
    checks = {
        "schema_version": version,
        "expected_version": expected,
        "migrations_current": version == expected,
        "integrity": integ,
        "integrity_ok": integ == "ok",
        "foreign_keys_on": fk_on,
        "foreign_key_violations": fk_violations,
    }
    checks["ok"] = (checks["migrations_current"] and checks["integrity_ok"]
                    and checks["foreign_keys_on"] and not fk_violations)
    return checks
