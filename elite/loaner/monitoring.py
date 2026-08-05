"""Zero-mile-rented monitoring.

Approved rule: when a unit is presently RENTED, its accepted Last Checkout Mileage is an explicit
ZERO, and meaningful time (a configurable, effective-dated threshold) has elapsed since its
authoritative in-service date, flag it for operational review. The prompt is exactly:
"Where is this customer's vehicle, and let's check the miles on the loaner?"

Evaluated against the current accepted snapshot only (no rental-history reconstruction). The rule
never invents the customer-vehicle location or the actual loaner mileage. Blank/missing/invalid
mileage never trigger it. The active alert clears when the unit is no longer rented or the accepted
checkout mileage changes from zero; prior alert history is preserved.
"""
from __future__ import annotations

import datetime as _dt

from ..ids import new_id
from .dating import DatingService
from .models import MonitoringAlert

PROMPT = "Where is this customer's vehicle, and let's check the miles on the loaner?"
RULE = "zero_mile_rented"


def _days_between(start, end):
    try:
        s = _dt.date.fromisoformat(str(start)[:10])
        e = _dt.date.fromisoformat(str(end)[:10])
        return (e - s).days
    except (ValueError, TypeError):
        return None


class MonitoringService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def evaluate(self, unit, *, at_date, threshold_days, policy_refs=None, snapshot_ref=None):
        """Evaluate the zero-mile-rented rule for a unit against the current accepted snapshot.
        Returns the active alert (created/kept) or None (creating nothing / clearing as needed)."""
        unit = self.store.get_unit(unit.id)
        mileage = self.store.current_mileage(unit.id)
        active = self.store.active_alert(unit.id, RULE)
        rented = unit.current_rental_state == "rented"
        zero = DatingService.is_authoritative_zero(mileage)
        elapsed = _days_between(unit.accepted_in_service_date, at_date)

        # Clear conditions: no longer rented, or mileage no longer an explicit zero.
        if active and (not rented or not zero):
            self.store.clear_alert(active.id, "no longer rented" if not rented else "checkout mileage no longer zero")
            return None

        if not (rented and zero):
            return None                                  # blank/missing/invalid mileage or not rented
        if elapsed is None or elapsed < threshold_days:
            return None                                  # do not flag before the threshold elapses
        if active:
            return active                                # idempotent: keep the existing active alert
        return self.store.add_alert(MonitoringAlert(
            id=new_id("slalert"), service_loaner_unit_id=unit.id, rule=RULE, prompt=PROMPT, status="active",
            snapshot_ref=snapshot_ref, in_service_date=unit.accepted_in_service_date, elapsed_days=elapsed,
            threshold_days=threshold_days, policy_refs=list(policy_refs or [])))
