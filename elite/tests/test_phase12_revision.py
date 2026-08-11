"""Phase 12 runtime-revision regression.

Proves the real launcher stamps a correct technical build/release identity (`revision`) on diagnostic
logs, resolved once from the runtime configuration — never the fixture "test" default:

  A. real launcher (ELITE_ENV=pilot, no ELITE_REVISION) -> logger revision "pilot" (the environment value);
  B. real launcher with an explicit ELITE_REVISION -> that exact value;
  C. the real launcher never emits revision="test" (the base-Stack default does not leak through);
  D. fixture/test construction still defaults to revision="test" (deterministic);
  E. environment stays "pilot" and is independent of revision;
  F. revision is NOT persisted into audit_event / governance rows (schema unchanged);
  G. the production-runtime protections proven earlier remain intact.

No schema change — the store schema remains v12.
"""
import io
import os
import tempfile
import unittest

from elite.clock import SystemClock
from elite.db import connect, current_version
from elite.environment import Environment, resolve_revision
from elite.release.fixtures import Phase12
from elite.ui.serve import build_app

REAL_PEPPER = "S1-real-production-pepper"
REAL_SCOPE = "store:HG_INFINITI_JACKSON"


class TestRuntimeRevision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "elite.db")
        self._prev = {k: os.environ.get(k)
                      for k in ("ELITE_ENV", "ELITE_AUTH_SECRET", "ELITE_PILOT_SCOPE",
                                "ELITE_REVISION", "ELITE_SINGLE_OPERATOR_PILOT")}
        os.environ["ELITE_ENV"] = "pilot"
        os.environ["ELITE_AUTH_SECRET"] = REAL_PEPPER
        os.environ["ELITE_PILOT_SCOPE"] = REAL_SCOPE
        os.environ.pop("ELITE_REVISION", None)
        os.environ.pop("ELITE_SINGLE_OPERATOR_PILOT", None)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # A. no ELITE_REVISION -> environment value ---------------------------------
    def test_A_default_revision_is_environment_value(self):
        app = build_app(db_path=self.db)
        self.assertEqual(app.stack.logger.revision, "pilot")   # falls back to environment value
        self.assertEqual(resolve_revision(os.environ, environment=Environment.PILOT), "pilot")

    # B. explicit ELITE_REVISION -> that exact value ----------------------------
    def test_B_explicit_revision_used_verbatim(self):
        os.environ["ELITE_REVISION"] = "2026.08.11-abc1234"
        app = build_app(db_path=self.db)
        self.assertEqual(app.stack.logger.revision, "2026.08.11-abc1234")

    # C. the real launcher never emits revision="test" --------------------------
    def test_C_real_launcher_never_emits_test_revision(self):
        app = build_app(db_path=self.db)
        self.assertNotEqual(app.stack.logger.revision, "test")
        buf = io.StringIO()
        app.stack.logger.stream = buf
        app.stack.logger.info("bootstrap.probe", result="ok")
        line = buf.getvalue()
        self.assertIn('"revision": "pilot"', line)
        self.assertNotIn('"revision": "test"', line)
        self.assertIn('"environment": "pilot"', line)

    # D. fixture/test construction still defaults to "test" ---------------------
    def test_D_fixture_defaults_to_test_revision(self):
        p = Phase12(os.path.join(self.tmp, "fixture.db"), seed=False)   # no runtime -> defaults
        try:
            self.assertEqual(p.stack.logger.revision, "test")
        finally:
            p.close()

    # E. environment stays pilot and is independent of revision -----------------
    def test_E_environment_independent_of_revision(self):
        os.environ["ELITE_REVISION"] = "build-XYZ"
        app = build_app(db_path=self.db)
        self.assertIs(app.stack.environment, Environment.PILOT)   # environment unchanged by revision
        self.assertEqual(app.environment, "pilot")
        self.assertEqual(app.stack.logger.revision, "build-XYZ")  # revision is the separate build identity

    # F. revision is NOT persisted into audit_event ----------------------------
    def test_F_revision_not_persisted_in_audit(self):
        build_app(db_path=self.db)
        c = connect(self.db)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(audit_event)").fetchall()]
        c.close()
        self.assertNotIn("revision", cols)   # governance record carries environment, not revision

    # G. production-runtime protections remain intact ---------------------------
    def test_G_production_runtime_protections_preserved(self):
        app = build_app(db_path=self.db)
        self.assertIs(app.stack.environment, Environment.PILOT)
        self.assertIsInstance(app.stack.clock, SystemClock)
        self.assertEqual(app.pilot_scope, REAL_SCOPE)
        self.assertIsNotNone(getattr(app, "live_executor", None))
        c = connect(self.db)
        self.assertEqual(current_version(c), 12)
        self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM capability_grant").fetchone()["n"], 0)
        c.close()
        pid = app.stack.authn.register("rt", "pw").id
        self.assertEqual(app.stack.authn.authenticate(pid, "pw").id, pid)


if __name__ == "__main__":
    unittest.main()
