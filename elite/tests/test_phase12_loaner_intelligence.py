"""Service Loaner Intelligence Layer (A + B), read-only. Pure empirical transforms (cohort gates, model-year
maturity with invalid-exclusion, transparent evidence quality) + the workflow-first page render. Hard
boundary: no economics — Ideal stays Undetermined, no RETIRE/HOLD/release-by/ICV/Velocity/write-down."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.db import current_version
from elite.loaner import intelligence as I
from elite.loaner.preowned_evidence import DtsDistribution


def _rows(n, price0=20000, year=2022, sold="2026-05-15", gross=2000):
    return [{"price": price0 + i * 100, "gross_profit": gross + i, "sold_date": sold, "year": year} for i in range(n)]


class TestTransforms(unittest.TestCase):
    def test_cohort_gate_and_recency_exposed(self):
        c = I._cohort("resale", "QX60 · MY2022", _rows(8, sold="2026-05-15"), lambda r: r["price"],
                      I.RESALE_MIN_N, "2026-08-15")
        self.assertEqual(c.n, 8)
        self.assertTrue(c.gated)                      # meets the n>=8 gate
        self.assertEqual(c.as_of, "2026-08-15")
        self.assertEqual(c.latest, "2026-05-15")
        self.assertGreater(c.recent_n, 0)             # observations within the recency window are counted
        thin = I._cohort("resale", "x", _rows(3), lambda r: r["price"], I.RESALE_MIN_N, "2026-08-15")
        self.assertFalse(thin.gated)                  # below gate -> not a headline

    def test_maturity_excludes_invalid_and_flags_thin(self):
        rows = (_rows(3, sold="2024-06-01", year=2022)        # maturity 2, n=3 -> thin (<5)
                + _rows(6, sold="2024-06-01", year=2019)      # maturity 5 -> '5+', n=6 -> plotted
                + [{"price": 1, "sold_date": "2019-01-01", "year": 2022}] * 4)  # maturity -3 -> excluded
        bins, excluded = I._maturity(rows)
        self.assertEqual(excluded, 4)                 # invalid (negative) maturity excluded + counted
        by = {b.label: b for b in bins}
        self.assertTrue(by["2"].thin)                 # n=3 < 5 gate
        self.assertFalse(by["5+"].thin)               # n=6 >= 5
        self.assertEqual(by["5+"].n, 6)

    def test_quality_factors_are_transparent(self):
        c = I._cohort("resale", "x", _rows(10, sold="2026-07-15"), lambda r: r["price"], I.RESALE_MIN_N, "2026-08-15")
        q = I._quality(c)
        self.assertIn(q.label, ("Strong", "Moderate", "Thin"))
        self.assertIn("n=10", q.sample)               # sample factor visible
        self.assertIn("within", q.recency)            # recency factor visible
        self.assertIn("IQR", q.spread)                # spread factor visible
        thin_q = I._quality(I._cohort("resale", "x", _rows(3), lambda r: r["price"], I.RESALE_MIN_N, "2026-08-15"))
        self.assertEqual(thin_q.label, "Thin")        # below gate -> Thin

    def test_gates_are_named_configurable_constants(self):
        for name in ("RESALE_MIN_N", "GROSS_MIN_N", "MATURITY_BIN_MIN_N"):
            self.assertIsInstance(getattr(I, name), int)
        self.assertEqual((I.RESALE_MIN_N, I.GROSS_MIN_N, I.MATURITY_BIN_MIN_N), (8, 8, 5))


def _fake_intel():
    dts = DtsDistribution(751, 3.0, 21.0, 34.0, 58.0, 190.0)
    resale = I.Cohort("resale", "QX60 · model-year 2023", DtsDistribution(40, 26000.0, 28000.0, 31000.0, 34000.0, 46000.0),
                      "2026-08-15", "2023-01-10", "2026-06-01", 12, I.RESALE_MIN_N, True)
    gross = I.Cohort("gross", "QX60 · all model-years", DtsDistribution(38, 0.0, 900.0, 2100.0, 3300.0, 6000.0),
                     "2026-08-15", "2019-01-01", "2026-06-01", 9, I.GROSS_MIN_N, True)
    mat = (I.MaturityBin("0", 12, 41000.0, False), I.MaturityBin("1", 3, 37000.0, True))
    q = I.EvidenceQuality("Strong", "n=40 (gate 8)", "latest 2026-06-01, 12/40 within 365d of as-of", "IQR/median = 0.19")
    model = I.ModelIntel("QX60", 27, 757, dts, resale, (resale,), gross, (gross,), mat, 5, q)
    unit = I.UnitIntel("slu_1", "JN1AZ0000000004821", "QX60", "2025-03-01", 533, 12940, True,
                       "ACTIVE_RENTED", "rented", ())
    unit2 = I.UnitIntel("slu_2", "JN1AZ0000000009007", "QX50", None, None, None, False,
                        "ACTIVE_AVAILABLE", "available", ("in-service date not resolved", "mileage not reported in latest snapshot"))
    att = (I.Attention("missing_mileage", "QX50 009007 — mileage not reported in latest snapshot", "slu_2", "JN1AZ0000000009007"),)
    return I.LoanerIntel(current_fleet=27, desired_fleet=20, ideal_fleet=None,
                         composition=(("QX60", 27),), units=(unit, unit2), attention=att, models=(model,),
                         retail_as_of="2026-08-15", retail_loaded=True, fleet_models_resolved=True)


class TestIntelligencePage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_page_sections_and_boundary(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=_fake_intel()):
            b = self.full.get("/service-loaner").body
        # 5-section workflow-first architecture
        for tok in ("Fleet state", "Operational attention", "What history says", "Active fleet"):
            self.assertIn(tok, b)
        # Current / Desired / Ideal distinct, Ideal Undetermined
        self.assertIn("Current fleet (authoritative)", b)
        self.assertIn("Undetermined", b)
        # evidence exposes cohort / n / as-of and quality label
        self.assertIn("model-year 2023", b)
        self.assertIn("as-of 2026-08-15", b)
        self.assertIn("Evidence: Strong", b)
        self.assertIn("Model-year age at resale (maturity)", b)   # NOT "depreciation" / time-in-service
        self.assertNotIn("depreciation", b.lower())
        # unit-level: age + mileage where available; data-quality gap surfaced (not vehicle performance)
        self.assertIn("533d in service", b)
        self.assertIn("mileage not reported", b)
        # boundary: no economics leaked
        for banned in ("RETIRE NOW", "release-by", "ICV $", "Ideal Mix", "HOLD "):
            self.assertNotIn(banned, b)

    def test_unit_page(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=_fake_intel()):
            b = self.full.get("/service-loaner/unit/slu_1").body
        self.assertIn("QX60", b)
        self.assertIn("Authoritative in-service date", b)
        self.assertIn("In-service age", b)
        self.assertIn("Historical recorded resale", b)

    def test_model_whatif_page(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=_fake_intel()):
            b = self.full.get("/service-loaner/model/QX60").body
        self.assertIn("resale what-if", b.lower())
        self.assertIn("Recorded resale by model-year", b)
        self.assertIn("not a current-value estimate", b)   # honest labelling

    def test_missing_data_is_quality_condition_not_performance(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=_fake_intel()):
            b = self.full.get("/service-loaner/unit/slu_2").body
        self.assertIn("data-quality condition", b)          # missing mileage/date framed as data quality
        self.assertNotIn("depreciation", b.lower())

    def test_certified_unchanged(self):
        with patch("elite.loaner.intelligence.build_intelligence", return_value=_fake_intel()):
            self.full.get("/service-loaner")
        self.assertEqual(current_version(self.p.stack.db.conn), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
