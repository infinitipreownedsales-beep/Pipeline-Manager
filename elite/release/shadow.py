"""Controlled shadow mode.

Each domain runs in a visible, domain-specific shadow mode. No domain advances automatically; every mode
change is governed + audited and appended to an immutable event log (the latest row is the current mode).
Execution stays BLOCKED unless a mode explicitly enables it. Mode history is preserved.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from .models import CAPS, SHADOW_MODES, SHADOW_EXECUTION_ENABLED

DEFAULT_MODE = "DATA_ONLY"


class ShadowModeService:
    def __init__(self, release_store, governor, clock, logger=None):
        self.store, self.gov, self.clock, self.logger = release_store, governor, clock, logger

    def current_mode(self, domain, scope):
        row = self.store.current_shadow_mode(domain, scope)
        return row["mode"] if row else DEFAULT_MODE

    def execution_enabled(self, domain, scope):
        return self.current_mode(domain, scope) in SHADOW_EXECUTION_ENABLED

    def set_mode(self, *, principal, scope, domain, mode, reason=None, correlation_id=None):
        if mode not in SHADOW_MODES:
            raise ValidationError(technical_detail=f"unknown shadow mode {mode}")

        def business(conn):
            sid = new_id("shm")
            conn.execute(
                "INSERT INTO domain_shadow_mode(id,domain,store_scope,mode,changed_by,reason,correlation_id,"
                "recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                (sid, domain, scope, mode, principal, reason, correlation_id,
                 self.store._now()))
            return (sid, sid), sid
        res = self.gov.perform(principal_id=principal, capability=CAPS["SHADOW_SET"], scope=scope,
                               action="release.shadow.set", business_fn=business,
                               correlation_id=correlation_id)
        # stamp the audit ref onto the row is not needed (immutable); the governed action recorded the audit
        if self.logger:
            self.logger.op("release", "release.shadow.set", result=mode, correlation_id=correlation_id,
                           domain=domain)
        return self.store.current_shadow_mode(domain, scope)

    def history(self, domain, scope):
        return self.store.shadow_history(domain, scope)
