"""Authoritative governed Decision issuance + dispositions.

A Decision references the exact recommendation reviewed, preserves the state known at Decision time,
keeps missing rationale unknown, and never invents unpresented alternatives. Issuance is idempotent,
writes its Audit Event atomically (audit failure rolls it back), and rejects a stale/superseded
recommendation unless an explicit OVERRIDE authority + reason is supplied. Scenario Decisions stay
Scenario-only; a private Scenario output can never become official Decision truth. Correction preserves
the original Decision; supersession links the newer Decision to the prior; cancellation preserves
history. Recommendation ≠ Decision — issuing a Decision never rewrites the recommendation.
"""
from __future__ import annotations

from ..errors import ConcurrencyError, ValidationError
from .models import DISPOSITIONS

_WORKSPACE_STATE = {
    "ACCEPT": "DECIDED", "REJECT": "REJECTED", "DEFER": "DEFERRED",
    "REQUEST_INFORMATION": "AWAITING_INFORMATION", "NO_ACTION": "DECIDED", "OVERRIDE": "DECIDED",
    "CANCEL": "CANCELLED", "CORRECT": "CORRECTED", "SUPERSEDE": "SUPERSEDED",
}


class DecisionService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def issue(self, principal, scope, item, *, disposition, selected_action=None, decision_type=None,
              rationale=None, presented_alternatives=None, selected_alternative=None, confidence_ack=None,
              uncertainty_ack=None, operational_constraints=None, expiration=None, facts=None, versions=None,
              override_reason=None, correlation_id=None, idempotency_key=None, as_official=False):
        if disposition not in DISPOSITIONS:
            raise ValidationError(technical_detail=f"unknown disposition {disposition}")
        if bool(item["stale"]) and disposition != "OVERRIDE":
            raise ValidationError(message="This recommendation is stale; renew review or override.",
                                  technical_detail="stale recommendation cannot be decided without override")
        if disposition == "OVERRIDE" and not override_reason:
            raise ValidationError(technical_detail="override requires a reason")
        if as_official and item["scenario_id"]:
            raise ValidationError(message="A private Scenario output cannot be an official Decision.",
                                  technical_detail="scenario recommendation cannot become official truth")
        cap = "decision.override" if disposition == "OVERRIDE" else "decision.issue"

        def business(conn):
            did = self.store.insert_decision(
                conn, workspace_item_id=item["id"], owning_domain=item["owning_domain"],
                subject_entity_type=item["subject_entity_type"], subject_entity_id=item["subject_entity_id"],
                store_scope=scope, decision_type=decision_type, disposition=disposition,
                selected_action=selected_action, selected_alternative=selected_alternative, decision_maker=principal,
                rationale=rationale, confidence_ack=confidence_ack, uncertainty_ack=uncertainty_ack,
                operational_constraints=operational_constraints or [], source_recommendation_ref=item["recommendation_ref"],
                recommendation_revision=str(item["version"]), facts=facts or [], versions=versions or {},
                scenario_id=item["scenario_id"], expiration=expiration, idempotency_key=idempotency_key,
                correlation_id=correlation_id, override=(1 if disposition == "OVERRIDE" else 0),
                override_reason=override_reason)
            for alt in (presented_alternatives or []):
                self.store.add_alternative(conn, did, alt, presented=True)
            rc = self.store.set_workspace_item(conn, item["id"], item["version"],
                                               workspace_state=_WORKSPACE_STATE[disposition], decision_ref=did)
            if rc == 0:
                raise ConcurrencyError(technical_detail="workspace item stale")
            return (did, did), did
        res = self.gov.perform(principal_id=principal, capability=cap, scope=scope, action="decision.issue",
                               business_fn=business, target_ref=item["id"], correlation_id=correlation_id,
                               idempotency_key=idempotency_key)
        if res.get("replayed"):
            return {"decision": self.store.get_decision(res["result_ref"]), "replayed": True}
        return {"decision": self.store.get_decision(res["value"][0]), "replayed": False,
                "audit_id": res.get("audit_id")}

    def correct(self, principal, scope, prior, *, reason, new_action=None):
        if not reason:
            raise ValidationError(technical_detail="decision correction requires a reason")

        def business(conn):
            did = self.store.insert_decision(
                conn, workspace_item_id=prior["workspace_item_id"], owning_domain=prior["owning_domain"],
                subject_entity_type=prior["subject_entity_type"], subject_entity_id=prior["subject_entity_id"],
                store_scope=scope, decision_type=prior["decision_type"], disposition="CORRECT",
                selected_action=new_action or prior["selected_action"], decision_maker=principal, rationale=reason,
                source_recommendation_ref=prior["source_recommendation_ref"], scenario_id=prior["scenario_id"],
                correction_of=prior["id"])
            return (did, did), did
        res = self.gov.perform(principal_id=principal, capability="decision.correct", scope=scope,
                               action="decision.correct", business_fn=business, target_ref=prior["id"])
        return self.store.get_decision(res["value"][0])

    def supersede(self, principal, scope, prior, *, reason, new_action=None):
        def business(conn):
            did = self.store.insert_decision(
                conn, workspace_item_id=prior["workspace_item_id"], owning_domain=prior["owning_domain"],
                subject_entity_type=prior["subject_entity_type"], subject_entity_id=prior["subject_entity_id"],
                store_scope=scope, decision_type=prior["decision_type"], disposition="SUPERSEDE",
                selected_action=new_action or prior["selected_action"], decision_maker=principal, rationale=reason,
                source_recommendation_ref=prior["source_recommendation_ref"], scenario_id=prior["scenario_id"],
                supersedes=prior["id"])
            return (did, did), did
        res = self.gov.perform(principal_id=principal, capability="decision.supersede", scope=scope,
                               action="decision.supersede", business_fn=business, target_ref=prior["id"])
        return self.store.get_decision(res["value"][0])
