"""Phase 3 — Service Loaner preowned evidence experience. The read-only bridge exposes DTS distribution +
model-year absorption (defensible sample only) from real source rows; the cockpit renders fleet composition,
DTS distribution and model-year comparison visuals WITHOUT inventing economics or determining Ideal Mix."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.preowned_evidence import (
    summarize_model_sales, summarize_model_year_sales, ModelEvidence, ModelYearEvidence,
    PreownedEvidence, DtsDistribution, _distribution, MIN_MODEL_YEAR_DTS)
from elite.loaner.loaner_cockpit import build_cockpit


class TestDistribution(unittest.TestCase):
    def test_distribution_stats_from_source_values(self):
        d = _distribution([10, 20, 30, 40])
        self.assertEqual(d.count, 4)
        self.assertEqual((d.minimum, d.maximum), (10.0, 40.0))
        self.assertEqual(d.median, 25.0)
        self.assertLessEqual(d.p25, d.median)
        self.assertGreaterEqual(d.p75, d.median)

    def test_empty_distribution_is_honest(self):
        d = _distribution([])
        self.assertEqual(d.count, 0)
        self.assertIsNone(d.median)

    def test_model_evidence_carries_distribution(self):
        rows = [{"model": "QX60", "days_to_sell": 20}, {"model": "QX60", "days_to_sell": 40},
                {"model": "QX60", "days_to_sell": 60}]
        ev = summarize_model_sales(rows, {"QX60": 5})
        self.assertEqual(ev[0].distribution.count, 3)
        self.assertEqual(ev[0].distribution.median, 40.0)

    # backward compatibility: constructing without the new field still works (defaults)
    def test_dataclasses_default_new_fields(self):
        m = ModelEvidence(model="QX60", active_units=1, sales_count=1, numeric_dts_count=0, median_dts=None)
        self.assertIsNone(m.distribution)
        p = PreownedEvidence(retail_received_at=None, models=(), retail_history_loaded=False,
                             fleet_models_resolved=False)
        self.assertEqual(p.model_years, ())


class TestModelYear(unittest.TestCase):
    def test_model_year_grouping_and_sample_gate(self):
        rows = ([{"model": "QX60", "year": 2024, "days_to_sell": 30}] * MIN_MODEL_YEAR_DTS
                + [{"model": "QX60", "year": 2023, "days_to_sell": 40}] * 2      # under-sampled
                + [{"model": "QX80", "year": 2024, "days_to_sell": 10}])         # not in active fleet
        my = summarize_model_year_sales(rows, {"QX60": 5})
        by = {(e.model, e.year): e for e in my}
        self.assertNotIn(("QX80", 2024), by)                     # not an active-fleet model
        self.assertTrue(by[("QX60", 2024)].defensible)           # meets sample gate
        self.assertFalse(by[("QX60", 2023)].defensible)          # too few usable DTS
        self.assertEqual(by[("QX60", 2024)].median_dts, 30.0)


class TestEvidenceCard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def _month(self):
        from elite.clock import to_utc_iso
        return to_utc_iso(self.p.clock.now())[:7]

    def test_card_renders_visuals_without_economics(self):
        evidence = PreownedEvidence(
            retail_received_at="2026-08-15T21:00:00+00:00",
            models=(ModelEvidence(model="QX60", active_units=27, sales_count=757, numeric_dts_count=751,
                                  median_dts=34.0,
                                  distribution=DtsDistribution(751, 3.0, 21.0, 34.0, 58.0, 190.0)),
                    ModelEvidence(model="QX50", active_units=4, sales_count=120, numeric_dts_count=118,
                                  median_dts=41.0,
                                  distribution=DtsDistribution(118, 5.0, 25.0, 41.0, 66.0, 150.0))),
            retail_history_loaded=True, fleet_models_resolved=True,
            model_years=(ModelYearEvidence("QX60", 2024, 90, 88, 30.0, True),
                         ModelYearEvidence("QX60", 2023, 3, 3, 45.0, False)))
        with patch("elite.loaner.preowned_evidence.build_preowned_evidence", return_value=evidence):
            body = self.full.get("/service-loaner").body
        # fleet composition + distribution + model-year sections, all present, provenance shown
        self.assertIn("Current fleet composition", body)
        self.assertIn("Historical resale speed", body)
        self.assertIn("Model-year resale absorption", body)
        self.assertIn("QX60 2024", body)                          # defensible model-year shown
        self.assertNotIn("QX60 2023", body)                       # under-sampled model-year held back
        self.assertIn("held back", body)
        self.assertIn("as of 2026-08-15", body)                   # provenance
        self.assertIn("34 days", body)                            # proof detail retained
        self.assertIn("class=\"bars\"", body) if False else self.assertIn('class="bars"', body)
        # economics remain undetermined
        self.assertIn("undetermined", body.lower())
        ck = build_cockpit(self.p.stack.db.conn, SCOPE, self.p.app.prefs, self._month())
        self.assertFalse(ck.economically_determined)
        self.assertIsNone(ck.ideal_fleet)

    def test_card_honest_when_no_history(self):
        ev = PreownedEvidence(retail_received_at=None, models=(), retail_history_loaded=False,
                              fleet_models_resolved=True)
        with patch("elite.loaner.preowned_evidence.build_preowned_evidence", return_value=ev):
            body = self.full.get("/service-loaner").body
        self.assertIn("No completed preowned-history v3 import", body)
        self.assertNotIn("Current fleet composition", body)       # no fabricated visuals


if __name__ == "__main__":
    unittest.main(verbosity=2)
