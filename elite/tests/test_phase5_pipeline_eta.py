"""Phase 5 acceptance — production pipeline + ETA/arrival windows (items 1-10)."""
import os
import tempfile
import unittest

from elite.workflow.fixtures import SCOPE, Phase5


class TestPhase5PipelineEta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmp, "elite.db")
        self.p = Phase5(self.dbp)
        self.c = self.p.combination(exterior_color="BLACK")

    def tearDown(self):
        self.p.close()

    def test_01_pipeline_projection_survives_restart(self):
        self.p.pipeline.project("po1", self.c.id, SCOPE, arrival_month="2026-10")
        self.p.close()
        p2 = Phase5(self.dbp)
        self.addCleanup(p2.close)
        rows = p2.wf.pipeline_for_order("po1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].arrival_month, "2026-10")

    def test_02_order_identity_stable_through_updates(self):
        self.p.pipeline.project("po1", self.c.id, SCOPE, production_status="planned")
        self.p.pipeline.project("po1", self.c.id, SCOPE, production_status="in_production")
        current = self.p.wf.pipeline_for_order("po1", current_only=True)
        allr = self.p.wf.pipeline_for_order("po1", current_only=False)
        self.assertEqual(len(current), 1)                          # one current per order
        self.assertEqual(current[0].production_status, "in_production")
        self.assertEqual(len(allr), 2)                             # prior preserved
        self.assertTrue(all(r.production_order_id == "po1" for r in allr))  # identity stable

    def test_03_pre_vin_to_vin_does_not_duplicate_pipeline(self):
        self.p.pipeline.project("po1", self.c.id, SCOPE, vin_status="pending")
        self.p.pipeline.link_vin("po1", "1GNSKBKC5FR000001", vehicle_unit_id="vu1")
        current = self.p.wf.pipeline_for_order("po1", current_only=True)
        self.assertEqual(len(current), 1)                          # still one order, no duplicate
        self.assertEqual(current[0].vin_status, "linked")
        self.assertEqual(current[0].identity_refs.get("vehicle_unit_id"), "vu1")

    def test_04_cancelled_order_excluded_from_qualifying_future_supply(self):
        pipe = self.p.pipeline.project("po_cx", self.c.id, SCOPE, order_status="cancelled", arrival_month="2026-10")
        eta = self.p.pipeline.record_eta("po_cx", "month", arrival_month="2026-10")
        fs = self.p.pipeline.emit_future_supply(self.p.ni, pipe, eta)
        self.assertIsNone(fs)                                      # cancelled -> no future supply
        self.assertEqual(len(self.p.supply.qualifying_supply(self.c.id, SCOPE)), 0)

    def test_05_conflicting_pipeline_facts_remain_explicit(self):
        pipe = self.p.pipeline.project("po_cf", self.c.id, SCOPE, conflict="two sources disagree on ETA")
        self.assertEqual(self.p.wf.get_pipeline(pipe.id).conflict, "two sources disagree on ETA")

    def test_06_eta_precision_does_not_exceed_source_evidence(self):
        eta = self.p.pipeline.record_eta("po_m", "month", arrival_month="2026-10")
        month, conf, eligible = self.p.pipeline.interpret_eta(eta)
        self.assertEqual(month, "2026-10")                         # month-only, no invented day
        self.assertEqual(eta.precision, "month")

    def test_07_revised_eta_preserves_prior_history(self):
        self.p.pipeline.record_eta("po_r", "month", arrival_month="2026-10")
        self.p.pipeline.record_eta("po_r", "month", arrival_month="2026-11")
        hist = self.p.wf.eta_history_for("po_r")
        self.assertEqual([h.arrival_month for h in hist], ["2026-10", "2026-11"])   # both preserved
        self.assertEqual(hist[1].supersedes, hist[0].id)

    def test_08_cross_month_range_does_not_pick_favorable_month(self):
        eta = self.p.pipeline.record_eta("po_x", "range", eta_start="2026-10-20", eta_end="2026-11-08")
        month, conf, eligible = self.p.pipeline.interpret_eta(eta)
        self.assertEqual(month, "2026-11")                         # conservative later month, not favorable 2026-10
        self.assertEqual(conf, "medium")

    def test_09_unknown_eta_does_not_become_confident_supply(self):
        pipe = self.p.pipeline.project("po_u", self.c.id, SCOPE, arrival_month=None)
        eta = self.p.pipeline.record_eta("po_u", "unresolved")
        month, conf, eligible = self.p.pipeline.interpret_eta(eta)
        self.assertFalse(eligible)
        self.assertIsNone(self.p.pipeline.emit_future_supply(self.p.ni, pipe, eta))
        self.assertEqual(len(self.p.supply.qualifying_supply(self.c.id, SCOPE)), 0)

    def test_10_stale_eta_reduces_confidence_or_review(self):
        eta = self.p.pipeline.record_eta("po_s", "month", arrival_month="2026-09", stale=True)
        month, conf, eligible = self.p.pipeline.interpret_eta(eta)
        self.assertEqual(conf, "low")
        self.assertFalse(eligible)                                 # requires review, not confident supply


if __name__ == "__main__":
    unittest.main()
