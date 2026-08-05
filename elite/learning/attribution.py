"""Attribution — an evidence-based explanation layer over an Error.

Attribution identifies supporting AND contradicting evidence and distinguishes hypothesis from fact. A
single outcome may have multiple contributing factors; weights/shares are avoided so no false precision
is implied. Unrecorded customer intent / Dealer Trade attempts stay UNKNOWN. A stockout may support a
constrained-demand Attribution but never an exact missed-sales quantity. Operational failure may
explain an outcome without rewriting the original Prediction. Human review preserves the original
automated proposal; corrections preserve history.
"""
from __future__ import annotations

from ..errors import ValidationError
from .models import ATTRIBUTION_CATEGORIES, ATTRIBUTION_STATUSES

# Categories whose Attribution must never assert an exact quantified missed outcome.
_NO_EXACT_QUANTITY = {"stockout", "availability_constraint", "market_or_customer_factor", "unknown"}


class AttributionService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def propose(self, error_id, *, factor_category, proposed_factor, subject_entity_id=None, confidence="low",
                evidence_strength="weak", source="automated"):
        if factor_category not in ATTRIBUTION_CATEGORIES:
            raise ValidationError(technical_detail=f"unknown attribution category {factor_category}")
        return self.store.add_attribution(error_id, proposed_factor=proposed_factor, factor_category=factor_category,
                                          subject_entity_id=subject_entity_id, confidence=confidence,
                                          evidence_strength=evidence_strength, status="PROPOSED", source=source)

    def add_evidence(self, attribution_id, *, evidence_kind, supports, description="", fact_refs=None):
        """Record supporting (supports=True) or contradicting (supports=False) evidence. Contradicting
        evidence stays visible; it does not delete the proposal."""
        return self.store.add_attribution_evidence(attribution_id, evidence_kind=evidence_kind, supports=supports,
                                                   description=description, fact_refs=fact_refs)

    def assess(self, attribution):
        """Move status from the recorded evidence: with supporting evidence and no contradiction ->
        SUPPORTED; mixed -> PARTIALLY_SUPPORTED; only contradiction -> CONTRADICTED; none -> stays
        PROPOSED. Never asserts causation, only evidential support."""
        ev = self.store.evidence_for_attribution(attribution["id"])
        supports = [e for e in ev if e["supports"]]
        against = [e for e in ev if not e["supports"]]
        if not ev:
            status = "PROPOSED"
        elif supports and against:
            status = "PARTIALLY_SUPPORTED"
        elif supports:
            status = "SUPPORTED"
        else:
            status = "CONTRADICTED"
        strength = "strong" if len(supports) >= 2 and not against else "moderate" if supports else "weak"
        self.store.set_attribution(attribution["id"], attribution["version"], status=status,
                                   evidence_strength=strength)
        return self.store.get_attribution(attribution["id"])

    def human_review(self, attribution, reviewer, *, outcome, notes=""):
        """Human-reviewed Attribution preserves the original automated proposal (a new review row +
        a NEW attribution referencing the original, never an in-place overwrite of the proposal text)."""
        if outcome not in ATTRIBUTION_STATUSES:
            raise ValidationError(technical_detail=f"unknown attribution status {outcome}")
        self.store.add_attribution_review(attribution["id"], reviewer, outcome, preserves_automated=True, notes=notes)
        reviewed = self.store.add_attribution(
            attribution["error_id"], proposed_factor=attribution["proposed_factor"],
            factor_category=attribution["factor_category"], subject_entity_id=attribution["subject_entity_id"],
            confidence=attribution["confidence"], evidence_strength=attribution["evidence_strength"], status=outcome,
            source="human", correction_of=attribution["id"])
        self.store.set_attribution(attribution["id"], attribution["version"], reviewing_principal=reviewer,
                                   review_time=self.store._now())
        return reviewed
