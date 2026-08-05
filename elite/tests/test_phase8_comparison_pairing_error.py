"""Phase 8 acceptance — Comparison Specification (14-15), Pairing (16-26), Error (27-36)."""
import os
import tempfile
import unittest

from elite.errors import ValidationError
from elite.learning.fixtures import Phase8
from elite.workflow.fixtures import SCOPE


class TestPhase8ComparisonPairingError(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase8(self.dbp)
        self.sp = self.p.spec()

    def tearDown(self):
        self.p.close()

    def _pred(self, **kw):
        return self.p.prediction(spec=self.sp, **kw)

    # ---- Comparison Specification (14-15) ---------------------------------
    def test_14_comparison_spec_survives_restart(self):
        self.p.close()
        p2 = Phase8(self.dbp)
        self.addCleanup(p2.close)
        self.assertIsNotNone(p2.store.get_comparison_spec(self.sp.id))
        self.assertEqual(p2.store.get_comparison_spec(self.sp.id).status, "active")

    def test_15_inactive_spec_cannot_pair(self):
        inactive = self.p.spec(active=False, version="9.9.9")
        pr, ob = self._pred(subject_entity_id="c"), self.p.observation(subject_entity_id="c")
        with self.assertRaises(ValidationError):
            self.p.pairing.pair(pr, ob, inactive)

    # ---- Pairing (16-26) ---------------------------------------------------
    def test_16_type_mismatch_rejected(self):
        pr = self._pred(subject_entity_id="c")
        wrong = self.p.observation(subject_entity_id="c", observation_type="actual_arrival_timing")
        with self.assertRaises(ValidationError):
            self.p.pairing.pair(pr, wrong, self.sp)

    def test_17_identity_mismatch_rejected(self):
        pr = self._pred(subject_entity_id="c1")
        ob = self.p.observation(subject_entity_id="c2")
        self.assertEqual(self.p.pairing.pair(pr, ob, self.sp).pairing_status, "IDENTITY_MISMATCH")

    def test_18_scope_mismatch_rejected(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c", scope="store:WEST")
        self.assertEqual(self.p.pairing.pair(pr, ob, self.sp).pairing_status, "SCOPE_MISMATCH")

    def test_19_unit_mismatch_rejected(self):
        pr = self._pred(subject_entity_id="c", unit="units")
        ob = self.p.observation(subject_entity_id="c", unit="dollars")
        self.assertEqual(self.p.pairing.pair(pr, ob, self.sp).pairing_status, "UNIT_MISMATCH")

    def test_20_observation_window_enforced(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        self.assertEqual(self.p.pairing.pair(pr, ob, self.sp, observed_late=True,
                                             within_tolerance=False).pairing_status, "OUTSIDE_WINDOW")

    def test_21_valid_exact_pairing(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        pa = self.p.pairing.pair(pr, ob, self.sp)
        self.assertEqual(pa.pairing_status, "PAIRED")
        self.assertTrue(pa.unit_compatible)

    def test_22_replayed_pairing_idempotent(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        a = self.p.pairing.pair(pr, ob, self.sp)
        b = self.p.pairing.pair(pr, ob, self.sp)
        self.assertEqual(a.id, b.id)                                  # no duplicate
        self.assertEqual(len(self.p.store.pairings_for_prediction(pr.id)), 1)

    def test_23_ambiguous_unresolved(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        self.assertEqual(self.p.pairing.pair(pr, ob, self.sp, ambiguous=True).pairing_status, "AMBIGUOUS")

    def test_24_partial_pairing(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c", completeness="partial")
        self.assertEqual(self.p.pairing.pair(pr, ob, self.sp).pairing_status, "PARTIAL")

    def test_25_late_pairing_labeled(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        pa = self.p.pairing.pair(pr, ob, self.sp, observed_late=True, within_tolerance=True)
        self.assertEqual(pa.pairing_status, "LATE_PAIRED")
        self.assertEqual(pa.timing_relationship, "late")

    def test_25b_pending_until_window(self):
        pr = self._pred(subject_entity_id="c")
        self.assertEqual(self.p.pairing.pair(pr, None, self.sp, window_open=True).pairing_status,
                         "PENDING_OBSERVATION")

    def test_25c_aggregation_only_when_permitted(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        with self.assertRaises(ValidationError):                     # spec does not permit aggregation
            self.p.pairing.pair_aggregate(pr, [ob], self.sp)
        agg_spec = self.p.spec(aggregate=True, version="agg.1")
        pr2 = self.p.prediction(spec=agg_spec, subject_entity_id="c")
        ob2 = self.p.observation(subject_entity_id="c")
        self.assertEqual(len(self.p.pairing.pair_aggregate(pr2, [ob2], agg_spec)), 1)

    def test_26_pairing_does_not_mutate(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c")
        self.p.pairing.pair(pr, ob, self.sp)
        self.assertEqual(self.p.store.get_prediction(pr.id).predicted_payload, pr.predicted_payload)
        self.assertEqual(self.p.store.get_observation(ob.id).observed_payload, ob.observed_payload)

    # ---- Error (27-36) -----------------------------------------------------
    def _paired(self, predicted, actual, **kw):
        pr = self._pred(subject_entity_id="c", value=predicted)
        ob = self.p.observation(subject_entity_id="c", value=actual, **kw)
        return pr, ob, self.p.pairing.pair(pr, ob, self.sp)

    def test_27_error_requires_valid_pairing(self):
        pr = self._pred(subject_entity_id="c1")
        ob = self.p.observation(subject_entity_id="c2")               # -> IDENTITY_MISMATCH pairing
        pa = self.p.pairing.pair(pr, ob, self.sp)
        with self.assertRaises(ValidationError):
            self.p.errors.compute(pa, pr, ob, self.sp)

    def test_28_29_signed_and_absolute_error(self):
        pr, ob, pa = self._paired(10, 7)
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        self.assertEqual(e.signed_error, "-3.0")
        self.assertEqual(e.absolute_error, "3.0")

    def test_30_percentage_zero_denominator_safe(self):
        pr, ob, pa = self._paired(0, 3)                              # expected 0 -> no percentage
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        self.assertIsNone(e.percentage_error)                        # safe, not division error
        self.assertEqual(e.signed_error, "3.0")

    def test_31_missing_observation_no_fabricated_error(self):
        pr = self._pred(subject_entity_id="c")
        ob = self.p.observation(subject_entity_id="c", payload_missing=True)
        pa = self.p.pairing.pair(pr, ob, self.sp)
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        self.assertEqual(e.resolution_status, "pending")
        self.assertIsNone(e.signed_error)

    def test_32_partial_observation_partial_error(self):
        pr, ob, pa = self._paired(10, 6, completeness="partial")
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        self.assertEqual(e.resolution_status, "partial")

    def test_33_materiality_resolves_through_policy(self):
        th, pv = self.p.materiality(threshold=5)
        pr, ob, pa = self._paired(10, 2)
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=th, materiality_policy_version=pv)
        self.assertEqual(e.materiality, "material")                  # |8| >= 5
        pr2, ob2, pa2 = self._paired(10, 9)
        e2 = self.p.errors.compute(pa2, pr2, ob2, self.sp, materiality_threshold=th, materiality_policy_version=pv)
        self.assertEqual(e2.materiality, "immaterial")

    def test_34_error_preserves_versions(self):
        pr, ob, pa = self._paired(10, 7)
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        self.assertEqual(e.comparison_spec_version, self.sp.version)
        self.assertEqual(e.calculation_version, self.p.error_cv)
        self.assertIsNotNone(e.reproducibility_package)

    def test_35_corrected_observation_superseding_error(self):
        pr, ob, pa = self._paired(10, 7)
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        corrected = self.p.observations.correct(ob, reason="restated", correcting_actor=self.p.observer,
                                                new_payload={"value": 9, "unit": "units"})
        pa2 = self.p.pairing.pair(pr, corrected, self.sp)
        e2 = self.p.errors.recompute_for_corrected_observation(e, pa2, pr, corrected, self.sp,
                                                               materiality_threshold=5)
        self.assertEqual(self.p.store.get_error(e.id).signed_error, "-3.0")   # original preserved
        self.assertEqual(e2.signed_error, "-1.0")

    def test_36_error_no_causation(self):
        # the Error record carries no causal field — causation belongs to Attribution
        pr, ob, pa = self._paired(10, 7)
        e = self.p.errors.compute(pa, pr, ob, self.sp, materiality_threshold=5)
        cols = [d[0] for d in self.p.store.conn.execute("SELECT * FROM prediction_error").description]
        self.assertNotIn("cause", cols)
        self.assertNotIn("attribution", cols)


if __name__ == "__main__":
    unittest.main()
