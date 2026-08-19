"""Live-style regression for the identity-governance permission defect.

Reproduces the real launcher path (build_app, seed=False, real pepper/scope): a manager principal provisioned
BEFORE `identity.govern` existed does not hold it, so the governed Translation bootstrap fails closed with
"Not permitted". The startup backfill grants `identity.govern` — through the normal grant mechanism — to
principals who already hold governance authority (`authority.grant`), and never to view-only users, so the wall
is preserved."""
import os
import tempfile
import unittest

from elite.ui.serve import build_app

REAL_SCOPE = "store:HG_INFINITI_JACKSON"
REAL_PEPPER = "S1-real-production-pepper"


class TestIdentityGovernanceGrant(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "elite.db")
        self._prev = {k: os.environ.get(k) for k in
                      ("ELITE_ENV", "ELITE_AUTH_SECRET", "ELITE_PILOT_SCOPE", "ELITE_SINGLE_OPERATOR_PILOT")}
        os.environ["ELITE_ENV"] = "pilot"
        os.environ["ELITE_AUTH_SECRET"] = REAL_PEPPER
        os.environ["ELITE_PILOT_SCOPE"] = REAL_SCOPE
        os.environ.pop("ELITE_SINGLE_OPERATOR_PILOT", None)

    def tearDown(self):
        for k, v in self._prev.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def _register(self, app, name, caps):
        pid = app.stack.authn.register(name, "pw").id
        for c in caps:
            app.stack.grant(pid, c, REAL_SCOPE)
        return pid

    def _post_bootstrap(self, app, pid):
        tok = app.login(pid, "pw", REAL_SCOPE)
        csrf = app.sessions[tok].csrf_token
        return app.handle("POST", "/admin/translation/import-reviewed-charts",
                          form={"_csrf": csrf}, session_token=tok)

    # a manager provisioned before identity.govern existed is backfilled on the next launch; bootstrap then works
    def test_manager_backfilled_and_bootstrap_succeeds(self):
        app = build_app(db_path=self.db)
        # GSM/admin manager bundle as provisioned earlier — governance authority, but NO identity.govern yet
        kyle = self._register(app, "Kyle Montgomery — GSM", ["workspace.view", "workspace.review",
                                                              "authority.view", "authority.grant"])
        self.assertFalse(app.stack.authz.decide(kyle, "identity.govern", REAL_SCOPE).allowed)   # the live defect
        # the governed bootstrap is denied at this point (the reported "Not permitted")
        self.assertEqual(self._post_bootstrap(app, kyle).status, 403)

        app2 = build_app(db_path=self.db)                        # restart -> startup backfill runs
        self.assertTrue(app2.stack.authz.decide(kyle, "identity.govern", REAL_SCOPE).allowed)  # granted normally
        self.assertEqual(self._post_bootstrap(app2, kyle).status, 303)                          # bootstrap works

    # the wall is preserved: a view-only user is never backfilled and is still denied the governed action
    def test_view_only_user_still_walled_out(self):
        app = build_app(db_path=self.db)
        viewer = self._register(app, "Sales Viewer", ["workspace.view"])   # no governance authority
        build_app(db_path=self.db)                                          # backfill runs again
        app2 = build_app(db_path=self.db)
        self.assertFalse(app2.stack.authz.decide(viewer, "identity.govern", REAL_SCOPE).allowed)
        self.assertEqual(self._post_bootstrap(app2, viewer).status, 403)   # governed action still refused

    # the backfill is idempotent — running it repeatedly grants nothing new the second time
    def test_backfill_is_idempotent(self):
        from elite.identity.provision import ensure_identity_governance_grants
        app = build_app(db_path=self.db)
        self._register(app, "Manager", ["authority.grant"])
        first = ensure_identity_governance_grants(app.stack)
        second = ensure_identity_governance_grants(app.stack)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
