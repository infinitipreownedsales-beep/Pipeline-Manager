"""Consolidated authority administration over the Phase 1 permission system.

This uses the Phase 1 `capability_grant` store + `Authorizer` — it does NOT create a second permission
store. Temporary authority expires automatically per its contract; a revoked grant is immediately
ineffective; delegation cannot exceed the delegator's own capability or scope; a delegated action stays
attributable to the acting Principal and the grant chain. Grant, delegation, expiration, and revocation
remain historical. Authority changes are governed (authorized + audited atomically); an audit failure
blocks the mutation.
"""
from __future__ import annotations

from ..authz import _scope_matches
from ..errors import ValidationError
from ..ids import new_id
from ..models import CapabilityGrant


class AuthorityAdminService:
    def __init__(self, store, stack, gov, clock):
        self.store, self.stack, self.gov, self.clock = store, stack, gov, clock

    def _principal_has(self, principal_id, capability, scope):
        for g in self.stack.grants.list_for(principal_id):
            if g.capability == capability and g.effective() and _scope_matches(g.scope, scope):
                return g
        return None

    def grant(self, principal, scope, *, to_principal, capability, grant_scope, reason=""):
        """Governed grant creation using the Phase 1 grant repository."""
        def business(conn):
            g = CapabilityGrant(id=new_id("grant"), principal_id=to_principal, capability=capability,
                                authority="delegated" if reason else "system", scope=grant_scope)
            conn.execute("INSERT INTO capability_grant(id,principal_id,capability,authority,scope,active,granted_at,"
                         "revoked_at,version) VALUES(?,?,?,?,?,?,?,?,?)",
                         (g.id, g.principal_id, g.capability, g.authority, g.scope, 1, self.store._now(), None, 1))
            return (g.id, g.id), g.id
        res = self.gov.perform(principal_id=principal, capability="authority.grant", scope=scope,
                               action="authority.grant", business_fn=business, target_ref=to_principal)
        return res["value"][0]

    def delegate(self, principal, scope, *, delegate, capability, delegate_scope, reason="", expiration=None):
        """Delegation cannot exceed the delegator's own capability or scope."""
        held = self._principal_has(principal, capability, delegate_scope)
        if held is None:
            raise ValidationError(message="You cannot delegate authority you do not hold.",
                                  technical_detail=f"delegator lacks {capability}@{delegate_scope}")
        if held.scope != "*" and held.scope != delegate_scope:
            raise ValidationError(message="Delegation cannot exceed your scope.",
                                  technical_detail=f"delegator scope {held.scope} < {delegate_scope}")

        def business(conn):
            gid = new_id("grant")
            conn.execute("INSERT INTO capability_grant(id,principal_id,capability,authority,scope,active,granted_at,"
                         "revoked_at,version) VALUES(?,?,?,?,?,?,?,?,?)",
                         (gid, delegate, capability, f"delegated_by:{principal}", delegate_scope, 1, self.store._now(),
                          None, 1))
            did = self.store.insert_delegation(conn, delegator=principal, delegate=delegate, capability=capability,
                                               scope=delegate_scope, grant_ref=gid, reason=reason, expiration=expiration)
            return (did, did), did
        res = self.gov.perform(principal_id=principal, capability="authority.delegate", scope=scope,
                               action="authority.delegate", business_fn=business, target_ref=delegate)
        return self.store.get_delegation(res["value"][0])

    def revoke_delegation(self, principal, scope, delegation):
        """Revoke a delegation and its backing grant — immediately ineffective."""
        def business(conn):
            if delegation["grant_ref"]:
                conn.execute("UPDATE capability_grant SET active=0,revoked_at=?,version=version+1 WHERE id=?",
                             (self.store._now(), delegation["grant_ref"]))
            self.store.set_delegation(conn, delegation["id"], delegation["version"], active=0,
                                      revoked_at=self.store._now())
            return (delegation["id"], delegation["id"]), delegation["id"]
        self.gov.perform(principal_id=principal, capability="authority.revoke", scope=scope,
                         action="authority.revoke", business_fn=business, target_ref=delegation["delegate"])
        return self.store.get_delegation(delegation["id"])

    def grant_temporary(self, principal, scope, *, to_principal, capability, grant_scope, expiration, reason=""):
        """A temporary grant that expires automatically per its contract."""
        def business(conn):
            gid = new_id("grant")
            conn.execute("INSERT INTO capability_grant(id,principal_id,capability,authority,scope,active,granted_at,"
                         "revoked_at,version) VALUES(?,?,?,?,?,?,?,?,?)",
                         (gid, to_principal, capability, f"temporary_by:{principal}", grant_scope, 1, self.store._now(),
                          None, 1))
            tid = self.store.insert_temporary_grant(conn, principal_id=to_principal, capability=capability,
                                                    scope=grant_scope, grant_ref=gid, grantor=principal, reason=reason,
                                                    expiration=expiration)
            return (tid, gid), tid
        res = self.gov.perform(principal_id=principal, capability="authority.grant", scope=scope,
                               action="authority.grant_temporary", business_fn=business, target_ref=to_principal)
        return res["value"][0], res["result_ref"]

    def enforce_temporary_expiry(self, *, now=None):
        """Revoke every temporary grant whose expiration has passed (contract-driven auto-expiry)."""
        from ..clock import to_utc_iso
        now = now or to_utc_iso(self.clock.now())
        expired = self.store.conn.execute("SELECT * FROM authority_temporary_grant WHERE expiration<=?",
                                          (now,)).fetchall()
        for t in expired:
            g = self.store.conn.execute("SELECT active FROM capability_grant WHERE id=?", (t["grant_ref"],)).fetchone()
            if g and g["active"]:
                with self.store.conn:
                    self.store.conn.execute("UPDATE capability_grant SET active=0,revoked_at=?,version=version+1 "
                                            "WHERE id=?", (now, t["grant_ref"]))
        return len(expired)
