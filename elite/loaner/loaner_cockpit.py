"""Service Loaner cockpit read model — the three fleet counts and the ECONOMIC Ideal Mix summary.

This is a thin, honest presentation layer over authoritative records and the certified `optimize_ideal_mix`
law. It never fabricates economics: when per-unit ICV / Velocity / preowned-DTS inputs have not been loaded,
the mix is reported as ECONOMICALLY UNDETERMINED (with the fleet counts still shown from authoritative state)
rather than inventing a ranking. Governed, temporary settings (desired fleet size, monthly placement
requirement) persist through the existing prefs store — no schema change.

Three counts are never conflated (product law):
  * CURRENT  — authoritative active ICV / Service-Loaner membership snapshot (count-once)
  * DESIRED  — the operational size the dealership wants to maintain (governed setting; optional)
  * IDEAL    — the economically optimal count `optimize_ideal_mix` returns from real per-unit economics
"""
from __future__ import annotations

from dataclasses import dataclass

from . import placement_settings as PS
from .ideal_mix import optimize_ideal_mix

# Membership states that count as physically in the active fleet right now.
_ACTIVE_STATES = ("ACTIVE_RENTED", "ACTIVE_AVAILABLE", "AWAITING_USED_CARS_RECEIPT")
_DESIRED_KEY = "loaner_desired_fleet"


class MetaPrefs:
    """Adapt the governed operator-preference store to the simple put/get contract `placement_settings`
    and this module use. Store-scoped dealership settings are keyed by scope so they are shared across the
    operators of that store (not tied to one principal), and persist across restarts in the governed DB."""

    def __init__(self, prefs, scope):
        self._prefs, self._scope = prefs, f"scope::{scope}"

    def put(self, key, value):
        self._prefs.set_pref(self._scope, key, "" if value is None else str(value))

    def get(self, key):
        return self._prefs.get_pref(self._scope, key, default=None)


def desired_fleet(meta):
    raw = meta.get(_DESIRED_KEY)
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def set_desired_fleet(meta, n):
    meta.put(_DESIRED_KEY, None if n is None else int(n))


def current_fleet_count(conn, scope):
    marks = ",".join("?" * len(_ACTIVE_STATES))
    row = conn.execute(
        f"SELECT COUNT(*) FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        f"AND active_fleet_presence=1 AND membership_state IN ({marks})", (scope, *_ACTIVE_STATES)).fetchone()
    return int(row[0]) if row else 0


@dataclass
class LoanerCockpit:
    current_fleet: int
    desired_fleet: int                     # may be None (operator has not stated one)
    ideal_fleet: int                       # economic optimum; None when undetermined
    economically_determined: bool
    requirement: dict                      # resolved monthly placement requirement, or None
    mix: object                            # MixResult, or None when undetermined
    planning_month: str

    def note(self):
        if not self.economically_determined:
            return ("Economic Ideal Mix is undetermined: the complete real per-unit economics required "
                    "for IN / HOLD / OUT are not available yet. Preowned market evidence may be shown "
                    "separately, but no economic ranking is created until the remaining required inputs are loaded.")
        return self.mix.note if self.mix else ""


def build_cockpit(conn, scope, prefs, planning_month, *, held=None, candidates=None):
    """Assemble the loaner cockpit read model. `held` / `candidates` are UnitEcon lists supplied by the
    caller from REAL per-unit economics; when both are empty the mix is left ECONOMICALLY UNDETERMINED and
    only the authoritative fleet counts + governed target/requirement are reported (no fabricated ranking)."""
    meta = MetaPrefs(prefs, scope)
    current = current_fleet_count(conn, scope)
    desired = desired_fleet(meta)
    req = PS.resolve(meta, planning_month)
    required_placements = req.get("required") if req else None

    held = list(held or [])
    candidates = list(candidates or [])
    determined = bool(held or candidates)
    target = desired if desired is not None else current
    if determined:
        mix = optimize_ideal_mix(held, candidates, operational_target=max(0, target),
                                 required_placements=required_placements)
        ideal = mix.economic_fleet_count
    else:
        mix, ideal = None, None
    return LoanerCockpit(current_fleet=current, desired_fleet=desired, ideal_fleet=ideal,
                         economically_determined=determined, requirement=req, mix=mix,
                         planning_month=planning_month)
