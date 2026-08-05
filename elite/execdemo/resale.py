"""Executive Demo resale + outcome foundations.

Foundational references only (designation, activation, expected lifecycle, retirement, return path,
Used Cars receipt, resale/New-Retail event, actual value where authorized) — enough for Phase 8 to
pair Executive Demo Predictions and Observations. No Prediction/Observation Pairing or Learning here.
"""
from __future__ import annotations


class ResaleService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def record_reference(self, unit, **kw):
        return self.store.add_resale_reference(unit.id, **kw)
