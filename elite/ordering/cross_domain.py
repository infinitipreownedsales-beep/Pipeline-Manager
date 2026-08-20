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
    """Append-only, store-scoped planned Service-Loaner requirement (governed JSON; no schema change).

    Also carries a governed 'no additional need' acknowledgement per model, so ordering can distinguish a
    resolved-and-empty future requirement ("management confirmed we need no more QX60 loaners") from an
    UNRESOLVED one (nobody has said either way). That distinction is what lets CPO fail safe."""
    KEY = "sl_planned_requirement"
    ACK_KEY = "sl_no_additional_need"

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

    # ---- governed 'no additional need' acknowledgement (resolved-empty, distinct from unresolved) -----------
    def _ack_rows(self):
        return dict(self.prefs.get_pref(self._sk, self.ACK_KEY, default={}) or {})

    def acknowledge_no_need(self, model, *, actor, at):
        """Governed record that no additional Service-Loaner units of this model are needed. It marks the
        model's future SL requirement RESOLVED (as zero) so CPO stops flagging it incomplete."""
        m = (model or "").upper().strip()
        if not m:
            raise ValueError("model required")
        rows = self._ack_rows()
        rows[m] = {"actor": actor, "at": at}
        self.prefs.set_pref(self._sk, self.ACK_KEY, rows)
        return m

    def clear_acknowledgement(self, model):
        m = (model or "").upper().strip()
        rows = self._ack_rows()
        if m in rows:
            del rows[m]
            self.prefs.set_pref(self._sk, self.ACK_KEY, rows)
            return True
        return False

    def acknowledged_models(self):
        """Models governed as 'no additional need'. A model that now carries an active planned need is NOT
        'acknowledged none' — an explicit planned quantity supersedes a prior no-need acknowledgement."""
        planned = set(self.by_model().keys())
        return {m for m in self._ack_rows().keys() if m not in planned}


# ---- cross-domain order-source decomposition (pure; never mutates certified Retail demand) ------------------
@dataclass(frozen=True)
class OrderSourceLine:
    """One model's decomposition of tomorrow's total dealership acquisition requirement into its sources.
    Retail is the certified acquire-now quantity (read, never recomputed). SL is the approved additive
    planned need, kept at model level (never fabricated onto an exact color). `sl_state` says whether the
    Service-Loaner future requirement for this model is resolved, and how."""
    model: str
    retail_certified: int
    sl_planned: int
    other_committed: int
    sl_state: str            # additive | acknowledged_none | unresolved | not_applicable
    sl_combo_resolved: bool  # is SL need allocated to exact combinations? (always False for now: model-level)

    @property
    def total(self):
        return self.retail_certified + self.sl_planned + self.other_committed

    @property
    def complete(self):
        """False only when a known Service-Loaner model's future requirement is unresolved — the one state in
        which a Retail-only order must NOT be presented as the complete dealership order."""
        return self.sl_state != "unresolved"


def decompose_orders(retail_by_model, planned_by_model, *, sl_relevant_models=(), acknowledged_models=(),
                     other_by_model=None):
    """Combine certified Retail acquire quantities with the approved additive Service-Loaner planned need and
    any other governed commitments into per-model order-source lines. Pure: it reads dictionaries and returns
    lines; it changes no certified state and invents no combination-level SL demand.

    sl_state per model:
      additive          — an approved planned SL need exists (add it; it is model-level, not a color)
      acknowledged_none — management governed 'no additional need' (resolved as zero)
      unresolved        — the model is operated as a Service Loaner but nobody has resolved its future need
      not_applicable    — not a Service-Loaner model; there is nothing to resolve
    """
    other = dict(other_by_model or {})
    sl_rel = {(m or "").upper() for m in sl_relevant_models}
    ack = {(m or "").upper() for m in acknowledged_models}
    retail = {(m or "").upper(): int(v or 0) for m, v in dict(retail_by_model).items()}
    planned = {(m or "").upper(): int(v or 0) for m, v in dict(planned_by_model).items()}
    other = {(m or "").upper(): int(v or 0) for m, v in other.items()}
    models = set(retail) | {m for m, q in planned.items() if q > 0} | sl_rel | {m for m, q in other.items() if q}
    lines = []
    for m in sorted(models):
        pq = planned.get(m, 0)
        if pq > 0:
            state = "additive"
        elif m in ack:
            state = "acknowledged_none"
        elif m in sl_rel:
            state = "unresolved"
        else:
            state = "not_applicable"
        lines.append(OrderSourceLine(model=m, retail_certified=retail.get(m, 0), sl_planned=pq,
                                     other_committed=other.get(m, 0), sl_state=state, sl_combo_resolved=False))
    return lines
