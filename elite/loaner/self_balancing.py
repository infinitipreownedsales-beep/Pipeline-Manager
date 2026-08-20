"""Service-Loaner self-balancing planning engine.

Elite derives future Service-Loaner acquisition need from authoritative/certified state instead of making the
operator invent a number to clear a banner. The planning identity is:

    desired operating fleet
    - active fleet expected to remain in service
    - already committed / designated incoming Service-Loaner supply
    = additional Service-Loaner acquisition requirement          (floored at zero)

"Expected to remain" excludes units already in a governed exit pipeline (releasing now). Timing-based FUTURE
exits (release-by from learned DTS) stay GATED until authoritative inputs exist — they are never guessed, so
when exit timing is unknown the calculated need is a LOWER BOUND (exits could only raise it), which the
engine states explicitly rather than fabricating a retire date.

This engine is program-level (the desired target is a program total). It never mutates certified Retail
demand; it exposes a separate, additive Service-Loaner requirement. A management directive can override or add
to it (governed, audited) — that lives in elite.ordering.cross_domain.PlannedRequirementStore.
"""
from __future__ import annotations

from dataclasses import dataclass

# Units still counted as remaining in the operating fleet.
_IN_FLEET = ("ACTIVE_AVAILABLE", "ACTIVE_RENTED", "ACTIVE_UNRESOLVED", "RETIREMENT_ELIGIBLE")
# Units physically present but already in a governed exit pipeline — "releasing now", not remaining.
_RELEASING = ("RETIREMENT_PROPOSED", "RETIREMENT_APPROVED", "PROVISIONAL_RETIREMENT", "AWAITING_RETURN",
              "AWAITING_USED_CARS_RECEIPT")


@dataclass(frozen=True)
class SelfBalancedRequirement:
    desired: int | None            # desired operating fleet target (None = operator has not set one)
    current_active: int            # physically present fleet (in-fleet + releasing)
    releasing_now: int             # governed exit pipeline (leaving; not remaining)
    projected_future_exits: int    # authoritative timing-based future exits (0 while gated — never guessed)
    committed_incoming: int        # incoming units already designated for Service Loaner
    unresolved_timing_units: int   # active units whose exit timing cannot be computed (missing in-service date)
    calculated_need: int           # additive SL acquisition requirement (>=0)
    resolution: str                # "no_target" | "resolved_zero" | "resolved_need"
    source: str                    # "none" | "order_specific" | "unresolved"
    is_lower_bound: bool           # True when exit timing is unresolved (need could be higher)

    @property
    def remaining(self):
        """Active fleet expected to remain after known/governed exits."""
        return self.current_active - self.releasing_now - self.projected_future_exits


def compute_requirement(*, desired, current_active, releasing_now=0, projected_future_exits=0,
                        committed_incoming=0, unresolved_timing_units=0):
    """Pure planning calculation. `desired=None` → cannot plan (no target). Otherwise the additive need is
    max(0, desired - remaining - committed_incoming); it is a lower bound whenever some exit timing is
    unresolved. When exit timing is unresolved AND the fleet already meets target, it still resolves to zero —
    a fleet at or above target needs nothing ordered right now — but is flagged as a lower bound."""
    ca = max(0, int(current_active or 0))
    rel = max(0, int(releasing_now or 0))
    fx = max(0, int(projected_future_exits or 0))
    ci = max(0, int(committed_incoming or 0))
    ut = max(0, int(unresolved_timing_units or 0))
    if desired is None:
        return SelfBalancedRequirement(None, ca, rel, fx, ci, ut, 0, "no_target", "unresolved", ut > 0)
    remaining = ca - rel - fx
    need = max(0, int(desired) - remaining - ci)
    if need == 0:
        return SelfBalancedRequirement(int(desired), ca, rel, fx, ci, ut, 0, "resolved_zero", "none", ut > 0)
    # need > 0 — recommend ordering specifically for Service Loaner so Retail is never silently shorted; using
    # a Retail-safe physical unit is an optimization that requires certified Retail-coverage evidence to prove
    # donation is safe, so it is not assumed here.
    return SelfBalancedRequirement(int(desired), ca, rel, fx, ci, ut, need, "resolved_need", "order_specific",
                                   ut > 0)


def _counts(conn, scope):
    marks_in = ",".join("?" * len(_IN_FLEET))
    marks_rel = ",".join("?" * len(_RELEASING))
    in_fleet = conn.execute(
        f"SELECT COUNT(*) FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        f"AND active_fleet_presence=1 AND membership_state IN ({marks_in})", (scope, *_IN_FLEET)).fetchone()[0]
    releasing = conn.execute(
        f"SELECT COUNT(*) FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        f"AND active_fleet_presence=1 AND membership_state IN ({marks_rel})", (scope, *_RELEASING)).fetchone()[0]
    unresolved = conn.execute(
        f"SELECT COUNT(*) FROM service_loaner_unit WHERE store_scope=? AND superseded_by IS NULL "
        f"AND active_fleet_presence=1 AND membership_state IN ({marks_in}) "
        f"AND accepted_in_service_date IS NULL", (scope, *_IN_FLEET)).fetchone()[0]
    return int(in_fleet), int(releasing), int(unresolved)


def build_requirement(conn, scope, prefs, *, committed_incoming=0):
    """Live self-balancing requirement from authoritative state. Reads the desired target and the current
    membership composition; projected future (timing-based) exits stay 0 until authoritative timing exists."""
    from .loaner_cockpit import MetaPrefs, desired_fleet
    desired = desired_fleet(MetaPrefs(prefs, scope))
    in_fleet, releasing, unresolved = _counts(conn, scope)
    current_active = in_fleet + releasing
    return compute_requirement(desired=desired, current_active=current_active, releasing_now=releasing,
                               projected_future_exits=0, committed_incoming=committed_incoming,
                               unresolved_timing_units=unresolved)
