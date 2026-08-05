"""Service Loaner resale + outcome foundations.

Foundational references only: retirement recommendation, actual retirement, Used Cars receipt,
resale event/timing/value, and predicted-vs-actual exit result. Enough references are preserved for
Phase 8 to pair future Service Loaner Predictions and Observations. Full Prediction/Observation
Pairing and Learning are NOT implemented here.
"""
from __future__ import annotations


class ResaleService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def record_reference(self, unit, *, retirement_event_ref=None, used_cars_receipt_ref=None,
                         resale_event_ref=None, resale_timing=None, resale_value=None, predicted_ref=None,
                         observed_ref=None):
        return self.store.add_resale_reference(
            unit.id, retirement_event_ref=retirement_event_ref, used_cars_receipt_ref=used_cars_receipt_ref,
            resale_event_ref=resale_event_ref, resale_timing=resale_timing, resale_value=resale_value,
            predicted_ref=predicted_ref, observed_ref=observed_ref)
