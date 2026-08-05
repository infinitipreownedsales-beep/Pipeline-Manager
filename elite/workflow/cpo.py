"""CPO workflow — a discrete production-order commitment path (NOT continuous replenishment).

CPO consumes the Phase 4 Need contract and computes no separate Demand. A proposal has no supply
effect; authorized approval creates ONE discrete Committed Supply for a specific eligible
Production Order / accepted allocation; a repeated approval (idempotent replay) or the same order
already represented in qualifying supply does not count twice; cancellation removes the prospective
contribution while preserving history; completion reconciles to the same order or a later Vehicle
Unit identity.
"""
from __future__ import annotations

from ..ids import new_id
from . import lifecycle, reconcile
from .models import SupplyWorkflow


class CpoService:
    def __init__(self, wfstore, nistore, supply, gov, clock):
        self.wf, self.ni, self.supply, self.gov, self.clock = wfstore, nistore, supply, gov, clock

    def propose(self, principal, scope, *, production_order_id, combination_id, arrival_month,
                need_ref=None, quantity=1, policy_versions=None, scenario_id=None, idempotency=None):
        w = SupplyWorkflow(id=new_id("wf"), workflow_type="cpo", store_scope=scope,
                           subject_identity=production_order_id, subject_kind="production_order",
                           combination_id=combination_id, target_month=arrival_month, quantity=quantity,
                           originating_need_ref=need_ref, proposal_reason="cpo proposal",
                           policy_versions=policy_versions or [], scenario_id=scenario_id,
                           idempotency_identity=idempotency or production_order_id,
                           qualifying_supply_at_propose=len(self.supply.qualifying_supply(combination_id, scope)))

        def propose_effect(conn, wf):
            self.wf.add_cpo_action(conn, workflow_id=wf.id, production_order_id=production_order_id,
                                   combination_id=combination_id, discrete_quantity=quantity,
                                   arrival_month=arrival_month)
            return reconcile.no_effect()(conn, wf)
        return lifecycle.governed_propose(self.gov, self.wf, principal=principal, capability="cpo.propose",
                                          scope=scope, workflow=w, action="cpo.propose",
                                          effect=propose_effect)["workflow"]

    def approve(self, principal, scope, workflow, *, decision_ref=None):
        """Authorized approval → one discrete Committed Supply (idempotent)."""
        eff = reconcile.create_commitment(self.ni, self.supply, unit_or_order_id=workflow.subject_identity,
                                          combination_id=workflow.combination_id, scope=scope,
                                          arrival_month=workflow.target_month, commitment_type="cpo",
                                          decision_ref=decision_ref or f"dec_{workflow.id}")
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="cpo.approve",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="cpo", to_status="COMMITTED", action="cpo.approve", effect=eff,
                                             idempotency_key=f"{workflow.id}:cpo.approve")

    def cancel(self, principal, scope, workflow, *, commitment_ref):
        eff = reconcile.cancel_commitment(self.ni, self.supply, commitment_ref=commitment_ref,
                                         combination_id=workflow.combination_id, scope=scope,
                                         subject_identity=workflow.subject_identity)
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="workflow.cancel",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="cpo", to_status="CANCELLED", action="cpo.cancel", effect=eff)

    def complete(self, principal, scope, workflow, *, received_unit_id, commitment_ref):
        eff = reconcile.complete_to_current(self.ni, self.supply, combination_id=workflow.combination_id,
                                           scope=scope, received_unit_id=received_unit_id, commitment_ref=commitment_ref,
                                           subject_identity=workflow.subject_identity)
        r = lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="production.execute",
                                          scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                          wf_type="cpo", to_status="COMPLETED", action="cpo.complete", effect=eff)
        self.wf.add_execution_confirmation(workflow.id, "cpo_completion", subject_identity=received_unit_id,
                                           resulting_supply_ref=r.get("supply_ref"), outcome=r.get("outcome"))
        return r

    def commitment_ref(self, workflow_id):
        for rr in self.wf.reconciliations_for(workflow_id):
            if rr.outcome == "COMMITMENT_CREATED":
                return rr.supply_ref
        return None
