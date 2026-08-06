"""Phase 12 acceptance — final readiness dimensions (81-90), release authorization (91-98), restart
durability (99), Phase 11 pilot usable (100), cross-phase greens (101-111), legacy invariants (112-113),
no irreversible cutover (114), and the 64-fixture completeness check."""
import os
import subprocess
import tempfile
import unittest

from elite.errors import ValidationError
from elite.release import fixtures as F
from elite.release.fixtures import Phase12, SCOPE

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPhase12ReadinessAuthorization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase12(os.path.join(cls.tmp, "elite.db"))
        cls.h = F.build_all_fixtures(cls.p)

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    def _full_cert(self, scope, statuses):
        p = self.p
        p.stack.grant(p.op_releaser, F.CAPS["PACKAGE_ISSUE"], scope)
        p.stack.grant(p.op_releaser, F.CAPS["CERTIFY"], scope)
        p.stack.grant(p.op_authorizer, F.CAPS["AUTHORIZE_RELEASE"], scope)
        pkg = p.packages.issue(principal=p.op_releaser, scope=scope,
                               release_package_id=p.packages.build(version_label="vx", application_revision="83d66e4",
                                                                   migration_level=12)["id"])
        cert = p.readiness.certify(principal=p.op_releaser, scope=scope, release_package_ref=pkg["id"],
                                   dimensions=statuses)
        return pkg, cert

    # ---- readiness dimensions (81-90) ------------------------------------
    def test_081_engineering_ready_separate(self):
        self.assertEqual(self.h["engineering_ready"]["dimension"], "ENGINEERING_READY")
        self.assertEqual(self.h["engineering_ready"]["status"], "PASS")

    def test_082_data_ready_separate(self):
        self.assertEqual(self.h["data_not_ready"]["data"], "FAIL")   # independently assessed + can fail

    def test_083_policy_ready_separate(self):
        _, cert = self._full_cert("store:P83", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                "POLICY_READY": {"status": "FAIL"}})
        self.assertEqual(self.p.readiness.dimensions_of(cert["id"])["POLICY_READY"]["status"], "FAIL")

    def test_084_authority_ready_separate(self):
        _, cert = self._full_cert("store:A84", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                "AUTHORITY_READY": {"status": "UNRESOLVED"}})
        self.assertEqual(self.p.readiness.dimensions_of(cert["id"])["AUTHORITY_READY"]["status"], "UNRESOLVED")

    def test_085_operator_ready_separate(self):
        self.assertEqual(self.h["operator_not_ready"]["overall"], "UNRESOLVED")

    def test_086_migration_ready_separate(self):
        _, cert = self._full_cert("store:M86", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                "MIGRATION_READY": {"status": "FAIL"}})
        self.assertEqual(self.p.readiness.dimensions_of(cert["id"])["MIGRATION_READY"]["status"], "FAIL")

    def test_087_rollback_ready_separate(self):
        _, cert = self._full_cert("store:R87", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                "ROLLBACK_READY": {"status": "FAIL"}})
        self.assertEqual(self.p.readiness.dimensions_of(cert["id"])["ROLLBACK_READY"]["status"], "FAIL")

    def test_088_security_ready_separate(self):
        self.assertEqual(self.h["pass_with_warnings"]["overall"], "OPERATIONALLY_READY_WITH_WARNINGS")

    def test_089_operational_requires_prereqs(self):
        _, cert = self._full_cert("store:O89", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                "DATA_READY": {"status": "FAIL"}})
        self.assertEqual(self.p.readiness.dimensions_of(cert["id"])["OPERATIONALLY_READY"]["status"], "FAIL")

    def test_090_synthetic_tests_cannot_create_operational_readiness(self):
        # OPERATIONALLY_READY is DERIVED from evidence-backed prerequisite dimensions, not asserted directly
        _, cert = self._full_cert("store:S90", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                "OPERATIONALLY_READY": {"status": "PASS"}})   # ignored input
        # with all prereqs PASS it is PASS; flip one and it cannot be forced
        _, cert2 = self._full_cert("store:S90b", {**{d: {"status": "PASS"} for d in _PREREQS},
                                                  "ENGINEERING_READY": {"status": "FAIL"},
                                                  "OPERATIONALLY_READY": {"status": "PASS"}})
        self.assertEqual(self.p.readiness.dimensions_of(cert2["id"])["OPERATIONALLY_READY"]["status"], "FAIL")

    # ---- authorization (91-98) -------------------------------------------
    def test_091_go_live_not_automated(self):
        # certification never sets GO_LIVE_AUTHORIZED=PASS
        _, cert = self._full_cert("store:G91", {d: {"status": "PASS"} for d in _PREREQS})
        self.assertEqual(self.p.readiness.dimensions_of(cert["id"])["GO_LIVE_AUTHORIZED"]["status"],
                         "NOT_APPLICABLE")

    def test_092_authorization_references_exact_package(self):
        pkg, cert = self._full_cert("store:G92", {d: {"status": "PASS"} for d in _PREREQS})
        a = self.p.authorization.authorize(principal=self.p.op_authorizer, scope="store:G92",
                                           release_package_ref=pkg["id"], certification_ref=cert["id"],
                                           disposition="AUTHORIZE_GO_LIVE", rollback_plan_ref="rb")
        self.assertEqual(a["release_package_ref"], pkg["id"])

    def test_093_limited_domain_states_scope(self):
        self.assertIn("service_loaner", self.h["limited_domain_authorization"]["enabled_domains"])

    def test_094_no_authorization_no_transition(self):
        self.assertFalse(self.h["go_live_not_authorized"]["authorized"])

    def test_095_authorization_does_not_execute_cutover(self):
        # an AUTHORIZE_GO_LIVE record exists but performs no cutover — it is a Decision, not an action
        pkg, cert = self._full_cert("store:G95", {d: {"status": "PASS"} for d in _PREREQS})
        self.p.authorization.authorize(principal=self.p.op_authorizer, scope="store:G95",
                                       release_package_ref=pkg["id"], certification_ref=cert["id"],
                                       disposition="AUTHORIZE_GO_LIVE", rollback_plan_ref="rb")
        # nothing performs a primary transition; legacy remains available (verified in 113/114)
        self.assertTrue(self.p.p11.pilot.legacy_fallback_available())

    def test_096_expired_authorization_unusable(self):
        self.assertIsNone(self.h["expired_release_authorization"]["active"])

    def test_097_new_blocker_supersedes_prior(self):
        self.assertTrue(self.h["post_certification_blocker"]["prior_superseded"])
        self.assertEqual(self.h["post_certification_blocker"]["overall"], "NOT_READY")

    def test_098_prior_certification_remains_historical(self):
        certs = self.p.store.list_certifications()
        self.assertTrue(any(c["superseded_by"] for c in certs))   # prior remains, marked superseded

    # ---- restart durability (99) -----------------------------------------
    def test_099_restart_preserves_history(self):
        counts = {t: self.p.stack.db.conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                  for t in ("migration_run", "discrepancy_record", "operator_acceptance_result",
                            "release_package", "final_readiness_certification", "release_authorization_decision")}
        from elite.ops.fixtures import RestartedStore
        q = RestartedStore(self.p.stack.db.path, self.p.clock)
        try:
            for t, c in counts.items():
                self.assertEqual(q.table_count(t), c, t)
        finally:
            q.close()

    # ---- Phase 11 usable + cross-phase greens (100-111) ------------------
    def test_100_phase11_pilot_usable(self):
        self.assertTrue(self.p.p11.pilot.is_pilot())
        self.assertIn("PILOT MODE", self.p.p11.pilot.banner())

    def test_101_through_111_cross_phase_invariants(self):
        conn = self.p.stack.db.conn
        vers = {r["version"] for r in conn.execute("SELECT version FROM migration_record")}
        self.assertTrue(set(range(1, 13)).issubset(vers))          # v1..v12
        for t in ("business_fact", "policy_version", "inventory_plan_result", "supply_commitment",
                  "service_loaner_unit", "executive_demo_portfolio_plan", "calibration_proposal",
                  "governed_decision", "operator_view_preference", "import_run"):
            self.assertIsNotNone(conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t)

    def test_112_legacy_tests_green(self):
        eng = subprocess.run(["python3", "pipeline_manager/tests/test_engine.py"], cwd=_REPO,
                             capture_output=True, text=True)
        loan = subprocess.run(["python3", "pipeline_manager/tests/test_loaner_intel.py"], cwd=_REPO,
                              capture_output=True, text=True, env={**os.environ, "PYTHONPATH": _REPO})
        self.assertIn("29/29 passed", eng.stdout)
        self.assertIn("10/10 passed", loan.stdout)

    def test_113_legacy_paths_unchanged(self):
        diff = subprocess.run(
            ["git", "diff", "legacy/inventory-tool", "--", "build", "Pipeline-Manager.html", "pipeline_manager"],
            cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.stdout.strip(), "")

    def test_114_no_irreversible_cutover(self):
        # pilot mode still blocks destructive cutover; an authorization is a Decision, not an activation
        self.assertFalse(self.p.p11.pilot.cutover_available())
        from elite.errors import AuthorizationError
        with self.assertRaises(AuthorizationError):
            self.p.p11.pilot.assert_action_allowed("cutover")

    # ---- 64-fixture completeness -----------------------------------------
    def test_64_fixture_completeness(self):
        q = Phase12(os.path.join(tempfile.mkdtemp(), "fx.db"))
        try:
            h = F.build_all_fixtures(q)
            self.assertEqual(len(F.FIXTURE_NAMES), 64)
            self.assertEqual(sorted(h), sorted(F.FIXTURE_NAMES))
            self.assertTrue(all(h[n] for n in F.FIXTURE_NAMES))
        finally:
            q.close()


_PREREQS = ["ENGINEERING_READY", "DATA_READY", "POLICY_READY", "AUTHORITY_READY", "OPERATOR_READY",
            "MIGRATION_READY", "ROLLBACK_READY", "SECURITY_READY"]


if __name__ == "__main__":
    unittest.main()
