"""Phase 8 acceptance — migration durability (79-80), cross-phase greens incl. legacy 39/39 (81-89),
no-out-of-scope-behavior guard (90) + 60-fixture completeness."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.learning.fixtures import Phase8, build_all_scenarios, SCENARIO_NAMES

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase8MigrationCross(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase8(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_79_migration_v8_survives_restart(self):
        pr = self.p.prediction(value=10)
        applied = [r["version"] for r in self.p.stack.db.conn.execute("SELECT version FROM migration_record").fetchall()]
        self.assertIn(8, applied)
        self.p.close()
        p2 = Phase8(self.dbp)
        self.addCleanup(p2.close)
        self.assertGreaterEqual(p2.stack.db.version(), 8)
        self.assertIsNotNone(p2.store.get_prediction(pr.id))

    def test_80_migration_v8_rerun_safe(self):
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase8(self.dbp)
        self.addCleanup(p2.close)
        after = p2.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual(before, after)
        applied = [r["version"] for r in p2.stack.db.conn.execute("SELECT version FROM migration_record").fetchall()]
        self.assertEqual(len(applied), len(set(applied)))

    def test_81_phase1_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_authz", "elite.tests.test_persistence",
                              "elite.tests.test_config_env", "elite.tests.test_audit_logging"])
        self.assertEqual(f, 0)

    def test_82_phase2_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase2_data", "elite.tests.test_phase2_facts",
                              "elite.tests.test_phase2_identity"])
        self.assertEqual(f, 0)

    def test_83_phase3_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase3_policy", "elite.tests.test_phase3_versions",
                              "elite.tests.test_phase3_scenario_gov"])
        self.assertEqual(f, 0)

    def test_84_phase4_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase4_combination", "elite.tests.test_phase4_supply",
                              "elite.tests.test_phase4_forecast_planning", "elite.tests.test_phase4_bug_cpo_002"])
        self.assertEqual(f, 0)

    def test_85_phase5_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase5_cpo", "elite.tests.test_phase5_ctp",
                              "elite.tests.test_phase5_bug_cpo_002_e2e"])
        self.assertEqual(f, 0)

    def test_86_phase6_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase6_snapshot_membership",
                              "elite.tests.test_phase6_retirement_handoff",
                              "elite.tests.test_phase6_migration_cross"])
        self.assertEqual(f, 0)

    def test_87_phase7_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase7_unit_portfolio",
                              "elite.tests.test_phase7_economics_designation_retirement",
                              "elite.tests.test_phase7_migration_cross"])
        self.assertEqual(f, 0)

    def test_88_legacy_tests_remain_green(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        for script in ("pipeline_manager/tests/test_engine.py", "pipeline_manager/tests/test_loaner_intel.py"):
            r = subprocess.run(["python3", script], cwd=_REPO, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("passed", r.stdout + r.stderr)

    def test_89_legacy_application_paths_unchanged(self):
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
                              cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])

    def test_90_no_out_of_scope_behavior(self):
        import elite.learning.attribution as _at
        import elite.learning.boundaries as _bo
        import elite.learning.calibration as _ca
        import elite.learning.comparison as _co
        import elite.learning.error as _er
        import elite.learning.observation as _ob
        import elite.learning.pairing as _pa
        import elite.learning.prediction as _pr
        import elite.learning.signal as _si
        import elite.learning.validation as _va
        # Completed Phase-9 Governance, full Decision workspace, broad Scenario administration,
        # Phase-10 UX, operational hardening, and migration/cutover are NOT introduced here.
        forbidden = ("phase9", "workspace", "cutover", "hardening", "scenario_admin", "ux_", "operational_harden")
        for mod in (_at, _bo, _ca, _co, _er, _ob, _pa, _pr, _si, _va):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"out-of-scope symbol {name} in {mod.__name__}")
        # Learning never mutates active policy directly: calibration.py touches no policy_version write.
        self.assertNotIn("policy_version", open(_ca.__file__).read())

    def test_90b_all_60_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 60)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
