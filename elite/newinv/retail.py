"""Historical retail projection from accepted Business Facts.

Retail count uses accepted facts only. A duplicate source row must not duplicate retail (one
physical unit retails once). Corrections and reversals update current analytical use WITHOUT
erasing history (append-preserving). Cross-store retail is never combined without an approved
aggregation rule — projection is always scoped.
"""
from __future__ import annotations

from ..ids import new_id
from .models import RetailHistory


def _month(date_str):
    return date_str[:7] if date_str and len(date_str) >= 7 else None


class RetailService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def project(self, combination_id, scope, events):
        """Project accepted retail events. Deduplicated by physical unit (or event ref) so a
        duplicate source observation does not double-count retail."""
        seen = set()
        out = []
        for e in events:
            key = e.get("vehicle_unit_id") or e.get("retail_event_ref")
            if key and key in seen:
                continue
            rh = RetailHistory(
                id=new_id("rh"), store_scope=scope, combination_id=combination_id,
                vehicle_unit_id=e.get("vehicle_unit_id"), retail_event_ref=e.get("retail_event_ref"),
                retail_date=e.get("retail_date"), retail_month=_month(e.get("retail_date")),
                model_year=e.get("model_year"), fact_refs=list(e.get("fact_refs", [])),
                arrival_refs=list(e.get("arrival_refs", [])), availability_refs=list(e.get("availability_refs", [])),
                quality_status=e.get("quality_status", "ok"))
            self.store.add_retail(rh)
            if key:
                seen.add(key)
            out.append(rh)
        return out

    def correct(self, retail_id, new_event, scope):
        """Correct a retail projection: a new current record + the original marked superseded
        (history preserved, current analytical use updated)."""
        orig = next((r for r in self.store.retail_for(new_event.get("combination_id"), scope, current_only=False)
                     if r.id == retail_id), None)
        combination_id = new_event.get("combination_id")
        corrected = RetailHistory(
            id=new_id("rh"), store_scope=scope, combination_id=combination_id,
            vehicle_unit_id=new_event.get("vehicle_unit_id"), retail_event_ref=new_event.get("retail_event_ref"),
            retail_date=new_event.get("retail_date"), retail_month=_month(new_event.get("retail_date")),
            model_year=new_event.get("model_year"), fact_refs=list(new_event.get("fact_refs", [])),
            correction_of=retail_id)
        self.store.add_retail(corrected)
        self.store.set_retail_status(retail_id, "superseded")
        return corrected

    def reverse(self, retail_id, combination_id, scope, *, reason=""):
        """Reverse a retail event (e.g. an unwound deal) while preserving its history."""
        rev = RetailHistory(
            id=new_id("rh"), store_scope=scope, combination_id=combination_id, retail_event_ref=f"reversal:{retail_id}",
            quality_status="reversed", status="reversed", correction_of=retail_id)
        self.store.add_retail(rev)
        self.store.set_retail_status(retail_id, "reversed")
        return rev

    def retail_by_month(self, combination_id, scope):
        """Accepted, current retail counts per 'YYYY-MM' — the direct demand evidence."""
        counts = {}
        for r in self.store.retail_for(combination_id, scope, current_only=True):
            if r.status != "current" or not r.retail_month:
                continue
            counts[r.retail_month] = counts.get(r.retail_month, 0) + 1
        return counts
