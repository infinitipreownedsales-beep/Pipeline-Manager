"""Phase 4 acceptance — Demand baseline, evidence hierarchy, seasonality, trend (items 24-32).

Demand is independent of acquisition/supply method: the DemandService takes no supply input.
"""
import inspect
import os
import tempfile
import unittest

from elite.newinv.demand import DemandService, derive_seasonality
from elite.newinv.fixtures import HORIZON, SCOPE, Phase4
from elite.newinv.models import SEASON_MAX, SEASON_MIN


class TestPhase4Demand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase4(os.path.join(self.tmp, "elite.db"))
        self.c = self.p.combination(exterior_color="BLACK")

    def tearDown(self):
        self.p.close()

    def _seed_stable(self, comb, per_month=2, months=None):
        months = months or ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        self.p.seed_retail(comb, {m: per_month for m in months})
        self.p.seed_availability(comb, [{"month": m, "opening_depth": 3, "arrivals": 1, "retail": per_month,
                                         "snapshot": "full"} for m in months])

    def test_24_demand_independent_of_supply_inputs(self):
        # Structural proof: no supply parameter exists on the Demand contract.
        params = set(inspect.signature(DemandService.issue).parameters)
        for forbidden in ("supply", "current_supply", "future_supply", "committed", "acquisition", "qualifying"):
            self.assertNotIn(forbidden, params)
        # And Demand is callable with no supply records present at all.
        self._seed_stable(self.c)
        d = self.p.issue_demand(self.c)
        self.assertTrue(d.monthly_expected)
        self.assertEqual(d.evidence_tier, "exact")

    def test_25_demand_unchanged_when_only_acquisition_path_changes(self):
        self._seed_stable(self.c)
        d1 = self.p.issue_demand(self.c)
        # add supply + an approved commitment (an acquisition path) — Demand must not move
        self.p.seed_future(self.c, [{"production_order_id": "po", "arrival_month": "2026-10"}])
        self.p.approved_commitment(self.c, unit_id="cpo", arrival_month="2026-10")
        d2 = self.p.issue_demand(self.c)
        self.assertEqual(d1.monthly_expected, d2.monthly_expected)

    def test_26_exact_evidence_outranks_inherited(self):
        self._seed_stable(self.c)
        inherited = {"retail_by_month": {"2025-01": 9}, "exposure_months": 1, "sample_size": 9,
                     "relationship": "new_model_year", "source_combination": "prior"}
        rbm = self.p.retail.retail_by_month(self.c.id, SCOPE)
        d = self.p.demand.issue(self.c, SCOPE, HORIZON, retail_by_month=rbm,
                                exposure_months=self.p.availability.exposure_months(self.c.id, SCOPE),
                                sample_size=sum(rbm.values()), inherited=inherited, inherit_allowed=True,
                                calculation_version=self.p.demand_cv)
        self.assertEqual(d.evidence_tier, "exact")           # direct exact wins over inherited
        self.assertTrue(d.direct_evidence)

    def test_27_inherited_evidence_is_labeled(self):
        inherited = {"retail_by_month": {"2025-03": 4, "2025-04": 4}, "exposure_months": 2, "sample_size": 8,
                     "relationship": "new_model_year", "source_combination": "prior_comb"}
        d = self.p.demand.issue(self.c, SCOPE, HORIZON, retail_by_month={}, exposure_months=0,
                                inherited=inherited, inherit_allowed=True, calculation_version=self.p.demand_cv)
        self.assertFalse(d.direct_evidence)
        self.assertEqual(d.evidence_tier, "lineage")
        self.assertIn("inherited", d.baseline_evidence["source"])

    def test_28_low_sample_reduces_confidence(self):
        self.p.seed_retail(self.c, {"2026-02": 1})
        self.p.seed_availability(self.c, [{"month": "2026-02", "opening_depth": 1, "arrivals": 0, "retail": 1,
                                          "snapshot": "full"}])
        d = self.p.issue_demand(self.c)
        self.assertNotEqual(d.confidence, "high")            # sample of 1 -> reduced

    def test_29_unsupported_lineage_does_not_silently_transfer(self):
        inherited = {"retail_by_month": {"2025-03": 9}, "exposure_months": 1, "sample_size": 9,
                     "relationship": "generation_change", "source_combination": "old_gen"}
        d = self.p.demand.issue(self.c, SCOPE, HORIZON, retail_by_month={}, exposure_months=0,
                                inherited=inherited, inherit_allowed=False,   # not approved
                                calculation_version=self.p.demand_cv)
        self.assertEqual(d.evidence_tier, "estimate")
        self.assertEqual(set(d.monthly_expected.values()), {0.0})   # inherited numbers NOT used
        self.assertEqual(d.confidence, "low")

    def test_30_seasonality_is_bounded_and_explainable(self):
        retail = {f"2025-{mm:02d}": (20 if mm == 3 else 1) for mm in range(1, 8)}   # 7 months, one spike
        idx, note = derive_seasonality(retail)
        self.assertTrue(idx)                                 # enough months -> derived
        self.assertTrue(all(SEASON_MIN <= v <= SEASON_MAX for v in idx.values()))   # bounded
        self.assertEqual(note, "derived_bounded")

    def test_31_sparse_history_does_not_exaggerate_seasonality(self):
        idx, note = derive_seasonality({"2026-03": 5})       # one month only
        self.assertEqual(idx, {})                            # flat, not exaggerated
        self.assertTrue(note.startswith("flat:sparse"))

    def test_32_trend_is_traceable(self):
        self._seed_stable(self.c)
        d = self.p.issue_demand(self.c, trend=1.2, trend_method="rising_linear")
        self.assertEqual(d.trend_ref, {"factor": 1.2, "method": "rising_linear"})
        base = self.p.combination(exterior_color="FLAT")
        self._seed_stable(base)
        d0 = self.p.issue_demand(base, trend=1.0)
        self.assertGreater(list(d.monthly_expected.values())[0], list(d0.monthly_expected.values())[0])


if __name__ == "__main__":
    unittest.main()
