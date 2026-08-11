"""Phase 12 store-scope runtime-alignment regression.

Proves the real launcher/login/authorization all operate at ONE authoritative store scope resolved from
``ELITE_PILOT_SCOPE`` (single source of truth on ``RuntimeConfig``) — never a hardcoded ``store:HG``:

  A. build_app resolves the exact configured scope onto the app;
  B. the login form defaults (read-only) to that exact scope;
  C. a login POST that supplies no scope authenticates at that exact scope;
  D. authorization succeeds for a capability granted at the configured scope;
  E. a store:HG grant does NOT satisfy the configured scope, and vice versa (opaque exact match);
  F. the real runtime fails closed (ConfigurationError) when ELITE_PILOT_SCOPE is missing/empty;
  G. test/fixture construction stays deterministic (App default scope + resolve_pilot_scope default);
  H. the production-runtime protections proven earlier remain intact.

No schema change — the store schema remains v12.
"""
import os
import tempfile
import unittest

from elite.clock import SystemClock
from elite.db import connect, current_version
from elite.environment import Environment, resolve_pilot_scope
from elite.errors import ConfigurationError
from elite.fixtures import RuntimeConfig
from elite.ui.fixtures import Phase10
from elite.ui.serve import build_app

REAL_SCOPE = "store:HG_INFINITI_JACKSON"
REAL_PEPPER = "S1-real-production-pepper"


class TestStoreScopeRuntimeAlignment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "elite.db")
        self._prev = {k: os.environ.get(k)
                      for k in ("ELITE_ENV", "ELITE_AUTH_SECRET", "ELITE_PILOT_SCOPE",
                                "ELITE_SINGLE_OPERATOR_PILOT")}
        os.environ["ELITE_ENV"] = "pilot"
        os.environ["ELITE_AUTH_SECRET"] = REAL_PEPPER
        os.environ["ELITE_PILOT_SCOPE"] = REAL_SCOPE
        os.environ.pop("ELITE_SINGLE_OPERATOR_PILOT", None)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # A. the launcher resolves the exact configured scope -----------------------
    def test_A_launcher_resolves_configured_scope(self):
        app = build_app(db_path=self.db)
        self.assertEqual(app.pilot_scope, REAL_SCOPE)
        # RuntimeConfig carries it as the single source of truth (no independent re-parsing).
        rc = RuntimeConfig(pepper="x", clock=SystemClock(), environment=Environment.PILOT,
                           pilot_scope=resolve_pilot_scope(os.environ))
        self.assertEqual(rc.pilot_scope, REAL_SCOPE)

    # B. the login form defaults (read-only) to the configured scope ------------
    def test_B_login_form_defaults_to_configured_scope(self):
        app = build_app(db_path=self.db)
        resp = app.handle("GET", "/login")
        html = resp.body if isinstance(resp.body, str) else resp.body.decode()
        self.assertIn(f'value="{REAL_SCOPE}"', html)     # pre-filled with the exact scope
        self.assertIn("readonly", html)                  # not user-editable in the single-store pilot
        self.assertNotIn('value="store:HG"', html)       # the old hardcoded default is gone

    # C. a default login POST (no scope field) authenticates at the exact scope --
    def test_C_login_post_without_scope_uses_configured_scope(self):
        app = build_app(db_path=self.db)
        pid = app.stack.authn.register("Kyle Montgomery — Elite Pipeline Administrator", "pw").id
        app.handle("POST", "/login", form={"principal_id": pid, "secret": "pw"})   # NO scope supplied
        sessions = list(app.sessions.values())
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].scope, REAL_SCOPE)  # landed at the configured scope, not store:HG

    # D. authorization succeeds for a capability granted at the configured scope -
    def test_D_authorization_at_configured_scope(self):
        app = build_app(db_path=self.db)
        pid = app.stack.authn.register("admin", "pw").id
        app.stack.grant(pid, "authority.grant", REAL_SCOPE)
        self.assertTrue(app.stack.authz.decide(pid, "authority.grant", REAL_SCOPE).allowed)

    # E. store:HG and the configured scope never satisfy each other -------------
    def test_E_scope_is_exact_match_not_prefix(self):
        app = build_app(db_path=self.db)
        p_full = app.stack.authn.register("full-scope", "pw").id
        app.stack.grant(p_full, "authority.grant", REAL_SCOPE)
        # a grant at the full ratified scope does NOT satisfy a bare store:HG request
        self.assertFalse(app.stack.authz.decide(p_full, "authority.grant", "store:HG").allowed)
        # and a bare store:HG grant does NOT satisfy the ratified scope
        p_hg = app.stack.authn.register("hg-scope", "pw").id
        app.stack.grant(p_hg, "authority.grant", "store:HG")
        self.assertFalse(app.stack.authz.decide(p_hg, "authority.grant", REAL_SCOPE).allowed)

    # F. real runtime fails closed on a missing/empty ELITE_PILOT_SCOPE ---------
    def test_F_missing_or_empty_scope_fails_closed(self):
        os.environ.pop("ELITE_PILOT_SCOPE", None)
        with self.assertRaises(ConfigurationError):
            build_app(db_path=self.db)                    # absent -> fail closed, no store:HG fallback
        os.environ["ELITE_PILOT_SCOPE"] = "   "
        with self.assertRaises(ConfigurationError):
            build_app(db_path=self.db)                    # empty/whitespace -> fail closed
        with self.assertRaises(ConfigurationError):
            resolve_pilot_scope({})                       # resolver itself fails closed with no default

    # G. test/fixture construction stays deterministic --------------------------
    def test_G_fixture_defaults_remain_deterministic(self):
        # The resolver, given an explicit default, returns it for absent/empty values.
        self.assertEqual(resolve_pilot_scope({}, default="store:HG"), "store:HG")
        self.assertEqual(resolve_pilot_scope({"ELITE_PILOT_SCOPE": ""}, default="store:HG"), "store:HG")
        # The fixture UI app (constructed without a RuntimeConfig) keeps the deterministic store:HG default.
        p10 = Phase10(os.path.join(self.tmp, "fixture.db"), seed=False)
        self.assertEqual(p10.app.pilot_scope, "store:HG")

    # H. production-runtime protections remain intact ---------------------------
    def test_H_production_runtime_protections_preserved(self):
        app = build_app(db_path=self.db)
        self.assertIs(app.stack.environment, Environment.PILOT)        # real environment
        self.assertIsInstance(app.stack.clock, SystemClock)           # real clock, not FixedClock
        self.assertIsNotNone(getattr(app, "live_executor", None))     # Phase 12 live executor wired
        c = connect(self.db)
        self.assertEqual(current_version(c), 12)                      # schema stays v12
        self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM capability_grant").fetchone()["n"], 0)  # seed=False
        c.close()
        # pepper is the real ELITE_AUTH_SECRET: a credential registered here authenticates under it.
        pid = app.stack.authn.register("rt", "pw").id
        self.assertEqual(app.stack.authn.authenticate(pid, "pw").id, pid)


if __name__ == "__main__":
    unittest.main()
