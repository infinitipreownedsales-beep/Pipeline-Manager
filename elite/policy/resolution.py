"""Deterministic, effective-dated policy resolution.

Precedence is by explicit rules — never insertion order or newest-recorded-wins:
Scenario-vs-official context -> active lifecycle -> effective time -> scope match ->
subject specificity -> approved precedence -> version status -> conflict. A newer
recorded time never automatically overrides a more appropriate effective-dated policy.
Equally-applicable conflicts with no approved precedence resolve to CONFLICTING.
Fallback is only what the Policy Family declares; the system never invents a value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import NON_RESOLVING

RESOLVED, UNRESOLVED, CONFLICTING = "RESOLVED", "UNRESOLVED", "CONFLICTING"
_CURRENT_OK = {"APPROVED", "SCHEDULED", "ACTIVE"}
_HISTORICAL_EXCLUDE = NON_RESOLVING          # DRAFT/PROPOSED/UNDER_REVIEW/REJECTED/WITHDRAWN


@dataclass
class Resolution:
    status: str
    value: Optional[dict] = None
    version: Optional[object] = None
    overrides_used: list = field(default_factory=list)
    baseline_version: Optional[str] = None
    fallback_used: bool = False
    note: str = ""
    candidates: list = field(default_factory=list)


def _within_window(pv, at):
    if pv.effective_start is not None:
        if not (at >= pv.effective_start if pv.start_inclusive else at > pv.effective_start):
            return False
    if pv.effective_end is not None:
        if not (at <= pv.effective_end if pv.end_inclusive else at < pv.effective_end):
            return False
    return True


def _scope_matches(pv, subject_scope):
    return all(subject_scope.get(k) == v for k, v in (pv.scope or {}).items())


def _effective(pv, at, historical):
    if not _within_window(pv, at):
        return False
    if historical:
        return pv.lifecycle_status not in _HISTORICAL_EXCLUDE
    if pv.lifecycle_status not in _CURRENT_OK:
        return False
    if pv.lifecycle_status == "REVOKED":
        return False
    # revocation contract: future/current use blocked once revoked-effective
    if pv.revocation and pv.revocation.get("effective_at") and at >= pv.revocation["effective_at"]:
        return False
    return True


def resolve(store, family, *, subject_scope, at_time, context="official",
            scenario_id=None, precedence=None, historical=False):
    """Resolve the applicable policy version. `precedence` (optional) is an ordered
    list of version ids that an approved rule ranks highest-first."""
    sid = scenario_id if context == "scenario" else "__official__"
    versions = store.versions_for_family(family.id, scenario_id=sid)

    applicable = [pv for pv in versions
                  if _scope_matches(pv, subject_scope) and _effective(pv, at_time, historical)
                  and (context == "scenario" or not pv.is_scenario)]

    if not applicable:
        return _fallback(store, family)

    # Scenario overrides take precedence within scenario context.
    scen = [pv for pv in applicable if pv.is_scenario and pv.scenario_id == scenario_id]
    official = [pv for pv in applicable if not pv.is_scenario]
    if context == "scenario" and scen:
        baseline = _pick_official(official, family, precedence)
        chosen = _pick_by_specificity(scen, family, precedence)
        if chosen.status == CONFLICTING:
            return chosen
        r = _as_resolution(chosen.version)
        r.overrides_used = [chosen.version.id]
        r.baseline_version = baseline.version.id if baseline and baseline.status == RESOLVED else None
        return r

    picked = _pick_by_specificity(official, family, precedence)
    return picked


def _pick_official(official, family, precedence):
    if not official:
        return None
    return _pick_by_specificity(official, family, precedence)


def _pick_by_specificity(cands, family, precedence):
    if not cands:
        return Resolution(UNRESOLVED)
    allow = family.default_resolution.get("allow_specificity_override", True)
    # rank by number of matched scope dimensions (more specific first)
    if allow:
        top = max(len(pv.scope or {}) for pv in cands)
        cands = [pv for pv in cands if len(pv.scope or {}) == top]
    if len(cands) == 1:
        return _as_resolution(cands[0])
    if precedence:
        ranked = [pv for pv in cands if pv.id in precedence]
        if ranked:
            ranked.sort(key=lambda pv: precedence.index(pv.id))
            return _as_resolution(ranked[0])
    # distinct values, equally specific, no approved precedence -> explicit conflict
    if len({_freeze(pv.value) for pv in cands}) > 1:
        return Resolution(CONFLICTING, candidates=[pv.id for pv in cands],
                          note="equally applicable authoritative policies conflict")
    return _as_resolution(cands[0])       # identical values -> deterministic pick


def _fallback(store, family):
    dr = family.default_resolution or {}
    mode = dr.get("mode", "unresolved")
    if mode in ("broad_fallback", "default_version") and dr.get("version_id"):
        pv = store.get_version(dr["version_id"])
        if pv is not None:
            r = _as_resolution(pv)
            r.fallback_used = True
            r.note = f"approved {mode}"
            return r
    return Resolution(UNRESOLVED, note=dr.get("note", "no applicable policy and no declared fallback"))


def _as_resolution(pv):
    return Resolution(RESOLVED, value=pv.value, version=pv)


def _freeze(v):
    import json
    return json.dumps(v, sort_keys=True)
