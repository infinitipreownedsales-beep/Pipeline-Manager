"""Phase 9 acceptance — migration durability (101-102), cross-phase greens incl. legacy 39/39
(103-112), no-out-of-scope-behavior guard (113) + 80-fixture completeness."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.govern.fixtures import Phase9, build_all_scenarios, SCENARIO_NAMES

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase9MigrationCross(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase9(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_101_migration_v9_survives_restart(self):
        it = self.p.item(rec="rec_r")
        applied = [r["version"] for r in self.p.stack.db.conn.execute("SELECT version FROM migration_record").fetchall()]
        self.assertIn(9, applied)
        self.p.close()
        p2 = Phase9(self.dbp)
        self.addCleanup(p2.close)
        self.assertGreaterEqual(p2.stack.db.version(), 9)
        self.assertIsNotNone(p2.store.get_workspace_item(it["id"]))

    def test_102_migration_v9_rerun_safe(self):
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase9(self.dbp)
        self.addCleanup(p2.close)
        after = p2.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual(before, after)
        applied = [r["version"] for r in p2.stack.db.conn.execute("SELECT version FROM migration_record").fetchall()]
        self.assertEqual(len(applied), len(set(applied)))

    def test_103_phase1_green(self):
        _r, f = _run_modules(["elite.tests.test_authz", "elite.tests.test_persistence",
                              "elite.tests.test_audit_logging"])
        self.assertEqual(f, 0)

    def test_104_phase2_green(self):
        _r, f = _run_modules(["elite.tests.test_phase2_data", "elite.tests.test_phase2_identity"])
        self.assertEqual(f, 0)

    def test_105_phase3_green(self):
        _r, f = _run_modules(["elite.tests.test_phase3_policy", "elite.tests.test_phase3_versions"])
        self.assertEqual(f, 0)

    def test_106_phase4_green(self):
        _r, f = _run_modules(["elite.tests.test_phase4_supply", "elite.tests.test_phase4_forecast_planning",
                              "elite.tests.test_phase4_bug_cpo_002"])
        self.assertEqual(f, 0)

    def test_107_phase5_green(self):
        _r, f = _run_modules(["elite.tests.test_phase5_cpo", "elite.tests.test_phase5_bug_cpo_002_e2e"])
        self.assertEqual(f, 0)

    def test_108_phase6_green(self):
        _r, f = _run_modules(["elite.tests.test_phase6_snapshot_membership", "elite.tests.test_phase6_migration_cross"])
        self.assertEqual(f, 0)

    def test_109_phase7_green(self):
        _r, f = _run_modules(["elite.tests.test_phase7_unit_portfolio", "elite.tests.test_phase7_migration_cross"])
        self.assertEqual(f, 0)

    def test_110_phase8_green(self):
        _r, f = _run_modules(["elite.tests.test_phase8_prediction_observation",
                              "elite.tests.test_phase8_calibration_validation",
                              "elite.tests.test_phase8_learning_governance_regression"])
        self.assertEqual(f, 0)

    def test_111_legacy_tests_green(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        for script in ("pipeline_manager/tests/test_engine.py", "pipeline_manager/tests/test_loaner_intel.py"):
            r = subprocess.run(["python3", script], cwd=_REPO, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("passed", r.stdout + r.stderr)

    def test_112_legacy_paths_unchanged(self):
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
                              cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])

    def test_113_no_out_of_scope_behavior(self):
        import elite.govern.authority as _au
        import elite.govern.calibration_workspace as _cw
        import elite.govern.decision as _de
        import elite.govern.execution as _ex
        import elite.govern.queues as _qu
        import elite.govern.readiness as _rd
        import elite.govern.scenario_admin as _sa
        import elite.govern.workspace as _ws
        # No full Phase-10 UX, operational hardening, live deployment, migration, or cutover here.
        forbidden = ("deploy", "cutover", "hardening", "live_source", "render_ui", "visualize", "phase10",
                     "migration_cutover")
        for mod in (_au, _cw, _de, _ex, _qu, _rd, _sa, _ws):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"out-of-scope symbol {name} in {mod.__name__}")
        # Phase 9 does not redefine domain mathematics: no domain calc symbols leak into governance.
        self.assertNotIn("monthly_expected", open(_ex.__file__).read())

    def test_113b_all_80_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 80)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
