"""Governed Calibration — Learning may PROPOSE change but never activates it.

A Calibration Proposal recommends a versioned change; it has no operational effect. Validation is
required before approval for a material behavior change; approval and activation are distinct;
future-effective Calibration stays scheduled. Activation creates or references a NEW approved version
(Calculation/Model/Comparison/… or a policy-REVIEW recommendation) — it never rewrites prior
Predictions, and never silently mutates active manufacturer/dealership policy, permissions, or facts.
Rollback restores an approved prior version prospectively and preserves history. Rejected/withdrawn
Calibration has no operational effect. No approved Calibration means no operational change. Every
transition authorizes below the UI and binds an Audit Event atomically; proposal/validation/approval/
activation/rollback authorities may be separated.
"""
from __future__ import annotations

from ..errors import ConcurrencyError, ValidationError
from ..ids import new_id
from ..policy.models import CalculationVersion, ModelVersion
from .models import CALIBRATION_TRANSITIONS, CALIBRATION_TARGETS, MATERIAL_TARGETS, ComparisonSpecRuntime


class CalibrationService:
    def __init__(self, store, policy_store, gov, clock):
        self.store, self.policy, self.gov, self.clock = store, policy_store, gov, clock

    # ---- proposal (Learning may only propose) -----------------------------
    def propose(self, principal, scope, *, target_type, target_family=None, current_version=None,
                proposed_change=None, affected_domains=None, learning_signal_refs=None, expected_benefit=None,
                known_risks=None, proposed_effective_period=None, rollback_plan=None,
                policy_review_recommendation=None):
        if target_type not in CALIBRATION_TARGETS:
            raise ValidationError(technical_detail=f"unknown calibration target {target_type}")

        def business(conn):
            cid = self.store.insert_calibration(
                conn, target_type=target_type, target_family=target_family, current_version=current_version,
                proposed_change=proposed_change or {}, affected_domains=affected_domains or [],
                expected_benefit=expected_benefit or {}, known_risks=known_risks or [],
                proposed_effective_period=proposed_effective_period, rollback_plan=rollback_plan or {},
                proposer=principal, review_state="PROPOSED",
                policy_review_recommendation=policy_review_recommendation)
            self.store.insert_calibration_transition(conn, cid, "DRAFT", "PROPOSED", actor=principal,
                                                     action="calibration.propose")
            return (cid, cid), cid
        res = self.gov.perform(principal_id=principal, capability="calibration.propose", scope=scope,
                               action="calibration.propose", business_fn=business, target_ref="calibration")
        cid = res["value"][0]
        for ref in (learning_signal_refs or []):
            self.store.add_calibration_evidence(cid, evidence_kind="learning_signal", learning_signal_ref=ref)
        return self.store.get_calibration(cid)

    def _transition(self, principal, scope, cal, to_state, *, capability, action, effect=None, guard=None,
                    field_updates=None, idempotency_key=None):
        def business(conn):
            cur = self.store.get_calibration(cal["id"])
            if cur is None:
                raise ValidationError(technical_detail="calibration proposal not found")
            frm = cur["review_state"]
            if to_state not in CALIBRATION_TRANSITIONS.get(frm, set()):
                raise ValidationError(message="That Calibration change is not allowed.",
                                      technical_detail=f"illegal transition {frm}->{to_state}")
            if guard:
                guard(cur)
            sets = {"review_state": to_state}
            if field_updates:
                sets.update(field_updates(cur))
            rc = self.store.set_calibration(conn, cal["id"], cal["version"], **sets)
            if rc == 0:
                raise ConcurrencyError(technical_detail=f"calibration {cal['id']} stale")
            eff = effect(conn, cur) if effect else {}
            self.store.insert_calibration_transition(conn, cal["id"], frm, to_state, actor=principal, action=action,
                                                     detail=eff.get("detail", ""))
            return (cal["id"], eff), cal["id"]
        res = self.gov.perform(principal_id=principal, capability=capability, scope=scope, action=action,
                               business_fn=business, target_ref=cal["id"], idempotency_key=idempotency_key)
        if res.get("replayed"):
            return {"calibration": self.store.get_calibration(cal["id"]), "replayed": True, "effect": {}}
        return {"calibration": self.store.get_calibration(cal["id"]), "replayed": False,
                "effect": res.get("value", (None, {}))[1]}

    def start_review(self, principal, scope, cal):
        return self._transition(principal, scope, cal, "UNDER_REVIEW", capability="calibration.validate",
                                action="calibration.start_review")

    def require_validation(self, principal, scope, cal):
        return self._transition(principal, scope, cal, "VALIDATION_REQUIRED", capability="calibration.validate",
                                action="calibration.require_validation")

    def mark_validated(self, principal, scope, cal, *, validation_run_id=None):
        return self._transition(principal, scope, cal, "VALIDATED", capability="calibration.validate",
                                action="calibration.mark_validated",
                                field_updates=lambda c: {"decision_ref": validation_run_id} if validation_run_id
                                else {})

    def approve(self, principal, scope, cal, *, decision_ref=None):
        """Approval is distinct from activation and has no operational effect. Material behavior change
        requires prior validation."""
        def guard(cur):
            if cur["target_type"] in MATERIAL_TARGETS and cur["review_state"] != "VALIDATED":
                raise ValidationError(message="This Calibration requires validation before approval.",
                                      technical_detail="material target not validated")
        return self._transition(principal, scope, cal, "APPROVED", capability="calibration.approve",
                                action="calibration.approve", guard=guard,
                                field_updates=lambda c: {"approval_state": "approved", "approving_principal": principal,
                                                         "decision_ref": decision_ref})

    def reject(self, principal, scope, cal, *, reason=""):
        return self._transition(principal, scope, cal, "REJECTED", capability="calibration.approve",
                                action="calibration.reject",
                                field_updates=lambda c: {"rejection_reason": reason or "rejected"})

    def withdraw(self, principal, scope, cal, *, reason=""):
        return self._transition(principal, scope, cal, "WITHDRAWN", capability="calibration.propose",
                                action="calibration.withdraw",
                                field_updates=lambda c: {"rejection_reason": reason or "withdrawn"})

    # ---- activation (the ONLY step that creates operational change) --------
    def activate(self, principal, scope, cal, *, future=False, idempotency_key=None):
        """Activate an APPROVED Calibration. Future-effective stays SCHEDULED. Creates or references a
        new approved version (or a policy-review recommendation for policy-adjacent targets); records an
        immutable activation reference. Never rewrites prior Predictions or mutates active policy."""
        to_state = "SCHEDULED" if future else "ACTIVATED"

        def effect(conn, cur):
            version_ref, kind = self._activate_target(conn, cur, future)
            aid = self.store.insert_activation(
                conn, cur["id"], target_type=cur["target_type"], activated_version_ref=version_ref,
                activated_version_kind=kind, effective_start=cur["proposed_effective_period"], scheduled=future,
                prior_version_ref=cur["current_version"], actor=principal)
            conn.execute("UPDATE calibration_proposal SET activation_ref=? WHERE id=?", (aid, cur["id"]))
            return {"detail": f"activated {kind} {version_ref}", "activation_ref": aid, "version_ref": version_ref,
                    "kind": kind}
        key = idempotency_key or f"{cal['id']}:activate"
        return self._transition(principal, scope, cal, to_state, capability="calibration.activate",
                                action="calibration.activate", effect=effect, idempotency_key=key)

    def _activate_target(self, conn, cur, future):
        """Create/reference the new approved version. Policy-adjacent targets create a policy-REVIEW
        recommendation only (never a direct policy mutation)."""
        tt, change = cur["target_type"], (cur["proposed_change"] or "{}")
        import json
        change = json.loads(change) if isinstance(change, str) else change
        lifecycle = "scheduled" if future else "active"
        if tt == "calculation_version":
            cv = CalculationVersion(id=new_id("calv"), family_id=(cur["target_family"] or "learning_calc"),
                                    semver=change.get("semver", "2.0.0"), lifecycle_status=lifecycle,
                                    change_summary="calibration-activated", supersedes=cur["current_version"])
            self.policy.insert_calc_version(conn, cv)
            return cv.id, "calculation_version"
        if tt == "model_version":
            mv = ModelVersion(id=new_id("modv"), model_family=(cur["target_family"] or "learning_model"),
                              version=change.get("version", "2.0.0"), status=lifecycle,
                              supersedes=cur["current_version"])
            self.policy.insert_model_version(conn, mv)
            return mv.id, "model_version"
        if tt == "comparison_specification_version":
            spec = ComparisonSpecRuntime(
                id=new_id("csr"), version=change.get("version", "2.0.0"),
                prediction_type=change.get("prediction_type", ""), observation_type=change.get("observation_type", ""),
                status=(lifecycle if lifecycle == "active" else "registered"), supersedes=cur["current_version"])
            self.store.insert_comparison_spec(conn, spec)
            return spec.id, "comparison_specification_version"
        # policy-adjacent targets => a policy-review recommendation, NOT a policy mutation.
        rec = new_id("prev_rec")
        conn.execute("UPDATE calibration_proposal SET policy_review_recommendation=? WHERE id=?",
                     (rec, cur["id"]))
        return rec, "policy_review_recommendation"

    def rollback(self, principal, scope, cal, *, restored_version_ref, reason=""):
        """Restore an approved prior version prospectively; preserves failed/new version history."""
        def effect(conn, cur):
            act = self.store.activation_for(cur["id"])
            rid = self.store.insert_rollback(conn, cur["id"], activation_ref=(act["id"] if act else None),
                                             restored_version_ref=restored_version_ref, reason=reason or "rollback",
                                             actor=principal, effective_start=self.store._now())
            return {"detail": f"rolled back to {restored_version_ref}", "rollback_ref": rid}
        return self._transition(principal, scope, cal, "ROLLED_BACK", capability="calibration.rollback",
                                action="calibration.rollback", effect=effect)
