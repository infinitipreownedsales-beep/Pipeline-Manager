"""Phase 8 acceptance — Prediction (1-6), Decision learning context (7-8), Observation (9-13)."""
import os
import sqlite3
import tempfile
import unittest

from elite.learning.fixtures import Phase8
from elite.workflow.fixtures import SCOPE


class TestPhase8PredictionObservation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase8(self.dbp)

    def tearDown(self):
        self.p.close()

    # ---- Prediction (1-6) --------------------------------------------------
    def test_01_prediction_survives_restart(self):
        pr = self.p.prediction(value=10)
        self.p.close()
        p2 = Phase8(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_prediction(pr.id))

    def test_02_prediction_immutable(self):
        pr = self.p.prediction(value=10)
        with self.assertRaises(sqlite3.Error):
            with self.p.store.conn:
                self.p.store.conn.execute("UPDATE prediction SET status='x' WHERE id=?", (pr.id,))

    def test_03_correction_preserves_original(self):
        pr = self.p.prediction(value=10)
        corrected = self.p.predictions.correct(pr, reason="typo", correcting_actor=self.p.predictor,
                                               new_attrs={"predicted_payload": {"value": 11, "unit": "units"}})
        self.assertNotEqual(corrected.id, pr.id)
        self.assertEqual(corrected.correction_of, pr.id)
        self.assertEqual(self.p.store.get_prediction(pr.id).predicted_payload["value"], 10)   # original intact
        self.assertTrue(self.p.store.prediction_corrections(pr.id))

    def test_04_new_facts_create_new_prediction(self):
        pr = self.p.prediction(value=10, period="2026-01")
        pr2 = self.p.prediction(value=12, period="2026-01")           # reissue under new facts
        self.assertNotEqual(pr.id, pr2.id)
        self.assertEqual(self.p.store.get_prediction(pr.id).predicted_payload["value"], 10)

    def test_05_prediction_preserves_versions(self):
        pr = self.p.prediction(value=10)
        self.assertIsNotNone(pr.calculation_version)
        self.assertIsNotNone(pr.comparison_spec_version)
        self.assertIsNotNone(pr.reproducibility_package)
        self.assertEqual(pr.fact_refs, ["bf_1"])
        self.assertEqual(pr.observation_contract, "actual_monthly_retail")   # declares its Observation contract

    def test_06_scenario_prediction_distinct(self):
        official = self.p.prediction(value=10, subject_entity_id="a")
        scenario = self.p.prediction(value=99, subject_entity_id="a", scenario_id="scn_1")
        self.assertIsNone(official.scenario_id)
        self.assertEqual(scenario.scenario_id, "scn_1")
        self.assertEqual([x.id for x in self.p.store.predictions_where(scenario_only=False)], [official.id])

    def test_06b_no_prediction_permitted(self):
        pr = self.p.prediction(resolution_status="no_prediction")
        self.assertEqual(pr.resolution_status, "no_prediction")
        self.assertEqual(pr.predicted_payload, {})                    # never manufactured

    # ---- Decision learning context (7-8) ----------------------------------
    def test_07_context_does_not_invent_rationale(self):
        ctx = self.p.decisions.attach(decision_ref="dec_1", owning_domain="new_inventory_forecasting",
                                      store_scope=SCOPE, selected_action="order_2", stated_rationale=None)
        self.assertIsNone(ctx["stated_rationale"])                    # absence stays unknown
        import json
        self.assertEqual(json.loads(ctx["rejected_alternatives"]), [])   # not invented

    def test_08_context_survives_restart(self):
        ctx = self.p.decisions.attach(decision_ref="dec_1", owning_domain="new_inventory_forecasting",
                                      store_scope=SCOPE, selected_action="order_2",
                                      rejected_alternatives=["order_1"], stated_rationale="cover need")
        self.p.close()
        p2 = Phase8(self.dbp)
        self.addCleanup(p2.close)
        row = p2.store.get_decision_context(ctx["id"])
        self.assertEqual(row["selected_action"], "order_2")

    # ---- Observation (9-13) -----------------------------------------------
    def test_09_observation_uses_accepted_facts(self):
        ob = self.p.observation(value=8)
        self.assertEqual(ob.fact_refs, ["bf_actual_1"])
        self.assertEqual(ob.observed_payload["value"], 8)

    def test_10_missing_observation_not_zero(self):
        ob = self.p.observation(payload_missing=True)
        self.assertIsNone(ob.observed_payload)                        # MISSING, not 0
        self.assertEqual(ob.completeness, "missing")
        self.assertEqual(ob.resolution_status, "incomplete")

    def test_11_observation_correction_preserves_original(self):
        ob = self.p.observation(value=8)
        corrected = self.p.observations.correct(ob, reason="restated", correcting_actor=self.p.observer,
                                                new_payload={"value": 9, "unit": "units"})
        self.assertEqual(self.p.store.get_observation(ob.id).observed_payload["value"], 8)   # original intact
        self.assertEqual(corrected.observed_payload["value"], 9)
        self.assertTrue(self.p.store.observation_corrections(ob.id))

    def test_12_reversal_preserves_history(self):
        ob = self.p.observation(value=8)
        self.p.observations.reverse(ob, reason="voided", correcting_actor=self.p.observer)
        self.assertEqual(self.p.store.get_observation(ob.id).observed_payload["value"], 8)   # preserved
        rows = self.p.store.observation_corrections(ob.id)
        self.assertTrue(any(r["correction_type"] == "reversal" and r["negates_effect"] for r in rows))

    def test_13_conflicting_facts_unresolved(self):
        ob = self.p.observations.accept(observation_type="actual_monthly_retail",
                                        owning_domain="new_inventory_forecasting", store_scope=SCOPE,
                                        subject_entity_id="c", observed_payload={"value": 5, "unit": "units"},
                                        resolution_status="conflicting", completeness="conflicting")
        self.assertEqual(ob.resolution_status, "conflicting")

    def test_13b_scenario_output_cannot_be_observation(self):
        from elite.errors import ValidationError
        with self.assertRaises(ValidationError):
            self.p.observations.accept(observation_type="actual_monthly_retail",
                                       owning_domain="new_inventory_forecasting", store_scope=SCOPE,
                                       observed_payload={"value": 5}, is_scenario_output=True)


if __name__ == "__main__":
    unittest.main()
