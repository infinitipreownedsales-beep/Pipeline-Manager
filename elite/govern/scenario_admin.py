"""Broad Scenario administration + promotion + policy-review requests.

A Scenario stays isolated from official state. Sharing does not imply approval; APPROVED_FOR_DISCUSSION
does not make it official. A promotion request has no direct operational effect and routes to the
correct governed review type: policy → policy-review request; Calibration target → Phase 8 Calibration
governance; operational target → a NEW official Decision from official facts (never a copy of Scenario
state). Scenario correction preserves history; output identifies all overrides and the official
baseline; private access is scoped; a Scenario can never become an Observation; a Scenario Prediction
is excluded from official learning unless explicitly permitted.
"""
from __future__ import annotations

from ..errors import ValidationError
from .models import PROMOTION_TARGETS, SCENARIO_TRANSITIONS


class ScenarioAdminService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def create(self, principal, scope, *, scenario_id, owning_domain, description="", assumptions=None,
               overrides=None, official_baseline_ref=None, expiration=None):
        def business(conn):
            sid = self.store.insert_scenario(conn, scenario_id=scenario_id, owner=principal, owning_domain=owning_domain,
                                             store_scope=scope, description=description, assumptions=assumptions or {},
                                             overrides=overrides or {}, official_baseline_ref=official_baseline_ref,
                                             expiration=expiration, status="DRAFT")
            return (sid, sid), sid
        res = self.gov.perform(principal_id=principal, capability="scenario.create", scope=scope,
                               action="scenario.create", business_fn=business, target_ref=scenario_id)
        return self.store.get_scenario(res["value"][0])

    def _transition(self, principal, scope, sc, to_state, *, capability, action, field_updates=None):
        def business(conn):
            cur = self.store.get_scenario(sc["id"])
            if to_state not in SCENARIO_TRANSITIONS.get(cur["status"], set()):
                raise ValidationError(technical_detail=f"illegal scenario transition {cur['status']}->{to_state}")
            sets = {"status": to_state}
            if field_updates:
                sets.update(field_updates(cur))
            rc = self.store.set_scenario(conn, sc["id"], sc["version"], **sets)
            if rc == 0:
                from ..errors import ConcurrencyError
                raise ConcurrencyError(technical_detail="scenario stale")
            return (sc["id"], sc["id"]), sc["id"]
        self.gov.perform(principal_id=principal, capability=capability, scope=scope, action=action,
                         business_fn=business, target_ref=sc["id"])
        return self.store.get_scenario(sc["id"])

    def share(self, principal, scope, sc, *, shared_with, note=""):
        self.store.add_scenario_share(sc["id"], shared_by=principal, shared_with=shared_with, scope=scope, note=note)
        return self._transition(principal, scope, sc, "SHARED", capability="scenario.share", action="scenario.share")

    def begin_review(self, principal, scope, sc):
        return self._transition(principal, scope, sc, "UNDER_REVIEW", capability="scenario.review",
                                action="scenario.begin_review")

    def expire(self, principal, scope, sc):
        return self._transition(principal, scope, sc, "EXPIRED", capability="scenario.review",
                                action="scenario.expire")

    def review(self, principal, scope, sc, *, outcome="approved_for_discussion", comment=""):
        self.store.add_scenario_review(sc["id"], reviewer=principal, outcome=outcome, comment=comment)
        to = "APPROVED_FOR_DISCUSSION" if outcome == "approved_for_discussion" else "REJECTED"
        cur = self.store.get_scenario(sc["id"])
        if cur["status"] not in ("SHARED", "UNDER_REVIEW", "READY"):
            return cur
        if cur["status"] != "UNDER_REVIEW":
            cur = self._transition(principal, scope, cur, "UNDER_REVIEW", capability="scenario.review",
                                   action="scenario.review")
        return self._transition(principal, scope, cur, to, capability="scenario.review", action="scenario.review")

    def correct(self, principal, scope, sc, *, reason, new_overrides=None):
        corrected = self.create(principal, scope, scenario_id=sc["scenario_id"], owning_domain=sc["owning_domain"],
                                description=f"correction: {reason}", overrides=new_overrides or {},
                                official_baseline_ref=sc["official_baseline_ref"])
        self.store.set_scenario_now(sc["id"], sc["version"], status="CORRECTED", superseded_by=corrected["id"])
        self.store.set_scenario_now(corrected["id"], corrected["version"], correction_of=sc["id"])
        return self.store.get_scenario(corrected["id"])

    def request_promotion(self, principal, scope, sc, *, target_type, evidence=None, limitations=None):
        """A promotion request has NO direct operational effect; it routes to the governed review type."""
        if target_type not in PROMOTION_TARGETS:
            raise ValidationError(technical_detail=f"unknown promotion target {target_type}")
        routed = PROMOTION_TARGETS[target_type]

        def business(conn):
            review_ref = None
            if routed == "policy_review":
                review_ref = self.store.add_policy_review_request(conn, source_type="scenario_promotion",
                                                                  source_ref=sc["id"], requested_by=principal,
                                                                  rationale=f"promote {target_type}")
            pid = self.store.insert_promotion(conn, sc["id"], target_type, requested_by=principal, routed_to=routed,
                                              review_ref=review_ref, evidence=evidence or {},
                                              limitations=limitations or {}, status="requested")
            to = "POLICY_REVIEW_REQUESTED" if routed == "policy_review" else "PROMOTION_REQUESTED"
            self.store.set_scenario(conn, sc["id"], sc["version"], status=to)
            return (pid, pid), pid
        cap = "scenario.policy_review_request" if routed == "policy_review" else "scenario.promote"
        res = self.gov.perform(principal_id=principal, capability=cap, scope=scope, action="scenario.promote",
                               business_fn=business, target_ref=sc["id"])
        return self.store.get_promotion(res["value"][0])

    def reject_promotion(self, principal, scope, promotion, *, reason=""):
        with self.store.conn:
            self.store.set_promotion(self.store.conn, promotion["id"], promotion["version"], status="rejected",
                                     rejection_reason=reason or "rejected")
        return self.store.get_promotion(promotion["id"])

    def scenario_can_become_observation(self):
        return False   # a Scenario can never become an actual Observation (see Phase 8 observation.accept)
