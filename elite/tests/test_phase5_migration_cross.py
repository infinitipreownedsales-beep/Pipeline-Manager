"""Phase 5 acceptance — migration durability, cross-phase greens, legacy invariants,
no-out-of-scope-behavior guard (items 70-78) + fixture completeness."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.workflow.fixtures import Phase5, build_all_scenarios, SCENARIO_NAMES

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase5MigrationCross(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase5(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_70_migration_v5_survives_restart(self):
        c, d, _ = self.p.need_combo(exterior_color="BLACK")
        w = self.p.cpo.propose(self.p.full, "store:HG", production_order_id="po", combination_id=c.id,
                               arrival_month="2026-10")
        self.p.close()
        p2 = Phase5(self.dbp)
        self.addCleanup(p2.close)
        applied = {r["version"] for r in p2.wf.conn.execute("SELECT version FROM migration_record").fetchall()}
        self.assertIn(5, applied)                              # v5 applied (later migrations may exist)
        self.assertGreaterEqual(p2.stack.db.version(), 5)
        self.assertIsNotNone(p2.wf.get_workflow(w.id))

    def test_71_migration_v5_rerun_safe(self):
        before = self.p.wf.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase5(self.dbp)
        self.addCleanup(p2.close)
        after = p2.wf.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual(before, after)                       # rerun applies nothing new
        self.assertGreaterEqual(after, 5)

    def test_72_phase1_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_authz", "elite.tests.test_persistence",
                                    "elite.tests.test_config_env", "elite.tests.test_audit_logging"])
        self.assertEqual(failed, 0)
        self.assertGreater(run, 0)

    def test_73_phase2_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_phase2_data", "elite.tests.test_phase2_facts",
                                    "elite.tests.test_phase2_identity"])
        self.assertEqual(failed, 0)

    def test_74_phase3_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_phase3_policy", "elite.tests.test_phase3_versions",
                                    "elite.tests.test_phase3_scenario_gov"])
        self.assertEqual(failed, 0)

    def test_75_phase4_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_phase4_combination", "elite.tests.test_phase4_supply",
                                    "elite.tests.test_phase4_demand", "elite.tests.test_phase4_forecast_planning",
                                    "elite.tests.test_phase4_bug_cpo_002"])
        self.assertEqual(failed, 0)

    def test_76_legacy_tests_remain_green(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        for script in ("pipeline_manager/tests/test_engine.py", "pipeline_manager/tests/test_loaner_intel.py"):
            r = subprocess.run(["python3", script], cwd=_REPO, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("passed", r.stdout + r.stderr)

    def test_77_legacy_application_paths_unchanged(self):
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
                              cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])

    def test_78_no_out_of_scope_behavior_introduced(self):
        import elite.workflow.cpo as _cpo
        import elite.workflow.ctp as _ctp
        import elite.workflow.dealer_trade as _dt
        import elite.workflow.integrate as _int
        import elite.workflow.lifecycle as _lc
        import elite.workflow.output as _out
        import elite.workflow.pipeline as _pl
        import elite.workflow.ppo as _ppo
        import elite.workflow.reconcile as _rc
        import elite.workflow.risk as _rk
        import elite.workflow.sequential as _sq
        import elite.workflow.store as _st
        forbidden = ("loaner", "executive_demo", "pairing", "learning", "service_loaner",
                     "observation_pairing", "prediction_pairing")
        mods = (_cpo, _ctp, _dt, _int, _lc, _out, _pl, _ppo, _rc, _rk, _sq, _st)
        for mod in mods:
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"out-of-scope symbol {name} in {mod.__name__}")

    def test_79_all_50_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 50)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
