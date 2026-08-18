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


if __name__ == "__main__":
    unittest.main(verbosity=2)
