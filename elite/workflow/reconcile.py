"""Deterministic commitment reconciliation effects.

Each factory returns an `effect(conn, workflow)` closure that applies a supply effect via RAW
inserts/updates on the governed connection and returns the reconciliation outcome. Outcomes are
the canonical set; the qualifying-supply count is measured before and after so the effect on
Phase 4 Supply is explicit. Count-once and monotonicity come from the Phase 4 qualifying-supply
dedup — a workflow that commits an already-represented identity yields ALREADY_REPRESENTED with no
new unit.
"""
from __future__ import annotations

from ..ids import new_id
from ..newinv.models import CurrentSupply, SupplyCommitment


def _qual(supply, combination_id, scope):
    q = supply.qualifying_supply(combination_id, scope)
    return len(q), {u["key"] for u in q}


def no_effect():
    def eff(conn, wf):
        return {"outcome": "NO_SUPPLY_EFFECT", "combination_id": wf.combination_id,
                "subject_identity": wf.subject_identity}
    return eff


def unresolved_identity(reason="identity unresolved"):
    def eff(conn, wf):
        return {"outcome": "UNRESOLVED_IDENTITY", "combination_id": wf.combination_id,
                "subject_identity": wf.subject_identity, "detail": reason}
    return eff


def failed():
    def eff(conn, wf):
        return {"outcome": "FAILED_NO_EFFECT", "combination_id": wf.combination_id,
                "subject_identity": wf.subject_identity}
    return eff


def create_commitment(nistore, supply, *, unit_or_order_id, combination_id, scope, arrival_month,
                      commitment_type, decision_ref=None):
    """Approve into Committed Supply — unless the identity is already represented in qualifying
    supply (then ALREADY_REPRESENTED, no new unit — count-once)."""
    def eff(conn, wf):
        if not unit_or_order_id:
            return {"outcome": "UNRESOLVED_IDENTITY", "combination_id": combination_id,
                    "detail": "no discrete unit/order identity"}
        prior, keys = _qual(supply, combination_id, scope)
        if unit_or_order_id in keys:
            return {"outcome": "ALREADY_REPRESENTED", "prior_qualifying": prior, "new_qualifying": prior,
                    "subject_identity": unit_or_order_id, "combination_id": combination_id,
                    "detail": "identity already represented in qualifying supply"}
        c = SupplyCommitment(id=new_id("cmt"), store_scope=scope, commitment_type=commitment_type,
                             unit_or_order_id=unit_or_order_id, combination_id=combination_id,
                             arrival_month=arrival_month, lifecycle_status="committed", decision_ref=decision_ref,
                             approval_time=nistore._now(), commitment_source=commitment_type)
        nistore.insert_commitment(conn, c)
        new, _ = _qual(supply, combination_id, scope)
        return {"outcome": "COMMITMENT_CREATED", "supply_ref": c.id, "prior_qualifying": prior,
                "new_qualifying": new, "subject_identity": unit_or_order_id, "combination_id": combination_id}
    return eff


def cancel_commitment(nistore, supply, *, commitment_ref, combination_id, scope, subject_identity):
    def eff(conn, wf):
        prior, _ = _qual(supply, combination_id, scope)
        conn.execute("UPDATE supply_commitment SET lifecycle_status='cancelled',cancellation_status=? WHERE id=?",
                     ("workflow_cancel", commitment_ref))
        new, _ = _qual(supply, combination_id, scope)
        return {"outcome": "COMMITMENT_CANCELLED", "supply_ref": commitment_ref, "prior_qualifying": prior,
                "new_qualifying": new, "subject_identity": subject_identity, "combination_id": combination_id}
    return eff


def complete_to_current(nistore, supply, *, combination_id, scope, received_unit_id, commitment_ref=None,
                        future_ref=None, subject_identity):
    """Reconcile a committed/future unit into Current Supply on completion, without double count:
    the committed commitment is marked fulfilled and any matching future projection superseded, then
    one Current Supply record is added for the (possibly later) received Vehicle Unit identity."""
    def eff(conn, wf):
        prior, _ = _qual(supply, combination_id, scope)
        if commitment_ref:
            conn.execute("UPDATE supply_commitment SET lifecycle_status='fulfilled' WHERE id=?", (commitment_ref,))
        if future_ref:
            conn.execute("UPDATE future_supply_projection SET status='superseded' WHERE id=?", (future_ref,))
        cs = CurrentSupply(id=new_id("csup"), store_scope=scope, availability_state="available_unsold",
                           vehicle_unit_id=received_unit_id or subject_identity, combination_id=combination_id,
                           retail_eligible=True, confidence="high")
        nistore.insert_current_supply(conn, cs)
        new, _ = _qual(supply, combination_id, scope)
        return {"outcome": "COMPLETED_TO_CURRENT", "supply_ref": cs.id, "prior_qualifying": prior,
                "new_qualifying": new, "subject_identity": received_unit_id or subject_identity,
                "combination_id": combination_id}
    return eff
