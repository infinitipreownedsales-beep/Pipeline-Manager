"""Service Loaner Economic Call (versioned) — separate from Execution Status.

Placement economics and exit-timing economics are distinct. Exit timing uses INCREMENTAL future
economics from the current decision point; sunk placement cost is never reapplied to the exit
decision. The Economic Call identifies assumptions, uncertainty, Policy Versions, Calculation
Version, facts, and a reproducibility package. Unsupported financial inputs produce unresolved or
lower-confidence output. No universal score replaces the underlying alternative-by-alternative
comparison, and the call is never rewritten merely because execution is currently blocked.
"""
from __future__ import annotations

from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import EconomicResult


class EconomicService:
    def __init__(self, store, policy_store, clock, calc_version):
        self.store, self.policy, self.clock, self.calc_version = store, policy_store, clock, calc_version

    def issue_call(self, unit, *, decision_point, alternatives, policy_status="resolved",
                   policy_versions=None, assumptions=None, fact_refs=None, uncertainty=None, scenario_id=None):
        """`alternatives`: [{alternative, incremental_value, basis}] — each carries its own explicit
        value + basis (never one opaque score). `decision_point` is 'placement' or 'exit'; for 'exit'
        the caller supplies incremental future values only (no sunk placement cost)."""
        if policy_status == "unresolved":
            status, call = "unresolved", {}
        elif policy_status == "conflicting":
            status, call = "conflicting", {}
        else:
            status = "resolved"
            best = max(alternatives, key=lambda a: a["incremental_value"]) if alternatives else None
            call = {"choice": best["alternative"], "value": best["incremental_value"], "basis": best.get("basis", "")} \
                if best else {}
        checksum = output_checksum({"decision_point": decision_point, "alternatives": alternatives, "call": call})
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "service_loaner_economic", "calculation_version": self.calc_version,
                                    "decision_point": decision_point, "alternatives": alternatives,
                                    "policy_versions": list(policy_versions or [])},
            calculation_timestamp=self.store._now(), implementation_revision="phase6-economic",
            output_reference=checksum))
        e = EconomicResult(
            id=new_id("sleco"), service_loaner_unit_id=unit.id, store_scope=unit.store_scope,
            resolution_status=status, decision_point=decision_point, alternatives=list(alternatives),
            economic_call=call, assumptions=assumptions or {}, uncertainty=uncertainty or {},
            policy_versions=list(policy_versions or []), calculation_version=self.calc_version,
            fact_refs=list(fact_refs or []), reproducibility_package=pkg.id, scenario_id=scenario_id)
        return self.store.add_economic(e)
