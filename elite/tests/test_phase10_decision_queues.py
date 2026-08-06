"""Phase 10 acceptance — Decision issuance (41-48), approval (49-52), execution (53-57),
acknowledgment (58-60)."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


class TestPhase10DecisionQueues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)
        self.decider = self.p.login(self.p.op_decider)
        self.approver = self.p.login(self.p.op_approver)
        self.executor = self.p.login(self.p.op_executor)

    def tearDown(self):
        self.p.close()

    def _decision_for(self, item):
        ds = self.p.p9.store.decisions_for_item(item["id"])
        return ds[0] if ds else None

    # ---- Decision issuance (41-48) ----------------------------------------
    def test_41_form_references_exact_revision(self):
        r = self.full.get("/item/" + self.p.fresh_item["id"] + "/decide")
        self.assertIn(f"revision {self.p.fresh_item['version']}", r.body)
        self.assertIn(self.p.fresh_item["recommendation_ref"], r.body)

    def test_42_missing_rationale_blank(self):
        r = self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide",
                              {"disposition": "ACCEPT", "selected_action": "x", "alternatives": "A,B"})
        self.assertEqual(r.status, 303)
        self.assertIsNone(self._decision_for(self.p.fresh_item)["rationale"])

    def test_43_override_requires_reason(self):
        # override without a reason is rejected by the service
        r = self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide",
                              {"disposition": "OVERRIDE", "selected_action": "x"})
        self.assertEqual(r.status, 409)
        r2 = self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide",
                               {"disposition": "OVERRIDE", "selected_action": "x", "override_reason": "urgent"})
        self.assertEqual(r2.status, 303)

    def test_44_stale_requires_renewal_or_override(self):
        r = self.decider.post("/item/" + self.p.stale_item["id"] + "/decide",
                              {"disposition": "ACCEPT", "selected_action": "x"})
        self.assertEqual(r.status, 409)                    # stale blocks ordinary issuance
        r2 = self.decider.post("/item/" + self.p.stale_item["id"] + "/decide",
                               {"disposition": "OVERRIDE", "selected_action": "x", "override_reason": "renewed"})
        self.assertEqual(r2.status, 303)

    def test_45_mutation_invokes_service(self):
        before = self.p.stack.audit.count()
        self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide",
                          {"disposition": "ACCEPT", "selected_action": "x"})
        self.assertIsNotNone(self._decision_for(self.p.fresh_item))     # governed_decision written
        self.assertEqual(self.p.stack.audit.count(), before + 1)        # via the Phase 9 governed service

    def test_46_replayed_submission_no_duplicate(self):
        form = {"disposition": "ACCEPT", "selected_action": "x", "_idem": "idem-abc"}
        self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide", dict(form))
        self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide", dict(form))
        self.assertEqual(len(self.p.p9.store.decisions_for_item(self.p.fresh_item["id"])), 1)

    def test_47_audit_failure_no_success(self):
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r = self.decider.post("/item/" + self.p.fresh_item["id"] + "/decide",
                                  {"disposition": "ACCEPT", "selected_action": "x"})
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(r.status, 409)                    # a safe failure, not a success
        self.assertNotIn("Decision recorded", r.body)
        self.assertEqual(self.p.p9.store.decisions_for_item(self.p.fresh_item["id"]), [])

    def test_48_scenario_decision_cannot_execute_officially(self):
        self.full.post("/item/" + self.p.scenario_item["id"] + "/decide",
                       {"disposition": "ACCEPT", "selected_action": "x"})
        d = self._decision_for(self.p.scenario_item)
        self.p.p9.approvals.approve(self.p.op_full, SCOPE, d)           # even if approved…
        r = self.full.post("/execution/" + d["id"] + "/authorize", {})
        self.assertEqual(r.status, 409)                                # …a scenario decision can't execute officially

    # ---- approval (49-52) -------------------------------------------------
    def test_49_50_approval_separate_authority_and_sod_visible(self):
        d = self._decision_for(self.p.decided_item)                    # issued by op_decider in the fixture
        # the decider viewing approvals sees the self-conflict note and no approve button
        body = self.decider.get("/approvals").body
        self.assertIn("You proposed this", body)
        # and the decider (lacking decision.approve) cannot approve — enforced below the UI
        self.assertEqual(self.decider.post("/approval/" + d["id"] + "/approve", {}).status, 403)
        # a separate approver can
        self.assertEqual(self.approver.post("/approval/" + d["id"] + "/approve", {}).status, 303)

    def test_51_approval_not_execution(self):
        d = self._decision_for(self.p.decided_item)
        self.approver.post("/approval/" + d["id"] + "/approve", {})
        self.assertEqual(self.p.p9.store.execauths_for(d["id"]), [])

    def test_52_expired_approval_cannot_proceed(self):
        d = self._decision_for(self.p.decided_item)
        a = self.approver.post("/approval/" + d["id"] + "/approve", {})
        appr = self.p.p9.store.approvals_for(d["id"])[-1]
        self.p.p9.expiration.expire(self.p.p9.expiration.set_expiration("approval", appr["id"],
                                                                        expires_at="2000-01-01T00:00:00Z"))
        r = self.executor.post("/execution/" + d["id"] + "/authorize", {})
        self.assertEqual(r.status, 409)

    # ---- execution (53-57) ------------------------------------------------
    def _approved_decision(self):
        d = self._decision_for(self.p.decided_item)
        self.p.p9.approvals.approve(self.p.op_approver, SCOPE, d)
        return d

    def test_53_execution_uses_domain_service(self):
        d = self._approved_decision()
        self.executor.post("/execution/" + d["id"] + "/authorize", {})
        e = self.p.p9.store.execauths_for(d["id"])[-1]
        self.assertTrue(e["domain_execution_ref"])                     # references the domain execution
        self.assertEqual(e["state"], "in_execution")

    def test_54_failed_not_completed(self):
        d = self._approved_decision()
        self.executor.post("/execution/" + d["id"] + "/authorize", {})
        e = self.p.p9.store.execauths_for(d["id"])[-1]
        self.p.p9.execution.complete(self.p.op_executor, SCOPE, e, failed=True)   # domain execution failed
        body = self.executor.get("/execution").body
        self.assertIn("failed", body)
        self.assertNotIn("completed", body.split("<tbody>")[-1])       # never shown completed

    def test_55_stages_separately_inspectable(self):
        d = self._approved_decision()
        self.executor.post("/execution/" + d["id"] + "/authorize", {})
        e = self.p.p9.store.execauths_for(d["id"])[-1]
        self.executor.post("/execution/" + e["id"] + "/complete", {})
        detail = self.full.get("/item/" + self.p.decided_item["id"]).body
        for stage in ("Decision:", "Approval", "Execution", "Reconciliation:"):
            self.assertIn(stage, detail)

    def test_56_reconciliation_conflict_unresolved(self):
        d = self._approved_decision()
        self.p.p9.execution.reconcile(d, conflict=True)
        self.assertIn("CONFLICTING", self.full.get("/item/" + self.p.decided_item["id"]).body)

    def test_57_replayed_execution_no_duplicate(self):
        d = self._approved_decision()
        form = {"_idem": "idem-exec-1"}
        self.executor.post("/execution/" + d["id"] + "/authorize", dict(form))
        self.executor.post("/execution/" + d["id"] + "/authorize", dict(form))
        self.assertEqual(len(self.p.p9.store.execauths_for(d["id"])), 1)

    # ---- acknowledgment (58-60) -------------------------------------------
    def test_58_59_ack_not_approval_or_execution(self):
        d = self._decision_for(self.p.decided_item)
        self.full.post("/ack/" + d["id"], {})
        self.assertEqual(self.p.p9.store.approvals_for(d["id"]), [])
        self.assertEqual(self.p.p9.store.execauths_for(d["id"]), [])

    def test_60_replayed_ack_idempotent(self):
        d = self._decision_for(self.p.decided_item)
        form = {"_idem": "idem-ack-1"}
        self.full.post("/ack/" + d["id"], dict(form))
        self.full.post("/ack/" + d["id"], dict(form))
        self.assertEqual(len(self.p.p9.store.acks_for_decision(d["id"])), 1)


if __name__ == "__main__":
    unittest.main()
