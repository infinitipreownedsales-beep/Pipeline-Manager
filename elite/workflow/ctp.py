"""CTP (Change The Production) — a governed modification of an EXISTING Production Order.

CTP does not create a second Production Order. Before accepted execution the original Future
Supply remains authoritative. Accepted completion changes the order's combination association
(moving the one future unit from the original to the proposed combination — counted once, never
both) while preserving prior history. Rejected/failed CTP leaves the original order unchanged. CTP
respects editability, consumes Phase 4 Need AND Excess, computes no separate Demand, and — when
moving from an Excess combination to a Need combination — requires recomputing both. A replayed
accepted CTP does not apply twice.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from ..newinv.models import FutureSupply
from . import lifecycle, reconcile
from .models import SupplyWorkflow
from .pipeline import PipelineService


class CtpService:
    def __init__(self, wfstore, nistore, supply, gov, clock):
        self.wf, self.ni, self.supply, self.gov, self.clock = wfstore, nistore, supply, gov, clock

    def propose(self, principal, scope, *, production_order_id, original_combination_id, proposed_combination_id,
                editability, need_ref=None, excess_ref=None, changes=None, scenario_id=None):
        """Propose a CTP. Rejected up front if the order is not executably editable (respects
        editability — locked/past-cutoff/unknown cannot receive an executable CTP)."""
        if not PipelineService.is_executably_editable(editability):
            raise ValidationError(message="This production order cannot be changed.",
                                  technical_detail=f"editability={getattr(editability, 'editability_state', None)}")
        w = SupplyWorkflow(id=new_id("wf"), workflow_type="ctp", store_scope=scope,
                           subject_identity=production_order_id, subject_kind="production_order",
                           combination_id=original_combination_id, proposal_reason="ctp proposal",
                           scenario_id=scenario_id, idempotency_identity=production_order_id,
                           originating_need_ref=need_ref,
                           evidence={"proposed_combination": proposed_combination_id, "excess_ref": excess_ref})
        changes = changes or {}

        def propose_effect(conn, wf):
            ctp_id = self.wf.add_ctp_action(conn, workflow_id=wf.id, production_order_id=production_order_id,
                                            original_combination_id=original_combination_id,
                                            proposed_combination_id=proposed_combination_id,
                                            editability_ref=editability.id, cutoff=editability.cutoff,
                                            originating_need_ref=need_ref, originating_excess_ref=excess_ref,
                                            resulting_order_state="proposed")
            for dim, (frm, to) in changes.items():
                self.wf.add_ctp_change_detail(conn, ctp_id, dim, str(frm), str(to), accepted=None)
            return reconcile.no_effect()(conn, wf)
        return lifecycle.governed_propose(self.gov, self.wf, principal=principal, capability="ctp.propose",
                                          scope=scope, workflow=w, action="ctp.propose",
                                          effect=propose_effect)["workflow"]

    def approve(self, principal, scope, workflow):
        """Approve the CTP intent WITHOUT moving supply — the original Future Supply remains
        authoritative until accepted execution (no double-count of original + proposed)."""
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="ctp.approve",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="ctp", to_status="APPROVED", action="ctp.approve",
                                             effect=reconcile.no_effect())

    def execute(self, principal, scope, workflow, *, proposed_combination_id, arrival_month=None):
        """Accepted execution: move the one future unit from the original to the proposed
        combination (supersede original projection, add proposed projection with the SAME order
        identity), preserving history. Idempotent — a replay does not apply twice."""
        original_combo = workflow.combination_id
        order = workflow.subject_identity

        def execute_effect(conn, wf):
            superseded = []
            for fs in self.ni.future_supply_for(original_combo, scope, active_only=False):
                if fs.production_order_id == order and fs.status == "current":
                    conn.execute("UPDATE future_supply_projection SET status='superseded' WHERE id=?", (fs.id,))
                    superseded.append(fs.id)
            nf = FutureSupply(id=new_id("fsup"), store_scope=scope, production_order_id=order,
                              combination_id=proposed_combination_id, arrival_month=arrival_month or wf.target_month,
                              production_state="planned",
                              identity_linkage={"production_order_id": order, "ctp_of": original_combo})
            self.ni.insert_future_supply(conn, nf)
            row = self.wf.ctp_action_for_workflow(wf.id)
            if row:
                conn.execute("UPDATE ctp_action SET resulting_order_state='accepted',superseded_future_supply=?,"
                             "new_future_supply=? WHERE id=?", (",".join(superseded), nf.id, row["id"]))
                conn.execute("UPDATE ctp_change_detail SET accepted=1 WHERE ctp_id=?", (row["id"],))
            return {"outcome": "COMMITMENT_UPDATED", "supply_ref": nf.id, "combination_id": proposed_combination_id,
                    "subject_identity": order, "detail": f"ctp moved order to {proposed_combination_id}"}
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="ctp.execute",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="ctp", to_status="COMPLETED", action="ctp.execute",
                                             effect=execute_effect,
                                             idempotency_key=f"{workflow.id}:ctp.execute")

    def reject(self, principal, scope, workflow):
        """Rejected CTP leaves the original Production Order unchanged."""
        return lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="ctp.approve",
                                             scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                             wf_type="ctp", to_status="REJECTED", action="ctp.reject",
                                             effect=reconcile.no_effect())
