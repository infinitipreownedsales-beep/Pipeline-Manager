"""Phase 7 acceptance — migration durability (80-81), cross-phase greens incl. legacy 39/39 (82-88),
no-out-of-scope-behavior guard (89), 60-fixture completeness (90)."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.execdemo.fixtures import Phase7, build_all_scenarios, SCENARIO_NAMES
from elite.workflow.fixtures import SCOPE

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase7MigrationCross(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase7(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_80_migration_v7_survives_restart(self):
        u = self.p.make_active("1HGCM82633A700001")
        applied = [r["version"] for r in self.p.stack.db.conn.execute(
            "SELECT version FROM migration_record").fetchall()]
        self.assertIn(7, applied)
        self.p.close()
        p2 = Phase7(self.dbp)
        self.addCleanup(p2.close)
        self.assertGreaterEqual(p2.stack.db.version(), 7)
        self.assertIsNotNone(p2.store.get_unit(u.id))

    def test_81_migration_v7_rerun_safe(self):
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase7(self.dbp)
        self.addCleanup(p2.close)
        after = p2.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual(before, after)                              # no duplicate migration rows
        applied = [r["version"] for r in p2.stack.db.conn.execute("SELECT version FROM migration_record").fetchall()]
        self.assertEqual(len(applied), len(set(applied)))

    def test_82_phase1_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_authz", "elite.tests.test_persistence",
                              "elite.tests.test_config_env", "elite.tests.test_audit_logging"])
        self.assertEqual(f, 0)

    def test_83_phase2_3_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase2_data", "elite.tests.test_phase2_facts",
                              "elite.tests.test_phase2_identity", "elite.tests.test_phase3_policy",
                              "elite.tests.test_phase3_versions", "elite.tests.test_phase3_scenario_gov"])
        self.assertEqual(f, 0)

    def test_84_phase4_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase4_combination", "elite.tests.test_phase4_supply",
                              "elite.tests.test_phase4_demand", "elite.tests.test_phase4_retail_availability",
                              "elite.tests.test_phase4_forecast_planning", "elite.tests.test_phase4_output_migration",
                              "elite.tests.test_phase4_bug_cpo_002"])
        self.assertEqual(f, 0)

    def test_85_phase5_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase5_cpo", "elite.tests.test_phase5_ppo_dealer",
                              "elite.tests.test_phase5_ctp", "elite.tests.test_phase5_pipeline_eta",
                              "elite.tests.test_phase5_editability_myt_risk",
                              "elite.tests.test_phase5_sequential_reconcile",
                              "elite.tests.test_phase5_integrate_governance",
                              "elite.tests.test_phase5_migration_cross",
                              "elite.tests.test_phase5_bug_cpo_002_e2e"])
        self.assertEqual(f, 0)

    def test_86_phase6_tests_remain_green(self):
        _r, f = _run_modules(["elite.tests.test_phase6_snapshot_membership",
                              "elite.tests.test_phase6_lifecycle_dating_mileage",
                              "elite.tests.test_phase6_monitoring", "elite.tests.test_phase6_economics_portfolio",
                              "elite.tests.test_phase6_retirement_handoff",
                              "elite.tests.test_phase6_scenario_governance",
                              "elite.tests.test_phase6_migration_cross"])
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
        import elite.execdemo.economics as _ec
        import elite.execdemo.eligibility as _el
        import elite.execdemo.opportunity as _op
        import elite.execdemo.portfolio as _po
        import elite.execdemo.preference as _pr
        import elite.execdemo.projection as _pj
        import elite.execdemo.resale as _rs
        import elite.execdemo.retirement as _re
        import elite.execdemo.scenario as _sc
        import elite.execdemo.unit as _un
        # Prediction/Observation Pairing, Learning, completed Phase 9 Governance, and full UX are NOT here.
        forbidden = ("pairing", "prediction_pairing", "observation_pairing", "learning", "train", "model_fit")
        for mod in (_ec, _el, _op, _po, _pr, _pj, _rs, _re, _sc, _un):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"out-of-scope symbol {name} in {mod.__name__}")
        # Executive Demo is a SEPARATE package from Service Loaner (no shared fleet engine imported)
        import elite.execdemo.portfolio as pf
        self.assertNotIn("..loaner", open(pf.__file__).read())

    def test_90_all_60_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 60)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
