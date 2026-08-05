"""Model preference — approved policy only.

Model preference is resolved through Phase 3 (never inferred from historical frequency alone). It may
influence selection but never overrides hard eligibility and never silently overrides New Retail
opportunity cost. Missing required preference policy produces the Policy Family's declared fallback or
UNRESOLVED; conflicting preference produces a conflict; scenario preference stays isolated from
official policy.
"""
from __future__ import annotations

from ..policy.resolution import CONFLICTING, RESOLVED, UNRESOLVED, resolve


class PreferenceService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def resolve(self, scope, *, policy_store, family, subject_scope, at_time, context="official",
                scenario_id=None):
        r = resolve(policy_store, family, subject_scope=subject_scope, at_time=at_time, context=context,
                    scenario_id=scenario_id)
        status = {RESOLVED: "resolved", UNRESOLVED: "unresolved", CONFLICTING: "conflicting"}[r.status]
        value = r.value if r.status == RESOLVED else {}
        return self.store.add_preference(
            scope, status, preferred=(value.get("preferred") if isinstance(value, dict) else None),
            hierarchy=(value.get("hierarchy") if isinstance(value, dict) else None),
            substitutions=(value.get("substitutions") if isinstance(value, dict) else None),
            policy_version=(r.version.id if r.version else None), subject_scope=subject_scope,
            note=r.note, scenario_id=scenario_id)
