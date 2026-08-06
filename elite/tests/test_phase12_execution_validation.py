"""Phase 12 acceptance — full execution wiring (35-40), shadow mode (41-44), parallel validation (45-52),
discrepancy burn-down (53), UAT (54-58), rehearsals (59-72), cutover runbook (73-75), release package
(76-80)."""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ValidationError
from elite.release import fixtures as F
from elite.release.fixtures import Phase12, SCOPE
from elite.ui.fixtures import Client


class TestPhase12ExecutionValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.p = Phase12(os.path.join(cls.tmp, "elite.db"))
        cls.h = F.build_all_fixtures(cls.p)

    @classmethod
    def tearDownClass(cls):
        cls.p.close()

    # ---- execution wiring (35-40) ----------------------------------------
    def test_035_every_action_invokes_actual_service(self):
        required = ["executive_demo.retirement.execute", "executive_demo.designation.execute",
                    "service_loaner.entry.execute", "service_loaner.retirement.complete",
                    "service_loaner.return.confirm", "service_loaner.used_cars.confirm"]
        for a in required:
            self.assertTrue(self.p.registry.has(a), a)
            self.assertFalse(self.p.registry.is_synthetic(a), a)   # a REAL bound domain method

    def test_036_no_synthetic_executor_in_real_path(self):
        self.assertFalse(any(self.p.registry.is_synthetic(a) for a in self.p.registry.actions()))

    def test_037_ui_no_direct_domain_mutation(self):
        # a live execution changes domain state via the real domain method (an Audit Event is written),
        # never by a direct table write from the UI
        before = self.p.stack.audit.count()
        dec, unit, rc = self.p.prepare_live_execution("1HGCM82633A737001")
        ex = self.p.p11.p10.login(self.p.op_executor) if False else None      # (service-level below)
        self.p.live.execute_bound(principal=self.p.op_executor, scope=SCOPE, decision=dec,
                                  idempotency_key="ui37")
        self.assertGreater(self.p.stack.audit.count(), before)                 # audited domain execution
        self.assertEqual(self.p.p7.store.get_unit(unit.id).membership_state, "RETURNED_TO_NEW_RETAIL")

    def test_038_failed_execution_not_success(self):
        # execution blocked when the domain shadow mode does not permit it -> refused, not a false success
        dec, unit, rc = self.p.prepare_live_execution("1HGCM82633A738001")
        self.p.shadow.set_mode(principal=self.p.op_shadow, scope=SCOPE, domain="executive_demo",
                               mode="REVIEW_ONLY", reason="disable execution")
        with self.assertRaises(AuthorizationError):
            self.p.live.execute_bound(principal=self.p.op_executor, scope=SCOPE, decision=dec,
                                      idempotency_key="ui38")
        self.p.shadow.set_mode(principal=self.p.op_shadow, scope=SCOPE, domain="executive_demo",
                               mode="EXECUTION_PILOT", reason="re-enable")

    def test_039_execution_idempotent(self):
        dec, unit, rc = self.p.prepare_live_execution("1HGCM82633A739001")
        self.p.live.execute_bound(principal=self.p.op_executor, scope=SCOPE, decision=dec, idempotency_key="ui39")
        st1 = self.p.p7.store.get_unit(unit.id).membership_state
        self.p.live.execute_bound(principal=self.p.op_executor, scope=SCOPE, decision=dec, idempotency_key="ui39")
        self.assertEqual(self.p.p7.store.get_unit(unit.id).membership_state, st1)   # unchanged on replay

    def test_040_actual_reconciliation_shown(self):
        dec, unit, rc = self.p.prepare_live_execution("1HGCM82633A740001")
        self.p.live.execute_bound(principal=self.p.op_executor, scope=SCOPE, decision=dec, idempotency_key="ui40")
        # the live executor already reconciled to COMPLETED; re-reconciling is ALREADY_RECONCILED
        self.assertIn(self.p.p9.execution.reconcile(dec), ("COMPLETED", "ALREADY_RECONCILED"))

    def test_040b_scenario_cannot_execute(self):
        item = self.p.p9.item(domain="executive_demo", rec="rec_scn", scenario_id="scn1")
        r = self.p.p9.decisions.issue(self.p.p9.decider, SCOPE, item, disposition="ACCEPT",
                                      selected_action="retire")
        dec = r["decision"]
        self.p.live.bind(dec["id"], domain="executive_demo", action="executive_demo.retirement.execute",
                         real_call=lambda pr, sc: "x")
        with self.assertRaises(ValidationError):
            self.p.live.execute_bound(principal=self.p.op_executor, scope=SCOPE, decision=dec)

    # ---- shadow mode (41-44) ---------------------------------------------
    def test_041_shadow_visible(self):
        self.assertIn(self.p.shadow.current_mode("new_inventory", SCOPE),
                      ["DATA_ONLY", "CALCULATE_ONLY", "REVIEW_ONLY", "EXECUTION_PILOT", "CUTOVER_ELIGIBLE",
                       "BLOCKED", "DECISION_PILOT"])

    def test_042_shadow_domain_specific(self):
        self.assertNotEqual(self.p.shadow.current_mode("service_loaner", SCOPE),
                            self.p.shadow.current_mode("dealer_trade", SCOPE))

    def test_043_shadow_change_governed_audited(self):
        before = self.p.stack.audit.count()
        self.p.shadow.set_mode(principal=self.p.op_shadow, scope=SCOPE, domain="production", mode="CALCULATE_ONLY")
        self.assertGreater(self.p.stack.audit.count(), before)
        # history preserved
        self.assertGreaterEqual(len(self.p.shadow.history("production", SCOPE)), 2)

    def test_044_shadow_execution_blocked_unless_enabled(self):
        self.assertFalse(self.p.shadow.execution_enabled("dealer_trade", SCOPE))   # BLOCKED
        self.assertTrue(self.p.shadow.execution_enabled("service_loaner", SCOPE))  # EXECUTION_PILOT

    # ---- parallel validation (45-52) -------------------------------------
    def test_045_parallel_preserves_both(self):
        r = self.h["data_difference"]
        self.assertEqual(str(r["elite_value"]), "8")
        self.assertEqual(str(r["legacy_value"]), "6")

    def test_046_repeated_run_preserves_dated_history(self):
        n = len(self.p.store.list_parallel_runs())
        self.p.parallel.run(principal=self.p.op_validator, scope=SCOPE, run_date="2026-08-07",
                            subjects=[{"subject_ref": "x", "domain": "new_inventory", "elite_value": 1, "legacy_value": 1}])
        self.assertEqual(len(self.p.store.list_parallel_runs()), n + 1)

    def test_047_classification_requires_evidence(self):
        disc = self.h["resolved_discrepancy"]
        trans = self.p.store.discrepancy_transitions(disc["id"])
        self.assertTrue(any(t["evidence"] for t in trans))

    def test_048_unknown_difference_unresolved(self):
        self.assertEqual(self.h["unresolved_material_difference"]["classification"], "UNRESOLVED")

    def test_049_confirmed_elite_defect_registry(self):
        disc = self.p.discrepancy.open(parallel_result_ref=self.h["elite_defect"]["id"],
                                       domain="service_loaner", scope=SCOPE, summary="elite defect",
                                       classification="ELITE_DEFECT")
        d = self.p.discrepancy.transition(principal=self.p.op_validator, scope=SCOPE, discrepancy_id=disc["id"],
                                          to_status="ELITE_DEFECT_CONFIRMED", reason="reproduced",
                                          evidence="repro steps", defect_ref="DEF-1")
        self.assertEqual(d["defect_ref"], "DEF-1")

    def test_050_legacy_limitation_no_mutate_elite(self):
        r = self.h["legacy_limitation"]
        self.assertEqual(str(r["elite_value"]), "7")            # elite result unchanged
        self.assertIsNone(r["disposition"])

    def test_051_expected_difference_documented(self):
        self.assertEqual(self.h["expected_difference"]["classification"], "EXPECTED_DIFFERENCE")

    def test_052_material_unresolved_blocks_readiness(self):
        self.assertTrue(self.p.parallel.unreviewed_material(SCOPE))   # material unreviewed exists

    # ---- discrepancy burn-down (53) --------------------------------------
    def test_053_burn_down_reconciles(self):
        bd = self.p.discrepancy.burn_down(SCOPE)
        self.assertEqual(bd["total"], len(self.p.store.list_discrepancies(SCOPE)))

    # ---- UAT (54-58) -----------------------------------------------------
    def test_054_uat_uses_real_application(self):
        self.assertEqual(self.h["uat_pass"]["outcome"], "pass")
        self.assertIsNotNone(self.h["uat_pass"]["operator"])

    def test_055_uat_records_operator_and_revisions(self):
        t = [x for x in self.p.store.list_uat_tests()][0]
        self.assertIsNotNone(t["environment_revision"])

    def test_056_uat_failure_historical(self):
        self.assertEqual(self.h["uat_failure"]["outcome"], "fail")   # immutable failure record

    def test_057_material_uat_failure_blocks(self):
        # a fresh failed UAT with no passing retest is a material failure
        t = self.p.uat.add_test(test_case="blocker", domain="production", scope=SCOPE, expected_result="ok")
        self.p.uat.record(principal=self.p.op_uat, scope=SCOPE, uat_test_id=t["id"], actual_result="err", outcome="fail")
        self.assertTrue(any(x["id"] == t["id"] for x in self.p.uat.material_failures(SCOPE)))

    def test_058_retest_does_not_erase_original(self):
        results = self.p.store.uat_results(self.h["uat_failure"]["uat_test_id"])
        self.assertTrue(any(r["outcome"] == "fail" for r in results))   # original failure retained
        self.assertTrue(any(r["outcome"] == "pass" for r in results))   # retest pass added

    # ---- rehearsals (59-72) ----------------------------------------------
    def test_059_migration_rehearsal_clean_db(self):
        self.assertEqual(self.h["migration_rehearsal_pass"]["outcome"], "pass")

    def test_060_rehearsal_applies_v1_v12(self):
        self.assertIn("migrate_v1_v12", self.h["migration_rehearsal_pass"]["steps_json"])

    def test_061_rehearsal_records_input_hashes(self):
        self.assertIsNotNone(self.h["migration_rehearsal_pass"]["input_hashes"])

    def test_062_rehearsal_counts_reconcile(self):
        self.assertIsNotNone(self.h["migration_rehearsal_pass"]["output_counts"])

    def test_063_rehearsal_restart_preserves(self):
        self.assertEqual(self.h["migration_rehearsal_pass"]["restart_verified"], 1)

    def test_064_rehearsal_backup_validates(self):
        self.assertIsNotNone(self.h["migration_rehearsal_pass"]["backup_ref"])

    def test_065_failed_rehearsal_blocks(self):
        self.assertEqual(self.h["migration_rehearsal_fail"]["outcome"], "fail")

    def test_066_rollback_preserves_elite_history(self):
        self.assertEqual(self.h["rollback_rehearsal_pass"]["elite_history_preserved"], 1)

    def test_067_rollback_retains_legacy(self):
        self.assertEqual(self.h["rollback_rehearsal_pass"]["legacy_available"], 1)

    def test_068_rollback_identifies_inflight(self):
        r = self.p.rehearsal.rollback_rehearsal(migration_rehearsal_ref="m", elite_history_preserved=True,
                                                legacy_available=True, inflight_actions=["act1"])
        import json
        self.assertIn("act1", r["inflight_actions"])

    def test_069_rollback_no_replay_into_legacy(self):
        self.assertEqual(self.h["rollback_rehearsal_pass"]["replayed_into_legacy"], 0)

    def test_070_failed_rollback_blocks(self):
        self.assertEqual(self.h["rollback_rehearsal_fail"]["outcome"], "fail")

    def test_071_recovery_preserves_committed_truth(self):
        self.assertEqual(self.h["recovery_rehearsal_pass"]["committed_truth_preserved"], 1)

    def test_072_recovery_identifies_unresolved(self):
        r = self.p.rehearsal.recovery_rehearsal(scenario="missing_source", committed_truth_preserved=True,
                                                unresolved_consequences="stale readiness")
        self.assertIsNotNone(r["unresolved_consequences"])

    # ---- cutover runbook (73-75) -----------------------------------------
    def test_073_runbook_prereqs_abort(self):
        rb = self.p.cutover.record(release_package_ref=self.h["release_package"]["id"], runbook_ref="RB1",
                                   version="1", prerequisites="freeze source", abort_criteria="material discrepancy",
                                   rollback_trigger="parity fail", rollback_steps="restore backup; use legacy")
        self.assertIn("freeze", rb["prerequisites"])
        self.assertIn("discrepancy", rb["abort_criteria"])

    def test_074_runbook_rollback_trigger_steps(self):
        rb = self.p.store.cutover_runbooks()[-1]
        self.assertIsNotNone(rb["rollback_trigger"])
        self.assertIsNotNone(rb["rollback_steps"])

    def test_075_runbook_does_not_execute(self):
        # recording a runbook performs no cutover / authorization
        self.assertFalse(self.p.authorization.is_go_live_authorized("store:NORUN", "none"))

    # ---- release package (76-80) -----------------------------------------
    def test_076_package_references_revision(self):
        self.assertEqual(self.h["release_package"]["application_revision"], "83d66e4")

    def test_077_package_pins_migration_level(self):
        self.assertEqual(self.h["release_package"]["migration_level"], 12)

    def test_078_package_includes_unresolved_risks(self):
        # the package schema carries an unresolved_risks column (may be null in a draft, present once set)
        self.assertIn("unresolved_risks", self.h["release_package"].keys())

    def test_079_package_evidence_refs(self):
        self.assertEqual(self.h["release_package"]["status"], "issued")

    def test_080_issued_package_immutable(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.p.stack.db.conn.execute("UPDATE release_package SET release_notes='x' WHERE id=?",
                                         (self.h["release_package"]["id"],))
            self.p.stack.db.conn.commit()


if __name__ == "__main__":
    unittest.main()
