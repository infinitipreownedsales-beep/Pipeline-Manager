"""Phase 9 acceptance — approval (27-35), execution authorization + reconciliation (36-44),
acknowledgment (45-48), expiration + staleness (49-53), reconciliation coverage (54)."""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ValidationError
from elite.govern.fixtures import OTHER_SCOPE, Phase9
from elite.workflow.fixtures import SCOPE


class TestPhase9ApprovalExecution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase9(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    # ---- approval (27-35) -------------------------------------------------
    def test_27_28_proposal_and_approval_authorities_separate(self):
        it, d = self.p.decide(rec="r1")                                # decider issues
        with self.assertRaises(AuthorizationError):
            self.p.approvals.approve(self.p.decider, SCOPE, d)         # decider cannot approve
        r = self.p.approvals.approve(self.p.approver, SCOPE, d)
        self.assertEqual(r["approval"]["approving_principal"], self.p.approver)

    def test_29_approval_validates_domain_state(self):
        it, d = self.p.decide(disposition="REJECT", rec="r2")
        with self.assertRaises(ValidationError):                       # a rejected decision is not approvable
            self.p.approvals.approve(self.p.approver, SCOPE, d)

    def test_30_stale_approval_rejected(self):
        it, d = self.p.decide(rec="r3")
        with self.assertRaises(ValidationError):
            self.p.approvals.approve(self.p.approver, SCOPE, d, stale=True)

    def test_31_replayed_approval_idempotent(self):
        it, d = self.p.decide(rec="r4")
        a = self.p.approvals.approve(self.p.approver, SCOPE, d, idempotency_key="ak1")
        b = self.p.approvals.approve(self.p.approver, SCOPE, d, idempotency_key="ak1")
        self.assertTrue(b["replayed"])
        self.assertEqual(len(self.p.store.approvals_for(d["id"])), 1)

    def test_32_approval_cannot_exceed_quantity(self):
        it, d = self.p.decide(rec="r5")
        with self.assertRaises(ValidationError):
            self.p.approvals.approve(self.p.approver, SCOPE, d, quantity=5, decision_quantity=3)

    def test_33_approval_within_quantity_ok(self):
        it, d = self.p.decide(rec="r5b")
        r = self.p.approvals.approve(self.p.approver, SCOPE, d, quantity=2, decision_quantity=3)
        self.assertEqual(r["approval"]["quantity"], 2)

    def test_34_approval_does_not_execute(self):
        it, d, a = self.p.approved(domain="cpo")
        self.assertEqual(self.p.store.execauths_for(d["id"]), [])      # no execution from approval

    def test_35_revoked_approval_authority_rejected(self):
        rid = self.p.stack.authn.register("TmpApprover", "pw").id
        g = self.p.stack.grant(rid, "decision.approve", "*")
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        it, d = self.p.decide(rec="r6")
        with self.assertRaises(AuthorizationError):
            self.p.approvals.approve(rid, SCOPE, d)

    # ---- execution + reconciliation (36-44) -------------------------------
    def test_36_37_38_execution_references_domain_service(self):
        it, d, a = self.p.approved(domain="dealer_trade")
        calls = []
        e = self.p.execution.authorize(self.p.executor, SCOPE, d, a, execution_capability="dealer_trade.execute",
                                       expected_action="trade", domain_execute_fn=lambda conn: calls.append(1) or "dom_ref")
        self.assertEqual(e["execution"]["decision_id"], d["id"])       # references Decision
        self.assertEqual(e["execution"]["approval_id"], a["id"])       # references approval
        self.assertEqual(e["execution"]["domain_execution_ref"], "dom_ref")   # references domain service
        self.assertEqual(len(calls), 1)                                # invoked the domain fn, did not reimplement

    def test_39_execution_requires_approval(self):
        it, d = self.p.decide(rec="r7")
        with self.assertRaises(ValidationError):
            self.p.execution.authorize(self.p.executor, SCOPE, d, None, execution_capability="x",
                                       expected_action="y", requires_approval=True)

    def test_40_41_completion_references_actual_event_no_false_complete(self):
        it, d, a, e = self.p.executed(domain="cpo")
        with self.assertRaises(ValidationError):                       # completion needs an actual ref
            self.p.execution.complete(self.p.executor, SCOPE, e)
        r = self.p.execution.complete(self.p.executor, SCOPE, e, domain_completion_ref="done_1")
        self.assertEqual(r["execution"]["completion_ref"], "done_1")
        # a failed domain execution can never be completed
        it2, d2, a2, e2 = self.p.executed(domain="cpo")
        self.p.execution.complete(self.p.executor, SCOPE, e2, failed=True)
        self.assertEqual(self.p.store.get_execution_auth(e2["id"])["state"], "failed")

    def test_42_replayed_execution_authorization_idempotent(self):
        it, d, a = self.p.approved()
        e1 = self.p.execution.authorize(self.p.executor, SCOPE, d, a, execution_capability="x", expected_action="y",
                                        domain_execute_fn=lambda conn: "ref", idempotency_key="ek1")
        e2 = self.p.execution.authorize(self.p.executor, SCOPE, d, a, execution_capability="x", expected_action="y",
                                        domain_execute_fn=lambda conn: "ref2", idempotency_key="ek1")
        self.assertTrue(e2["replayed"])
        self.assertEqual(len(self.p.store.execauths_for(d["id"])), 1)

    def test_43_stages_separately_inspectable(self):
        it, d, a, e = self.p.executed()
        self.p.execution.complete(self.p.executor, SCOPE, e, domain_completion_ref="done")
        self.assertIsNotNone(self.p.store.get_decision(d["id"]))
        self.assertTrue(self.p.store.approvals_for(d["id"]))
        self.assertTrue(self.p.store.execauths_for(d["id"]))           # decision/approval/exec/completion distinct

    def test_44_reconciliation_conflict_unresolved(self):
        it, d, a, e = self.p.executed()
        self.assertEqual(self.p.execution.reconcile(d, conflict=True), "CONFLICTING")
        self.assertEqual(self.p.execution.reconcile(d, unresolved_identity=True), "UNRESOLVED_IDENTITY")

    # ---- acknowledgment (45-48) -------------------------------------------
    def test_45_46_ack_not_approval_not_execution(self):
        it, d = self.p.decide(rec="r8")
        self.p.ack.acknowledge(self.p.acknowledger, SCOPE, decision_id=d["id"])
        self.assertEqual(self.p.store.approvals_for(d["id"]), [])
        self.assertEqual(self.p.store.execauths_for(d["id"]), [])

    def test_47_replayed_ack_idempotent(self):
        it, d = self.p.decide(rec="r9")
        self.p.ack.acknowledge(self.p.acknowledger, SCOPE, decision_id=d["id"], idempotency_key="ick")
        r = self.p.ack.acknowledge(self.p.acknowledger, SCOPE, decision_id=d["id"], idempotency_key="ick")
        self.assertTrue(r["replayed"])
        self.assertEqual(len(self.p.store.acks_for_decision(d["id"])), 1)

    def test_48_unacknowledged_required_visible(self):
        it, d = self.p.decide(rec="r10")
        self.assertTrue(self.p.ack.outstanding(d["id"]))
        self.p.ack.acknowledge(self.p.acknowledger, SCOPE, decision_id=d["id"])
        self.assertFalse(self.p.ack.outstanding(d["id"]))

    # ---- expiration + staleness (49-53) -----------------------------------
    def test_49_50_new_facts_make_stale_remains_historical(self):
        it = self.p.item(rec="r11")
        self.p.expiration.mark_recommendation_stale(it, reason="new accepted fact", triggering_fact="bf_new")
        self.assertTrue(self.p.expiration.is_recommendation_stale(it["id"]))
        self.assertIsNotNone(self.p.store.get_workspace_item(it["id"]))          # not deleted
        self.assertEqual(self.p.store.get_workspace_item(it["id"])["recommendation_ref"], "r11")

    def test_51_stale_decision_cannot_execute_without_renewal(self):
        it, d, a = self.p.approved()
        with self.assertRaises(ValidationError):
            self.p.execution.authorize(self.p.executor, SCOPE, d, a, execution_capability="x", expected_action="y",
                                       stale=True)

    def test_52_expiration_not_rejection(self):
        it, d = self.p.decide(rec="r12")
        eid = self.p.expiration.set_expiration("decision", d["id"], expires_at="2000-01-01T00:00:00Z")
        self.p.expiration.expire(eid)
        self.assertTrue(self.p.expiration.is_expired(d["id"]))
        self.assertNotEqual(self.p.store.get_decision(d["id"])["disposition"], "REJECT")   # expiry != rejection

    def test_53_expired_authority_cannot_act(self):
        rid = self.p.stack.authn.register("ExpAuth", "pw").id
        _tid, gid = self.p.authority.grant_temporary(self.p.authority_admin, SCOPE, to_principal=rid,
                                                     capability="decision.approve", grant_scope="*",
                                                     expiration="2000-01-01T00:00:00Z")
        self.p.authority.enforce_temporary_expiry()
        it, d = self.p.decide(rec="r13")
        with self.assertRaises(AuthorizationError):
            self.p.approvals.approve(rid, SCOPE, d)

    # ---- reconciliation coverage (54) -------------------------------------
    def test_54_every_actionable_decision_reconciles(self):
        it, d = self.p.decide(disposition="ACCEPT", rec="r14")
        self.assertEqual(self.p.execution.reconcile(d), "AWAITING_APPROVAL")
        a = self.p.approvals.approve(self.p.approver, SCOPE, d)["approval"]
        self.assertEqual(self.p.execution.reconcile(d), "APPROVED_AWAITING_EXECUTION")
        it2, d2 = self.p.decide(disposition="NO_ACTION", rec="r15")
        self.assertEqual(self.p.execution.reconcile(d2), "NO_EXECUTION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
