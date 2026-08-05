"""Phase 9 acceptance — authority administration + delegation + temporary (73-78), separation of duties
(79-82), authority governance (83-84), audit administration (85-88), exception queues (89-91),
operational-control summaries (92)."""
import os
import sqlite3
import tempfile
import unittest

from elite.errors import AuthorizationError, PersistenceError, ValidationError
from elite.govern.fixtures import OTHER_SCOPE, Phase9
from elite.workflow.fixtures import SCOPE


class TestPhase9AuthoritySodAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase9(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    # ---- authority admin (73-78) ------------------------------------------
    def test_73_uses_phase1_permission_records(self):
        d = self.p.stack.authn.register("Del", "pw").id
        self.p.authority.delegate(self.p.full, SCOPE, delegate=d, capability="decision.approve", delegate_scope="*")
        # the delegated grant lives in the Phase 1 capability_grant store — no second permission table
        self.assertTrue(any(g.capability == "decision.approve" and g.effective()
                            for g in self.p.stack.grants.list_for(d)))
        self.p.stack.authz.require(d, "decision.approve", SCOPE)       # authz honors it

    def test_74_temporary_authority_expires(self):
        h = self.p.stack.authn.register("Tmp", "pw").id
        self.p.authority.grant_temporary(self.p.authority_admin, SCOPE, to_principal=h,
                                         capability="workspace.view", grant_scope="*",
                                         expiration="2000-01-01T00:00:00Z")
        self.p.stack.authz.require(h, "workspace.view", SCOPE)         # effective before expiry sweep
        self.p.authority.enforce_temporary_expiry()
        with self.assertRaises(AuthorizationError):
            self.p.stack.authz.require(h, "workspace.view", SCOPE)     # expired

    def test_75_revoked_authority_ineffective(self):
        d = self.p.stack.authn.register("Del2", "pw").id
        dg = self.p.authority.delegate(self.p.full, SCOPE, delegate=d, capability="decision.approve",
                                       delegate_scope="*")
        self.p.authority.revoke_delegation(self.p.authority_admin, SCOPE, dg)
        with self.assertRaises(AuthorizationError):
            self.p.stack.authz.require(d, "decision.approve", SCOPE)

    def test_76_delegation_cannot_exceed_capability(self):
        weak = self.p.stack.authn.register("Weak", "pw").id
        self.p.stack.grant(weak, "authority.delegate", "*")           # can delegate, but holds no approve
        d = self.p.stack.authn.register("Del3", "pw").id
        with self.assertRaises(ValidationError):
            self.p.authority.delegate(weak, SCOPE, delegate=d, capability="decision.approve", delegate_scope="*")

    def test_77_delegation_cannot_exceed_scope(self):
        scoped = self.p.stack.authn.register("Scoped", "pw").id
        self.p.stack.grant(scoped, "authority.delegate", "*")
        self.p.stack.grant(scoped, "decision.approve", SCOPE)         # only store:HG
        d = self.p.stack.authn.register("Del4", "pw").id
        with self.assertRaises(ValidationError):
            self.p.authority.delegate(scoped, OTHER_SCOPE, delegate=d, capability="decision.approve",
                                      delegate_scope=OTHER_SCOPE)

    def test_78_delegated_action_preserves_grant_chain(self):
        d = self.p.stack.authn.register("Del5", "pw").id
        dg = self.p.authority.delegate(self.p.full, SCOPE, delegate=d, capability="decision.approve",
                                       delegate_scope="*", reason="coverage")
        g = self.p.store.conn.execute("SELECT * FROM capability_grant WHERE id=?", (dg["grant_ref"],)).fetchone()
        self.assertTrue(g["authority"].startswith("delegated_by:"))   # grant chain attribution
        self.assertIn(self.p.full, g["authority"])

    # ---- separation of duties (79-82) -------------------------------------
    def test_79_conflict_detected(self):
        self.p.store.add_sod_rule(rule_type="proposer_not_approver", action_a="decision.issue",
                                  action_b="decision.approve")
        with self.assertRaises(AuthorizationError):
            self.p.sod.enforce(self.p.full, SCOPE, rule_type="proposer_not_approver", actor_a="x", actor_b="x")
        self.assertTrue(self.p.store.sod_exceptions())                 # conflict recorded

    def test_80_self_approval_blocked_above_materiality(self):
        self.p.store.add_sod_rule(rule_type="self_approval_prohibited_above_materiality",
                                  materiality_threshold="1000")
        with self.assertRaises(AuthorizationError):
            self.p.sod.enforce(self.p.full, SCOPE, rule_type="self_approval_prohibited_above_materiality",
                               actor_a="x", actor_b="x", materiality=5000)
        # below threshold is allowed
        self.assertTrue(self.p.sod.enforce(self.p.full, SCOPE,
                                           rule_type="self_approval_prohibited_above_materiality",
                                           actor_a="x", actor_b="x", materiality=100))

    def test_81_authorized_override_requires_capability_and_reason(self):
        with self.assertRaises(ValidationError):                       # missing reason
            self.p.sod.override(self.p.authority_admin, SCOPE, rule_type="proposer_not_approver", actor_a="x",
                                actor_b="x", reason="")
        eid = self.p.sod.override(self.p.authority_admin, SCOPE, rule_type="proposer_not_approver", actor_a="x",
                                  actor_b="x", reason="single-staff store")
        ex = self.p.store.conn.execute("SELECT * FROM separation_of_duties_exception WHERE id=?", (eid,)).fetchone()
        self.assertTrue(ex["override"])
        self.assertEqual(ex["override_reason"], "single-staff store")

    def test_82_unauthorized_override_rejected(self):
        nobody = self.p.stack.authn.register("NoOverride", "pw").id
        with self.assertRaises(AuthorizationError):
            self.p.sod.override(nobody, SCOPE, rule_type="proposer_not_approver", actor_a="x", actor_b="x",
                                reason="try")

    # ---- authority governance (83-84) -------------------------------------
    def test_83_authority_mutation_requires_authorization(self):
        # holds the capability to delegate, but lacks authority.delegate -> mutation denied below the UI
        actor = self.p.stack.authn.register("NoDelegateCap", "pw").id
        self.p.stack.grant(actor, "decision.approve", "*")
        d = self.p.stack.authn.register("Del6", "pw").id
        with self.assertRaises(AuthorizationError):
            self.p.authority.delegate(actor, SCOPE, delegate=d, capability="decision.approve", delegate_scope="*")

    def test_84_authority_audit_failure_blocks_mutation(self):
        d = self.p.stack.authn.register("Del7", "pw").id
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                self.p.authority.delegate(self.p.full, SCOPE, delegate=d, capability="decision.approve",
                                          delegate_scope="*")
        finally:
            self.p.stack.audit.append = orig
        self.assertFalse(any(g.capability == "decision.approve" for g in self.p.stack.grants.list_for(d)))

    # ---- audit administration (85-88) -------------------------------------
    def test_85_audit_event_immutable(self):
        self.p.decide(rec="ra")
        row = self.p.store.conn.execute("SELECT id FROM audit_event LIMIT 1").fetchone()
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("UPDATE audit_event SET action='x' WHERE id=?", (row["id"],))

    def test_86_audit_review_scoped_and_authorized(self):
        with self.assertRaises(AuthorizationError):
            self.p.audit_admin.review(self.p.reviewer, SCOPE)          # reviewer lacks audit.view
        rows = self.p.audit_admin.review(self.p.auditor, SCOPE, action="decision.issue")
        self.assertIsInstance(rows, list)

    def test_87_correlated_action_traceable(self):
        it = self.p.item(rec="rc")
        self.p.decisions.issue(self.p.decider, SCOPE, it, disposition="ACCEPT", selected_action="a",
                               correlation_id="corr_1")
        d = self.p.store.decisions_for_item(it["id"])[0]
        self.p.approvals.approve(self.p.approver, SCOPE, d, correlation_id="corr_1")
        trace = self.p.audit_admin.trace(self.p.auditor, SCOPE, "corr_1")
        self.assertGreaterEqual(len(trace), 2)                         # multi-step correlated

    def test_88_missing_audit_event_creates_exception(self):
        ex = self.p.audit_admin.detect_missing(expected_action="never.happened", correlation_id="c_missing")
        self.assertIsNotNone(ex)
        self.assertEqual(ex["kind"], "missing_expected_event")

    # ---- exception queues (89-91) -----------------------------------------
    def test_89_90_queue_references_source_and_close_preserves_it(self):
        it = self.p.item(rec="rq")
        q = self.p.queues.enqueue(queue="stale_recommendation", source_type="workspace_item", source_ref=it["id"],
                                  owning_domain="new_inventory")
        self.assertEqual(q["source_ref"], it["id"])                    # references authoritative source
        self.p.queues.close(q)
        self.assertEqual(self.p.store.get_op_exception(q["id"])["status"], "closed")
        self.assertEqual(self.p.store.get_workspace_item(it["id"])["workspace_state"], "READY_FOR_REVIEW")  # source untouched

    def test_91_dismissal_requires_authority_and_reason(self):
        q = self.p.queues.enqueue(queue="missing_policy", source_type="policy_family", source_ref="pf",
                                  owning_domain="new_inventory")
        with self.assertRaises(ValidationError):
            self.p.queues.dismiss(self.p.auditor, SCOPE, q, reason="")
        nobody = self.p.stack.authn.register("NoDismiss", "pw").id
        with self.assertRaises(AuthorizationError):
            self.p.queues.dismiss(nobody, SCOPE, self.p.store.get_op_exception(q["id"]), reason="n/a")
        r = self.p.queues.dismiss(self.p.auditor, SCOPE, self.p.store.get_op_exception(q["id"]), reason="duplicate")
        self.assertEqual(r["status"], "dismissed")

    # ---- summaries (92) ---------------------------------------------------
    def test_92_summaries_reconcile_to_source(self):
        self.p.decide(disposition="ACCEPT", rec="s1")
        self.p.decide(disposition="DEFER", rec="s2")
        summary = self.p.summaries.summarize(scope=SCOPE)
        self.assertTrue(self.p.summaries.reconciles_to_items(summary, scope=SCOPE))
        self.assertEqual(summary["total_items"], len(self.p.store.all_items(scope=SCOPE)))


if __name__ == "__main__":
    unittest.main()
