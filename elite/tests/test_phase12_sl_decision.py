"""Live KEEP/PULL/SWAP wiring per active unit (Sections 1, 5, 8): reads governed invoice + Program Inputs,
forecasts the future exit price from maturity evidence, gates on missing authoritative facts, and degrades
gracefully. No fabricated defaults for invoice / price / in-service date."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE
from elite.loaner.sl_decision import build_unit_decision, _price_at_model_year_age
from elite.loaner.intelligence import UnitIntel, ModelIntel, MaturityBin
from elite.loaner.sl_policy import SLPolicyStore
from elite.loaner.program_inputs import ProgramInputsStore

VIN = "5N1AZ2CS0PC900001"


def _unit(in_service="2026-02-10", age=180, my="2026"):
    return UnitIntel(id="u1", vin=VIN, model="QX60", in_service_date=in_service, age_days=age, mileage=8000,
                     mileage_available=True, membership_state="ACTIVE_AVAILABLE", rental_state=None,
                     quality_flags=(), model_year=my)


def _mi(price_age0=52000, price_age1=45000):
    return ModelIntel(model="QX60", active_units=3, sales_count=40, dts=None, resale_model=None,
                      maturity=(MaturityBin("0", 12, price_age0, False), MaturityBin("1", 10, price_age1, False)))


class TestUnitDecision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.app = self.p.app
        pol = SLPolicyStore(self.app.prefs, SCOPE)
        pol.set_invoice(VIN, 60000, actor="k", at="t")                 # authoritative invoice
        pol.set_protection_buffer_days(20, actor="k", at="t")
        pis = ProgramInputsStore(self.app.prefs, SCOPE)
        pis.add("icv", effective_month="2026-02", model="QX60", model_year="2026", value=6500, actor="k",
                recorded_at="t")
        pis.add("velocity", effective_month="2026-02", model="QX60", model_year="2026", value=2500,
                day_cap=240, mile_cap=10000, actor="k", recorded_at="t")

    def tearDown(self):
        self.p.close()

    def test_full_inputs_produce_action_with_facts(self):
        with patch("elite.loaner.sl_decision._retail_rows",
                   return_value=[{"model": "QX60", "year": "2026", "days_to_sell": 40} for _ in range(8)]):
            d = build_unit_decision(self.app, SCOPE, _unit(), _mi(), today="2026-08-09", keep_horizon_days=60)
        self.assertIn(d["action"], ("KEEP", "PULL", "SWAP"))
        self.assertEqual(d["facts"]["invoice"], 60000)
        self.assertEqual(d["facts"]["rate"], 1.25)                     # governed default of invoice
        self.assertEqual(d["facts"]["icv"], 6500)
        self.assertEqual(d["facts"]["velocity"], 2500)
        self.assertEqual(d["facts"]["total_to_retail_days"], 240)      # from the Velocity day cap
        self.assertEqual(d["gated"], [])

    def test_missing_invoice_gates_action(self):
        SLPolicyStore(self.app.prefs, SCOPE)                            # invoice for a DIFFERENT vin only
        u = _unit()
        u = UnitIntel(**{**u.__dict__, "vin": "OTHERVIN0000000001"})
        d = build_unit_decision(self.app, SCOPE, u, _mi(), today="2026-08-09", keep_horizon_days=60)
        self.assertIn("authoritative invoice", d["gated"])
        self.assertEqual(d["action"], "UNRESOLVED")                    # no fabricated basis
        self.assertIn("invoice", d["why"])

    def test_missing_in_service_gates(self):
        d = build_unit_decision(self.app, SCOPE, _unit(in_service=None, age=None), _mi(),
                                today="2026-08-09", keep_horizon_days=60)
        self.assertIn("authoritative in-service date / tenure", d["gated"])

    def test_future_price_reflects_maturity_depreciation(self):
        # a MY2026 unit whose future exit crosses into model-year age 1 -> lower expected price
        with patch("elite.loaner.sl_decision._retail_rows",
                   return_value=[{"model": "QX60", "year": "2026", "days_to_sell": 300}]):
            d = build_unit_decision(self.app, SCOPE, _unit(in_service="2026-06-01", age=60), _mi(52000, 40000),
                                    today="2026-08-01", keep_horizon_days=200)
        # future exit lands in a later calendar year -> maturity age 1 median (40000) < age 0 (52000)
        self.assertLess(d["facts"]["price_future"], d["facts"]["price_now"])

    def test_no_resale_evidence_gates_prices(self):
        empty_mi = ModelIntel(model="QX60", active_units=3, sales_count=0, dts=None, resale_model=None,
                              maturity=())
        d = build_unit_decision(self.app, SCOPE, _unit(), empty_mi, today="2026-08-09", keep_horizon_days=60)
        self.assertIn("expected used price now", d["gated"])
        self.assertIn("expected future used price (KEEP)", d["gated"])

    def test_price_estimator_degrades_and_flags_confidence(self):
        price, basis, conf = _price_at_model_year_age(_mi(), 0)
        self.assertEqual(price, 52000)
        self.assertEqual(conf, "moderate")
        price2, basis2, conf2 = _price_at_model_year_age(ModelIntel(model="QX60", active_units=1, sales_count=0,
                                                                    dts=None, resale_model=None, maturity=()), 0)
        self.assertIsNone(price2)
        self.assertEqual(conf2, "none")

    def test_unknown_model_year_age_gates_not_oldest_cohort(self):
        # a unit whose model-year age is UNKNOWN must NOT be priced off the oldest ("5+") maturity cohort
        # (the ~$18,993 near-new bug). It gates honestly instead.
        mi = ModelIntel(model="QX60", active_units=10, sales_count=60, dts=None, resale_model=None,
                        maturity=(MaturityBin("0", 15, 48250.0, False), MaturityBin("5+", 22, 18993.0, False)))
        self.assertEqual(_price_at_model_year_age(mi, 5)[0], 18993.0)     # the 5+ cohort is the $18,993 source
        price, _basis, conf = _price_at_model_year_age(mi, None)          # unknown age -> gate, never the 5+ cohort
        self.assertIsNone(price)
        self.assertEqual(conf, "none")


class TestBoardSurface(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    def test_board_surfaces_per_unit_action(self):
        import elite.tests.test_phase12_loaner_intelligence as INTEL
        intel = INTEL._fake_intel()
        with patch("elite.loaner.intelligence.build_intelligence", return_value=intel):
            b = self.full.get("/service-loaner").body
        self.assertIn("Recommended action per unit", b)
        self.assertIn("KEEP / PULL / SWAP", b)
        self.assertIn("already-earned ICV is sunk", b)      # incremental-from-now framing on the surface
        # units without an authoritative invoice gate to UNRESOLVED rather than a fabricated call
        self.assertIn("UNRESOLVED", b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
