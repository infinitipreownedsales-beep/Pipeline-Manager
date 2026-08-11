"""Phase 12 production-runtime configuration regression.

Proves the ACTUAL shipped launcher (`elite.ui.serve.build_app`, run by `python -m elite.ui.serve`)
constructs the base Stack with REAL runtime configuration — the credential pepper from ELITE_AUTH_SECRET,
a real system clock, and the explicit ELITE_ENV environment — instead of the fixture defaults
(`test-pepper` / FixedClock / TEST), while test/fixture constructors keep those deterministic defaults.
"""
import os
import tempfile
import unittest

from elite.auth import Authenticator
from elite.clock import FixedClock, SystemClock
from elite.environment import Environment
from elite.errors import AuthenticationError, ConfigurationError
from elite.release.fixtures import Phase12
from elite.ui.serve import build_app

REAL_PEPPER = "S1-real-production-pepper"


class TestProductionRuntimeConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "elite.db")
        self._prev = {k: os.environ.get(k)
                      for k in ("ELITE_ENV", "ELITE_AUTH_SECRET", "ELITE_PILOT_SCOPE",
                                "ELITE_SINGLE_OPERATOR_PILOT")}
        os.environ["ELITE_ENV"] = "pilot"
        os.environ["ELITE_AUTH_SECRET"] = REAL_PEPPER
        os.environ["ELITE_PILOT_SCOPE"] = "store:HG_INFINITI_JACKSON"
        os.environ.pop("ELITE_SINGLE_OPERATOR_PILOT", None)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # A. PEPPER --------------------------------------------------------------
    def test_A_pepper_is_elite_auth_secret(self):
        app = build_app(db_path=self.db)
        st = app.stack
        p = st.authn.register("Dealer Principal", "correct-horse-battery")
        # a credential created under S1 authenticates under S1
        self.assertIsNotNone(st.authn.authenticate(p.id, "correct-horse-battery"))
        # the same credential does NOT authenticate under the fixture "test-pepper"
        with self.assertRaises(AuthenticationError):
            Authenticator(st.principals, "test-pepper").authenticate(p.id, "correct-horse-battery")
        # a different secret S2 does NOT authenticate
        with self.assertRaises(AuthenticationError):
            Authenticator(st.principals, "S2-different-secret").authenticate(p.id, "correct-horse-battery")
        # the secret value is never persisted anywhere in the database
        conn = st.db.conn
        for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            for row in conn.execute('SELECT * FROM "%s"' % t):
                for val in tuple(row):
                    if isinstance(val, str):
                        self.assertNotIn(REAL_PEPPER, val)

    # B. MISSING SECRET ------------------------------------------------------
    def test_B_missing_secret_fails_closed(self):
        os.environ.pop("ELITE_AUTH_SECRET", None)
        with self.assertRaises(ConfigurationError):
            build_app(db_path=self.db)                      # absent -> fail closed, no fallback
        os.environ["ELITE_AUTH_SECRET"] = "   "
        with self.assertRaises(ConfigurationError):
            build_app(db_path=self.db)                      # empty/whitespace -> fail closed

    # C. CLOCK ---------------------------------------------------------------
    def test_C_real_clock_not_fixed(self):
        app = build_app(db_path=self.db)
        self.assertIsInstance(app.stack.clock, SystemClock)
        self.assertNotIsInstance(app.stack.clock, FixedClock)
        # test/fixture construction retains FixedClock determinism
        p = Phase12(os.path.join(tempfile.mkdtemp(), "t.db"), seed=False)   # no runtime -> defaults
        try:
            self.assertIsInstance(p.stack.clock, FixedClock)
        finally:
            p.close()

    # D. ENVIRONMENT ---------------------------------------------------------
    def test_D_environment_pilot_not_test(self):
        app = build_app(db_path=self.db)
        self.assertIs(app.stack.environment, Environment.PILOT)
        self.assertIsNot(app.stack.environment, Environment.TEST)
        self.assertEqual(app.environment, "pilot")
        self.assertEqual(app.stack.metadata.get("environment"), "pilot")   # DB stamped pilot, not test
        # test/fixture construction still resolves TEST by default
        p = Phase12(os.path.join(tempfile.mkdtemp(), "t2.db"), seed=False)
        try:
            self.assertIs(p.stack.environment, Environment.TEST)
        finally:
            p.close()

    # E. STACK (Phase 12 wired, seed off, real live executor) ----------------
    def test_E_stack_phase12_wired_seed_off(self):
        app = build_app(db_path=self.db)
        self.assertIsNotNone(getattr(app, "live_executor", None))
        self.assertTrue(app.live_executor.registry.has("executive_demo.retirement.execute"))
        self.assertFalse(app.live_executor.registry.is_synthetic("executive_demo.retirement.execute"))
        self.assertEqual(app.stack.db.conn.execute("SELECT COUNT(*) c FROM principal").fetchone()["c"], 0)

    # F. DATABASE SAFETY (no seeded principals/grants/jobs/domain records) ----
    def test_F_no_seeded_governance_or_dealership_data(self):
        app = build_app(db_path=self.db)
        conn = app.stack.db.conn
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        for table in ("principal", "capability_grant", "scheduled_job", "workspace_item",
                      "governed_decision", "execution_authorization", "executive_demo_unit",
                      "service_loaner_unit", "inventory_plan_result", "business_fact"):
            if table in existing:
                self.assertEqual(conn.execute('SELECT COUNT(*) c FROM "%s"' % table).fetchone()["c"], 0,
                                 f"{table} must be empty at launcher startup")


if __name__ == "__main__":
    unittest.main()
