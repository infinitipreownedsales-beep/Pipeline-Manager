"""Executive Demo Unit management + designation workflow.

The Executive Demo Unit ID never replaces Vehicle Unit identity. Candidate is not membership; approval
creates committed portfolio state only; designation EXECUTION establishes actual membership once and
reconciles New Retail supply (the unit leaves Current Supply — it is now a demo, not sellable New
inventory) to prevent double-counting. A unit that is an active Service Loaner cannot be designated
(the two fleet domains stay separate). Corrections preserve prior lifecycle history.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from . import lifecycle
from .models import ExecDemoUnit


class UnitService:
    def __init__(self, store, nistore, gov, clock, *, loaner_store=None):
        self.store, self.ni, self.gov, self.clock, self.loaner = store, nistore, gov, clock, loaner_store

    def create_candidate(self, scope, *, vehicle_unit_id, vin=None, combination_id=None):
        return self.store.add_unit(ExecDemoUnit(id=new_id("edu"), store_scope=scope, vehicle_unit_id=vehicle_unit_id,
                                                vin=vin, combination_id=combination_id, membership_state="CANDIDATE"))

    def propose_designation(self, principal, scope, unit, *, candidate_id=None, economic_result_id=None):
        aid = self.store.add_designation_action(unit.id, scope, "proposed", candidate_id=candidate_id,
                                                economic_result_id=economic_result_id, decision_ref=f"dprop_{unit.id}")
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.designation.propose", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="DESIGNATION_PROPOSED", action="executive_demo.designation.propose",
                                             field_updates=lambda c: {"designation_decision": aid})

    def approve_designation(self, principal, scope, unit):
        """Approval creates committed portfolio state only (no membership, no supply effect yet)."""
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.designation.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version,
                                             to_state="DESIGNATION_APPROVED", action="executive_demo.designation.approve")

    def execute_designation(self, principal, scope, unit):
        """Execution establishes active membership once AND reconciles New Retail supply (removes the
        unit from Current Supply). Idempotent. Blocked if the unit is an active Service Loaner."""
        if self.loaner is not None and unit.vin:
            sl = self.loaner.unit_for_vin(unit.vin, scope, active_only=True)
            if sl is not None and sl.active_fleet_presence and sl.membership_state not in (
                    "RETIRED", "USED_CARS_RECEIVED", "RETURNED_TO_NEW_RETAIL", "CANCELLED"):
                raise ValidationError(message="Unit is an active Service Loaner.",
                                      technical_detail=f"vin {unit.vin} active in Service Loaner domain")

        def eff(conn, cur):
            supply_ref = None
            for s in self.ni.current_supply_for(cur.combination_id, scope):
                if s.vehicle_unit_id == cur.vehicle_unit_id and s.status == "current":
                    conn.execute("UPDATE current_supply_projection SET status='superseded' WHERE id=?", (s.id,))
                    supply_ref = s.id
                    break
            self.store.set_unit_field(conn, unit.id, active_fleet_supply_ref=supply_ref,
                                      designation_execution_event=new_id("edev"), active_date=self.store._now())
            rid = self.store.insert_reconciliation(conn, unit.id, cur.vehicle_unit_id, scope, "ACTIVE_DEMO",
                                                   supply_ref=supply_ref, detail="removed from New Retail Current Supply")
            return {"reconciliation_ref": rid, "detail": "active demo; New Retail supply reconciled",
                    "supply_ref": supply_ref}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.designation.execute", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version, to_state="ACTIVE",
                                             action="executive_demo.designation.execute", effect=eff,
                                             idempotency_key=f"{unit.id}:designation.execute")

    def cancel_designation(self, principal, scope, unit, *, reason=""):
        def eff(conn, cur):
            if cur.designation_decision:
                self.store.set_designation_action(conn, cur.designation_decision, lifecycle_status="cancelled",
                                                  cancellation_status=reason or "cancelled")
            return {"detail": f"designation cancelled ({reason or 'cancelled'})"}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="executive_demo.designation.approve", scope=scope,
                                             unit_id=unit.id, expected_version=unit.version, to_state="CANCELLED",
                                             action="executive_demo.designation.cancel", effect=eff)

    def correct(self, principal, scope, unit, new_attrs, *, reason):
        if not reason:
            raise ValidationError(technical_detail="correction requires a reason")
        corrected = self.store.add_unit(ExecDemoUnit(
            id=new_id("edu"), store_scope=scope, vehicle_unit_id=new_attrs.get("vehicle_unit_id", unit.vehicle_unit_id),
            vin=new_attrs.get("vin", unit.vin), combination_id=new_attrs.get("combination_id", unit.combination_id),
            membership_state=new_attrs.get("membership_state", unit.membership_state), correction_of=unit.id))
        lifecycle.governed_transition(self.gov, self.store, principal=principal, capability="executive_demo.correct",
                                      scope=scope, unit_id=unit.id, expected_version=unit.version, to_state="CORRECTED",
                                      action="executive_demo.correct",
                                      field_updates=lambda c: {"superseded_by": corrected.id})
        return corrected
