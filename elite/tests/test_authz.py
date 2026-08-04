"""Acceptance 11,12,13,14: authorization is authoritative and below the UI."""
import os
import tempfile
import unittest

from elite.errors import AuthenticationError, AuthorizationError
from elite.fixtures import Stack


class TestAuthz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.s = Stack(os.path.join(self.tmp, "elite.db"))
        self.p = self.s.authn.register("Sales Manager", "correct-horse")

    def tearDown(self):
        self.s.close()

    def test_authenticate_is_not_authorize(self):
        who = self.s.authn.authenticate(self.p.id, "correct-horse")   # authn ok
        self.assertEqual(who.id, self.p.id)
        # ...but with no grant, authorization is denied (11 + "authenticated != authorized")
        d = self.s.authz.decide(self.p.id, "principal.grant", "store:HG")
        self.assertFalse(d.allowed)
        with self.assertRaises(AuthenticationError):
            self.s.authn.authenticate(self.p.id, "wrong")

    def test_11_authenticated_without_capability_denied(self):
        with self.assertRaises(AuthorizationError):
            self.s.authz.require(self.p.id, "principal.grant", "store:HG")

    def test_12_scope_mismatch_denied(self):
        self.s.grant(self.p.id, "audit.read", "store:HG")
        self.assertTrue(self.s.authz.decide(self.p.id, "audit.read", "store:HG").allowed)
        with self.assertRaises(AuthorizationError):  # different store scope
            self.s.authz.require(self.p.id, "audit.read", "store:OTHER")

    def test_13_revoked_grant_denied(self):
        g = self.s.grant(self.p.id, "audit.read", "store:HG")
        self.assertTrue(self.s.authz.decide(self.p.id, "audit.read", "store:HG").allowed)
        self.s.grants.revoke(g.id, expected_version=1, when=self.s.clock.now())
        self.assertFalse(self.s.authz.decide(self.p.id, "audit.read", "store:HG").allowed)

    def test_14_enforced_below_ui(self):
        # The decision is a pure function of Principal + Capability + Scope + grant state;
        # it takes no UI/visibility input and cannot be bypassed by presentation.
        self.s.grant(self.p.id, "audit.read", "*")   # wildcard scope authority
        self.assertTrue(self.s.authz.require(self.p.id, "audit.read", "store:ANY").allowed)
        self.assertFalse(self.s.authz.decide(self.p.id, "audit.write", "store:ANY").allowed)


if __name__ == "__main__":
    unittest.main()
