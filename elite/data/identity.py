"""Identity evidence + resolution.

Stable internal identity is separate from VIN / stock number / order number / source
row id. Only an accepted, valid VIN may establish or support Vehicle Unit identity.
Class similarity and stock numbers never establish physical-unit identity. Scope
prevents cross-store merging. Corrections preserve prior resolution history.
"""
from __future__ import annotations

from ..ids import new_id
from .models import IdentityEvidence, ProductionOrder, VehicleUnit
from .normalize import Special, vin_status

RULE_VERSION = "1.0.0"

# resolution results
MATCHED, CREATED, DISTINCT, UNRESOLVED, CONFLICTING, CORRECTED, SUPERSEDED = (
    "matched", "created", "distinct", "unresolved", "conflicting", "corrected", "superseded")


def _evidence(store, entity_type, id_type, id_value, status, scope, *, candidates=None,
              reason="", resolver="auto", correction_ref=None, source_ref=None, record_ref=None):
    return store.add_evidence(IdentityEvidence(
        id=new_id("evd"), entity_type=entity_type, identifier_type=id_type, identifier_value=str(id_value),
        resolution_status=status, recorded_at=None, candidate_entities=candidates or [], reason=reason,
        resolver=resolver, resolution_rule_version=RULE_VERSION, correction_ref=correction_ref,
        source_ref=source_ref, record_ref=record_ref, store_scope=scope))


def resolve_vehicle(store, vin_value, scope, *, source_ref=None, record_ref=None):
    """Resolve a Vehicle Unit from a VIN within a store scope. Returns
    (status, vehicle_unit_or_None, evidence). Only a *valid* VIN establishes identity;
    invalid/placeholder VINs are UNRESOLVED (stock/config never used to establish)."""
    st = vin_status(vin_value if isinstance(vin_value, str) else None)
    if st != "valid":
        ev = _evidence(store, "vehicle_unit", "vin", vin_value if isinstance(vin_value, str) else "",
                       UNRESOLVED, scope, reason=f"vin {st}; identity cannot be established",
                       source_ref=source_ref, record_ref=record_ref)
        return UNRESOLVED, None, ev
    existing = store.find_vehicle_by_vin(vin_value, scope)   # scoped: cross-store never merges
    if existing:
        ev = _evidence(store, "vehicle_unit", "vin", vin_value, MATCHED, scope,
                       candidates=[existing.id], source_ref=source_ref, record_ref=record_ref)
        return MATCHED, existing, ev
    v = store.add_vehicle(VehicleUnit(id=new_id("veh"), vin=vin_value, identity_status="vin_established",
                                      store_scope=scope))
    store.add_alias("vehicle_unit", v.id, "vin", vin_value, scope, source_ref)
    ev = _evidence(store, "vehicle_unit", "vin", vin_value, CREATED, scope, candidates=[v.id],
                   source_ref=source_ref, record_ref=record_ref)
    return CREATED, v, ev


def resolve_production_order(store, moid, vin_value, scope, *, source_ref=None, record_ref=None):
    """Resolve a Production Order. Orders are distinguished by manufacturer order id,
    never by configuration. Two same-configuration orders remain distinct. A pre-VIN
    order is created without VIN identity."""
    moid = None if moid in (None, "") or isinstance(moid, Special) else str(moid)
    vst = vin_status(vin_value if isinstance(vin_value, str) else None)
    if moid:
        existing = store.find_orders_by_moid(moid, scope)
        if existing:
            ev = _evidence(store, "production_order", "manufacturer_order_id", moid, MATCHED, scope,
                           candidates=[o.id for o in existing], source_ref=source_ref, record_ref=record_ref)
            return MATCHED, existing[0], ev
        status = "vin_supported" if vst == "valid" else "pre_vin"
        o = store.add_order(ProductionOrder(id=new_id("pord"), manufacturer_order_id=moid,
                                            vin=(vin_value if vst == "valid" else None),
                                            identity_status=status, store_scope=scope))
        store.add_alias("production_order", o.id, "manufacturer_order_id", moid, scope, source_ref)
        ev = _evidence(store, "production_order", "manufacturer_order_id", moid, CREATED, scope,
                       candidates=[o.id], reason=status, source_ref=source_ref, record_ref=record_ref)
        return CREATED, o, ev
    # No order id: cannot match by configuration -> a fresh DISTINCT candidate.
    o = store.add_order(ProductionOrder(id=new_id("pord"), manufacturer_order_id=None,
                                        vin=(vin_value if vst == "valid" else None),
                                        identity_status=("vin_supported" if vst == "valid" else "pre_vin"),
                                        store_scope=scope))
    ev = _evidence(store, "production_order", "config", "no-order-id", DISTINCT, scope, candidates=[o.id],
                   reason="no manufacturer order id; distinct physical-order candidate",
                   source_ref=source_ref, record_ref=record_ref)
    return DISTINCT, o, ev


def link_order_to_vin(store, order_id, vin_value, scope, *, source_ref=None):
    """Later VIN assignment for a pre-VIN order. Links to the single canonical Vehicle
    Unit for that VIN (creating it if absent) — never creating a duplicate unit.
    Ambiguity (VIN already tied to a different scope/unit conflict) stays UNRESOLVED."""
    order = store.get_order(order_id)
    if order is None:
        return UNRESOLVED, None, None
    if vin_status(vin_value) != "valid":
        ev = _evidence(store, "production_order", "vin", str(vin_value), UNRESOLVED, scope,
                       reason="cannot link a non-valid VIN")
        return UNRESOLVED, order, ev
    status, unit, _ = resolve_vehicle(store, vin_value, scope, source_ref=source_ref)
    if unit is None:
        ev = _evidence(store, "production_order", "vin", vin_value, UNRESOLVED, scope, reason="vin unresolved")
        return UNRESOLVED, order, ev
    linked = store.link_order_vin(order.id, order.version, vin_value, unit.id)
    ev = _evidence(store, "production_order", "vin", vin_value, MATCHED, scope,
                   candidates=[order.id, unit.id], reason="pre-VIN order linked to canonical vehicle unit")
    return MATCHED, (linked, unit), ev


def correct_identity(store, entity_type, id_type, id_value, scope, new_status, *, reason, resolver, prior_evidence_id):
    """Record an identity correction that PRESERVES the prior resolution (a new evidence
    row referencing it) and flags dependent-state review."""
    ev = _evidence(store, entity_type, id_type, id_value, CORRECTED, scope, reason=reason,
                   resolver=resolver, correction_ref=prior_evidence_id)
    return ev
