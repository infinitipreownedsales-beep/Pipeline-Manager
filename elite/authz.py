"""Authorization foundation — authoritative access decisions.

Separate from authentication. A decision requires an authenticated Principal to
hold an EFFECTIVE Capability Grant matching the requested capability and scope.

Contracts proven by tests:
  * authenticated != authorized (no grant -> denied);
  * revoked / inactive grant -> denied;
  * scope mismatch -> denied;
  * enforced below the UI (this function takes no UI input and returns a decision).
Job titles are never hardcoded as permanent authority — authority is grant state.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import AuthorizationError


@dataclass
class Decision:
    allowed: bool
    reason: str
    capability: str
    scope: str


def _scope_matches(grant_scope: str, requested_scope: str) -> bool:
    if grant_scope == "*":
        return True
    return grant_scope == requested_scope


class Authorizer:
    def __init__(self, grants):
        self.grants = grants   # GrantRepository

    def decide(self, principal_id: str, capability: str, scope: str) -> Decision:
        for g in self.grants.list_for(principal_id):
            if g.capability == capability and g.effective() and _scope_matches(g.scope, scope):
                return Decision(True, "granted", capability, scope)
        return Decision(False, "no effective grant for capability+scope", capability, scope)

    def require(self, principal_id: str, capability: str, scope: str, correlation_id=None) -> Decision:
        d = self.decide(principal_id, capability, scope)
        if not d.allowed:
            raise AuthorizationError(
                message="You do not have permission to do that.",
                technical_detail=f"principal={principal_id} capability={capability} scope={scope}: {d.reason}",
                **({"correlation_id": correlation_id} if correlation_id else {}))
        return d
