"""Executable versioned Comparison Specification.

Extends the Phase 3 Comparison Specification registry (`registry_ref`) into a runtime contract with
scope/matching/timing/window/unit/transformation/aggregation rules and explicit partial / conflicting
/ missing / late behavior + error semantics. A Comparison Specification must be ACTIVE and applicable
before Pairing; changing comparison behavior requires a NEW version (historical Pairings retain the
version they used). The Comparison Specification never itself alters domain behavior.
"""
from __future__ import annotations

from ..ids import new_id
from .models import ComparisonSpecRuntime


class ComparisonService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def register(self, *, version, prediction_type, observation_type, subject_entity_type=None, registry_ref=None,
                 scope_rules=None, matching_keys=None, timing_rules=None, observation_window=None,
                 lateness_tolerance=None, unit_contract=None, transformation_rules=None, aggregation_rules=None,
                 partial_behavior="partial_error", conflicting_behavior="unresolved", missing_behavior="pending",
                 error_semantics="signed_numeric", directionality="over_under", materiality_threshold_ref=None,
                 confidence_rules=None, status="registered", effective_start=None, supersedes=None):
        c = ComparisonSpecRuntime(
            id=new_id("csr"), version=version, prediction_type=prediction_type, observation_type=observation_type,
            subject_entity_type=subject_entity_type, registry_ref=registry_ref, scope_rules=scope_rules or {},
            matching_keys=matching_keys or ["subject_entity_id", "period"], timing_rules=timing_rules or {},
            observation_window=observation_window or {}, lateness_tolerance=lateness_tolerance or {},
            unit_contract=unit_contract or {}, transformation_rules=transformation_rules or {},
            aggregation_rules=aggregation_rules or {}, partial_behavior=partial_behavior,
            conflicting_behavior=conflicting_behavior, missing_behavior=missing_behavior,
            error_semantics=error_semantics, directionality=directionality,
            materiality_threshold_ref=materiality_threshold_ref, confidence_rules=confidence_rules or {},
            status=status, effective_start=effective_start, supersedes=supersedes)
        return self.store.add_comparison_spec(c)

    def approve(self, spec_id):
        return self.store.set_comparison_spec_status(spec_id, "active")

    def supersede(self, old_id, *, new_spec):
        """Register a new version and mark the old one superseded (behavior change => new version)."""
        self.store.set_comparison_spec_status(old_id, "superseded", superseded_by=new_spec.id)
        return new_spec

    def applicable(self, spec, prediction, observation=None):
        """Return (ok, reason). A spec must be active and match the prediction's type/subject before use."""
        if spec is None:
            return False, "no comparison specification"
        if spec.status != "active":
            return False, "comparison specification not active"
        if spec.prediction_type != prediction.prediction_type:
            return False, "prediction type mismatch"
        if observation is not None and spec.observation_type != observation.observation_type:
            return False, "observation type mismatch"
        return True, "applicable"
