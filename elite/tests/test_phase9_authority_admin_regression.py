"""Phase 9 dedicated authority-administration regression (14 points).

Proves delegation/temporary/revocation over the Phase 1 permission store, separation-of-duties
detection + authorized override, atomic authority mutation + audit, and full historical preservation.
"""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, PersistenceError, ValidationError
from elite.govern.fixtures import OTHER_SCOPE, Phase9
from elite.workflow.fixtures import SCOPE


class TestAuthorityAdminRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase9(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def test_authority_admin_regression(self):
        p = self.p
        # 1 grantor possesses a capability and scope
        grantor = p.stack.authn.register("Grantor", "pw").id
        p.stack.grant(grantor, "authority.delegate", "*")
        p.stack.grant(grantor, "decision.approve", "*")
        # 2 valid delegation is created
        delegate = p.stack.authn.register("Delegate", "pw").id
        dg = p.authority.delegate(grantor, SCOPE, delegate=delegate, capability="decision.approve",
                                  delegate_scope="*", reason="coverage")
        self.assertTrue(dg["active"])
        # 3 delegated Principal acts within scope
        it, d = p.decide(rec="ra")
        appr = p.approvals.approve(delegate, SCOPE, d)["approval"]
        self.assertEqual(appr["approving_principal"], delegate)
        # 4 action records the delegation chain
        g = p.store.conn.execute("SELECT authority FROM capability_grant WHERE id=?", (dg["grant_ref"],)).fetchone()
        self.assertEqual(g["authority"], f"delegated_by:{grantor}")
        # 5 broader capability delegation is rejected (grantor lacks execution.authorize)
        with self.assertRaises(ValidationError):
            p.authority.delegate(grantor, SCOPE, delegate=delegate, capability="execution.authorize",
                                 delegate_scope="*")
        # 6 broader scope delegation is rejected
        scoped = p.stack.authn.register("ScopedGrantor", "pw").id
        p.stack.grant(scoped, "authority.delegate", "*")
        p.stack.grant(scoped, "decision.approve", SCOPE)              # only store:HG
        with self.assertRaises(ValidationError):
            p.authority.delegate(scoped, OTHER_SCOPE, delegate=delegate, capability="decision.approve",
                                 delegate_scope=OTHER_SCOPE)
        # 7 temporary authority expires
        tmp = p.stack.authn.register("TmpP", "pw").id
        p.authority.grant_temporary(p.authority_admin, SCOPE, to_principal=tmp, capability="workspace.view",
                                    grant_scope="*", expiration="2000-01-01T00:00:00Z")
        p.authority.enforce_temporary_expiry()
        with self.assertRaises(AuthorizationError):
            p.stack.authz.require(tmp, "workspace.view", SCOPE)
        # 8 revoked delegated authority is immediately rejected
        p.authority.revoke_delegation(p.authority_admin, SCOPE, dg)
        with self.assertRaises(AuthorizationError):
            p.stack.authz.require(delegate, "decision.approve", SCOPE)
        # 9 proposer/approver conflict is detected
        p.store.add_sod_rule(rule_type="proposer_not_approver", action_a="decision.issue",
                             action_b="decision.approve")
        with self.assertRaises(AuthorizationError):
            p.sod.enforce(p.full, SCOPE, rule_type="proposer_not_approver", actor_a="same", actor_b="same")
        # 10 authorized separation override requires explicit capability and reason
        with self.assertRaises(ValidationError):
            p.sod.override(p.authority_admin, SCOPE, rule_type="proposer_not_approver", actor_a="s", actor_b="s",
                           reason="")
        eid = p.sod.override(p.authority_admin, SCOPE, rule_type="proposer_not_approver", actor_a="s", actor_b="s",
                             reason="single-staff store")
        self.assertTrue(p.store.conn.execute("SELECT override FROM separation_of_duties_exception WHERE id=?",
                                             (eid,)).fetchone()["override"])
        # 11 unauthorized override is rejected
        nobody = p.stack.authn.register("NoOv", "pw").id
        with self.assertRaises(AuthorizationError):
            p.sod.override(nobody, SCOPE, rule_type="proposer_not_approver", actor_a="s", actor_b="s", reason="x")
        # 12 authority mutation and Audit Event are atomic; 13 Audit failure leaves authority unchanged
        d2 = p.stack.authn.register("Delegate2", "pw").id
        orig = p.stack.audit.append
        p.stack.audit.append = lambda conn, ev: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                p.authority.delegate(grantor, SCOPE, delegate=d2, capability="decision.approve", delegate_scope="*")
        finally:
            p.stack.audit.append = orig
        self.assertFalse(any(g.capability == "decision.approve" for g in p.stack.grants.list_for(d2)))
        # 14 prior grants, delegations, expirations, and revocations remain historical
        self.assertIsNotNone(p.store.get_delegation(dg["id"]))        # revoked delegation still present
        self.assertEqual(p.store.get_delegation(dg["id"])["active"], 0)
        self.assertTrue(p.store.temporary_grants_for(tmp))            # temporary grant preserved


if __name__ == "__main__":
    unittest.main()
