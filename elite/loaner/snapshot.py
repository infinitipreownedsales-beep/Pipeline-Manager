"""Authoritative active-fleet snapshot + membership reconciliation by accepted VIN.

Raw source values are preserved through Phase 2 ingestion (import batch + observations). Only a
valid, compatible Full Snapshot may support absence reconciliation; a Partial Snapshot absence never
removes membership; a Full Snapshot absence yields a membership-review signal only (never invented
retirement/return). Invalid/unresolved VINs never silently enter the fleet; duplicate VINs and
conflicting operational states are explicit.
"""
from __future__ import annotations

import json

from ..data.identity import resolve_vehicle
from ..data.normalize import normalize_vin, vin_status
from ..ids import new_id
from .models import ServiceLoanerUnit


class SnapshotService:
    def __init__(self, store, data_store, ingestion, clock, scope):
        self.store, self.data, self.ingestion, self.clock, self.scope = store, data_store, ingestion, clock, scope

    def ingest_fleet(self, rows, *, snapshot_type="full", authoritative=True, effective_time=None):
        """Route the fleet file through Phase 2 ingestion (raw preserved + full/partial classified).
        `authoritative=False` uses a non-snapshot-capable source so a full claim validates as partial
        (an invalid Full Snapshot claim)."""
        source_id = "src_loaner" if authoritative else "src_loaner_feed"
        raw = json.dumps(rows, sort_keys=True)
        fact_type = "loaner_present" if authoritative else None
        return self.ingestion.ingest(source_id=source_id, profile_version=1, rows=rows, raw_text=raw,
                                     scope=self.scope, entity_kind="vehicle", fact_type=fact_type,
                                     claimed_snapshot=snapshot_type, effective_time=effective_time)

    def reconcile(self, batch, rows):
        """Reconcile active-fleet membership by accepted VIN. Returns a summary dict of outcomes."""
        snapshot_type = batch.validated_snapshot_type
        present, seen, summary = set(), set(), {}

        def bump(outcome):
            summary[outcome] = summary.get(outcome, 0) + 1

        for row in rows:
            raw_vin = row.get("vin")
            status = vin_status(raw_vin)
            vin = normalize_vin(raw_vin or "")
            if status != "valid":
                self.store.add_snapshot_recon(batch.id, snapshot_type, self.scope, vin, None,
                                              "INVALID_VIN_EXCLUDED", status)
                bump("INVALID_VIN_EXCLUDED")
                continue
            if vin in seen:
                self.store.add_snapshot_recon(batch.id, snapshot_type, self.scope, vin, None, "DUPLICATE_VIN")
                bump("DUPLICATE_VIN")
                continue
            seen.add(vin)
            present.add(vin)
            rental = row.get("rental_status")
            conflicting = bool(row.get("conflicting_state"))

            # Service Loaner membership and Phase 2 physical identity must share the
            # canonical scoped VehicleUnit. Never manufacture an ID-shaped reference
            # such as ``vu_<VIN>`` when no such VehicleUnit exists.
            _, vehicle, _ = resolve_vehicle(self.data, vin, self.scope)
            if vehicle is None:
                self.store.add_snapshot_recon(batch.id, snapshot_type, self.scope, vin, None,
                                              "VEHICLE_IDENTITY_UNRESOLVED")
                bump("VEHICLE_IDENTITY_UNRESOLVED")
                continue

            unit = self.store.unit_for_vin(vin, self.scope, active_only=True)
            if unit is None:
                unit = self.store.add_unit(ServiceLoanerUnit(
                    id=new_id("slu"), store_scope=self.scope, vin=vin,
                    vehicle_unit_id=vehicle.id,
                    combination_id=row.get("combination_id"),
                    membership_state=("ACTIVE_RENTED" if rental == "rented" else "ACTIVE_AVAILABLE"),
                    current_rental_state=rental, last_accepted_snapshot=batch.id, active_fleet_presence=True,
                    in_service_date_authority="snapshot"))
                outcome = "MEMBER_ADDED"
            else:
                with self.store.conn:
                    self.store.set_unit_field(
                        self.store.conn, unit.id,
                        vehicle_unit_id=vehicle.id,
                        current_rental_state=rental,
                        last_accepted_snapshot=batch.id,
                        active_fleet_presence=1)
                outcome = "MEMBER_CONFIRMED"
            if conflicting:
                outcome = "CONFLICTING_STATE"
            self.store.add_operational_state(unit.id, snapshot_ref=batch.id, rental_state=rental,
                                             conflict="conflicting operational state" if conflicting else None)
            self.store.add_snapshot_recon(batch.id, snapshot_type, self.scope, vin, unit.id, outcome)
            bump(outcome)

        # Absence handling — only a valid Full Snapshot supports it, and only as a review signal.
        active = self.store.units_in_states(self.scope, ["ACTIVE_AVAILABLE", "ACTIVE_RENTED", "ACTIVE_UNRESOLVED"])
        for u in active:
            if u.vin and u.vin not in present:
                if snapshot_type == "full":
                    self.store.add_snapshot_recon(batch.id, snapshot_type, self.scope, u.vin, u.id, "ABSENT_REVIEW",
                                                  "present before, absent from this full snapshot")
                    bump("ABSENT_REVIEW")
                else:
                    self.store.add_snapshot_recon(batch.id, snapshot_type, self.scope, u.vin, u.id, "ABSENT_NO_CHANGE",
                                                  "partial snapshot absence: no removal")
                    bump("ABSENT_NO_CHANGE")
        return summary
