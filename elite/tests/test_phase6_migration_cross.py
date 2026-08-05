"""Phase 6 acceptance — migration durability, cross-phase greens, legacy invariants,
no-out-of-scope-behavior guard (items 80-89) + fixture completeness."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.loaner.fixtures import Phase6, build_all_scenarios, SCENARIO_NAMES
from elite.workflow.fixtures import SCOPE

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase6MigrationCross(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase6(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_80_migration_v6_survives_restart(self):
        u = self.p.make_active("1GNSKBKC5FR000701")
        self.p.close()
        p2 = Phase6(self.dbp)
        self.addCleanup(p2.close)
        self.assertEqual(p2.stack.db.version(), 6)
        self.assertIsNotNone(p2.store.get_unit(u.id))

    def test_81_migration_v6_rerun_safe(self):
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase6(self.dbp)
        self.addCleanup(p2.close)
        after = p2.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual((before, after), (6, 6))

    def test_82_phase1_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_authz", "elite.tests.test_persistence",
                              "elite.tests.test_config_env", "elite.tests.test_audit_logging"])
        self.assertEqual(f, 0)

    def test_83_phase2_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase2_data", "elite.tests.test_phase2_facts",
                              "elite.tests.test_phase2_identity"])
        self.assertEqual(f, 0)

    def test_84_phase3_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase3_policy", "elite.tests.test_phase3_versions",
                              "elite.tests.test_phase3_scenario_gov"])
        self.assertEqual(f, 0)

    def test_85_phase4_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase4_combination", "elite.tests.test_phase4_supply",
                              "elite.tests.test_phase4_forecast_planning", "elite.tests.test_phase4_bug_cpo_002"])
        self.assertEqual(f, 0)

    def test_86_phase5_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase5_cpo", "elite.tests.test_phase5_ctp",
                              "elite.tests.test_phase5_bug_cpo_002_e2e"])
        self.assertEqual(f, 0)

    def test_87_legacy_tests_remain_green(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        for script in ("pipeline_manager/tests/test_engine.py", "pipeline_manager/tests/test_loaner_intel.py"):
            r = subprocess.run(["python3", script], cwd=_REPO, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("passed", r.stdout + r.stderr)

    def test_88_legacy_application_paths_unchanged(self):
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
                              cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])

    def test_89_no_out_of_scope_behavior(self):
        import elite.loaner.dating as _dt
        import elite.loaner.economics as _ec
        import elite.loaner.monitoring as _mo
        import elite.loaner.portfolio as _po
        import elite.loaner.retirement as _re
        import elite.loaner.scenario as _sc
        import elite.loaner.snapshot as _sn
        import elite.loaner.unit as _un
        # Executive Demo (Phase 7), Pairing, Learning, and full Governance are NOT introduced here.
        forbidden = ("executive_demo", "executive", "demo", "pairing", "prediction_pairing",
                     "observation_pairing", "learning")
        for mod in (_dt, _ec, _mo, _po, _re, _sc, _sn, _un):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"out-of-scope symbol {name} in {mod.__name__}")

    def test_90_all_60_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 60)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
