"""Deterministic Prediction-to-Observation Pairing.

Pairing runs only under an ACTIVE, applicable Comparison Specification and preserves subject identity,
timing, units, scope, and semantic compatibility. It is idempotent (replaying the same Prediction +
Observation + Comparison version returns the existing Pairing), never mutates the Prediction or
Observation, may remain pending until the observation window closes, and follows the late-observation
contract afterward. Ambiguous matches remain unresolved. An identity correction may create a new
Pairing while preserving the prior one. Aggregation (one Prediction, many Observations) is permitted
only when the Comparison Specification explicitly allows it.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from .models import Pairing


def _unit(contract):
    return (contract or {}).get("unit")


class PairingService:
    def __init__(self, store, comparison, clock):
        self.store, self.comparison, self.clock = store, comparison, clock

    def _gate(self, prediction, spec):
        if spec is None or spec.status != "active":
            raise ValidationError(message="Pairing requires an active Comparison Specification.",
                                  technical_detail="inactive comparison specification cannot pair")
        if spec.prediction_type != prediction.prediction_type:
            raise ValidationError(message="Prediction type does not match the Comparison Specification.",
                                  technical_detail="prediction type mismatch")

    def _classify(self, prediction, observation, spec, *, window_open, observed_late, within_tolerance,
                  ambiguous, conflicting):
        if observation is None:
            return "PENDING_OBSERVATION", None, "waiting for observation (window open)" if window_open else \
                "waiting for observation"
        if observation.observation_type != spec.observation_type:
            raise ValidationError(message="Observation type does not match the Comparison Specification.",
                                  technical_detail="observation type mismatch")
        if observation.subject_entity_id != prediction.subject_entity_id:
            return "IDENTITY_MISMATCH", False, "subject identity mismatch"
        if observation.store_scope != prediction.store_scope:
            return "SCOPE_MISMATCH", False, "store/scope mismatch"
        pu, ou = _unit(prediction.unit_contract), _unit(observation.unit_contract)
        if pu and ou and pu != ou:
            return "UNIT_MISMATCH", False, f"unit mismatch {pu} vs {ou}"
        if ambiguous:
            return "AMBIGUOUS", None, "multiple candidate observations; unresolved"
        if conflicting:
            return "CONFLICTING", None, "conflicting observation evidence"
        if observed_late and not within_tolerance:
            return "OUTSIDE_WINDOW", None, "observation beyond lateness tolerance"
        if observed_late and within_tolerance:
            return "LATE_PAIRED", True, "paired late within tolerance"
        if observation.observed_payload is None or observation.completeness in ("partial", "missing"):
            return "PARTIAL", None, f"partial observation ({observation.completeness})"
        return "PAIRED", True, "exact match"

    def pair(self, prediction, observation, spec, *, window_open=False, observed_late=False,
             within_tolerance=True, ambiguous=False, conflicting=False, rule_or_principal="auto",
             correction_of=None):
        self._gate(prediction, spec)
        key = f"{prediction.id}:{observation.id if observation else 'none'}:{spec.version}"
        if correction_of is None:
            existing = self.store.pairing_by_idempotency(key)
            if existing is not None:
                return existing                                    # idempotent replay — no duplicate
        else:
            key = f"{key}:corr:{new_id('k')}"                      # a correction is a NEW pairing
        status, unit_ok, reason = self._classify(
            prediction, observation, spec, window_open=window_open, observed_late=observed_late,
            within_tolerance=within_tolerance, ambiguous=ambiguous, conflicting=conflicting)
        completeness = "complete" if status in ("PAIRED", "LATE_PAIRED") else \
            ("partial" if status == "PARTIAL" else "pending" if status == "PENDING_OBSERVATION" else "unresolved")
        confidence = "high" if status == "PAIRED" else "medium" if status == "LATE_PAIRED" else "low"
        p = Pairing(
            id=new_id("pair"), prediction_id=prediction.id, comparison_spec_version=spec.version,
            pairing_status=status, observation_id=(observation.id if observation else None),
            subject_entity_type=prediction.subject_entity_type, subject_entity_id=prediction.subject_entity_id,
            store_scope=prediction.store_scope, matching_evidence={"keys": spec.matching_keys, "reason": reason},
            timing_relationship=("late" if observed_late else "in_window"), unit_compatible=unit_ok,
            completeness=completeness, confidence=confidence,
            paired_time=(self.store._now() if status in ("PAIRED", "LATE_PAIRED", "PARTIAL") else None),
            rule_or_principal=rule_or_principal, correction_of=correction_of, reason=reason, idempotency_key=key)
        return self.store.add_pairing(p)

    def pair_aggregate(self, prediction, observations, spec, **kw):
        """One Prediction over multiple Observations — only if the spec explicitly permits aggregation."""
        if not spec.aggregation_rules.get("allow"):
            raise ValidationError(message="This Comparison Specification does not permit aggregation.",
                                  technical_detail="aggregation not permitted by comparison specification")
        return [self.pair(prediction, o, spec, **kw) for o in observations]

    def supersede(self, pairing, new_pairing):
        self.store.set_pairing(pairing.id, pairing.version, pairing_status="SUPERSEDED",
                               superseded_by=new_pairing.id)
        return new_pairing
