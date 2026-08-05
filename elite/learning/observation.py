"""Observation acceptance.

An accepted Observation represents what actually occurred (never a restatement of the Prediction). It
uses accepted Business Facts, may remain incomplete, keeps observation-time and recorded-time distinct,
identifies quality + completeness, and preserves prior-as-known history under correction or reversal.
Missing Observation stays missing (never zero); conflicting facts yield a conflicting/unresolved
Observation; scenario output can never become an actual Observation.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from .models import OBSERVATION_TYPES, Observation


class ObservationService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def accept(self, *, observation_type, owning_domain, store_scope, subject_entity_type=None,
               subject_entity_id=None, observed_period=None, observed_payload=None, unit_contract=None,
               fact_refs=None, source_observation_refs=None, accepted_time=None, quality="ok",
               confidence="medium", completeness="complete", resolution_status="accepted", provenance=None,
               is_scenario_output=False, correction_of=None):
        """Accept an Observation from accepted Business Facts. `observed_payload=None` means MISSING
        (not zero). Scenario output cannot be accepted as an actual Observation."""
        if observation_type not in OBSERVATION_TYPES:
            raise ValidationError(technical_detail=f"unknown observation type {observation_type}")
        if is_scenario_output:
            raise ValidationError(message="Scenario output cannot be accepted as an actual Observation.",
                                  technical_detail="scenario output is not an actual fact")
        if observed_payload is None and resolution_status == "accepted":
            resolution_status, completeness = "incomplete", "missing"
        o = Observation(
            id=new_id("obs"), observation_type=observation_type, owning_domain=owning_domain, store_scope=store_scope,
            subject_entity_type=subject_entity_type, subject_entity_id=subject_entity_id, observed_period=observed_period,
            observed_payload=observed_payload, unit_contract=unit_contract or {}, fact_refs=fact_refs or [],
            source_observation_refs=source_observation_refs or [], accepted_time=accepted_time or self.store._now(),
            quality=quality, confidence=confidence, completeness=completeness, resolution_status=resolution_status,
            status=resolution_status, provenance=provenance or {}, correction_of=correction_of)
        return self.store.add_observation(o)

    def correct(self, original, *, reason, correcting_actor, new_payload=None, quality=None):
        """Preserve the original; accept a corrected Observation and record prior-as-known lineage."""
        if not reason:
            raise ValidationError(technical_detail="observation correction requires a reason")
        corrected = self.accept(
            observation_type=original.observation_type, owning_domain=original.owning_domain,
            store_scope=original.store_scope, subject_entity_type=original.subject_entity_type,
            subject_entity_id=original.subject_entity_id, observed_period=original.observed_period,
            observed_payload=(original.observed_payload if new_payload is None else new_payload),
            unit_contract=original.unit_contract, quality=quality or original.quality, correction_of=original.id)
        self.store.add_observation_correction(original.id, "correction", replacement_observation_id=corrected.id,
                                              reason=reason, correcting_actor=correcting_actor,
                                              prior_as_known=(original.observed_payload or {}))
        return corrected

    def reverse(self, original, *, reason, correcting_actor):
        """Reversal preserves the original Observation and negates its current analytical effect."""
        if not reason:
            raise ValidationError(technical_detail="observation reversal requires a reason")
        self.store.add_observation_correction(original.id, "reversal", negates_effect=True, reason=reason,
                                              correcting_actor=correcting_actor,
                                              prior_as_known=(original.observed_payload or {}))
        return original
