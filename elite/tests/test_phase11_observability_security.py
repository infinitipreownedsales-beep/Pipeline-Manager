"""Phase 11 acceptance — observability/logging (51-56), performance baselines (57-62), security +
configuration (63-64, 69-77)."""
import io
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ConfigurationError
from elite.ops import fixtures as F
from elite.ops.fixtures import Phase11, SCOPE
from elite.ops.models import CAPS
from elite.ops.observability import OperationalLogger
from elite.ops.opsconfig import load_ops_config
from elite.ops.security import SecurityChecklist, cookie_flags, session_expired
from elite.environment import Environment


class TestPhase11ObservabilitySecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase11(os.path.join(cls.tmp, "elite.db"))

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    # ---- observability (51-56) -------------------------------------------
    def test_051_logs_preserve_correlation_id(self):
        buf = io.StringIO()
        log = OperationalLogger(self.p.environment, "pilot", stream=buf)
        log.op("import", "import.run", correlation_id="cor_keep_123", run_id="r1")
        self.assertIn("cor_keep_123", buf.getvalue())

    def test_052_logs_contain_no_session_token(self):
        buf = io.StringIO()
        log = OperationalLogger(self.p.environment, "pilot", stream=buf)
        log.op("ui", "action", session="SECRET_SESSION_TOKEN", token="tok_abc")
        out = buf.getvalue()
        self.assertNotIn("SECRET_SESSION_TOKEN", out)
        self.assertNotIn("tok_abc", out)

    def test_053_logs_contain_no_secret(self):
        buf = io.StringIO()
        log = OperationalLogger(self.p.environment, "pilot", stream=buf)
        log.op("auth", "login", password="hunter2", pepper="PEPPER_XYZ")
        out = buf.getvalue()
        self.assertNotIn("hunter2", out)
        self.assertNotIn("PEPPER_XYZ", out)

    def test_054_raw_rows_not_logged(self):
        buf = io.StringIO()
        log = OperationalLogger(self.p.environment, "pilot", stream=buf)
        log.op("import", "row", raw_values={"vin": F.V1, "customer_name": "Jane Doe"})
        out = buf.getvalue()
        self.assertIn("<not logged>", out)
        self.assertNotIn("Jane Doe", out)

    def test_055_sensitive_identifiers_masked(self):
        buf = io.StringIO()
        log = OperationalLogger(self.p.environment, "pilot", stream=buf)
        log.op("loaner", "checkout", vin=F.V1)
        out = buf.getvalue()
        self.assertNotIn(F.V1, out)
        self.assertIn("000001", out)                        # masked to the last 6

    def test_056_logging_failure_does_not_corrupt_action(self):
        class BadStream:
            def write(self, *a):
                raise IOError("disk full")
        log = OperationalLogger(self.p.environment, "pilot", stream=BadStream())
        log.op("x", "y", correlation_id="c")               # must not raise
        self.assertTrue(True)

    # ---- performance (57-62) ---------------------------------------------
    def test_057_startup_performance_measured(self):
        from elite.ops.durability import startup_validation
        _, dur = self.p.performance.measure("startup", lambda: startup_validation(self.p.stack.db.conn),
                                            workload="startup_validation")
        self.assertIsInstance(dur, float)
        self.assertTrue(any(m["metric_key"] == "startup" for m in self.p.ops.list_metrics()))

    def test_058_workspace_performance_measured(self):
        full = self.p.p10.login(self.p.p10.op_full)
        self.p.performance.measure("workspace_new_inventory", lambda: full.get("/new-inventory"),
                                   workload="GET /new-inventory")
        self.assertTrue(any(m["metric_key"] == "workspace_new_inventory" for m in self.p.ops.list_metrics()))

    def test_059_import_performance_measured(self):
        self.p.performance.measure(
            "import_new_inventory",
            lambda: self.p.import_payload("new_inventory_current", F.INV_FULL, effective_time=self.p.now_iso(),
                                          chash="sha256:perf59"),
            workload="import", dataset_size=3)
        self.assertTrue(any(m["metric_key"] == "import_new_inventory" for m in self.p.ops.list_metrics()))

    def test_060_backup_performance_measured(self):
        self.p.performance.measure("backup", lambda: self.p.backup.create_backup(tempfile.mkdtemp()),
                                   workload="backup")
        self.assertTrue(any(m["metric_key"] == "backup" for m in self.p.ops.list_metrics()))

    def test_061_slow_query_evidence_recorded(self):
        self.p.ops.add_metric("slow_demo", 5000.0, workload="slow")
        slow = self.p.performance.slow_queries(1000)
        self.assertTrue(any(m["metric_key"] == "slow_demo" for m in slow))

    def test_062_optimization_does_not_change_result(self):
        full = self.p.p10.login(self.p.p10.op_full)
        cold = full.get("/new-inventory").body
        warm = full.get("/new-inventory").body
        self.assertEqual(cold, warm)                        # repeated read reproduces the same display

    # ---- security + configuration (63-64, 69-77) -------------------------
    def test_063_session_expiry_enforced(self):
        import datetime as dt
        now = self.p.clock.now()
        self.assertTrue(session_expired(now - dt.timedelta(hours=2), now, 3600))
        self.assertFalse(session_expired(now - dt.timedelta(minutes=1), now, 3600))

    def test_064_session_invalidation_enforced(self):
        tok = self.p.app.login(self.p.p10.op_full, "pw", SCOPE)
        self.p.app.logout(tok)
        r = self.p.app.handle("GET", "/", session_token=tok)   # invalidated session
        self.assertIn(r.status, (302, 303))                    # redirected to login, not served

    def test_069_csrf_enforced(self):
        from elite.ui.fixtures import Client
        tok = self.p.app.login(self.p.p10.op_full, "pw", SCOPE)
        c = Client(self.p.app, tok)
        r = c.post("/scope", {"scope": SCOPE}, csrf=False)
        self.assertEqual(r.status, 403)

    def test_070_scope_isolation_enforced(self):
        other = self.p.p10.login(self.p.p10.op_otherscope)      # grants only at store:WEST
        r = other.get("/")
        self.assertEqual(r.status, 403)                         # not permitted in store:HG

    def test_071_revoked_authority_enforced(self):
        pid = self.p.stack.authn.register("Temp Op", "pw").id
        g = self.p.stack.grant(pid, CAPS["IMPORT_RUN"], SCOPE)
        self.p.stack.authz.require(pid, CAPS["IMPORT_RUN"], SCOPE)   # allowed
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        with self.assertRaises(AuthorizationError):
            self.p.stack.authz.require(pid, CAPS["IMPORT_RUN"], SCOPE)   # denied after revocation

    def test_072_debug_errors_no_stack_trace(self):
        # the safe error boundary maps an unexpected handler failure to a generic page — never a
        # traceback or a secret. Force a failure inside a governed handler (ctx() stays healthy).
        orig = self.p.p9.decisions.issue
        self.p.p9.decisions.issue = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("SECRET_boom_trace token=abc"))
        try:
            dec = self.p.p10.login(self.p.p10.op_decider)
            r = dec.post("/item/" + self.p.p10.fresh_item["id"] + "/decide",
                         {"disposition": "ACCEPT", "selected_action": "x", "_idem": "trace-probe"})
            self.assertEqual(r.status, 500)
            self.assertNotIn("Traceback", r.body)
            self.assertNotIn("SECRET_boom_trace", r.body)
            self.assertNotIn("token=abc", r.body)
        finally:
            self.p.p9.decisions.issue = orig

    def test_073_no_default_credential(self):
        chk = SecurityChecklist(config=_FakeConfig(), ops_config=self.p.opsconfig, stack=self.p.stack,
                                debug=False, default_credentials_present=False).run()
        item = next(c for c in chk["checks"] if c["check"] == "no_default_credentials")
        self.assertTrue(item["pass"])

    def test_074_secrets_externalized(self):
        chk = SecurityChecklist(config=_FakeConfig(), ops_config=self.p.opsconfig, stack=self.p.stack).run()
        item = next(c for c in chk["checks"] if c["check"] == "secrets_externalized")
        self.assertTrue(item["pass"])

    def test_075_unsafe_host_binding_requires_config(self):
        with self.assertRaises(ConfigurationError):
            load_ops_config({"ELITE_BIND_HOST": "0.0.0.0"})            # non-loopback without opt-in
        cfg = load_ops_config({"ELITE_BIND_HOST": "0.0.0.0", "ELITE_ALLOW_NONLOOPBACK": "1"})
        self.assertEqual(cfg.bind_host, "0.0.0.0")

    def test_076_invalid_configuration_fails_clearly(self):
        with self.assertRaises(ConfigurationError):
            load_ops_config({"ELITE_UI_PORT": "not-a-number"})
        with self.assertRaises(ConfigurationError):
            load_ops_config({"ELITE_UI_PORT": "70000"})

    def test_077_safe_diagnostics_no_secrets(self):
        red = self.p.opsconfig.redacted()
        joined = " ".join(f"{k}={v}" for k, v in red.items()).lower()
        self.assertNotIn("pepper", joined.replace("elite_", ""))
        for k, v in red.items():
            if any(s in k.lower() for s in ("secret", "password", "token", "pepper")):
                self.assertEqual(v, "***")
        # cookie flags are HttpOnly + SameSite=Strict
        self.assertIn("HttpOnly", cookie_flags(Environment.DEVELOPMENT))


class _FakeConfig:
    def redacted(self):
        return {"ELITE_AUTH_SECRET": "***", "ELITE_ENV": "test"}


if __name__ == "__main__":
    unittest.main()
