"""Phase 8 acceptance — backtesting/validation (54-59), Calibration governance/activation/rollback
(60-77), operational output slices (78)."""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, ConcurrencyError, PersistenceError, ValidationError
from elite.learning import output
from elite.learning.fixtures import OTHER_SCOPE, Phase8, _to_approved, _to_validated
from elite.workflow.fixtures import SCOPE


class TestPhase8CalibrationValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase8(self.dbp)

    def tearDown(self):
        self.p.close()

    def _cv_count(self):
        return self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]

    # ---- validation / backtest (54-59) ------------------------------------
    def test_54_proposal_no_operational_effect(self):
        before = self._cv_count()
        self.p.calib(self.p.proposer)                                # PROPOSED only
        self.assertEqual(self._cv_count(), before)                   # no new version
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"], 0)

    def test_55_56_validation_preserves_historical(self):
        pr = self.p.prediction(value=10, subject_entity_id="h")
        cal = _to_validated(self.p, self.p.calib(self.p.proposer))
        run = self.p.backtest.run(cal["id"], current_version="cv1", proposed_version="cv2",
                                  cohorts=[{"name": "all", "current_error": 10, "proposed_error": 6, "material": True}])
        self.assertTrue(run["hypothetical"])                         # 55: labeled hypothetical
        self.assertEqual(self.p.store.get_prediction(pr.id).predicted_payload["value"], 10)   # 56: unchanged

    def test_57_leakage_prohibited(self):
        cal = _to_validated(self.p, self.p.calib(self.p.proposer))
        with self.assertRaises(ValidationError):
            self.p.backtest.run(cal["id"], current_version="cv1", proposed_version="cv2",
                                cohorts=[{"name": "a", "current_error": 1, "proposed_error": 1}], leakage=True)

    def test_58_identifies_improved_and_worsened(self):
        cal = _to_validated(self.p, self.p.calib(self.p.proposer))
        run = self.p.backtest.run(cal["id"], current_version="cv1", proposed_version="cv2", cohorts=[
            {"name": "up", "current_error": 10, "proposed_error": 4, "material": True},
            {"name": "down", "current_error": 4, "proposed_error": 9, "material": True}])
        self.assertEqual(run["improved"], ["up"])
        self.assertEqual(run["worsened"], ["down"])

    def test_59_aggregate_cannot_hide_material_degradation(self):
        cal = _to_validated(self.p, self.p.calib(self.p.proposer))
        run = self.p.backtest.run(cal["id"], current_version="cv1", proposed_version="cv2", cohorts=[
            {"name": "big", "current_error": 100, "proposed_error": 70, "material": False},
            {"name": "small", "current_error": 5, "proposed_error": 20, "material": True}])
        self.assertTrue(run["aggregate_improved"])                   # aggregate looks better
        self.assertTrue(run["hides_material_degradation"])           # but a material cohort degraded — flagged

    # ---- calibration governance (60-77) -----------------------------------
    def test_60_approval_distinct_from_activation(self):
        before = self._cv_count()
        cal = _to_approved(self.p, target_type="calculation_version")
        self.assertEqual(cal["review_state"], "APPROVED")
        self.assertEqual(self._cv_count(), before)                   # approval alone creates no version
        self.assertIsNone(self.p.store.activation_for(cal["id"]))

    def test_61_future_effective_scheduled(self):
        cal = _to_approved(self.p, target_type="calculation_version", effective="2030-01-01T00:00:00+00:00")
        r = self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]), future=True)
        self.assertEqual(r["calibration"]["review_state"], "SCHEDULED")
        self.assertEqual(self.p.store.activation_for(cal["id"])["scheduled"], 1)

    def test_62_activation_creates_new_version(self):
        before = self._cv_count()
        cal = _to_approved(self.p, target_type="calculation_version")
        r = self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        self.assertEqual(r["effect"]["kind"], "calculation_version")
        self.assertEqual(self._cv_count(), before + 1)               # a NEW version referenced
        self.assertIsNotNone(self.p.policy.get_calc_version(r["effect"]["version_ref"]))

    def test_63_activation_does_not_rewrite_prior_predictions(self):
        pr = self.p.prediction(value=10, subject_entity_id="prior")
        cv_before = pr.calculation_version
        cal = _to_approved(self.p, target_type="calculation_version")
        self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        after = self.p.store.get_prediction(pr.id)
        self.assertEqual(after.calculation_version, cv_before)       # prior prediction unchanged
        self.assertEqual(after.predicted_payload["value"], 10)

    def test_64_rejected_no_effect(self):
        before = self._cv_count()
        cal = self.p.calib(self.p.proposer)
        self.p.calibration.reject(self.p.approver, SCOPE, cal, reason="no")
        self.assertEqual(self.p.store.get_calibration(cal["id"])["review_state"], "REJECTED")
        self.assertEqual(self._cv_count(), before)

    def test_65_withdrawn_no_effect(self):
        before = self._cv_count()
        cal = self.p.calib(self.p.proposer)
        self.p.calibration.withdraw(self.p.proposer, SCOPE, cal, reason="later")
        self.assertEqual(self.p.store.get_calibration(cal["id"])["review_state"], "WITHDRAWN")
        self.assertEqual(self._cv_count(), before)

    def test_66_67_rollback_history_and_restore(self):
        cal = _to_approved(self.p, target_type="calculation_version", current_version="cv_prior")
        self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        r = self.p.calibration.rollback(self.p.rollbacker, SCOPE, self.p.store.get_calibration(cal["id"]),
                                        restored_version_ref="cv_prior", reason="regressed")
        self.assertEqual(r["calibration"]["review_state"], "ROLLED_BACK")
        rb = self.p.store.rollback_for(cal["id"])
        self.assertTrue(rb and rb[0]["restored_version_ref"] == "cv_prior")   # 67: prior restored prospectively
        self.assertIsNotNone(self.p.store.activation_for(cal["id"]))          # 66: activation history preserved

    def test_68_policy_target_creates_review_recommendation(self):
        pv_before = self.p.store.conn.execute("SELECT COUNT(*) n FROM policy_version").fetchone()["n"]
        cal = _to_approved(self.p, target_type="materiality_threshold")
        r = self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        self.assertEqual(r["effect"]["kind"], "policy_review_recommendation")
        self.assertIsNotNone(self.p.store.get_calibration(cal["id"])["policy_review_recommendation"])
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM policy_version").fetchone()["n"],
                         pv_before)                                   # no direct policy mutation

    def test_69_no_approved_calibration_no_change(self):
        before = self._cv_count()
        cal = self.p.calib(self.p.proposer)
        self.p.calibration.start_review(self.p.validator, SCOPE, cal)
        self.p.calibration.require_validation(self.p.validator, SCOPE, self.p.store.get_calibration(cal["id"]))
        # never approved/activated
        self.assertEqual(self._cv_count(), before)
        self.assertIsNone(self.p.store.activation_for(cal["id"]))

    def test_70_material_requires_validation_before_approval(self):
        cal = self.p.calib(self.p.proposer, target_type="calculation_version")
        self.p.calibration.start_review(self.p.validator, SCOPE, cal)
        with self.assertRaises(ValidationError):                     # material target not validated
            self.p.calibration.approve(self.p.approver, SCOPE, self.p.store.get_calibration(cal["id"]))

    def test_71_authorities_separate_and_below_ui(self):
        cal = _to_approved(self.p, target_type="calculation_version")
        with self.assertRaises(AuthorizationError):                  # approver cannot activate
            self.p.calibration.activate(self.p.approver, SCOPE, self.p.store.get_calibration(cal["id"]))
        with self.assertRaises(AuthorizationError):                  # proposer cannot approve
            self.p.calibration.approve(self.p.proposer, SCOPE,
                                       _to_validated(self.p, self.p.calib(self.p.proposer)))

    def test_72_scope_mismatch_rejected(self):
        scoped = self.p.stack.authn.register("ScopedAct", "pw").id
        self.p.stack.grant(scoped, "calibration.activate", SCOPE)    # only store:HG
        cal = _to_approved(self.p, target_type="calculation_version")
        with self.assertRaises(AuthorizationError):
            self.p.calibration.activate(scoped, OTHER_SCOPE, self.p.store.get_calibration(cal["id"]))

    def test_73_revoked_authority_rejected(self):
        rid = self.p.stack.authn.register("TempAct", "pw").id
        g = self.p.stack.grant(rid, "calibration.activate", "*")
        self.p.stack.grants.revoke(g.id, g.version, self.p.clock.now())
        cal = _to_approved(self.p, target_type="calculation_version")
        with self.assertRaises(AuthorizationError):
            self.p.calibration.activate(rid, SCOPE, self.p.store.get_calibration(cal["id"]))

    def test_74_stale_transition_rejected(self):
        cal = _to_validated(self.p, self.p.calib(self.p.proposer, target_type="monitoring_threshold"))
        stale = dict(cal)
        stale["version"] = 999                                       # wrong version -> optimistic guard fails
        with self.assertRaises(ConcurrencyError):
            self.p.calibration.approve(self.p.approver, SCOPE, stale)

    def test_75_idempotent_activation_no_duplicate(self):
        cal = _to_approved(self.p, target_type="calculation_version")
        self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        r2 = self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        self.assertTrue(r2["replayed"])
        self.assertEqual(self.p.store.conn.execute(
            "SELECT COUNT(*) n FROM calibration_activation WHERE calibration_proposal_id=?", (cal["id"],)
        ).fetchone()["n"], 1)

    def test_76_audit_written_atomically(self):
        before = self.p.stack.audit.count()
        self.p.calib(self.p.proposer)
        self.assertEqual(self.p.stack.audit.count(), before + 1)

    def test_77_audit_failure_blocks_activation(self):
        cal = _to_approved(self.p, target_type="calculation_version")
        cv_before = self._cv_count()
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                self.p.calibration.activate(self.p.activator, SCOPE, self.p.store.get_calibration(cal["id"]))
        finally:
            self.p.stack.audit.append = orig
        self.assertEqual(self.p.store.get_calibration(cal["id"])["review_state"], "APPROVED")   # rolled back
        self.assertIsNone(self.p.store.activation_for(cal["id"]))
        self.assertEqual(self._cv_count(), cv_before)                # no version leaked

    # ---- output slices (78) -----------------------------------------------
    def test_78_output_slices_use_real_records(self):
        pr, ob, pa, er = self.p.chain(predicted=10, actual=2)
        a = self.p.attribution.propose(er.id, factor_category="stockout", proposed_factor="stockout")
        self.p.attribution.add_evidence(a["id"], evidence_kind="avail", supports=True, description="0")
        self.p.attribution.assess(a)
        s = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c", error_refs=[er.id],
                                   pattern_type="over_forecast")
        cal = _to_validated(self.p, self.p.calib(self.p.proposer))
        run = self.p.backtest.run(cal["id"], current_version="cv1", proposed_version="cv2",
                                  cohorts=[{"name": "all", "current_error": 10, "proposed_error": 6, "material": True}])
        self.assertEqual(output.prediction_slice(self.p.store, pr.id)["prediction_id"], pr.id)
        self.assertEqual(output.pairing_slice(self.p.store, pa.id)["pairing_status"], "PAIRED")
        self.assertEqual(output.error_slice(self.p.store, er.id)["signed_error"], "-8.0")
        self.assertTrue(output.attribution_slice(self.p.store, er.id)[0]["evidence"])
        self.assertTrue(output.learning_signal_queue(self.p.store, "new_inventory_forecasting"))
        self.assertTrue(output.calibration_queue(self.p.store, "VALIDATED"))
        self.assertTrue(output.validation_comparison(self.p.store, run["run_id"])["results"])
        self.assertIn("raw_history_path", output.prediction_slice(self.p.store, pr.id))


if __name__ == "__main__":
    unittest.main()
