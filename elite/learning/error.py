"""Versioned Error, derived ONLY from a valid Pairing.

Error semantics come from the Comparison Specification. Units must be compatible; percentage error is
skipped for an invalid/meaningless denominator; zero predicted/actual follow explicit semantics;
missing Observation yields pending/unresolved (never a fabricated error); a partial Observation yields
only the permitted partial Error. The materiality threshold resolves through policy. Error preserves
the Comparison + Calculation Versions and a reproducibility package. Error does NOT establish
causation. A corrected Observation produces a corrected/superseding Error without deleting history.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import PredictionError

_VALID_FOR_ERROR = {"PAIRED", "LATE_PAIRED", "PARTIAL"}
_PENDING = {"PENDING_OBSERVATION"}


def _num(payload):
    if not isinstance(payload, dict):
        return None
    v = payload.get("value")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ErrorService:
    def __init__(self, store, policy_store, clock, calc_version):
        self.store, self.policy, self.clock, self.calc_version = store, policy_store, clock, calc_version

    def compute(self, pairing, prediction, observation, spec, *, materiality_threshold=None,
                materiality_policy_version=None):
        """Compute an Error from a valid Pairing. Returns the stored Error record."""
        if pairing.pairing_status not in _VALID_FOR_ERROR | _PENDING:
            raise ValidationError(message="Error requires a valid Pairing.",
                                  technical_detail=f"pairing status {pairing.pairing_status} cannot yield an error")

        if pairing.pairing_status in _PENDING or observation is None or observation.observed_payload is None:
            return self._store(pairing, prediction, observation, spec, resolution_status="pending",
                               classification="pending_observation")

        expected, actual = _num(prediction.predicted_payload), _num(observation.observed_payload)
        if pairing.unit_compatible is False:
            raise ValidationError(technical_detail="cannot compute error for incompatible units")
        if expected is None or actual is None:
            return self._store(pairing, prediction, observation, spec, resolution_status="unresolved",
                               classification="non_numeric", expected=expected, actual=actual)

        signed = round(actual - expected, 6)
        absolute = round(abs(signed), 6)
        # Percentage error only when the denominator is valid + semantically meaningful.
        percentage = None if expected == 0 else round(signed / expected * 100.0, 6)
        classification = "over" if signed > 0 else "under" if signed < 0 else "exact"
        partial = pairing.pairing_status == "PARTIAL"
        materiality = self._materiality(absolute, materiality_threshold)
        return self._store(pairing, prediction, observation, spec, resolution_status=("partial" if partial else
                           "calculated"), expected=expected, actual=actual, signed=signed, absolute=absolute,
                           percentage=percentage, classification=classification, materiality=materiality,
                           materiality_policy_version=materiality_policy_version, timing_error=self._timing(pairing))

    @staticmethod
    def _materiality(absolute, threshold):
        if threshold is None:
            return "unresolved"
        return "material" if absolute >= float(threshold) else "immaterial"

    @staticmethod
    def _timing(pairing):
        return "late" if pairing.timing_relationship == "late" else None

    def _store(self, pairing, prediction, observation, spec, *, resolution_status, expected=None, actual=None,
               signed=None, absolute=None, percentage=None, classification=None, materiality="unresolved",
               materiality_policy_version=None, timing_error=None, correction_of=None):
        checksum = output_checksum({"pairing": pairing.id, "expected": expected, "actual": actual,
                                    "signed": signed, "spec": spec.version})
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "prediction_error", "pairing": pairing.id,
                                    "comparison_specification_version": spec.version,
                                    "calculation_version": self.calc_version,
                                    "materiality_policy_version": materiality_policy_version,
                                    "expected": expected, "actual": actual, "signed": signed},
            calculation_timestamp=self.store._now(), implementation_revision="phase8-error",
            output_reference=checksum))
        e = PredictionError(
            id=new_id("err"), pairing_id=pairing.id, prediction_id=prediction.id,
            observation_id=(observation.id if observation else None), comparison_spec_version=spec.version,
            expected_value=(None if expected is None else str(expected)),
            actual_value=(None if actual is None else str(actual)),
            signed_error=(None if signed is None else str(signed)),
            absolute_error=(None if absolute is None else str(absolute)),
            percentage_error=(None if percentage is None else str(percentage)),
            timing_error=timing_error, classification=classification, materiality=materiality,
            confidence=(pairing.confidence or "low"), resolution_status=resolution_status,
            calculation_version=self.calc_version, reproducibility_package=pkg.id, correction_of=correction_of)
        return self.store.add_error(e)

    def recompute_for_corrected_observation(self, prior_error, pairing, prediction, corrected_observation, spec,
                                            **kw):
        """A corrected Observation creates a superseding Error and preserves the prior (item 35)."""
        new_err = self.compute(pairing, prediction, corrected_observation, spec, **kw)
        self.store.add_error_correction(prior_error.id, "superseded", replacement_error_id=new_err.id,
                                        reason="observation corrected")
        return new_err
