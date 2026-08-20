"""Cross-domain ordering integrity.

Two things Retail/CPO ordering must know about the OTHER inventory-consuming domains:

  1. COMMITTED PHYSICAL VEHICLES — one physical vehicle, one committed purpose at a time, counted once. A VIN
     committed to Service Loaner or Demo is no longer free Retail supply. committed_vins() is the single
     authoritative exclusion set (Service Loaner active fleet + committed Demo units).

  2. PLANNED (non-economic) SERVICE-LOANER REQUIREMENT — a governed, additive future need that management /
     the operator has authoritatively stated (e.g. "we will need 3 more QX60 loaners"). It is NOT the Phase-4
     economic Ideal (which stays Undetermined). It participates in total dealership acquisition planning as a
     SEPARATE additive need and never mutates certified Retail demand.

No certified New-Retail demand math is changed here. This module reads certified state and exposes need; it
does not recompute the plan.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..ids import new_id

# Service-Loaner active membership states (mirrors elite.loaner.intelligence)
_SL_ACTIVE = ("ACTIVE_RENTED", "ACTIVE_AVAILABLE", "AWAITING_USED_CARS_RECEIPT")


def committed_vins(conn, scope, prefs=None):
    """Authoritative VIN -> committed purpose map for every physical vehicle currently consumed by a non-Retail
    domain. Count-once: a VIN appears at most once (Service Loaner wins over Demo). These VINs must be excluded
    from free Retail supply and from placement candidacy."""
    out = {}
    try:
        for r in conn.execute(
                f"SELECT vin FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
                f"AND active_fleet_presence=1 AND membership_state IN ({','.join('?' * len(_SL_ACTIVE))})",
                (scope, *_SL_ACTIVE)).fetchall():
            v = (r["vin"] or "").strip().upper()
            if v:
                out.setdefault(v, "service_loaner")
    except Exception:   # noqa: BLE001
        pass
    try:
        for r in conn.execute(
                "SELECT vin FROM executive_demo_unit WHERE store_scope=? AND vin IS NOT NULL "
                "AND membership_state NOT IN ('CANDIDATE','RETIRED','RELEASED')", (scope,)).fetchall():
            v = (r["vin"] or "").strip().upper()
            if v:
                out.setdefault(v, "demo")
    except Exception:   # noqa: BLE001
        pass
    if prefs is not None:                       # operator-managed demo roster (current assignments)
        try:
            roster = prefs.get_pref(f"scope::{scope}", "demo_roster", default=[]) or []
            for u in roster:
                cur = u.get("current") or {}
                v = (cur.get("vin") or "").strip().upper()
                if v:
                    out.setdefault(v, "demo")
        except Exception:   # noqa: BLE001
            pass
    return out


# ---- governed planned Service-Loaner requirement (additive, non-economic) ----------------------------------
@dataclass(frozen=True)
class PlannedSLRequirement:
    id: str
    model: str
    quantity: int
    model_year: str = ""
    trim: str = ""
    required_by: str = ""        # YYYY-MM window, when known
    reason: str = ""
    actor: str = ""
    recorded_at: str = ""
    status: str = "active"       # active | retired
    correction_of: str = ""

    def to_dict(self):
        return dict(id=self.id, model=self.model, quantity=self.quantity, model_year=self.model_year,
                    trim=self.trim, required_by=self.required_by, reason=self.reason, actor=self.actor,
                    recorded_at=self.recorded_at, status=self.status, correction_of=self.correction_of)

    @staticmethod
    def from_dict(d):
        return PlannedSLRequirement(d["id"], (d.get("model") or "").upper(), int(d.get("quantity") or 0),
                                    d.get("model_year", ""), d.get("trim", ""), d.get("required_by", ""),
                                    d.get("reason", ""), d.get("actor", ""), d.get("recorded_at", ""),
                                    d.get("status", "active"), d.get("correction_of", ""))


class PlannedRequirementStore:
    """Append-only, store-scoped planned Service-Loaner requirement (governed JSON; no schema change)."""
    KEY = "sl_planned_requirement"

    def __init__(self, prefs, scope):
        self.prefs = prefs
        self.scope = scope
        self._sk = f"scope::{scope}"

    def _rows(self):
        return self.prefs.get_pref(self._sk, self.KEY, default=[]) or []

    def entries(self):
        return [PlannedSLRequirement.from_dict(d) for d in self._rows()]

    def active(self):
        return [e for e in self.entries() if e.status == "active" and e.quantity > 0]

    def add(self, *, model, quantity, actor, recorded_at, model_year="", trim="", required_by="", reason="",
            correction_of=""):
        try:
            q = int(quantity)
        except (TypeError, ValueError):
            raise ValueError("quantity must be a whole number")
        if q <= 0:
            raise ValueError("quantity must be positive")
        e = PlannedSLRequirement(new_id("slreq"), (model or "").upper(), q, (model_year or "").strip(),
                                 (trim or "").strip(), (required_by or "").strip(), (reason or "").strip(),
                                 actor, recorded_at, "active", correction_of)
        rows = self._rows() + [e.to_dict()]
        self.prefs.set_pref(self._sk, self.KEY, rows)
        return e

    def retire(self, req_id, *, actor, at):
        rows = self._rows()
        for r in rows:
            if r["id"] == req_id and r.get("status", "active") != "retired":
                r["status"] = "retired"
                r["reason"] = (r.get("reason") or "") + f" · retired by {actor} {at[:10]}"
                self.prefs.set_pref(self._sk, self.KEY, rows)
                return True
        return False

    def by_model(self):
        """Active planned SL quantity summed per model (model-level need; not fabricated to a color combo)."""
        out = {}
        for e in self.active():
            out[e.model] = out.get(e.model, 0) + e.quantity
        return out
