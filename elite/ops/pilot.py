"""Controlled pilot mode, parallel-run comparison, operator feedback, and readiness certification.

Pilot mode runs the Elite Pipeline ALONGSIDE the legacy tool. It is visibly identified as a non-production
pilot, keeps the legacy tool as the operational fallback, and BLOCKS destructive cutover / legacy-
replacement / destructive-migration actions.

Parallel-run comparison is NON-AUTHORITATIVE: it captures a snapshot of the Elite result and the legacy
result and classifies the difference. It mutates NEITHER tool's result. Legacy is not authoritative merely
because it is legacy; Elite is not authoritative merely because it is new. An unknown cause stays
UNRESOLVED. A material unresolved difference blocks readiness until reviewed.

Operator feedback never changes authoritative data; an incorrect-result claim creates a review, not a
correction, and is traceable to the exact screen + revision.
"""
from __future__ import annotations

from ..errors import AuthorizationError, ValidationError
from ..ids import new_id
from .models import CAPS, COMPARISON_MATERIAL, NOT_READY, READY, READY_WITH_WARNINGS


class PilotService:
    def __init__(self, ops_store, stack, governor, clock, *, environment="pilot", pilot_mode=True,
                 logger=None):
        self.ops, self.stack, self.gov, self.clock = ops_store, stack, governor, clock
        self.environment = environment
        self.pilot_mode = pilot_mode
        self.logger = logger

    # ---- pilot mode ----------------------------------------------------------
    def is_pilot(self):
        return bool(self.pilot_mode)

    def banner(self):
        if not self.pilot_mode:
            return None
        return (f"PILOT MODE ({self.environment}) — NOT PRODUCTION. Elite Pipeline runs alongside the "
                f"legacy tool, which remains the operational fallback. No cutover.")

    def legacy_fallback_available(self):
        return True

    # destructive operations that are unavailable during a pilot
    CUTOVER_ACTIONS = {"cutover", "legacy_replacement", "destructive_migration", "production_go_live",
                       "delete_legacy", "disable_legacy"}

    def assert_action_allowed(self, action):
        """Block destructive cutover-class actions while in pilot mode."""
        if self.pilot_mode and action in self.CUTOVER_ACTIONS:
            raise AuthorizationError(message="This action is disabled during the controlled pilot.",
                                     technical_detail=f"pilot_blocks_destructive_action: {action}")
        return True

    def cutover_available(self):
        return not self.pilot_mode

    # ---- parallel-run comparison --------------------------------------------
    def compare(self, *, domain, subjects, scope, initiated_by, trigger="manual", correlation_id=None):
        """subjects: list of {subject_ref, elite_result, legacy_result, classification?, likely_source?}.
        Records a comparison run + per-subject results. Mutates neither tool's result."""
        self.stack.authz.require(initiated_by, CAPS["PILOT_COMPARE"], scope, correlation_id=correlation_id)
        run = self.ops.add_comparison_run(domain=domain, store_scope=scope, initiated_by=initiated_by,
                                          trigger=trigger, correlation_id=correlation_id,
                                          started_at=self.ops._now())
        match = diff = unresolved = 0
        results = []
        for s in subjects:
            elite, legacy = s.get("elite_result"), s.get("legacy_result")
            classification = s.get("classification")
            if classification is None:
                classification = "MATCH" if elite == legacy else "UNRESOLVED"
            if classification == "MATCH":
                match += 1
            else:
                diff += 1
                if classification == "UNRESOLVED":
                    unresolved += 1
            difference = None if classification == "MATCH" else {"elite": elite, "legacy": legacy}
            res = self.ops.add_comparison_result(
                comparison_run_id=run["id"], domain=domain, subject_ref=s.get("subject_ref"),
                elite_result=elite, legacy_result=legacy, difference=difference,
                classification=classification, likely_source=s.get("likely_source"),
                evidence=s.get("evidence"))
            results.append(self.ops.get_comparison_result(res["id"]))   # full row (all columns)
        self.ops.update_comparison_run(run["id"], subject_count=len(subjects), match_count=match,
                                       difference_count=diff, unresolved_count=unresolved,
                                       completed_at=self.ops._now())
        if self.logger:
            self.logger.op("pilot", "pilot.compare", result="ok", correlation_id=correlation_id,
                           domain=domain, matches=match, differences=diff)
        return {"run": self.ops.conn.execute("SELECT * FROM pilot_comparison_run WHERE id=?",
                                             (run["id"],)).fetchone(), "results": results}

    def review_difference(self, *, result_id, reviewer, disposition, scope, notes=None,
                          correlation_id=None):
        """Governed review of a comparison difference. Records reviewer + disposition + rationale, and
        NEVER rewrites the captured elite/legacy result. Rationale is stored only as supplied."""
        res = self.ops.get_comparison_result(result_id)
        if res is None:
            raise ValidationError(technical_detail=f"unknown comparison result {result_id}")

        def business(conn):
            conn.execute(
                "UPDATE pilot_comparison_result SET reviewer=?, disposition=?, notes=?, reviewed_at=? WHERE id=?",
                (reviewer, disposition, notes, self.ops._now(), result_id))
            return (result_id, result_id), result_id
        self.gov.perform(principal_id=reviewer, capability=CAPS["PILOT_REVIEW"], scope=scope,
                         action="pilot.compare.review", business_fn=business, target_ref=result_id,
                         correlation_id=correlation_id)
        return self.ops.get_comparison_result(result_id)

    def unreviewed_material(self, scope=None):
        return self.ops.unreviewed_material_results(COMPARISON_MATERIAL, scope=scope)

    # ---- operator feedback ---------------------------------------------------
    def submit_feedback(self, *, principal_id, scope, category, description, subject_ref=None,
                        screen_ref=None, revision_ref=None, severity="normal", expected_behavior=None,
                        actual_behavior=None, evidence_ref=None, correlation_id=None):
        """Governed feedback capture. Never mutates authoritative data. An incorrect-result claim is
        recorded with status 'review' — a review, not a correction."""
        status = "review" if category == "incorrect_result" else "open"

        def business(conn):
            fid = new_id("fbk")
            now = self.ops._now()
            conn.execute(
                "INSERT INTO operator_feedback(id,principal_id,store_scope,category,subject_ref,screen_ref,"
                "revision_ref,description,severity,expected_behavior,actual_behavior,evidence_ref,status,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, principal_id, scope, category, subject_ref, screen_ref, revision_ref, description,
                 severity, expected_behavior, actual_behavior, evidence_ref, status, now, now))
            return (fid, fid), fid
        res = self.gov.perform(principal_id=principal_id, capability=CAPS["FEEDBACK_SUBMIT"], scope=scope,
                               action="pilot.feedback.submit", business_fn=business,
                               correlation_id=correlation_id)
        fid = res["result_ref"]
        self.ops.update_feedback(fid, audit_ref=res.get("audit_id"))
        return self.ops.get_feedback(fid)

    def triage_feedback(self, *, feedback_id, owner, disposition, scope, status="triaged",
                        correction_ref=None, correlation_id=None):
        """Governed triage. An incorrect-result claim's disposition is a REVIEW outcome; it never applies
        an automatic correction to authoritative data."""
        fb = self.ops.get_feedback(feedback_id)
        if fb is None:
            raise ValidationError(technical_detail=f"unknown feedback {feedback_id}")
        if fb["category"] == "incorrect_result" and disposition == "auto_correct":
            raise ValidationError(message="Feedback cannot auto-correct authoritative data.",
                                  technical_detail="incorrect_result requires review, not correction")

        def business(conn):
            conn.execute(
                "UPDATE operator_feedback SET owner=?, disposition=?, status=?, correction_ref=?, updated_at=? "
                "WHERE id=?", (owner, disposition, status, correction_ref, self.ops._now(), feedback_id))
            return (feedback_id, feedback_id), feedback_id
        self.gov.perform(principal_id=owner, capability=CAPS["FEEDBACK_TRIAGE"], scope=scope,
                         action="pilot.feedback.triage", business_fn=business, target_ref=feedback_id,
                         correlation_id=correlation_id)
        return self.ops.get_feedback(feedback_id)

    # ---- readiness certification --------------------------------------------
    def certify_readiness(self, *, scope, domain, certified_by, readiness_status, blockers=None,
                          evidence=None, correlation_id=None):
        """Governed, evidence-based pilot-readiness certification. A material unresolved discrepancy forces
        NOT_READY regardless of the requested classification."""
        material = self.unreviewed_material(scope)
        blockers = list(blockers or [])
        if material:
            if "unreviewed_material_discrepancy" not in blockers:
                blockers.append("unreviewed_material_discrepancy")
            classification = NOT_READY
        elif readiness_status == NOT_READY or blockers:
            classification = NOT_READY
        elif readiness_status == READY_WITH_WARNINGS:
            classification = READY_WITH_WARNINGS
        else:
            classification = READY

        def business(conn):
            cid = new_id("cert")
            import json
            conn.execute(
                "INSERT INTO pilot_readiness_certification(id,store_scope,domain,classification,blockers,"
                "evidence,certified_by,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (cid, scope, domain, classification, json.dumps(blockers),
                 json.dumps(evidence or {}), certified_by, correlation_id, self.ops._now()))
            return (cid, cid), cid
        res = self.gov.perform(principal_id=certified_by, capability=CAPS["PILOT_CERTIFY"], scope=scope,
                               action="pilot.readiness.certify", business_fn=business,
                               correlation_id=correlation_id)
        return {"classification": classification, "blockers": blockers,
                "certification": self.ops.get_certification(res["result_ref"])}
