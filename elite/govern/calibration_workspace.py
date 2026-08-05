"""Operational workspace around Phase 8 Calibration records.

Phase 9 USES the Phase 8 Calibration lifecycle + services — it does not activate a Calibration by
directly editing a target version, and does not create a second activation process. Approval and
activation stay separate; scheduled activation stays future-effective; a policy target remains a
policy-review request; rollback stays governed; historical Predictions remain unchanged.
"""
from __future__ import annotations


class CalibrationWorkspaceService:
    def __init__(self, learning_store, calibration_service, clock):
        self.ls, self.cal, self.clock = learning_store, calibration_service, clock

    def review(self, calibration_proposal_id):
        """Return the review projection over the Phase 8 records (proposal, evidence, validation,
        transitions, activation, rollback) — read-only; never mutates a target version directly."""
        c = self.ls.get_calibration(calibration_proposal_id)
        if c is None:
            return None
        import json
        evidence = self.ls.conn.execute("SELECT * FROM calibration_evidence WHERE calibration_proposal_id=?",
                                        (calibration_proposal_id,)).fetchall()
        runs = self.ls.conn.execute("SELECT * FROM calibration_validation_run WHERE calibration_proposal_id=?",
                                   (calibration_proposal_id,)).fetchall()
        results = []
        for r in runs:
            results += [dict(x) for x in self.ls.validation_results(r["id"])]
        improved = [x["cohort"] for x in results if x["direction"] == "improved"]
        regressed = [x["cohort"] for x in results if x["direction"] == "worsened"]
        act = self.ls.activation_for(calibration_proposal_id)
        return {
            "calibration_id": c["id"], "target_type": c["target_type"], "current_version": c["current_version"],
            "proposed_change": json.loads(c["proposed_change"] or "{}"), "review_state": c["review_state"],
            "learning_signals": [e["learning_signal_ref"] for e in evidence if e["learning_signal_ref"]],
            "validation_runs": [r["id"] for r in runs], "cohort_improvements": improved,
            "cohort_regressions": regressed, "leakage_checked": all(bool(r["leakage_checked"]) for r in runs),
            "proposer": c["proposer"], "approval_state": c["approval_state"],
            "activation": (dict(act) if act else None), "scheduled": (bool(act["scheduled"]) if act else False),
            "rollbacks": [dict(x) for x in self.ls.rollback_for(calibration_proposal_id)],
            "policy_review_recommendation": c["policy_review_recommendation"],
            "raw_history_path": f"calibration_proposal/{c['id']}"}

    # Deliberately delegate every state change to the Phase 8 service (no second activation path).
    def approve(self, principal, scope, cal):
        return self.cal.approve(principal, scope, self.ls.get_calibration(cal["id"]))

    def activate(self, principal, scope, cal, *, future=False):
        return self.cal.activate(principal, scope, self.ls.get_calibration(cal["id"]), future=future)

    def rollback(self, principal, scope, cal, *, restored_version_ref, reason=""):
        return self.cal.rollback(principal, scope, self.ls.get_calibration(cal["id"]),
                                 restored_version_ref=restored_version_ref, reason=reason)
