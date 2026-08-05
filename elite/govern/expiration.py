"""Expiration + staleness for recommendations, Decisions, approvals, execution authorizations,
Scenarios, and Calibration schedules.

Staleness rules are explicit and policy-resolvable. New accepted facts — or new policy/calculation
versions where defined — may make a recommendation stale. Stale does NOT delete the record; a stale
Decision cannot execute without renewed review or an authorized override. Expiration is never inferred
as rejection; an expired authority cannot approve or execute; historical expired/stale records remain
inspectable.
"""
from __future__ import annotations

from ..clock import to_utc_iso


class ExpirationService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def mark_recommendation_stale(self, item, *, reason, triggering_fact=None, triggering_version=None,
                                  policy_versions=None):
        """A new accepted fact (or new version) makes the recommendation stale. The recommendation and
        workspace item remain historical (only a stale marker is set)."""
        res = self.store.add_staleness("workspace_item", item["id"], stale=True, reason=reason,
                                       triggering_fact=triggering_fact, triggering_version=triggering_version,
                                       policy_versions=policy_versions)
        self.store.set_workspace_item_now(item["id"], item["version"], stale=1)
        return res

    def is_recommendation_stale(self, item_id):
        rows = self.store.staleness_for(item_id)
        return bool(rows) and bool(rows[-1]["stale"])

    def set_expiration(self, target_type, target_ref, *, expires_at, policy_versions=None):
        return self.store.add_expiration(target_type, target_ref, expires_at=expires_at,
                                         policy_versions=policy_versions)

    def expire(self, expiration_id):
        self.store.mark_expired(expiration_id)

    def is_expired(self, target_ref, *, now=None):
        now = now or to_utc_iso(self.clock.now())
        for e in self.store.expirations_for(target_ref):
            if e["expired"]:
                return True
            if e["expires_at"] and e["expires_at"] <= now:
                return True
        return False
