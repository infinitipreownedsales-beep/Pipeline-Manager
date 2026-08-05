"""Prediction issuance + Decision learning context.

An issued Prediction is immutable: it references accepted facts + all applicable versions, identifies
the state known at issue time, preserves confidence/uncertainty, declares its expected Observation
contract, and never claims certainty about future customer/market/manufacturer/operational behavior. A
correction preserves the original (a new Prediction + a correction record); reissuing under new facts
or versions creates a NEW Prediction. A no-prediction / unresolved result is permitted. Scenario
Predictions stay distinguishable from official Predictions. The Decision learning context never invents
management rationale — absence of recorded rationale stays unknown.
"""
from __future__ import annotations

from ..errors import ValidationError
from ..ids import new_id
from ..policy.calc import output_checksum
from ..policy.models import ReproducibilityPackage
from .models import OBSERVATION_CONTRACT, PREDICTION_TYPES, Prediction


class PredictionService:
    def __init__(self, store, policy_store, clock):
        self.store, self.policy, self.clock = store, policy_store, clock

    def issue(self, *, prediction_type, owning_domain, store_scope, subject_entity_type=None,
              subject_entity_id=None, predicted_payload=None, resolution_status="issued", confidence=None,
              uncertainty=None, unit_contract=None, evidence_classification=None, fact_refs=None,
              source_state_refs=None, policy_versions=None, calculation_version=None, model_version=None,
              identity_rule_version=None, comparison_spec_version=None, comparison_spec_family=None,
              effective_period=None, prediction_horizon=None, org_scope=None, scenario_id=None,
              issuing_actor=None, correction_of=None):
        """Issue an immutable Prediction. `resolution_status='no_prediction'`/`'unresolved'` is allowed
        when evidence is insufficient (payload stays empty, never manufactured)."""
        if prediction_type not in PREDICTION_TYPES:
            raise ValidationError(technical_detail=f"unknown prediction type {prediction_type}")
        if resolution_status in ("no_prediction", "unresolved"):
            predicted_payload = {}
        observation_contract = OBSERVATION_CONTRACT.get(prediction_type)
        checksum = output_checksum({"type": prediction_type, "subject": subject_entity_id,
                                    "payload": predicted_payload or {}, "period": effective_period})
        pkg = self.policy.add_reproducibility(ReproducibilityPackage(
            id=new_id("rep"), refs={"kind": "prediction", "prediction_type": prediction_type,
                                    "calculation_version": calculation_version, "model_version": model_version,
                                    "identity_rule_version": identity_rule_version,
                                    "comparison_specification_version": comparison_spec_version,
                                    "policy_versions": list(policy_versions or []), "fact_refs": list(fact_refs or []),
                                    "scenario": scenario_id},
            calculation_timestamp=self.store._now(), implementation_revision="phase8-prediction",
            output_reference=checksum))
        p = Prediction(
            id=new_id("pred"), prediction_type=prediction_type, owning_domain=owning_domain, store_scope=store_scope,
            subject_entity_type=subject_entity_type, subject_entity_id=subject_entity_id, org_scope=org_scope,
            effective_period=effective_period, prediction_horizon=prediction_horizon,
            predicted_payload=predicted_payload or {}, unit_contract=unit_contract or {}, confidence=confidence,
            uncertainty=uncertainty or {}, evidence_classification=evidence_classification, fact_refs=fact_refs or [],
            source_state_refs=source_state_refs or [], policy_versions=policy_versions or [],
            calculation_version=calculation_version, model_version=model_version,
            identity_rule_version=identity_rule_version, comparison_spec_version=comparison_spec_version,
            comparison_spec_family=comparison_spec_family, observation_contract=observation_contract,
            scenario_id=scenario_id, reproducibility_package=pkg.id, issuing_actor=issuing_actor,
            resolution_status=resolution_status, status=resolution_status, correction_of=correction_of)
        return self.store.add_prediction(p)

    def correct(self, original, *, reason, correcting_actor, new_attrs=None):
        """Preserve the original; issue a corrected Prediction and record the correction lineage."""
        if not reason:
            raise ValidationError(technical_detail="prediction correction requires a reason")
        attrs = dict(prediction_type=original.prediction_type, owning_domain=original.owning_domain,
                     store_scope=original.store_scope, subject_entity_type=original.subject_entity_type,
                     subject_entity_id=original.subject_entity_id, predicted_payload=original.predicted_payload,
                     confidence=original.confidence, uncertainty=original.uncertainty,
                     effective_period=original.effective_period, calculation_version=original.calculation_version,
                     comparison_spec_version=original.comparison_spec_version, policy_versions=original.policy_versions,
                     fact_refs=original.fact_refs, scenario_id=original.scenario_id)
        attrs.update(new_attrs or {})
        corrected = self.issue(correction_of=original.id, issuing_actor=correcting_actor, **attrs)
        self.store.add_prediction_correction(original.id, "correction", replacement_prediction_id=corrected.id,
                                             reason=reason, correcting_actor=correcting_actor)
        return corrected


class DecisionContextService:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def attach(self, *, decision_ref, owning_domain, store_scope, selected_action, subject_entity_type=None,
               subject_entity_id=None, originating_prediction_refs=None, recommendation_refs=None,
               rejected_alternatives=None, decision_maker=None, applicable_facts=None, policies=None,
               calculations=None, confidence=None, uncertainty=None, stated_rationale=None,
               operational_constraints=None, scenario_id=None, execution_expectation=None, decision_time=None):
        """Attach a learning context to an issued Decision. `stated_rationale=None` stays unknown (never
        invented). `rejected_alternatives` may be recorded only when actually presented/considered."""
        return self.store.add_decision_context(
            decision_ref=decision_ref, owning_domain=owning_domain, store_scope=store_scope,
            subject_entity_type=subject_entity_type, subject_entity_id=subject_entity_id,
            originating_prediction_refs=originating_prediction_refs or [],
            recommendation_refs=recommendation_refs or [], selected_action=selected_action,
            rejected_alternatives=rejected_alternatives or [], decision_time=decision_time or self.store._now(),
            decision_maker=decision_maker, applicable_facts=applicable_facts or [], policies=policies or [],
            calculations=calculations or [], confidence=confidence, uncertainty=uncertainty or {},
            stated_rationale=stated_rationale, operational_constraints=operational_constraints or [],
            scenario_id=scenario_id, execution_expectation=execution_expectation)
