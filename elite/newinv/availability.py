"""Availability reconstruction.

Sales and availability are interpreted together. "No availability" is NOT "zero demand"; an
available month with no sales differs from an unavailable month with no sales. A partial
snapshot must not invent continuous availability; a stockout does not prove an exact missed-
sales quantity; unresolved gaps reduce confidence rather than fabricate continuity.
"""
from __future__ import annotations

from ..ids import new_id
from .models import AvailabilityInterval

_DAYS = 30          # month bucket exposure basis (approved simplification, recorded in unit_contract)


def classify(month_row) -> str:
    """Return the availability state for one reconstructed month bucket."""
    if month_row.get("gap"):
        return "unknown"
    if month_row.get("conflicting"):
        return "conflicting"
    if month_row.get("snapshot") == "partial" and not month_row.get("depth_known", True):
        return "partial"                       # cannot assert continuous availability
    depth = month_row.get("opening_depth", 0) + month_row.get("arrivals", 0)
    retail = month_row.get("retail", 0)
    if month_row.get("stockout"):
        return "stockout"
    if depth <= 0:
        return "unavailable"                   # genuinely no inventory (distinct from stockout)
    if 0 < depth < month_row.get("expected_depth", depth + 1) and month_row.get("constrained"):
        return "constrained"
    return "available_sold" if retail > 0 else "available_unsold"


def _confidence(state, month_row):
    if state in ("unknown", "conflicting", "partial"):
        return "low"
    if month_row.get("snapshot") == "partial":
        return "low"
    if state == "stockout":
        return "medium"                        # constrained evidence; do not fabricate lost sales
    return "high"


class AvailabilityService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def reconstruct(self, combination_id, scope, month_rows):
        """Reconstruct month-bucketed availability. `month_rows` are ordered dicts with
        {month, opening_depth, arrivals, retail, stockout, snapshot, gap, ...}."""
        out = []
        for row in month_rows:
            state = classify(row)
            depth = row.get("opening_depth", 0) + row.get("arrivals", 0)
            closing = max(0, depth - row.get("retail", 0))
            # exposure only accrues when actually available; unknown/unavailable/partial accrue none
            exposure = depth * _DAYS if state in ("available_unsold", "available_sold", "constrained", "stockout") else 0.0
            gaps = ["snapshot_partial"] if row.get("snapshot") == "partial" else []
            if row.get("gap"):
                gaps.append("unresolved_period")
            a = AvailabilityInterval(
                id=new_id("av"), store_scope=scope, available_state=state, combination_id=combination_id,
                bucket="month", period_start=row["month"] + "-01", period_end=row["month"] + "-28",
                available_unit_days=exposure, opening_depth=row.get("opening_depth", 0),
                closing_depth=closing, arrivals=row.get("arrivals", 0), retail_events=row.get("retail", 0),
                stockout_periods=[row["month"]] if state == "stockout" else [],
                fact_refs=list(row.get("fact_refs", [])), confidence=_confidence(state, row),
                unresolved_gaps=gaps, quality_status="ok" if not gaps else "partial")
            self.store.add_availability(a)
            out.append(a)
        return out

    def exposure_months(self, combination_id, scope):
        """Calendar months of retail exposure — the demand-rate denominator. Counting *calendar
        months available* (not depth-weighted unit-days) keeps 'no availability' from being read
        as 'zero demand': unavailable/unknown/partial months are simply not in the denominator,
        so they never dilute the rate. Depth informs constraint/stockout, not the base rate."""
        total = 0.0
        for a in self.store.availability_for(combination_id, scope):
            if a.available_state in ("available_unsold", "available_sold", "constrained", "stockout"):
                total += 1.0
        return total

    def has_gaps(self, combination_id, scope):
        return any(a.unresolved_gaps for a in self.store.availability_for(combination_id, scope))
