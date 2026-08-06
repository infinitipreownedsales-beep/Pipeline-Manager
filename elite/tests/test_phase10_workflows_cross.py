"""Phase 10 acceptance — end-to-end operator workflows (101-107), presentation durability (108),
migration v10 (109), cross-phase greens incl. legacy (110-120), no-out-of-scope guard (121)."""
import io
import os
import subprocess
import tempfile
import unittest

from elite.ui.fixtures import Phase10, build_all_scenarios, SCENARIO_NAMES
from elite.workflow.fixtures import SCOPE

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_APP_PATHS = ["build", "Pipeline-Manager.html", "pipeline_manager"]


def _run_modules(modules):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(m) for m in modules])
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return result.testsRun, len(result.failures) + len(result.errors)


class TestPhase10WorkflowsCross(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase10(self.dbp)

    def tearDown(self):
        self.p.close()

    def test_101_end_to_end_workflow_through_real_services(self):
        p = self.p
        full = p.login(p.op_full)
        dec, appr, exe = p.login(p.op_decider), p.login(p.op_approver), p.login(p.op_executor)
        # 1 open inbox; 2 review NI recommendation; 3 Call/Why/Proof/Raw History
        self.assertEqual(full.get("/").status, 200)
        detail = full.get("/item/" + p.ni_item["id"]).body
        self.assertTrue(all(x in detail for x in ("Call", "Why", "Proof", "Raw History")))
        # 4 issue Decision; 5 route for approval
        self.assertEqual(dec.post("/item/" + p.ni_item["id"] + "/decide",
                                  {"disposition": "ACCEPT", "selected_action": "order"}).status, 303)
        d = p.p9.store.decisions_for_item(p.ni_item["id"])[0]
        # 6 approve with separate authority
        self.assertEqual(appr.post("/approval/" + d["id"] + "/approve", {}).status, 303)
        # 7 authorize execution; 8 domain result; 9 completion + reconciliation
        self.assertEqual(exe.post("/execution/" + d["id"] + "/authorize", {}).status, 303)
        e = p.p9.store.execauths_for(d["id"])[-1]
        self.assertTrue(e["domain_execution_ref"])
        self.assertEqual(exe.post("/execution/" + e["id"] + "/complete", {}).status, 303)
        self.assertIn("COMPLETED", [r["outcome"] for r in p.p9.store.reconciliations_for(d["id"])])

    def test_102_used_cars_confirmation_real_service(self):
        full = self.p.login(self.p.op_full)
        u = self.p.sl_used_cars_unit
        self.assertEqual(full.post("/service-loaner/" + u.id + "/used-cars", {}).status, 303)
        self.assertIsNotNone(self.p.p6.store.used_cars_receipt_for(u.id))

    def test_103_executive_demo_uses_real_records(self):
        import json
        body = self.p.login(self.p.op_full).get("/executive-demo").body
        self.assertIn(json.loads(self.p.ed_plan["best_overall"])["pick"]["vehicle_unit_id"], body)

    def test_104_scenario_comparison_uses_real_records(self):
        body = self.p.login(self.p.op_full).get("/scenario/" + self.p.scn["id"]).body
        self.assertIn("coverage_target", body)

    def test_105_calibration_review_uses_real_records(self):
        body = self.p.login(self.p.op_full).get("/calibration/" + self.p.cal["id"]).body
        self.assertIn(self.p.cal["target_type"], body)

    def test_106_audit_trace_uses_real_records(self):
        full = self.p.login(self.p.op_full)
        dec = self.p.login(self.p.op_decider)
        dec.post("/item/" + self.p.fresh_item["id"] + "/decide",
                 {"disposition": "ACCEPT", "selected_action": "x"}, correlation_id="corr_z")
        self.assertIn("corr_z", full.get("/audit", correlation_id="corr_z").body)

    def test_107_readiness_uses_real_records(self):
        self.assertIn("NOT_READY", self.p.login(self.p.op_full).get("/readiness").body)

    def test_108_presentation_persistence_survives_restart(self):
        self.p.app.prefs.set_pref(self.p.op_full, "preferred_store", "store:HG")
        self.p.close()
        p2 = Phase10(self.dbp)
        self.addCleanup(p2.close)
        self.assertEqual(p2.app.prefs.get_pref(self.p.op_full, "preferred_store"), "store:HG")

    def test_109_migration_v10_rerun_safe(self):
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.p.stack.db.migrate()
        after = self.p.stack.db.conn.execute("SELECT COUNT(*) n FROM migration_record").fetchone()["n"]
        self.assertEqual((before, after), (10, 10))

    def test_110_through_118_prior_phases_green(self):
        _r, f = _run_modules([
            "elite.tests.test_authz", "elite.tests.test_phase2_identity", "elite.tests.test_phase3_policy",
            "elite.tests.test_phase4_bug_cpo_002", "elite.tests.test_phase5_cpo",
            "elite.tests.test_phase6_snapshot_membership", "elite.tests.test_phase7_unit_portfolio",
            "elite.tests.test_phase8_prediction_observation", "elite.tests.test_phase9_workspace_decision"])
        self.assertEqual(f, 0)

    def test_119_legacy_tests_green(self):
        env = dict(os.environ, PYTHONPATH=_REPO)
        for script in ("pipeline_manager/tests/test_engine.py", "pipeline_manager/tests/test_loaner_intel.py"):
            r = subprocess.run(["python3", script], cwd=_REPO, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("passed", r.stdout + r.stderr)

    def test_120_legacy_paths_unchanged(self):
        diff = subprocess.run(["git", "diff", "--name-only", "legacy/inventory-tool", "--"] + LEGACY_APP_PATHS,
                              cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual([l for l in diff.stdout.strip().splitlines() if l.strip()], [])

    def test_121_no_out_of_scope_behavior(self):
        import elite.ui.app as _app
        import elite.ui.views.domains as _dom
        import elite.ui.views.decision as _dec
        import elite.ui.prefs as _prefs
        forbidden = ("hardening", "cutover", "deploy_prod", "live_source", "migration_cutover", "replace_legacy")
        for mod in (_app, _dom, _dec, _prefs):
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                self.assertFalse(any(tok in name.lower() for tok in forbidden),
                                 f"out-of-scope symbol {name} in {mod.__name__}")
        # the UI never recomputes domain mathematics (it reads stored results)
        self.assertNotIn("monthly_expected", open(_dom.__file__).read())

    def test_121b_all_40_fixtures_build(self):
        scenarios = build_all_scenarios(self.p)
        self.assertEqual(len(SCENARIO_NAMES), 40)
        self.assertEqual(set(scenarios), set(SCENARIO_NAMES))


if __name__ == "__main__":
    unittest.main()
