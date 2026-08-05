"""Executive Demo retirement + return-to-retail + Used Cars handoff + reconciliation.

Eligibility is not retirement; approval is not actual retirement; actual retirement removes active
membership only at the defined event. Approved retirement updates committed portfolio state. Return to
New Retail restores Current Supply exactly once (existing supply prevents duplicate restoration); Used
Cars receipt (a SEPARATE record from Service Loaner) creates no New Retail Supply, is one idempotent
immutable confirmation, and cannot precede retirement. Cancellation restores the correct state
preserving history; corrections preserve prior records. One Vehicle Unit counts once.
"""
from __future__ import annotations

from ..ids import new_id
from ..newinv.models import CurrentSupply
from . import lifecycle
from .models import RetirementAction


class RetirementService:
    def __init__(self, store, nistore, gov, clock):
        self.store, self.ni, self.gov, self.clock = store, nistore, gov, clock

    def assess_eligibility(self, unit, *, eligible, tenure_days=None, reasons=None, policy_versions=None):
        return self.store.add_retirement_eligibility(unit.id, eligible, reasons=reasons,
                                                     policy_versions=policy_versions, tenure_days=tenure_days)

    def propose(self, principal, scope, unit, *, economic_result_id=None):
        a = RetirementAction(id=new_id("edra"), executive_demo_unit_id=unit.id, store_scope=scope,
                             lifecycle_status="proposed", economic_result_id=economic_result_id,
                             decision_ref=f"rprop_{unit.id}")
        self.store.add_retirement_action(a)
        r = lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                          capability="executive_demo.retirement.propose", scope=scope, unit_id=unit.id,
                                          expected_version=unit.version, to_state="RETIREMENT_PROPOSED",
                                          action="executive_demo.retirement.propose",
                                          field_updates=lambda c: {"retirement_decision": a.id})
        return r, a

    def approve(self, principal, scope, unit):
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.retirement.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="RETIREMENT_APPROVED", action="executive_demo.retirement.approve")

    def execute(self, principal, scope, unit, *, disposition="new_retail"):
        """Actual retirement removes active membership at the retirement event; then dispose via
        return-to-New-Retail (default) or Used Cars handoff."""
        def eff(conn, cur):
            eid = self.store.add_retirement_event(conn, unit.id, cur.retirement_decision, scope)
            self.store.set_unit_field(conn, unit.id, retirement_event=eid)
            return {"detail": f"retired {eid}"}
        r = lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                          capability="executive_demo.retirement.execute", scope=scope, unit_id=unit.id,
                                          expected_version=unit.version, to_state="RETIRED",
                                          action="executive_demo.retirement.execute", effect=eff)
        self.store.add_reconciliation(unit.id, unit.vehicle_unit_id, scope, "RETIRED_AWAITING_DISPOSITION")
        unit = self.store.get_unit(unit.id)
        if disposition == "used_cars":
            return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                                 capability="executive_demo.retirement.execute", scope=scope,
                                                 unit_id=unit.id, expected_version=unit.version,
                                                 to_state="AWAITING_USED_CARS_RECEIPT",
                                                 action="executive_demo.retirement.queue_used_cars")
        return self.return_to_new_retail(principal, scope, unit)

    def return_to_new_retail(self, principal, scope, unit):
        """Restore New Retail Current Supply exactly once (existing supply → ALREADY_RECONCILED)."""
        def eff(conn, cur):
            existing = [s for s in self.ni.current_supply_for(cur.combination_id, scope)
                        if s.vehicle_unit_id == cur.vehicle_unit_id and s.status == "current"]
            if existing:
                rid = self.store.insert_reconciliation(conn, unit.id, cur.vehicle_unit_id, scope, "ALREADY_RECONCILED",
                                                       detail="current supply already present")
                return {"reconciliation_ref": rid, "detail": "already in current supply"}
            cs = CurrentSupply(id=new_id("csup"), store_scope=scope, availability_state="available_unsold",
                               vehicle_unit_id=cur.vehicle_unit_id, combination_id=cur.combination_id,
                               retail_eligible=True, confidence="high")
            self.ni.insert_current_supply(conn, cs)
            evid = self.store.add_return_to_retail_event(conn, unit.id, cur.retirement_event, scope,
                                                         restored_supply_ref=cs.id, confirmed_by=principal)
            self.store.set_unit_field(conn, unit.id, return_to_retail_event=evid, active_fleet_supply_ref=cs.id)
            rid = self.store.insert_reconciliation(conn, unit.id, cur.vehicle_unit_id, scope, "RETURNED_TO_NEW_RETAIL",
                                                   supply_ref=cs.id)
            return {"reconciliation_ref": rid, "detail": f"restored current supply {cs.id}", "supply_ref": cs.id}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.return_to_retail.confirm", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="RETURNED_TO_NEW_RETAIL",
                                             action="executive_demo.return_to_new_retail", effect=eff)

    def confirm_used_cars_receipt(self, principal, scope, unit, *, correlation_id=None):
        """One idempotent, immutable confirmation. Creates no New Retail supply; cannot precede
        retirement (guarded by the legal transition)."""
        existing = self.store.used_cars_receipt_for(unit.id)
        if existing is not None:
            return {"unit": self.store.get_unit(unit.id), "receipt_id": existing["id"], "replayed": True}

        def eff(conn, cur):
            rid = self.store.add_used_cars_receipt(conn, unit.id, cur.vehicle_unit_id, cur.retirement_event, scope,
                                                   confirming_principal=principal, correlation_id=correlation_id)
            self.store.set_unit_field(conn, unit.id, used_cars_receipt=rid)
            self.store.insert_reconciliation(conn, unit.id, cur.vehicle_unit_id, scope, "USED_CARS_RECEIVED")
            return {"detail": f"used cars receipt {rid}", "receipt_id": rid}
        r = lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                          capability="executive_demo.used_cars_receipt.confirm", scope=scope,
                                          unit_id=unit.id, expected_version=unit.version, to_state="USED_CARS_RECEIVED",
                                          action="executive_demo.used_cars_receipt.confirm", effect=eff,
                                          idempotency_key=f"{unit.id}:used_cars_receipt")
        r["receipt_id"] = r.get("effect", {}).get("receipt_id")
        return r

    def cancel(self, principal, scope, unit, *, restore_state="ACTIVE", reason=""):
        def eff(conn, cur):
            if cur.retirement_decision:
                self.store.set_retirement_action(conn, cur.retirement_decision, lifecycle_status="cancelled",
                                                 cancellation_status=reason or "cancelled")
            return {"detail": f"retirement cancelled ({reason or 'cancelled'})"}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.retirement.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version, to_state=restore_state,
                                             action="executive_demo.retirement.cancel", effect=eff)
