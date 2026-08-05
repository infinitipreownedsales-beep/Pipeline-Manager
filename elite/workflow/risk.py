"""Incoming Risk — a versioned, component-explained risk result.

Risk is NEVER exposed only as one opaque universal score: every result lists its component
reasons (each with a factor + detail + severity) and derives a classification from them. Risk is
operational feasibility signal; it never rewrites Economic or planning truth.
"""
from __future__ import annotations

from ..ids import new_id
from .models import IncomingRisk

_SEVERITY_ORDER = {"low": 0, "elevated": 1, "high": 2}


def _classify(reasons):
    if not reasons:
        return "low"
    worst = max((_SEVERITY_ORDER.get(r.get("severity", "low"), 0) for r in reasons), default=0)
    return {0: "low", 1: "elevated", 2: "high"}[worst]


class IncomingRiskService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def assess(self, *, subject_kind, subject_ref, combination_id, scope, reasons, timing=None,
               affected_need_window=None, source_facts=None, policy_versions=None, calculation_version=None,
               confidence="medium"):
        """Assess Incoming Risk from an explicit list of component `reasons`
        (each: {factor, detail, severity}). Classification is derived from the component severities;
        there is no single hidden score."""
        classification = "unresolved" if any(r.get("factor") == "conflicting_facts" for r in reasons) \
            else _classify(reasons)
        r = IncomingRisk(
            id=new_id("risk"), classification=classification, subject_kind=subject_kind, subject_ref=subject_ref,
            combination_id=combination_id, store_scope=scope, reasons=list(reasons), timing=timing or {},
            affected_need_window=affected_need_window or {}, source_facts=list(source_facts or []),
            policy_versions=list(policy_versions or []), calculation_version=calculation_version,
            confidence=confidence)
        return self.store.add_risk(r)


# Component reason builders (synthetic, explainable) -------------------------
def reason(factor, detail, severity="elevated"):
    return {"factor": factor, "detail": detail, "severity": severity}


def late_arrival(month, need_window):
    return reason("arrival_after_window", f"arrives {month}, need window ends {need_window}", "high")


def excessive_depth(depth, target):
    return reason("excessive_depth", f"depth {depth} exceeds target {target}", "elevated")


def low_confidence_eta():
    return reason("low_confidence_eta", "ETA precision below evidence threshold", "elevated")


def duplicate_commitment_exposure(identity):
    return reason("duplicate_commitment", f"identity {identity} already represented", "elevated")


def model_year_transition_risk():
    return reason("model_year_transition", "unit spans a model-year transition window", "elevated")


def conflicting_facts(detail="conflicting source facts"):
    return reason("conflicting_facts", detail, "high")
