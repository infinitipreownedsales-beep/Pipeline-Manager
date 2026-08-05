"""Current / Future / Committed Supply projection + qualifying-supply resolution.

Supply is kept strictly separate from Demand. The three supply states remain distinguishable
and one physical unit or future-order identity is counted at most once across them. A proposed
action is not Committed Supply; an approved unit-level commitment counts exactly once and
affects the next calculation. A supply method may change feasibility / timing / confidence /
commitment status but never Demand truth.
"""
from __future__ import annotations

import json

from ..errors import ValidationError
from ..ids import new_id
from .models import CurrentSupply, FutureSupply, SupplyCommitment

# Current-supply availability states and whether each is eligible for New Retail supply.
CURRENT_ELIGIBLE = {"available_unsold", "on_lot", "in_transit", "reconditioning"}
CURRENT_EXCLUDED = {"sold", "retired", "transferred", "duplicate", "invalid", "unresolved"}


class SupplyService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    # ---- Current Supply ----------------------------------------------------
    def project_current(self, combination_id, scope, units):
        """Project Current Supply from accepted current-state units. One effect per physical
        Vehicle Unit; sold/retired/transferred/duplicate/invalid/unresolved are excluded with a
        recorded reason; operational presence and retail availability stay distinguishable."""
        seen = {}
        out = []
        for u in units:
            vuid = u.get("vehicle_unit_id")
            state = u.get("state", "unknown")
            identity_status = u.get("identity_status", "resolved")
            if vuid and vuid in seen:
                continue                                  # one effect per physical unit
            eligible = state in CURRENT_ELIGIBLE and identity_status == "resolved"
            reason = None
            if identity_status != "resolved":
                eligible, reason = False, "unresolved_identity"
            elif state in CURRENT_EXCLUDED:
                eligible, reason = False, state
            elif state not in CURRENT_ELIGIBLE:
                eligible, reason = False, f"state_not_eligible:{state}"
            cs = CurrentSupply(
                id=new_id("csup"), store_scope=scope, availability_state=state, vehicle_unit_id=vuid,
                combination_id=combination_id, arrival_date=u.get("arrival_date"),
                available_for_retail_date=u.get("available_for_retail_date"), age_days=u.get("age_days"),
                fact_refs=list(u.get("fact_refs", [])), retail_eligible=eligible, exclusion_reason=reason,
                confidence=u.get("confidence", "medium"),
                quality_status="ok" if identity_status == "resolved" else "unresolved")
            self.store.add_current_supply(cs)
            if vuid:
                seen[vuid] = cs.id
            out.append(cs)
        return out

    # ---- Future Supply -----------------------------------------------------
    def project_future(self, combination_id, scope, orders):
        """Project Future Supply from accepted Production Orders. Two same-config orders remain
        two distinct future units; a cancelled/invalid order does not count; pre-VIN and later
        VIN identity resolve to one unit (no double count); ETA uncertainty stays visible."""
        by_order = {}
        out = []
        for o in orders:
            poid = o.get("production_order_id")
            cancel = o.get("cancellation_status")
            if poid and poid in by_order:
                continue                                  # pre-VIN + VIN of same order -> one future unit
            fs = FutureSupply(
                id=new_id("fsup"), store_scope=scope, production_order_id=poid, combination_id=combination_id,
                production_state=o.get("production_state", "planned"), eta_start=o.get("eta_start"),
                eta_end=o.get("eta_end"), arrival_month=o.get("arrival_month"),
                timing_confidence=o.get("timing_confidence", "medium"), editability=o.get("editability"),
                cancellation_status=cancel,
                identity_linkage={"production_order_id": poid, "vehicle_unit_id": o.get("vehicle_unit_id")},
                source_refs=list(o.get("source_refs", [])), fact_refs=list(o.get("fact_refs", [])))
            self.store.add_future_supply(fs)
            if poid:
                by_order[poid] = fs.id
            out.append(fs)
        return out

    # ---- Committed Supply --------------------------------------------------
    def propose_commitment(self, combination_id, scope, *, commitment_type, unit_or_order_id,
                           unit_identity_kind="production_order", arrival_month=None, source="", fact_refs=None):
        """Record a PROPOSED commitment. A proposal is not Committed Supply and does not count."""
        c = SupplyCommitment(
            id=new_id("cmt"), store_scope=scope, commitment_type=commitment_type, unit_or_order_id=unit_or_order_id,
            unit_identity_kind=unit_identity_kind, combination_id=combination_id, arrival_month=arrival_month,
            lifecycle_status="proposed", commitment_source=source, fact_refs=list(fact_refs or []))
        return self.store.add_commitment(c)

    def approve_commitment(self, commitment_id, *, decision_ref, approval_time, audit_refs=None):
        """Approve a proposed commitment into Committed Supply. Approval creates commitment only
        here — existence of a proposal never does. The committed unit counts exactly once."""
        c = self.store.get_commitment(commitment_id)
        if c is None:
            raise ValidationError(technical_detail="commitment not found")
        if c.lifecycle_status not in ("proposed",):
            raise ValidationError(message="Only a proposed commitment can be approved.",
                                  technical_detail=f"commitment {commitment_id} is {c.lifecycle_status}")
        updated = self.store.set_commitment_status(commitment_id, c.version, "committed")
        # record approval metadata on a fresh read+write (append-preserving fields)
        with self.store.conn:
            self.store.conn.execute("UPDATE supply_commitment SET decision_ref=?,approval_time=?,audit_refs=?"
                                    " WHERE id=?", (decision_ref, approval_time,
                                                    json.dumps(list(audit_refs or [])), commitment_id))
        return self.store.get_commitment(commitment_id)

    def cancel_commitment(self, commitment_id, *, reason=""):
        """Cancel a commitment. It stops contributing prospectively but remains historical."""
        c = self.store.get_commitment(commitment_id)
        if c is None:
            raise ValidationError(technical_detail="commitment not found")
        return self.store.set_commitment_status(commitment_id, c.version, "cancelled",
                                                cancellation_status=reason or "cancelled")

    # ---- Qualifying supply (deduped across the three states) ---------------
    def qualifying_supply(self, combination_id, scope):
        """Union eligible Current + active Future + committed Commitment units, deduped by a
        single canonical unit/order identity so one physical or future unit counts once.

        Returns a list of dicts: {key, kind, available_month} where available_month is None for
        units already available (current) and a 'YYYY-MM' string for future/committed arrivals.
        """
        entries = {}

        def put(key, kind, month):
            # A concrete unit identity wins over an anonymous fallback key; earliest availability
            # is kept (a unit already on the lot dominates a future arrival of the same identity).
            if key in entries:
                prior = entries[key]
                if _month_key(month) < _month_key(prior["available_month"]):
                    entries[key] = {"key": key, "kind": prior["kind"], "available_month": month}
                return
            entries[key] = {"key": key, "kind": kind, "available_month": month}

        for cs in self.store.current_supply_for(combination_id, scope, eligible_only=True):
            put(cs.vehicle_unit_id or cs.id, "current", None)
        for fs in self.store.future_supply_for(combination_id, scope, active_only=True):
            key = (fs.identity_linkage or {}).get("vehicle_unit_id") or fs.production_order_id or fs.id
            put(key, "future", fs.arrival_month)
        for cm in self.store.commitments_for(combination_id, scope, committed_only=True):
            put(cm.unit_or_order_id or cm.id, "committed", cm.arrival_month)
        return list(entries.values())

    def counts(self, combination_id, scope):
        """Separately-inspectable counts for each supply state (before dedup)."""
        cur = len(self.store.current_supply_for(combination_id, scope, eligible_only=True))
        fut = len(self.store.future_supply_for(combination_id, scope, active_only=True))
        com = len(self.store.commitments_for(combination_id, scope, committed_only=True))
        return {"current": cur, "future": fut, "committed": com,
                "qualifying": len(self.qualifying_supply(combination_id, scope))}


def _month_key(m):
    return m if m else "0000-00"       # None (already available) sorts earliest
