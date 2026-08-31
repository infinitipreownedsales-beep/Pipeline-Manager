
import unittest

from elite.loaner.sl_decision import (
    _paired_bounded_market,
    _same_my_used_market_band,
)


def row(*, model="QX60", year="2026", sold="2026-08-01", price=42000, kind="USED"):
    return {
        "model": model,
        "year": year,
        "sold_date": sold,
        "price": price,
        "_sale_kind": kind,
    }


class TestBoundedActiveLoanerMarket(unittest.TestCase):
    def test_explicit_new_rows_never_supply_used_market_band(self):
        rows = [row(kind="NEW", price=60000) for _ in range(20)]
        self.assertIsNone(
            _same_my_used_market_band(rows, "QX60", "2026", "2026-08-31", {})
        )

    def test_same_model_year_and_sample_gate_are_required(self):
        rows = [row(year="2025") for _ in range(20)]
        self.assertIsNone(
            _same_my_used_market_band(rows, "QX60", "2026", "2026-08-31", {})
        )
        rows = [row(price=41000 + i * 100) for i in range(7)]
        self.assertIsNone(
            _same_my_used_market_band(rows, "QX60", "2026", "2026-08-31", {})
        )

    def test_spread_gate_fails_closed(self):
        prices = [25000, 26000, 27000, 28000, 52000, 53000, 54000, 55000]
        rows = [row(price=p) for p in prices]
        self.assertIsNone(
            _same_my_used_market_band(rows, "QX60", "2026", "2026-08-31", {})
        )

    def test_paired_rank_never_credits_future_appreciation(self):
        now = {"p25": 41000, "p50": 42500, "p75": 46000}
        future = {"p25": 42000, "p50": 45000, "p75": 45500}
        p = _paired_bounded_market(now, future)
        self.assertEqual(p["p25"]["future_decision"], 41000)
        self.assertEqual(p["p50"]["future_decision"], 42500)
        self.assertEqual(p["p75"]["future_decision"], 45500)
        self.assertEqual(p["p50"]["future_observed"], 45000)


if __name__ == "__main__":
    unittest.main()
