"""Service-Loaner economic-decision resolution repair (live acceptance 2026-08-26).

Two live-blocking resolver defects fixed (economics MATH unchanged):
  1. Applicable ICV/Velocity read 'Unknown' per unit even though Program Coverage read 'complete', because the
     coverage check is model-year-agnostic but the per-unit `applicable()` required an exact model-year match —
     so MY-specific program entries never resolved for a unit whose model year is unknown. Now `applicable()`
     resolves the effective-dated program by (model, in-service month) when the unit MY is unknown, provided the
     MY variants in force agree (unambiguous); disagreement still gates honestly.
  2. When a unit's model-year age is unknown, expected used price gated to nothing (UNRESOLVED). It now DEGRADES
     to the governed all-model-years resale median (the same thin fallback used for a thin maturity bin — never
     the removed oldest '5+' cohort), at thin confidence, so a decision resolves honestly where real evidence
     exists.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_decision import build_unit_decision, _price_at_model_year_age
from elite.loaner.intelligence import UnitIntel, ModelIntel, MaturityBin, Cohort
from elite.loaner.preowned_evidence import DtsDistribution
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore

VIN = "5N1AZ2CS0PC900777"


def _resale_model(median=41000.0, count=30):
    dist = DtsDistribution(count=count, minimum=20000.0, p25=34000.0, median=median, p75=48000.0, maximum=60000.0)
    return Cohort(kind="resale", label="QX60 · all model-years", dist=dist, as_of="2026-08-01",
                  earliest="2024-01-01", latest="2026-07-01", recent_n=count, gate=8, gated=count >= 8)


def _unit(my=""):
    return UnitIntel(id="u1", vin=VIN, model="QX60", in_service_date="2026-02-10", age_days=180, mileage=8000,
                     mileage_available=True, membership_state="ACTIVE_AVAILABLE", rental_state=None,
                     quality_flags=(), model_year=my)


class TestIcvResolvesFromInServiceMonth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.pis = ProgramInputsStore(self.p.app.prefs, SCOPE)

    def tearDown(self):
        self.p.close()

    def test_my_specific_entry_resolves_for_unknown_my_unit(self):
        # ICV entered ONLY under a specific model year — the live shape that read 'complete' in coverage but
        # 'Unknown' per unit. A unit whose MY is unknown must still resolve it from the in-service month.
        self.pis.add("icv", effective_month="2026-01", model="QX60", model_year="2026", value=6500,
                     actor="k", recorded_at="t")
        e = self.pis.applicable("icv", "QX60", "2026-02", model_year="")
        self.assertIsNotNone(e)
        self.assertEqual(e.value, 6500)

    def test_ambiguous_my_variants_stay_unknown(self):
        # two model years disagree on ICV at the same effective month -> unknown-MY unit stays honest Unknown
        self.pis.add("icv", effective_month="2026-01", model="QX60", model_year="2025", value=6000,
                     actor="k", recorded_at="t")
        self.pis.add("icv", effective_month="2026-01", model="QX60", model_year="2026", value=7000,
                     actor="k", recorded_at="t")
        self.assertIsNone(self.pis.applicable("icv", "QX60", "2026-02", model_year=""))

    def test_all_my_entry_still_wins_normally(self):
        self.pis.add("icv", effective_month="2026-01", model="QX60", model_year="", value=6200,
                     actor="k", recorded_at="t")
        self.assertEqual(self.pis.applicable("icv", "QX60", "2026-02", model_year="").value, 6200)


class TestUsedPriceDegrade(unittest.TestCase):
    def test_unknown_age_degrades_to_model_median_not_oldest_cohort(self):
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=(MaturityBin("0", 15, 48250.0, False), MaturityBin("5+", 22, 18993.0, False)))
        self.assertEqual(_price_at_model_year_age(mi, 5)[0], 18993.0)     # the 5+ cohort remains the $18,993 source
        price, basis, conf = _price_at_model_year_age(mi, None)           # unknown age
        self.assertEqual(price, 41000.0)                                  # model all-MY median, NOT 18993
        self.assertEqual(conf, "thin")
        self.assertIn("degraded", basis)

    def test_unknown_age_without_model_evidence_still_gates(self):
        mi = ModelIntel(model="QX60", active_units=1, sales_count=0, dts=None, resale_model=None, maturity=())
        price, _b, conf = _price_at_model_year_age(mi, None)
        self.assertIsNone(price)                                          # nothing real to degrade to -> honest gate
        self.assertEqual(conf, "none")


class TestUnitDecisionResolvesWithUnknownMy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_invoice(VIN, 60000, actor="k", at="t")
        pol.set_protection_buffer_days(20, actor="k", at="t")
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        # program entered MY-specific (the live shape) and the loaner's MY is unknown
        pis.add("icv", effective_month="2026-01", model="QX60", model_year="2026", value=6500, actor="k",
                recorded_at="t")
        pis.add("velocity", effective_month="2026-01", model="QX60", model_year="2026", value=2500,
                day_cap=240, mile_cap=10000, actor="k", recorded_at="t")

    def tearDown(self):
        self.p.close()

    def test_unknown_my_unit_now_resolves_with_thin_confidence(self):
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=())
        with patch("elite.loaner.sl_decision._retail_rows",
                   return_value=[{"model": "QX60", "year": "2026", "days_to_sell": 40} for _ in range(8)]):
            d = build_unit_decision(self.app, SCOPE, _unit(my=""), mi, today="2026-08-09", keep_horizon_days=60)
        self.assertIn(d["action"], ("KEEP", "PULL", "SWAP"))             # a real decision, no longer UNRESOLVED
        self.assertEqual(d["facts"]["icv"], 6500)                        # ICV resolved from in-service month
        self.assertEqual(d["facts"]["velocity"], 2500)
        self.assertEqual(d["facts"]["price_now"], 41000.0)              # degraded model median (not the 5+ bug)
        self.assertEqual(d["confidence"], "thin")                        # honestly low-confidence
        self.assertEqual(d["gated"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
