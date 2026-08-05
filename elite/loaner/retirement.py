"""Retirement, provisional retirement, return confirmation, final retirement, Used Cars handoff,
and return-to-retail reconciliation.

Eligibility is not retirement; approval is not return; a rented unit may receive a provisional
retirement Decision but remains active/rented until returned; return confirmation is an actual
operational event; final retirement reconciles fleet membership at the defined event; cancellation
restores the correct current state without deleting history; corrections preserve prior records.
Used Cars receipt is a single idempotent, immutable confirmation AFTER retirement (auto-records the
Principal + timestamp; no checklist). Used Cars receipt never creates New Retail Supply; an actual
return-to-New-Retail restores Current Supply exactly once (existing supply prevents duplication).
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from ..newinv.models import CurrentSupply
from . import lifecycle
from .models import RetirementAction


class RetirementService:
    def __init__(self, store, nistore, gov, clock):
        self.store, self.ni, self.gov, self.clock = store, nistore, gov, clock

    # ---- eligibility (not retirement) -------------------------------------
    def assess_eligibility(self, unit, *, eligible, tenure_days=None, reasons=None, policy_versions=None):
        return self.store.add_retirement_eligibility(unit.id, eligible, reasons=reasons,
                                                     policy_versions=policy_versions, tenure_days=tenure_days)

    # ---- propose / approve / provisional ----------------------------------
    def propose(self, principal, scope, unit, *, economic_result_id=None):
        action = RetirementAction(id=new_id("slra"), service_loaner_unit_id=unit.id, store_scope=scope,
                                  lifecycle_status="proposed", economic_result_id=economic_result_id,
                                  decision_ref=f"rprop_{unit.id}")
        self.store.add_retirement_action(action)
        r = lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                          capability="service_loaner.retirement.propose", scope=scope, unit_id=unit.id,
                                          expected_version=unit.version, to_state="RETIREMENT_PROPOSED",
                                          action="service_loaner.retirement.propose",
                                          field_updates=lambda c: {"retirement_decision": action.id})
        return r, action

    def approve(self, principal, scope, unit):
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.retirement.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="RETIREMENT_APPROVED", action="service_loaner.retirement.approve")

    def provisional(self, principal, scope, unit):
        """Provisional retirement Decision — the unit remains active/rented until returned."""
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.retirement.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="PROVISIONAL_RETIREMENT",
                                             action="service_loaner.retirement.provisional")

    # ---- return confirmation + final retirement ---------------------------
    def confirm_return(self, principal, scope, unit, *, actual_event_ref):
        def eff(conn, cur):
            cid = self.store.add_return_confirmation(conn, unit.id, cur.retirement_decision,
                                                     actual_event_ref=actual_event_ref, confirmed_by=principal)
            self.store.set_unit_field(conn, unit.id, return_confirmation=cid)
            return {"detail": f"return confirmed {cid}"}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.return.confirm", scope=scope, unit_id=unit.id,
                                             expected_version=unit.version, to_state="RETURN_CONFIRMED",
                                             action="service_loaner.return.confirm", effect=eff)

    def complete(self, principal, scope, unit, *, handoff="used_cars"):
        """Final retirement: reconcile membership at the retirement event, then queue for Used Cars
        handoff (default) or return to New Retail."""
        def eff(conn, cur):
            eid = self.store.add_retirement_event(conn, unit.id, cur.retirement_decision, cur.return_confirmation, scope)
            self.store.set_unit_field(conn, unit.id, retirement_event=eid)
            return {"detail": f"retired {eid}", "retirement_event": eid}
        r = lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                          capability="service_loaner.retirement.complete", scope=scope, unit_id=unit.id,
                                          expected_version=unit.version, to_state="RETIRED",
                                          action="service_loaner.retirement.complete", effect=eff)
        self.store.add_reconciliation(unit.id, unit.vehicle_unit_id, scope, "RETIRED_AWAITING_HANDOFF")
        unit = self.store.get_unit(unit.id)
        if handoff == "new_retail":
            return self.return_to_new_retail(principal, scope, unit)
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.retirement.complete", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="AWAITING_USED_CARS_RECEIPT",
                                             action="service_loaner.retirement.queue_used_cars")

    # ---- Used Cars receipt (idempotent, immutable) ------------------------
    def confirm_used_cars_receipt(self, principal, scope, unit, *, correlation_id=None):
        """One simple confirmation. Auto-records Principal + timestamp; no checklist; idempotent;
        cannot occur before retirement (guarded by the legal transition)."""
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
                                          capability="service_loaner.used_cars_receipt.confirm", scope=scope,
                                          unit_id=unit.id, expected_version=unit.version, to_state="USED_CARS_RECEIVED",
                                          action="service_loaner.used_cars_receipt.confirm", effect=eff,
                                          idempotency_key=f"{unit.id}:used_cars_receipt")
        r["receipt_id"] = r.get("effect", {}).get("receipt_id")
        return r

    # ---- return-to-retail reconciliation ----------------------------------
    def return_to_new_retail(self, principal, scope, unit):
        """Restore New Retail Current Supply exactly once (existing supply prevents duplication).
        Used Cars receipt, by contrast, never creates New Retail Supply."""
        def eff(conn, cur):
            existing = [s for s in self.ni.current_supply_for(cur.combination_id, scope)
                        if s.vehicle_unit_id == cur.vehicle_unit_id]
            if existing:
                self.store.insert_reconciliation(conn, unit.id, cur.vehicle_unit_id, scope, "ALREADY_RECONCILED",
                                                 detail="current supply already present")
                return {"detail": "already in current supply"}
            cs = CurrentSupply(id=new_id("csup"), store_scope=scope, availability_state="available_unsold",
                               vehicle_unit_id=cur.vehicle_unit_id, combination_id=cur.combination_id,
                               retail_eligible=True, confidence="high")
            self.ni.insert_current_supply(conn, cs)
            self.store.set_unit_field(conn, unit.id, return_to_retail_ref=cs.id)
            self.store.insert_reconciliation(conn, unit.id, cur.vehicle_unit_id, scope, "RETURNED_TO_NEW_RETAIL",
                                             supply_ref=cs.id)
            return {"detail": f"restored current supply {cs.id}", "supply_ref": cs.id}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.retirement.complete", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="RETURNED_TO_NEW_RETAIL",
                                             action="service_loaner.return_to_new_retail", effect=eff)

    # ---- cancellation (restore state, preserve history) -------------------
    def cancel(self, principal, scope, unit, *, restore_state="ACTIVE_AVAILABLE", reason=""):
        """Cancel a retirement Decision, restoring the correct current state without deleting
        history (the retirement action is marked cancelled, not removed)."""
        def eff(conn, cur):
            if cur.retirement_decision:
                self.store.set_retirement_action(conn, cur.retirement_decision, lifecycle_status="cancelled",
                                                 cancellation_status=reason or "cancelled")
            return {"detail": f"retirement cancelled ({reason or 'cancelled'})"}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.retirement.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version, to_state=restore_state,
                                             action="service_loaner.retirement.cancel", effect=eff)
