"""Phase 4 acceptance — operational output slice, migration durability, cross-phase greens,
legacy invariants, and no-Phase-5-behavior guard (items 54-63) + fixture completeness."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.newinv.fixtures import SCOPE, Phase4, build_all_scenarios, SCENARIO_NAMES
from elite.newinv.output import build_slice

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    """Run the given elite test modules in-process; return (run, failures+errors)."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase4OutputMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase4(self.dbp)

    def tearDown(self):
        self.p.close()

    def _plan(self):
        c = self.p.combination(exterior_color="BLACK")
        months = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p.seed_retail(c, {m: 2 for m in months})
        self.p.seed_availability(c, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": 2,
                                     "snapshot": "full"} for m in months])
        d = self.p.issue_demand(c, policy_versions=["pv_demo"])
        return c, d, self.p.issue_plan(c, d, coverage_target=2)

    def test_54_planning_output_identifies_facts_policies_versions_confidence(self):
        _c, d, plan = self._plan()
        self.assertIsNotNone(plan.calculation_version)
        self.assertEqual(plan.policy_versions, ["pv_demo"])
        self.assertIn(plan.confidence, ("low", "medium", "high"))
        self.assertIsNotNone(plan.reproducibility_package)
        self.assertIn("sample_size", d.uncertainty)          # uncertainty carried

    def test_55_output_slice_uses_real_domain_output(self):
        _c, d, plan = self._plan()
        sl = build_slice(self.p.store, plan.id)
        # values come straight from the stored domain records, not mock text
        self.assertEqual(sl["need"], plan.need)
        self.assertEqual(sl["demand"], d.monthly_expected)
        self.assertEqual(sl["supply"]["qualifying"], plan.qualifying_supply)
        self.assertEqual(sl["versions"]["calculation_version"], plan.calculation_version)
        self.assertEqual(len(sl["month_by_month"]), len(plan.months))
        for key in ("call", "why", "proof", "raw_history_refs", "confidence", "uncertainty", "unresolved"):
            self.assertIn(key, sl)

    def test_56_migration_v4_survives_restart(self):
        c = self.p.combination(exterior_color="BLACK")
        self.p.close()
        p2 = Phase4(self.dbp)
        self.addCleanup(p2.close)
        self.assertEqual(p2.stack.db.version(), 4)
        self.assertIsNotNone(p2.store.get_combination(c.id))

    def test_57_migration_v4_rerun_is_safe(self):
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.close()
        p2 = Phase4(self.dbp)
        self.addCleanup(p2.close)
        after = p2.store.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual((before, after), (4, 4))

    def test_58_phase1_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_authz", "elite.tests.test_persistence",
                                    "elite.tests.test_config_env", "elite.tests.test_audit_logging"])
        self.assertEqual(failed, 0)
        self.assertGreater(run, 0)

    def test_59_phase2_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_phase2_data", "elite.tests.test_phase2_facts",
                                    "elite.tests.test_phase2_identity"])
        self.assertEqual(failed, 0)
        self.assertGreater(run, 0)

    def test_60_phase3_tests_remain_green(self):
        run, failed = _run_modules(["elite.tests.test_phase3_policy", "elite.tests.test_phase3_versions",
                                    "elite.tests.test_phase3_scenario_gov"])
        self.assertEqual(failed, 0)
        self.assertGreater(run, 0)

    def test_61_legacy_tests_remain_green(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        for script in ("pipeline_manager/tests/test_engine.py", "pipeline_manager/tests/test_loaner_intel.py"):
            r = subprocess.run(["python3", script], cwd=_REPO, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("passed", r.stdout + r.stderr)

    def test_62_legacy_application_paths_unchanged(self):
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
                              cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])

    def test_63_no_phase5_or_domain_behavior_introduced(self):
        import elite.newinv.availability as _av
        import elite.newinv.combination as _cb
        import elite.newinv.coverage as _cv
        import elite.newinv.demand as _dm
        import elite.newinv.forecast as _fc
        import elite.newinv.output as _out
        import elite.newinv.planning as _pl
        import elite.newinv.retail as _rt
        import elite.newinv.supply as _sp
        forbidden = ("cpo", "ppo", "ctp", "loaner", "demo", "pairing", "learning", "executive",
                     "dealer_trade", "service_loaner")
        for mod in (_av, _cb, _cv, _dm, _fc, _out, _pl, _rt, _sp):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                low = name.lower()
                self.assertFalse(any(tok in low for tok in forbidden),
                                 f"domain/phase-5 symbol {name} in {mod.__name__}")

    def test_64_all_40_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 40)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
