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
    def test_unknown_age_gates_never_static_median(self):
        # unknown model-year age must GATE — never a flat all-model-years median (the $36,780 bug) or the 5+ cohort
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=(MaturityBin("0", 15, 48250.0, False), MaturityBin("5+", 22, 18993.0, False)))
        price, _basis, conf = _price_at_model_year_age(mi, None)
        self.assertIsNone(price)
        self.assertEqual(conf, "none")

    def test_pricing_is_age_specific_and_preserves_depreciation(self):
        # a populated younger and older bin -> now (age 0) and future (age 1) differ; never a flat median
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=(MaturityBin("0", 15, 48000.0, False), MaturityBin("1", 12, 43000.0, False)))
        self.assertEqual(_price_at_model_year_age(mi, 0)[0], 48000.0)
        self.assertEqual(_price_at_model_year_age(mi, 1)[0], 43000.0)     # depreciates with age

    def test_thin_bin_uses_age_specific_evidence_not_flat_median(self):
        # exact age-2 bin is thin -> still use the age-specific evidence (thin confidence), NEVER the 41000 flat
        # all-model-years median; when the exact age is absent the nearest populated age bin is used instead.
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=(MaturityBin("0", 15, 48000.0, False), MaturityBin("1", 12, 43000.0, False),
                                  MaturityBin("2", 2, 40000.0, True)))
        price, basis, conf = _price_at_model_year_age(mi, 2)             # exact bin thin
        self.assertEqual(price, 40000.0)                                  # age-specific (age 2), not the 41000 flat median
        self.assertNotEqual(price, 41000.0)
        self.assertEqual(conf, "thin")
        # an ABSENT age (age 4) degrades to the nearest populated age bin (age 2 = 40000), still age-specific
        self.assertEqual(_price_at_model_year_age(mi, 4)[0], 40000.0)

    def test_no_age_specific_evidence_gates(self):
        mi = ModelIntel(model="QX60", active_units=1, sales_count=0, dts=None, resale_model=_resale_model(41000.0),
                        maturity=())                                      # only a flat model median exists
        self.assertIsNone(_price_at_model_year_age(mi, 0)[0])            # never the flat median -> gate


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

    def test_unknown_my_gates_price_never_flat_median(self):
        # MY unknown -> age unknown -> used price GATES (no static median). ICV still resolves from in-service month.
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=(MaturityBin("0", 15, 48000.0, False),))
        with patch("elite.loaner.sl_decision._retail_rows",
                   return_value=[{"model": "QX60", "year": "2026", "days_to_sell": 40} for _ in range(8)]):
            d = build_unit_decision(self.app, SCOPE, _unit(my=""), mi, today="2026-08-09", keep_horizon_days=60)
        self.assertEqual(d["facts"]["icv"], 6500)                        # ICV resolves from in-service month
        self.assertIn("expected used price now", d["gated"])             # price gates on unknown MY, never flat median
        self.assertEqual(d["action"], "UNRESOLVED")

    def test_resolved_my_yields_age_specific_decision(self):
        # a RESOLVED MY (2026) + age bins -> real decision, price_now != price_future when the exit crosses a year
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=_resale_model(41000.0),
                        maturity=(MaturityBin("0", 15, 48000.0, False), MaturityBin("1", 12, 43000.0, False)))
        with patch("elite.loaner.sl_decision._retail_rows",
                   return_value=[{"model": "QX60", "year": "2026", "days_to_sell": 40} for _ in range(8)]):
            d = build_unit_decision(self.app, SCOPE, _unit(my="2026"), mi, today="2026-08-09",
                                    keep_horizon_days=200)
        self.assertIn(d["action"], ("KEEP", "PULL", "SWAP"))             # real decision
        self.assertEqual(d["facts"]["icv"], 6500)
        self.assertEqual(d["facts"]["price_now"], 48000.0)             # age-0 bin
        self.assertLess(d["facts"]["price_future"], d["facts"]["price_now"])   # future exit depreciates


if __name__ == "__main__":
    unittest.main(verbosity=2)
