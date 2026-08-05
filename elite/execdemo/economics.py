"""Executive Demo Economic Call (versioned) + Execution Status.

The Economic Call is kept separate from candidate SELECTION and from Execution Status. Entry economics
and retirement economics are distinguishable; retirement timing uses INCREMENTAL future economics from
the decision point; sunk designation cost is not reapplied. The call is never rewritten because
execution is currently blocked; missing material inputs → unresolved / lower confidence; alternatives
carry their own values (no unexplained score). Execution Status explains whether/why the call can be
acted on (including `BLOCKED_NEW_RETAIL_RISK`).
"""
from __future__ import annotations

from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import EconomicResult


class EconomicService:
    def __init__(self, store, policy_store, clock, calc_version):
        self.store, self.policy, self.clock, self.calc_version = store, policy_store, clock, calc_version

    def issue_call(self, unit, *, decision_point, alternatives, policy_status="resolved", candidate_id=None,
                   opportunity_cost_ref=None, expected_benefit=None, retirement_impact=None, policy_versions=None,
                   assumptions=None, uncertainty=None, fact_refs=None, scenario_id=None):
        """`decision_point` is 'entry' or 'retirement'; for 'retirement' the caller supplies
        incremental future values only (no sunk designation cost)."""
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
            id=new_id("rep"), refs={"kind": "executive_demo_economic", "calculation_version": self.calc_version,
                                    "decision_point": decision_point, "alternatives": alternatives,
                                    "policy_versions": list(policy_versions or [])},
            calculation_timestamp=self.store._now(), implementation_revision="phase7-economic",
            output_reference=checksum))
        e = EconomicResult(
            id=new_id("edeco"), executive_demo_unit_id=unit.id, store_scope=unit.store_scope, resolution_status=status,
            decision_point=decision_point, candidate_id=candidate_id, alternatives=list(alternatives),
            economic_call=call, opportunity_cost_ref=opportunity_cost_ref, expected_benefit=expected_benefit or {},
            retirement_impact=retirement_impact or {}, assumptions=assumptions or {}, uncertainty=uncertainty or {},
            policy_versions=list(policy_versions or []), calculation_version=self.calc_version,
            fact_refs=list(fact_refs or []), scenario_id=scenario_id, reproducibility_package=pkg.id)
        return self.store.add_economic(e)


class ExecutionService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def assess(self, unit, economic_result_id, *, identity_ok=True, data_ok=True, policy_ok=True,
               new_retail_risk=False, operational_ok=True, approved=False, executed=False, failed=False):
        blockers = []
        if failed:
            status = "FAILED"
        elif not identity_ok:
            status, _ = "BLOCKED_IDENTITY", blockers.append("unresolved identity")
        elif not data_ok:
            status, _ = "BLOCKED_DATA", blockers.append("insufficient accepted data")
        elif not policy_ok:
            status, _ = "BLOCKED_POLICY", blockers.append("policy does not permit")
        elif new_retail_risk:
            status, _ = "BLOCKED_NEW_RETAIL_RISK", blockers.append("excessive New Retail risk")
        elif not operational_ok:
            status, _ = "BLOCKED_OPERATIONAL", blockers.append("operational constraint")
        elif executed:
            status = "COMPLETED"
        elif approved:
            status = "APPROVED_NOT_EXECUTED"
        else:
            status = "READY"
        return self.store.add_execution_status(unit.id, economic_result_id, status, reason="; ".join(blockers),
                                               blocking_factors=blockers)
