"""Capability provisioning for the identity-governance surface.

`identity.govern` was introduced after the pilot database was provisioned, so principals granted their capability
bundle earlier (e.g. Kyle's live GSM/admin principal) never received it — the governed Translation bootstrap then
fails closed with "Not permitted". This backfills the grant through the NORMAL grant mechanism, idempotently, and
without weakening the wall: only principals who ALREADY hold governance authority (the `authority.grant`
capability — the manager/admin designation) receive `identity.govern`; ordinary view-only users never do.
Safe to run on every startup (a no-op once granted).
"""
from __future__ import annotations

ANCHOR = "authority.grant"      # the capability that designates a governance-authorized manager/admin
CAPABILITY = "identity.govern"


def ensure_identity_governance_grants(stack, *, anchor=ANCHOR, capability=CAPABILITY):
    """Grant `capability` at each scope where a principal already holds `anchor` but lacks `capability`.
    Returns the list of (principal_id, scope) newly granted. Uses stack.grant (the same governed path as every
    other grant); never revokes or widens an existing grant."""
    conn = stack.db.conn
    try:
        rows = conn.execute(
            "SELECT DISTINCT principal_id, scope FROM capability_grant WHERE capability=? AND active=1",
            (anchor,)).fetchall()
    except Exception:   # noqa: BLE001 — a missing/older schema must never block startup
        return []
    granted = []
    for r in rows:
        pid, scope = r["principal_id"], r["scope"]
        try:
            if stack.authz.decide(pid, capability, scope).allowed:
                continue
            stack.grant(pid, capability, scope, authority="system:identity-provision")
            granted.append((pid, scope))
        except Exception:   # noqa: BLE001 — one principal's provisioning failure must not abort the rest
            continue
    return granted
