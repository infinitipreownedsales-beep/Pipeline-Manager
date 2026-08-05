"""Phase 8 dedicated learning-governance regression (20 points).

Proves the end-to-end institutional-memory loop AND its constitutional guardrail: Learning may propose
change but never activates it; no approved Calibration means no operational change; historical
Predictions are never rewritten.
"""
import os
import tempfile
import unittest

from elite.errors import AuthorizationError, PersistenceError, ValidationError
from elite.learning.fixtures import Phase8, _to_validated
from elite.workflow.fixtures import SCOPE


class TestLearningGovernanceRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase8(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _cv_count(self):
        return self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]

    def test_learning_governance_regression(self):
        p = self.p
        # 1 an official Prediction is issued
        sp = p.spec()
        pred = p.prediction(value=10, subject_entity_id="c1", spec=sp)
        self.assertIsNone(pred.scenario_id)
        pred_cv = pred.calculation_version
        # 2 an accepted Observation later arrives
        obs = p.observation(value=4, subject_entity_id="c1")
        # 3 the applicable Comparison Specification pairs them
        pair = p.pairing.pair(pred, obs, sp)
        self.assertEqual(pair.pairing_status, "PAIRED")
        # 4 Error is calculated
        th, pv = p.materiality(threshold=5)
        err = p.errors.compute(pair, pred, obs, sp, materiality_threshold=th, materiality_policy_version=pv)
        self.assertEqual(err.signed_error, "-6.0")
        self.assertEqual(err.materiality, "material")
        # 5 evidence-supported Attribution is recorded
        attr = p.attribution.propose(err.id, factor_category="stockout", proposed_factor="constrained")
        p.attribution.add_evidence(attr["id"], evidence_kind="availability", supports=True, description="0 avail")
        self.assertEqual(p.attribution.assess(attr)["status"], "SUPPORTED")
        # 6 repeated evidence creates a supported Learning Signal
        refs = [err.id] + [p.chain(predicted=10, actual=5, subject_entity_id=f"r{i}")[3].id for i in range(3)]
        signal = p.signals.observe("new_inventory_forecasting", subject_or_cohort="cohort", error_refs=refs,
                                   attribution_refs=[attr["id"]], pattern_type="over_forecast")
        self.assertEqual(signal["status"], "SUPPORTED")
        self.assertEqual(signal["sample_size"], 4)
        # 7 Learning Signal alone changes nothing
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"], 0)
        cv_after_signal = self._cv_count()
        # 8 Calibration Proposal is created
        p.signals.escalate(signal)
        cal = p.calibration.propose(p.proposer, SCOPE, target_type="calculation_version",
                                    target_family=p.calc_target_family, current_version=pred_cv,
                                    proposed_change={"semver": "2.0.0"}, learning_signal_refs=[signal["id"]],
                                    affected_domains=["new_inventory_forecasting"])
        # 9 Proposal alone changes nothing
        self.assertEqual(self._cv_count(), cv_after_signal)
        self.assertIsNone(p.store.activation_for(cal["id"]))
        # 10 validation compares current and proposed versions on preserved historical inputs
        cal = _to_validated(p, cal)
        run = p.backtest.run(cal["id"], current_version=pred_cv, proposed_version="cv_new", cohorts=[
            {"name": "cohort", "current_error": 10, "proposed_error": 5, "material": True}])
        self.assertTrue(run["hypothetical"] and run["aggregate_improved"])
        self.assertEqual(p.store.get_prediction(pred.id).predicted_payload["value"], 10)   # inputs preserved
        # 11 approval alone does not activate
        p.calibration.approve(p.approver, SCOPE, p.store.get_calibration(cal["id"]))
        self.assertEqual(p.store.get_calibration(cal["id"])["review_state"], "APPROVED")
        self.assertIsNone(p.store.activation_for(cal["id"]))
        cv_before_activation = self._cv_count()
        # 12 authorized activation creates or references a new version
        r = p.calibration.activate(p.activator, SCOPE, p.store.get_calibration(cal["id"]))
        new_cv = r["effect"]["version_ref"]
        self.assertEqual(self._cv_count(), cv_before_activation + 1)
        self.assertIsNotNone(p.policy.get_calc_version(new_cv))
        # 13 future Predictions may use the new version
        future_pred = p.predictions.issue(prediction_type="new_inventory_monthly_demand",
                                          owning_domain="new_inventory_forecasting", store_scope=SCOPE,
                                          subject_entity_id="c2", predicted_payload={"value": 7, "unit": "units"},
                                          calculation_version=new_cv, comparison_spec_version=sp.version)
        self.assertEqual(future_pred.calculation_version, new_cv)
        # 14 prior Predictions retain the old version
        self.assertEqual(p.store.get_prediction(pred.id).calculation_version, pred_cv)
        # 15 rollback restores the prior approved version prospectively
        rb = p.calibration.rollback(p.rollbacker, SCOPE, p.store.get_calibration(cal["id"]),
                                    restored_version_ref=pred_cv, reason="regressed")
        self.assertEqual(rb["calibration"]["review_state"], "ROLLED_BACK")
        self.assertEqual(p.store.rollback_for(cal["id"])[0]["restored_version_ref"], pred_cv)
        # 16 no historical Prediction is rewritten (throughout)
        self.assertEqual(p.store.get_prediction(pred.id).predicted_payload["value"], 10)
        self.assertEqual(p.store.get_prediction(pred.id).calculation_version, pred_cv)
        # 17 audit failure prevents activation
        cal2 = _to_validated(p, p.calib(p.proposer))
        p.calibration.approve(p.approver, SCOPE, p.store.get_calibration(cal2["id"]))
        orig = p.stack.audit.append
        p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(PersistenceError):
                p.calibration.activate(p.activator, SCOPE, p.store.get_calibration(cal2["id"]))
        finally:
            p.stack.audit.append = orig
        self.assertIsNone(p.store.activation_for(cal2["id"]))
        # 18 replayed activation does not duplicate the version or activation record
        p.calibration.activate(p.activator, SCOPE, p.store.get_calibration(cal2["id"]))
        cv_once = self._cv_count()
        replay = p.calibration.activate(p.activator, SCOPE, p.store.get_calibration(cal2["id"]))
        self.assertTrue(replay["replayed"])
        self.assertEqual(self._cv_count(), cv_once)
        self.assertEqual(p.store.conn.execute(
            "SELECT COUNT(*) n FROM calibration_activation WHERE calibration_proposal_id=?", (cal2["id"],)
        ).fetchone()["n"], 1)
        # 19 a policy-targeted proposal does not directly mutate policy
        pv_before = p.store.conn.execute("SELECT COUNT(*) n FROM policy_version").fetchone()["n"]
        from elite.learning.fixtures import _to_approved
        cal3 = _to_approved(p, target_type="materiality_threshold")
        eff = p.calibration.activate(p.activator, SCOPE, p.store.get_calibration(cal3["id"]))["effect"]
        self.assertEqual(eff["kind"], "policy_review_recommendation")
        self.assertEqual(p.store.conn.execute("SELECT COUNT(*) n FROM policy_version").fetchone()["n"], pv_before)
        # 20 no approved Calibration means no operational change
        cv_now = self._cv_count()
        unapproved = p.calib(p.proposer)                              # PROPOSED only
        self.assertEqual(self._cv_count(), cv_now)
        self.assertIsNone(p.store.activation_for(unapproved["id"]))
        # bonus: an unauthorized activator is rejected below the UI
        cal4 = _to_validated(p, p.calib(p.proposer))
        p.calibration.approve(p.approver, SCOPE, p.store.get_calibration(cal4["id"]))
        with self.assertRaises(AuthorizationError):
            p.calibration.activate(p.proposer, SCOPE, p.store.get_calibration(cal4["id"]))


if __name__ == "__main__":
    unittest.main()
