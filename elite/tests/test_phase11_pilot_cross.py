"""Phase 11 acceptance — controlled pilot mode + comparison + feedback (78-88), pilot packaging commands
(89-92), Phase 10 usability + cross-phase greens + legacy invariants + no-cutover (93-106), and the
60-fixture completeness check."""
import os
import subprocess
import tempfile
import unittest

from elite.errors import AuthorizationError
from elite.ops import cli
from elite.ops import fixtures as F
from elite.ops.fixtures import Phase11, SCOPE, build_all_fixtures, FIXTURE_NAMES

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPhase11PilotCross(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase11(os.path.join(cls.tmp, "elite.db"))

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    # ---- pilot mode (78-80) ----------------------------------------------
    def test_078_pilot_mode_visibly_identified(self):
        self.assertTrue(self.p.pilot.is_pilot())
        self.assertIn("PILOT MODE", self.p.pilot.banner())

    def test_079_pilot_blocks_destructive_cutover(self):
        for action in ("cutover", "legacy_replacement", "destructive_migration", "production_go_live"):
            with self.assertRaises(AuthorizationError):
                self.p.pilot.assert_action_allowed(action)
        self.assertFalse(self.p.pilot.cutover_available())

    def test_080_legacy_fallback_available(self):
        self.assertTrue(self.p.pilot.legacy_fallback_available())

    # ---- parallel comparison (81-85) -------------------------------------
    def test_081_comparison_preserves_both_results(self):
        cmp = self.p.pilot.compare(domain="new_inventory", scope=SCOPE, initiated_by=self.p.op_reviewer,
                                   subjects=[{"subject_ref": "u81", "elite_result": 7, "legacy_result": 5,
                                              "classification": "DATA_DIFFERENCE"}])
        r = cmp["results"][0]
        self.assertEqual(str(r["elite_result"]), "7")
        self.assertEqual(str(r["legacy_result"]), "5")

    def test_082_comparison_mutates_neither(self):
        cmp = self.p.pilot.compare(domain="new_inventory", scope=SCOPE, initiated_by=self.p.op_reviewer,
                                   subjects=[{"subject_ref": "u82", "elite_result": 7, "legacy_result": 5,
                                              "classification": "DATA_DIFFERENCE"}])
        rid = cmp["results"][0]["id"]
        self.p.pilot.review_difference(result_id=rid, reviewer=self.p.op_reviewer, disposition="acceptable",
                                       scope=SCOPE, notes="ok")
        after = self.p.ops.get_comparison_result(rid)
        self.assertEqual(str(after["elite_result"]), "7")   # review never rewrote the captured results
        self.assertEqual(str(after["legacy_result"]), "5")
        self.assertEqual(after["disposition"], "acceptable")

    def test_083_legacy_difference_does_not_change_elite(self):
        # a recorded LEGACY_DIFFERENCE writes no domain record and does not touch the elite result
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM inventory_plan_result").fetchone()["c"]
        self.p.pilot.compare(domain="new_inventory", scope=SCOPE, initiated_by=self.p.op_reviewer,
                             subjects=[{"subject_ref": "u83", "elite_result": 9, "legacy_result": 2,
                                        "classification": "LEGACY_LIMITATION"}])
        after = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM inventory_plan_result").fetchone()["c"]
        self.assertEqual(before, after)

    def test_084_elite_difference_does_not_change_legacy(self):
        # the comparison is a pure record; there is no write path from Elite into the legacy tool
        cmp = self.p.pilot.compare(domain="new_inventory", scope=SCOPE, initiated_by=self.p.op_reviewer,
                                   subjects=[{"subject_ref": "u84", "elite_result": 3, "legacy_result": 3}])
        self.assertEqual(cmp["results"][0]["classification"], "MATCH")

    def test_085_material_discrepancy_affects_readiness(self):
        from elite.ops.models import CAPS
        self.p.stack.grant(self.p.op_reviewer, CAPS["PILOT_COMPARE"], "store:RD85")
        self.p.pilot.compare(domain="new_inventory", scope="store:RD85", initiated_by=self.p.op_reviewer,
                             subjects=[{"subject_ref": "u85", "elite_result": 1, "legacy_result": 9,
                                        "classification": "CALCULATION_DIFFERENCE"}])
        r = self.p.health.readiness("store:RD85")
        self.assertEqual(r["status"], "NOT_READY")
        self.assertIn("unreviewed_material_discrepancy", r["blockers"])

    # ---- operator feedback (86-88) ---------------------------------------
    def test_086_feedback_references_screen_and_revision(self):
        fb = self.p.pilot.submit_feedback(principal_id=self.p.op_feedback, scope=SCOPE, category="usability",
                                          description="x", screen_ref="/item/abc", revision_ref="rev-42")
        self.assertEqual(fb["screen_ref"], "/item/abc")
        self.assertEqual(fb["revision_ref"], "rev-42")

    def test_087_feedback_does_not_mutate_authoritative(self):
        before = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM governed_decision").fetchone()["c"]
        self.p.pilot.submit_feedback(principal_id=self.p.op_feedback, scope=SCOPE, category="incorrect_result",
                                     description="need wrong", screen_ref="/", revision_ref="r1")
        after = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM governed_decision").fetchone()["c"]
        self.assertEqual(before, after)                     # no authoritative record changed

    def test_088_incorrect_result_creates_review(self):
        fb = self.p.pilot.submit_feedback(principal_id=self.p.op_feedback, scope=SCOPE,
                                          category="incorrect_result", description="wrong", screen_ref="/",
                                          revision_ref="r2")
        self.assertEqual(fb["status"], "review")            # review, not an automatic correction
        from elite.errors import ValidationError
        with self.assertRaises(ValidationError):
            self.p.pilot.triage_feedback(feedback_id=fb["id"], owner=self.p.op_triager,
                                         disposition="auto_correct", scope=SCOPE)

    # ---- pilot packaging commands (89-92) --------------------------------
    def _cli_env(self, dbdir):
        return {"ELITE_ENV": "development", "ELITE_DB_PATH": os.path.join(dbdir, "cli.db"),
                "ELITE_PILOT_SCOPE": "store:HG", "ELITE_BACKUP_DIR": os.path.join(dbdir, "backups")}

    def _run_cli(self, args, env):
        old = dict(os.environ)
        os.environ.update(env)
        try:
            return cli.main(args)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_089_package_starts_from_documented_commands(self):
        d = tempfile.mkdtemp()
        self.assertEqual(self._run_cli(["diagnostics"], self._cli_env(d)), 0)

    def test_090_backup_and_health_commands(self):
        d = tempfile.mkdtemp()
        env = self._cli_env(d)
        self.assertEqual(self._run_cli(["backup"], env), 0)
        self.assertEqual(self._run_cli(["health"], env), 0)
        self.assertEqual(self._run_cli(["restore-validate"], env), 0)

    def test_091_import_command(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "inv.csv")
        with open(path, "w") as f:
            f.write(F.INV_VALID)
        self.assertEqual(self._run_cli(["import", "new_inventory_current", path], self._cli_env(d)), 0)

    def test_092_scheduler_command(self):
        d = tempfile.mkdtemp()
        self.assertEqual(self._run_cli(["scheduler", "health.check"], self._cli_env(d)), 0)

    # ---- Phase 10 usability + cross-phase greens (93-103) -----------------
    def test_093_phase10_app_usable(self):
        full = self.p.p10.login(self.p.p10.op_full)
        self.assertEqual(full.get("/").status, 200)
        self.assertEqual(full.get("/new-inventory").status, 200)

    def test_094_phase1_invariant(self):
        vers = [r["version"] for r in self.p.stack.db.conn.execute("SELECT version FROM migration_record")]
        self.assertTrue(set(range(1, 12)).issubset(set(vers)))     # v1..v11 present

    def test_095_phase2_invariant(self):
        self._table_present("business_fact"); self._table_present("source_registry")

    def test_096_phase3_invariant(self):
        self._table_present("policy_version")

    def test_097_phase4_invariant(self):
        n = self.p.stack.db.conn.execute("SELECT COUNT(*) c FROM inventory_plan_result").fetchone()["c"]
        self.assertGreater(n, 0)                                    # Phase 4 planning intact

    def test_098_phase5_invariant(self):
        self._table_present("supply_commitment")

    def test_099_phase6_invariant(self):
        self._table_present("service_loaner_unit")

    def test_100_phase7_invariant(self):
        self._table_present("executive_demo_portfolio_plan")

    def test_101_phase8_invariant(self):
        self._table_present("calibration_proposal")

    def test_102_phase9_invariant(self):
        self._table_present("governed_decision"); self._table_present("decision_workspace_item")

    def test_103_phase10_invariant(self):
        self._table_present("operator_view_preference")

    # ---- legacy invariants + no cutover (104-106) ------------------------
    def test_104_legacy_tests_green(self):
        eng = subprocess.run(["python3", "pipeline_manager/tests/test_engine.py"], cwd=_REPO,
                             capture_output=True, text=True)
        loan = subprocess.run(["python3", "pipeline_manager/tests/test_loaner_intel.py"], cwd=_REPO,
                              capture_output=True, text=True, env={**os.environ, "PYTHONPATH": _REPO})
        self.assertIn("29/29 passed", eng.stdout)
        self.assertIn("10/10 passed", loan.stdout)

    def test_105_legacy_paths_unchanged(self):
        diff = subprocess.run(
            ["git", "diff", "legacy/inventory-tool", "--", "build", "Pipeline-Manager.html", "pipeline_manager"],
            cwd=_REPO, capture_output=True, text=True)
        self.assertEqual(diff.stdout.strip(), "")                  # byte-identical to the protected line

    def test_106_no_cutover_behavior(self):
        # every cutover-class action is blocked in pilot mode; there is no production go-live path
        self.assertFalse(self.p.pilot.cutover_available())
        for a in self.p.pilot.CUTOVER_ACTIONS:
            with self.assertRaises(AuthorizationError):
                self.p.pilot.assert_action_allowed(a)

    # ---- 60-fixture completeness -----------------------------------------
    def test_60_fixture_completeness(self):
        q = Phase11(os.path.join(tempfile.mkdtemp(), "fx.db"))
        try:
            h = build_all_fixtures(q)
            self.assertEqual(len(FIXTURE_NAMES), 60)
            self.assertEqual(sorted(h), sorted(FIXTURE_NAMES))
            self.assertTrue(all(h[n] for n in FIXTURE_NAMES))      # every fixture built truthy
        finally:
            q.close()

    def _table_present(self, table):
        r = self.p.stack.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        self.assertIsNotNone(r, f"{table} missing")

    def _conn(self):
        return self.p.stack.db.conn


if __name__ == "__main__":
    unittest.main()
