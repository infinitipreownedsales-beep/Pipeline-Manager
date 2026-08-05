"""Phase 8 acceptance — Attribution (37-43), Learning Signal (44-50), cross-domain boundaries (51-53)."""
import os
import tempfile
import unittest

from elite.errors import ValidationError
from elite.learning.boundaries import assert_same_domain
from elite.learning.fixtures import Phase8


class TestPhase8AttributionSignal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase8(os.path.join(self.tmp, "elite.db"))
        _, _, _, self.err = self.p.chain(predicted=10, actual=2)      # a material error to explain

    def tearDown(self):
        self.p.close()

    # ---- Attribution (37-43) ----------------------------------------------
    def test_37_attribution_identifies_evidence(self):
        a = self.p.attribution.propose(self.err.id, factor_category="stockout", proposed_factor="stockout")
        self.p.attribution.add_evidence(a["id"], evidence_kind="availability", supports=True, description="0 avail")
        assessed = self.p.attribution.assess(a)
        self.assertEqual(assessed["status"], "SUPPORTED")
        self.assertTrue(self.p.store.evidence_for_attribution(a["id"]))

    def test_38_contradicting_evidence_visible(self):
        a = self.p.attribution.propose(self.err.id, factor_category="timing_shift", proposed_factor="timing")
        self.p.attribution.add_evidence(a["id"], evidence_kind="x", supports=True, description="s")
        self.p.attribution.add_evidence(a["id"], evidence_kind="y", supports=False, description="against")
        assessed = self.p.attribution.assess(a)
        self.assertEqual(assessed["status"], "PARTIALLY_SUPPORTED")
        ev = self.p.store.evidence_for_attribution(a["id"])
        self.assertTrue(any(not e["supports"] for e in ev))          # contradiction stays visible

    def test_39_unsupported_stays_proposed(self):
        a = self.p.attribution.propose(self.err.id, factor_category="market_or_customer_factor",
                                       proposed_factor="maybe lost sales")
        self.assertEqual(self.p.attribution.assess(a)["status"], "PROPOSED")   # no evidence -> not asserted

    def test_40_unknown_customer_intent_stays_unknown(self):
        a = self.p.attribution.propose(self.err.id, factor_category="unknown",
                                       proposed_factor="customer intent unrecorded")
        self.assertEqual(a["factor_category"], "unknown")
        self.assertEqual(self.p.attribution.assess(a)["status"], "PROPOSED")

    def test_41_stockout_no_exact_missed_sales(self):
        # a stockout attribution supports constrained demand but records no exact missed quantity
        a = self.p.attribution.propose(self.err.id, factor_category="stockout",
                                       proposed_factor="constrained by stockout")
        self.assertNotIn("missed_units", a.keys())
        self.assertNotIn("exact_missed", (a["proposed_factor"] or ""))

    def test_42_multiple_factors_coexist(self):
        a1 = self.p.attribution.propose(self.err.id, factor_category="stockout", proposed_factor="stockout")
        a2 = self.p.attribution.propose(self.err.id, factor_category="eta_variance", proposed_factor="late eta")
        cats = {r["factor_category"] for r in self.p.store.attributions_for_error(self.err.id)}
        self.assertEqual(cats, {"stockout", "eta_variance"})          # one outcome, many factors

    def test_43_human_review_preserves_automated(self):
        a = self.p.attribution.propose(self.err.id, factor_category="source_data_quality",
                                       proposed_factor="bad feed", source="automated")
        reviewed = self.p.attribution.human_review(a, self.p.full, outcome="SUPPORTED", notes="confirmed")
        self.assertEqual(self.p.store.get_attribution(a["id"])["source"], "automated")   # original preserved
        self.assertEqual(reviewed["source"], "human")
        self.assertEqual(reviewed["correction_of"], a["id"])

    # ---- Learning Signal (44-50) ------------------------------------------
    def test_44_single_error_no_supported_signal(self):
        s = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c", error_refs=[self.err.id],
                                   pattern_type="over_forecast")
        self.assertNotEqual(s["status"], "SUPPORTED")

    def test_45_46_47_min_evidence_sample_recurrence(self):
        refs = [self.p.chain(predicted=10, actual=6, subject_entity_id=f"r{i}")[3].id for i in range(4)]
        weak = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c1", error_refs=refs[:1],
                                      pattern_type="over_forecast", min_sample=3, min_recurrence=2)
        strong = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c2", error_refs=refs,
                                        pattern_type="over_forecast", min_sample=3, min_recurrence=2)
        self.assertEqual(weak["status"], "INSUFFICIENT_EVIDENCE")     # 45: enforced
        self.assertEqual(weak["sample_size"], 1)                      # 46: visible
        self.assertEqual(strong["status"], "SUPPORTED")               # 47: recurrence demonstrated
        self.assertEqual(strong["recurrence"], 4)

    def test_48_conflicting_evidence_conflicting_signal(self):
        refs = [self.p.chain(predicted=10, actual=6, subject_entity_id=f"q{i}")[3].id for i in range(4)]
        s = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c", error_refs=refs,
                                   pattern_type="mixed", conflicting=True)
        self.assertEqual(s["status"], "CONFLICTING")

    def test_49_data_quality_reduces_confidence(self):
        refs = [self.p.chain(predicted=10, actual=6, subject_entity_id=f"d{i}")[3].id for i in range(4)]
        s = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c", error_refs=refs,
                                   pattern_type="over_forecast", data_quality_conditions={"weak": True})
        self.assertEqual(s["status"], "MONITORING")
        self.assertEqual(s["confidence"], "low")

    def test_50_signal_no_operational_effect(self):
        # a Learning Signal cannot itself create/activate any version; escalation is a separate step
        refs = [self.p.chain(predicted=10, actual=6, subject_entity_id=f"e{i}")[3].id for i in range(4)]
        s = self.p.signals.observe("new_inventory_forecasting", subject_or_cohort="c", error_refs=refs,
                                   pattern_type="over_forecast")
        before = self.p.store.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"]
        self.assertEqual(before, 0)                                   # no activation from a signal
        escalated = self.p.signals.escalate(s)
        self.assertEqual(escalated["status"], "ESCALATED_TO_CALIBRATION")   # explicit, not automatic
        self.assertEqual(self.p.store.conn.execute("SELECT COUNT(*) n FROM calibration_activation").fetchone()["n"], 0)

    # ---- cross-domain boundaries (51-53) ----------------------------------
    def test_51_ni_signal_cannot_mutate_service_loaner(self):
        with self.assertRaises(ValidationError):
            assert_same_domain("new_inventory_forecasting", "service_loaner")

    def test_52_service_loaner_signal_cannot_mutate_ni(self):
        with self.assertRaises(ValidationError):
            assert_same_domain("service_loaner", "new_inventory_forecasting")

    def test_53_executive_demo_signal_cannot_mutate_service_loaner(self):
        with self.assertRaises(ValidationError):
            assert_same_domain("executive_demo", "service_loaner")
        # ...unless an explicit approved cross-domain relationship exists
        self.assertTrue(assert_same_domain("executive_demo", "service_loaner", approved_cross_domain=True))


if __name__ == "__main__":
    unittest.main()
