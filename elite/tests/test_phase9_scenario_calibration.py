"""Phase 9 acceptance — Scenario administration + promotion (55-67), Calibration workspace (68-72)."""
import os
import tempfile
import unittest

from elite.errors import ValidationError
from elite.govern.fixtures import Phase9
from elite.learning.fixtures import _to_approved, _to_validated
from elite.workflow.fixtures import SCOPE


class TestPhase9ScenarioCalibration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase9(os.path.join(self.tmp, "elite.db"))

    def tearDown(self):
        self.p.close()

    def _shared_reviewed(self, sid):
        sc = self.p.scenario(scenario_id=sid)
        self.p.scenarios.share(self.p.scenario_owner, SCOPE, sc, shared_with=self.p.reviewer)
        self.p.scenarios.review(self.p.scenario_reviewer, SCOPE, self.p.store.get_scenario(sc["id"]))
        return self.p.store.get_scenario(sc["id"])

    # ---- scenario administration (55-67) ----------------------------------
    def test_55_scenario_isolated_from_official(self):
        sc = self.p.scenario(scenario_id="s1")
        # a scenario has its own record + status; it changes no official workspace/decision state
        self.assertEqual(sc["status"], "DRAFT")
        self.assertEqual(self.p.store.all_items(), [])                 # no official items created

    def test_56_sharing_not_approval(self):
        sc = self.p.scenario(scenario_id="s2")
        shared = self.p.scenarios.share(self.p.scenario_owner, SCOPE, sc, shared_with=self.p.reviewer)
        self.assertEqual(shared["status"], "SHARED")                   # shared, NOT approved/official

    def test_57_approved_for_discussion_not_official(self):
        sc = self._shared_reviewed("s3")
        self.assertEqual(sc["status"], "APPROVED_FOR_DISCUSSION")      # discussion only, not official

    def test_58_59_promotion_no_effect_policy_routes(self):
        sc = self._shared_reviewed("s4")
        cv_before = self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]
        prom = self.p.scenarios.request_promotion(self.p.scenario_owner, SCOPE, sc,
                                                  target_type="official_policy_review")
        self.assertEqual(prom["routed_to"], "policy_review")           # 59: routes to policy-review request
        self.assertIsNotNone(prom["review_ref"])
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"],
                         cv_before)                                    # 58: no operational effect

    def test_60_calibration_promotion_routes_to_calibration(self):
        sc = self._shared_reviewed("s5")
        prom = self.p.scenarios.request_promotion(self.p.scenario_owner, SCOPE, sc,
                                                  target_type="calculation_version_review")
        self.assertEqual(prom["routed_to"], "calibration")             # routes through Phase 8 governance

    def test_61_operational_promotion_requires_new_decision(self):
        sc = self._shared_reviewed("s6")
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM governed_decision").fetchone()["n"]
        prom = self.p.scenarios.request_promotion(self.p.scenario_owner, SCOPE, sc, target_type="operational_decision")
        self.assertEqual(prom["routed_to"], "official_decision")
        # the promotion does NOT copy scenario state into an official Decision
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM governed_decision").fetchone()["n"], before)

    def test_62_rejected_promotion_no_effect(self):
        sc = self._shared_reviewed("s7")
        prom = self.p.scenarios.request_promotion(self.p.scenario_owner, SCOPE, sc, target_type="operational_decision")
        rej = self.p.scenarios.reject_promotion(self.p.scenario_owner, SCOPE, prom, reason="no")
        self.assertEqual(rej["status"], "rejected")

    def test_63_scenario_correction_preserves_history(self):
        sc = self.p.scenario(scenario_id="s8")
        corrected = self.p.scenarios.correct(self.p.scenario_owner, SCOPE, sc, reason="fix",
                                             new_overrides={"coverage_target": 9})
        self.assertEqual(corrected["correction_of"], sc["id"])
        self.assertEqual(self.p.store.get_scenario(sc["id"])["status"], "CORRECTED")   # original preserved

    def test_64_scenario_identifies_overrides_and_baseline(self):
        import json
        sc = self.p.scenario(scenario_id="s9", overrides={"coverage_target": 7})
        self.assertEqual(json.loads(sc["overrides"])["coverage_target"], 7)
        self.assertEqual(sc["official_baseline_ref"], "base_1")

    def test_65_private_scenario_scoped(self):
        sc = self.p.scenario(scenario_id="s10")
        self.assertEqual(sc["store_scope"], SCOPE)                     # access is scoped to its store

    def test_66_scenario_cannot_become_observation(self):
        self.assertFalse(self.p.scenarios.scenario_can_become_observation())
        with self.assertRaises(ValidationError):
            self.p.p8.observations.accept(observation_type="actual_monthly_retail",
                                          owning_domain="new_inventory_forecasting", store_scope=SCOPE,
                                          observed_payload={"value": 5}, is_scenario_output=True)

    def test_67_scenario_prediction_excluded_from_official_learning(self):
        official = self.p.p8.prediction(value=10, subject_entity_id="a")
        scenario_pred = self.p.p8.prediction(value=99, subject_entity_id="a", scenario_id="scn_x")
        official_only = [pr.id for pr in self.p.p8.store.predictions_where(scenario_only=False)]
        self.assertIn(official.id, official_only)
        self.assertNotIn(scenario_pred.id, official_only)              # scenario prediction excluded

    # ---- Calibration workspace (68-72) ------------------------------------
    def test_68_calibration_workspace_uses_phase8(self):
        cal = _to_validated(self.p.p8, self.p.p8.calib(self.p.p8.proposer))
        review = self.p.calibration_ws.review(cal["id"])
        self.assertEqual(review["calibration_id"], cal["id"])         # reads the Phase 8 record
        self.assertEqual(review["review_state"], "VALIDATED")

    def test_69_approval_distinct_from_activation(self):
        cal = _to_validated(self.p.p8, self.p.p8.calib(self.p.p8.proposer))
        cv_before = self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"]
        self.p.calibration_ws.approve(self.p.p8.approver, SCOPE, cal)
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calculation_version").fetchone()["n"],
                         cv_before)                                    # approval creates no version
        self.assertIsNone(self.p.p8.store.activation_for(cal["id"]))

    def test_70_scheduled_calibration_future_effective(self):
        cal = _to_approved(self.p.p8, target_type="calculation_version", effective="2030-01-01T00:00:00+00:00")
        r = self.p.calibration_ws.activate(self.p.p8.activator, SCOPE, cal, future=True)
        self.assertEqual(r["calibration"]["review_state"], "SCHEDULED")
        self.assertEqual(self.p.p8.store.activation_for(cal["id"])["scheduled"], 1)

    def test_71_policy_target_no_direct_policy_mutation(self):
        pv_before = self.p.store.conn.execute("SELECT COUNT(*) n FROM policy_version").fetchone()["n"]
        cal = _to_approved(self.p.p8, target_type="materiality_threshold")
        r = self.p.calibration_ws.activate(self.p.p8.activator, SCOPE, cal)
        self.assertEqual(r["effect"]["kind"], "policy_review_recommendation")
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM policy_version").fetchone()["n"], pv_before)

    def test_72_rollback_governed_and_historical(self):
        cal = _to_approved(self.p.p8, target_type="calculation_version", current_version="cv_old")
        self.p.calibration_ws.activate(self.p.p8.activator, SCOPE, cal)
        r = self.p.calibration_ws.rollback(self.p.p8.rollbacker, SCOPE, cal, restored_version_ref="cv_old",
                                           reason="regressed")
        self.assertEqual(r["calibration"]["review_state"], "ROLLED_BACK")
        self.assertTrue(self.p.p8.store.rollback_for(cal["id"]))       # historical


if __name__ == "__main__":
    unittest.main()
