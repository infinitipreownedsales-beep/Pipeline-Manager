"""Dealer Trade workflow.

A proposed Dealer Trade is not Supply; sending a request is not Supply; acceptance alone is not
completed Supply unless the approved contract explicitly treats it as a firm unit-level commitment.
Confirmed completion creates/reconciles exactly one qualifying Supply effect. Rejected/expired/
withdrawn/failed trades do not count. Received Vehicle Unit identity reconciles with the completed
trade. Dealer Trade consumes Phase 4 Need without changing Demand.
"""
from __future__ import annotations

from ..ids import new_id
from . import lifecycle, reconcile
from .models import SupplyWorkflow


class DealerTradeService:
    def __init__(self, wfstore, nistore, supply, gov, clock):
        self.wf, self.ni, self.supply, self.gov, self.clock = wfstore, nistore, supply, gov, clock

    def propose(self, principal, scope, *, unit_identity, combination_id, arrival_month, counterparty="synthetic_dealer",
                direction="incoming", need_ref=None, scenario_id=None):
        w = SupplyWorkflow(id=new_id("wf"), workflow_type="dealer_trade", store_scope=scope,
                           subject_identity=unit_identity, subject_kind="vehicle_unit", combination_id=combination_id,
                           target_month=arrival_month, originating_need_ref=need_ref, proposal_reason="dealer trade",
                           scenario_id=scenario_id, idempotency_identity=unit_identity,
                           evidence={"counterparty": counterparty, "direction": direction})

        def propose_effect(conn, wf):
            self.wf.add_dealer_trade_action(conn, workflow_id=wf.id, direction=direction, counterparty=counterparty,
                                            unit_identity=unit_identity, combination_id=combination_id,
                                            arrival_month=arrival_month)
            return reconcile.no_effect()(conn, wf)
        wf = lifecycle.governed_propose(self.gov, self.wf, principal=principal, capability="dealer_trade.propose",
                                        scope=scope, workflow=w, action="dealer_trade.propose",
                                        effect=propose_effect)["workflow"]
        self.wf.add_dealer_trade_status(wf.id, "proposed", actor=principal)
        return wf

    def send_request(self, principal, scope, workflow):
        r = lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="dealer_trade.propose",
                                          scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                          wf_type="dealer_trade", to_status="UNDER_REVIEW", action="dealer_trade.request",
                                          effect=reconcile.no_effect())
        self.wf.add_dealer_trade_status(workflow.id, "request_sent", actor=principal)
        return r

    def accept(self, principal, scope, workflow, *, firm_on_accept=False):
        """Acceptance per the explicit contract: firm_on_accept=False (default) → no supply effect
        until completion; True → acceptance is a firm commitment."""
        eff = reconcile.no_effect()
        if firm_on_accept:
            eff = reconcile.create_commitment(self.ni, self.supply, unit_or_order_id=workflow.subject_identity,
                                              combination_id=workflow.combination_id, scope=scope,
                                              arrival_month=workflow.target_month, commitment_type="dealer_trade")
        r = lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="dealer_trade.approve",
                                          scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                          wf_type="dealer_trade", to_status="APPROVED", action="dealer_trade.accept",
                                          effect=eff)
        self.wf.add_dealer_trade_status(workflow.id, "accepted", actor=principal)
        return r

    def complete(self, principal, scope, workflow, *, received_unit_id):
        eff = reconcile.complete_to_current(self.ni, self.supply, combination_id=workflow.combination_id, scope=scope,
                                           received_unit_id=received_unit_id, subject_identity=workflow.subject_identity)
        r = lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="dealer_trade.complete",
                                          scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                          wf_type="dealer_trade", to_status="COMPLETED", action="dealer_trade.complete",
                                          effect=eff)
        self.wf.add_dealer_trade_status(workflow.id, "completed", actor=principal)
        self.wf.add_execution_confirmation(workflow.id, "dealer_trade_completion", subject_identity=received_unit_id,
                                           resulting_supply_ref=r.get("supply_ref"), outcome=r.get("outcome"))
        return r

    def terminate(self, principal, scope, workflow, *, to_status, reason=""):
        """Rejected / expired / withdrawn / failed — no supply effect, history preserved."""
        r = lifecycle.governed_transition(self.gov, self.wf, principal=principal, capability="dealer_trade.approve",
                                          scope=scope, workflow_id=workflow.id, expected_version=workflow.version,
                                          wf_type="dealer_trade", to_status=to_status, action=f"dealer_trade.{to_status.lower()}",
                                          effect=reconcile.no_effect())
        self.wf.add_dealer_trade_status(workflow.id, to_status.lower(), actor=principal, reason=reason)
        return r
