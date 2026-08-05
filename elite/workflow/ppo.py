"""PPO workflow — its own governed discrete supply path, distinguishable from CPO.

Consumes Phase 4 Need; represents a discrete unit/order opportunity; creates no qualifying Supply
before the approved commitment point; counts exactly once; preserves identity continuity; computes
no separate Demand. Synthetic manufacturer/allocation evidence only (no real PPO policy).
"""
from __future__ import annotations

from ..ids import new_id
from . import lifecycle, reconcile
from .models import SupplyWorkflow


class PpoService:
    def __init__(self, wfstore, nistore, supply, gov, clock):
        self.wf, self.ni, self.supply, self.gov, self.clock = wfstore, nistore, supply, gov, clock

    def propose(self, principal, scope, *, order_or_unit_id, combination_id, arrival_month,
                need_ref=None, allocation_evidence="synthetic_allocation", policy_versions=None, scenario_id=None):
        w = SupplyWorkflow(id=new_id("wf"), workflow_type="ppo", store_scope=scope,
                           subject_identity=order_or_unit_id, subject_kind="order_or_unit",
                           combination_id=combination_id, target_month=arrival_month,
                           originating_need_ref=need_ref, proposal_reason="ppo proposal",
                           policy_versions=policy_versions or [], scenario_id=scenario_id,
                           idempotency_identity=order_or_unit_id,
                           evidence={"allocation_evidence": allocation_evidence})

        def propose_effect(conn, wf):
            self.wf.add_ppo_action(conn, workflow_id=wf.id, order_or_unit_id=order_or_unit_id,
                                   allocation_evidence=allocation_evidence, combination_id=combination_id,
                                   arrival_month=arrival_month)
            return reconcile.no_effect()(conn, wf)
        return lifecycle.governed_propose(self.gov, self.wf, principal=principal, capability="ppo.propose",
                                          scope=scope, workflow=w, action="ppo.propose",
                                          effect=propose_effect)["workflow"]

    def approve(self, principal, scope, workflow, *, decision_ref=None):
        eff = reconcile.create_commitment(self.ni, self.supply, unit_or_order_id=workflow.subject_identity,
                                          combination_id=workflow.combination_id, scope=scope,
                                          arrival_month=workflow.target_month, commitment_type="ppo",
                                          decision_ref=decision_ref or f"dec_{workflow.id}")
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="ppo.approve",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="ppo", to_status="COMMITTED", action="ppo.approve", effect=eff,
                                             idempotency_key=f"{workflow.id}:ppo.approve")

    def reject(self, principal, scope, workflow):
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="ppo.approve",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="ppo", to_status="REJECTED", action="ppo.reject",
                                             effect=reconcile.no_effect())
