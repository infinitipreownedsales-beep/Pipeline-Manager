"""Service Loaner Unit management + entry lifecycle.

The Service Loaner Unit ID never replaces Vehicle Unit identity. Candidate is not active membership;
approval is not execution; entry execution establishes actual membership exactly once. Rental state
is a separate operational fact and never changes membership by itself. Corrections preserve prior
lifecycle history.
"""
from __future__ import annotations

from ..ids import new_id
from . import lifecycle
from .models import ServiceLoanerUnit


class UnitService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def create_candidate(self, scope, *, vehicle_unit_id, vin=None, combination_id=None):
        """Register a CANDIDATE (not active membership; ungoverned — no supply effect)."""
        u = ServiceLoanerUnit(id=new_id("slu"), store_scope=scope, vehicle_unit_id=vehicle_unit_id, vin=vin,
                              combination_id=combination_id, membership_state="CANDIDATE")
        return self.store.add_unit(u)

    def propose_entry(self, principal, scope, unit, *, decision_ref=None):
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.entry.propose", scope=scope, unit_id=unit.id,
                                             expected_version=unit.version, to_state="ENTRY_PROPOSED",
                                             action="service_loaner.entry.propose",
                                             field_updates=lambda c: {"entry_decision": decision_ref or f"prop_{unit.id}"})

    def approve_entry(self, principal, scope, unit):
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.entry.approve", scope=scope, unit_id=unit.id,
                                             expected_version=unit.version, to_state="ENTRY_APPROVED",
                                             action="service_loaner.entry.approve")

    def execute_entry(self, principal, scope, unit, *, in_service_date=None, rental_state="available"):
        """Entry EXECUTION establishes actual membership exactly once (idempotent)."""
        def fields(cur):
            return {"active_fleet_presence": 1, "entry_execution_event": new_id("slev"),
                    "current_rental_state": rental_state,
                    "accepted_in_service_date": in_service_date or cur.accepted_in_service_date}
        return lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                             capability="service_loaner.entry.execute", scope=scope, unit_id=unit.id,
                                             expected_version=unit.version, to_state="ACTIVE_AVAILABLE",
                                             action="service_loaner.entry.execute", field_updates=fields,
                                             idempotency_key=f"{unit.id}:entry.execute")

    def correct(self, principal, scope, unit, new_attrs: dict, *, reason):
        """Correction creates a NEW unit record (correction_of) and marks the original CORRECTED —
        prior lifecycle history preserved. Requires explicit authority + reason."""
        if not reason:
            from ..errors import ValidationError
            raise ValidationError(technical_detail="correction requires a reason")
        corrected = ServiceLoanerUnit(
            id=new_id("slu"), store_scope=scope, vehicle_unit_id=new_attrs.get("vehicle_unit_id", unit.vehicle_unit_id),
            vin=new_attrs.get("vin", unit.vin), combination_id=new_attrs.get("combination_id", unit.combination_id),
            membership_state=new_attrs.get("membership_state", unit.membership_state),
            accepted_in_service_date=new_attrs.get("accepted_in_service_date", unit.accepted_in_service_date),
            correction_of=unit.id, active_fleet_presence=unit.active_fleet_presence)
        self.store.add_unit(corrected)
        r = lifecycle.governed_transition(self.gov, self.store, principal=principal,
                                          capability="service_loaner.correct", scope=scope, unit_id=unit.id,
                                          expected_version=unit.version, to_state="CORRECTED",
                                          action="service_loaner.correct",
                                          field_updates=lambda c: {"superseded_by": corrected.id})
        return corrected

    def set_rental_state(self, unit, rental_state, *, snapshot_ref=None):
        """Update the operational rental fact WITHOUT changing membership (separate concern)."""
        with self.store.conn:
            self.store.set_unit_field(self.store.conn, unit.id, current_rental_state=rental_state,
                                      last_accepted_snapshot=snapshot_ref or unit.last_accepted_snapshot)
        self.store.add_operational_state(unit.id, snapshot_ref=snapshot_ref, rental_state=rental_state)
        return self.store.get_unit(unit.id)
