"""Operational workflow output slices.

The smallest real output for production-pipeline review, CPO/PPO proposal+approval, Dealer Trade
proposal+completion, CTP proposal+execution, and sequential recomputation. Each slice consumes REAL
domain output (a stored workflow + its transitions/reconciliations + the Phase 4 plan/demand), never
mocked text. Not the full Phase 10 UX.
"""
from __future__ import annotations


def _call(workflow, plan):
    st = workflow.lifecycle_status
    if st in ("PROPOSED", "UNDER_REVIEW"):
        return f"REVIEW — {workflow.workflow_type.upper()} proposed (no supply effect yet)."
    if st == "COMMITTED":
        return f"COMMITTED — {workflow.workflow_type.upper()} contributes qualifying supply."
    if st == "COMPLETED":
        return f"COMPLETED — {workflow.workflow_type.upper()} reconciled to current supply."
    if st in ("REJECTED", "WITHDRAWN", "CANCELLED", "FAILED", "EXPIRED", "SUPERSEDED"):
        return f"CLOSED — {workflow.workflow_type.upper()} {st.lower()} (no prospective supply)."
    return f"{workflow.workflow_type.upper()} — {st}."


def build_workflow_slice(wfstore, nistore, workflow_id, *, plan=None, demand=None):
    """Structured slice for a workflow. Values come from stored records."""
    w = wfstore.get_workflow(workflow_id)
    if w is None:
        return None
    recons = wfstore.reconciliations_for(workflow_id)
    transitions = wfstore.transitions_for(workflow_id)
    return {
        "call": _call(w, plan),
        "why": {
            "workflow_type": w.workflow_type, "lifecycle_status": w.lifecycle_status,
            "originating_need_ref": w.originating_need_ref,
            "reconciliation_outcomes": [r.outcome for r in recons],
        },
        "proof": {
            "transitions": [(t["from_status"], t["to_status"], t["action"]) for t in transitions],
            "reconciliations": [{"outcome": r.outcome, "prior_qualifying": r.prior_qualifying,
                                 "new_qualifying": r.new_qualifying, "supply_ref": r.supply_ref} for r in recons],
            "evidence": w.evidence,
        },
        "demand": demand.monthly_expected if demand else {},
        "supply": {"current": plan.current_supply, "future": plan.future_supply,
                   "committed": plan.committed_supply, "qualifying": plan.qualifying_supply} if plan else {},
        "need": plan.need if plan else None,
        "excess": plan.excess if plan else None,
        "affected_months": [m.month for m in plan.months] if plan else [],
        "identity": {"subject_identity": w.subject_identity, "subject_kind": w.subject_kind,
                     "combination_id": w.combination_id},
        "timing": {"target_month": w.target_month},
        "incoming_risk": w.evidence.get("incoming_risk") if isinstance(w.evidence, dict) else None,
        "workflow_state": w.lifecycle_status,
        "approval_or_execution_state": {"approval_decision": w.approval_decision,
                                        "execution_refs": w.execution_refs},
        "versions": {"calculation_version": (plan.calculation_version if plan else w.calculation_version),
                     "policy_versions": w.policy_versions,
                     "reproducibility_package": (plan.reproducibility_package if plan else None),
                     "scenario_id": w.scenario_id},
        "evidence_references": {"audit_refs": w.audit_refs, "reconciliations": [r.id for r in recons]},
        "unresolved": w.lifecycle_status == "UNRESOLVED",
    }
