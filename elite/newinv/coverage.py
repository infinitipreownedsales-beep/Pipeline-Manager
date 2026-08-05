"""Desired ending coverage — resolved through Phase 3 policy, never hardcoded.

The target buffer (coverage units / coverage months / explicit unit target) is a governed
Policy Version resolved deterministically. Missing required policy yields an UNRESOLVED planning
target — never an invented number. More specific policy overrides broader policy; conflicting
equally-applicable policy yields a conflict; a broad fallback resolves only when the family
declares it.
"""
from __future__ import annotations

from ..ids import new_id
from ..policy.resolution import CONFLICTING, RESOLVED, UNRESOLVED, resolve
from .models import DesiredCoverageResolution


class CoverageService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def resolve(self, combination_id, scope, *, policy_store, family, subject_scope, at_time,
                context="official", scenario_id=None, precedence=None):
        r = resolve(policy_store, family, subject_scope=subject_scope, at_time=at_time,
                    context=context, scenario_id=scenario_id, precedence=precedence)
        status = {RESOLVED: "resolved", UNRESOLVED: "unresolved", CONFLICTING: "conflicting"}[r.status]
        value = r.value if r.status == RESOLVED else {}
        c = DesiredCoverageResolution(
            id=new_id("cov"), store_scope=scope, resolution_status=status, combination_id=combination_id,
            policy_version=(r.version.id if r.version else None), scope=dict(subject_scope),
            unit_contract=(value.get("mode", "") if isinstance(value, dict) else ""),
            resolved_value=value if isinstance(value, dict) else {"value": value},
            fallback_used=r.fallback_used, note=r.note)
        return self.store.add_coverage(c)


def target_units(coverage: DesiredCoverageResolution, monthly_rate: float) -> float:
    """Convert a resolved coverage policy into a numeric ending-inventory target (units).

    Returns None when coverage is unresolved/conflicting — the plan must stay unresolved rather
    than invent a target."""
    if coverage.resolution_status != "resolved":
        return None
    v = coverage.resolved_value or {}
    mode = v.get("mode")
    if mode == "units":
        return float(v.get("value", 0))
    if mode == "months":
        return float(v.get("value", 0)) * float(monthly_rate)
    if "value" in v:
        return float(v["value"])
    return None
