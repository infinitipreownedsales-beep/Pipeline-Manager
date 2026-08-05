"""Separation-of-duties administration.

Versioned/policy-resolved rules (proposer≠approver, approver≠executor, executor≠completer, Calibration
proposer≠activator, policy proposer≠approver, correction actor differs, self-approval prohibited above a
materiality threshold). Conflicts are checked below the UI. A missing required separation rule may
produce UNRESOLVED governance rather than permissive behavior. An authorized override needs an explicit
capability + reason + Audit Event and stays visible.
"""
from __future__ import annotations

from ..errors import AuthorizationError, ValidationError


class SeparationOfDutiesService:
    def __init__(self, store, gov, clock):
        self.store, self.gov, self.clock = store, gov, clock

    def check(self, *, rule_type, actor_a, actor_b, decision_ref=None, materiality=None, require_rule=False):
        """Return (ok, conflict). A conflict means the same actor performed both sides of a separated
        pair. When `require_rule` and no active rule exists, governance is UNRESOLVED (not permissive)."""
        rules = self.store.sod_rules(rule_type=rule_type)
        if not rules:
            if require_rule:
                raise ValidationError(message="Required separation-of-duties rule is missing.",
                                      technical_detail=f"no active rule for {rule_type} (governance unresolved)")
            return True, False
        rule = rules[0]
        if rule_type == "self_approval_prohibited_above_materiality":
            threshold = rule["materiality_threshold"]
            conflict = (actor_a == actor_b) and (threshold is None or (materiality is not None and
                                                                       float(materiality) >= float(threshold)))
        else:
            conflict = actor_a is not None and actor_a == actor_b
        return (not conflict), conflict

    def enforce(self, principal, scope, *, rule_type, actor_a, actor_b, decision_ref=None, materiality=None,
                require_rule=False):
        """Raise on a separation conflict; record nothing when clean. A conflict is a hard block unless
        overridden (see `override`)."""
        ok, conflict = self.check(rule_type=rule_type, actor_a=actor_a, actor_b=actor_b, decision_ref=decision_ref,
                                  materiality=materiality, require_rule=require_rule)
        if conflict:
            self.store.add_sod_exception(rule_id=(self.store.sod_rules(rule_type=rule_type)[0]["id"]),
                                         decision_ref=decision_ref, actor_a=actor_a, actor_b=actor_b,
                                         detail=f"{rule_type} conflict", override=0)
            raise AuthorizationError(message="Separation of duties prohibits this action.",
                                     technical_detail=f"{rule_type}: {actor_a} == {actor_b}")
        return True

    def override(self, principal, scope, *, rule_type, actor_a, actor_b, reason, decision_ref=None):
        """An authorized override requires the explicit capability + reason and remains visible + audited."""
        if not reason:
            raise ValidationError(technical_detail="separation override requires a reason")

        def business(conn):
            eid = self.store.insert_sod_exception(conn, rule_id=None, decision_ref=decision_ref, actor_a=actor_a,
                                                  actor_b=actor_b, detail=f"{rule_type} override", override=1,
                                                  override_principal=principal, override_reason=reason)
            return (eid, eid), eid
        res = self.gov.perform(principal_id=principal, capability="authority.override_separation", scope=scope,
                               action="authority.override_separation", business_fn=business, target_ref=decision_ref)
        return res["value"][0]
